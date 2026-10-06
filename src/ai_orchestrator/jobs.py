"""Durable, bounded dispatch queue. Jobs never encode operator authority."""

from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any, Literal

from pydantic import model_validator

from .safety import storage_constructor, cancellation_mutation, serialized, assert_ready, bind_storage, assert_storage_current
from .models import Contract, OrchestratorError, identifier
from .persistence import (
    JOB_DB_READABLE_VERSIONS,
    JOB_DB_VERSION,
    validate_database_version,
)
from .project import Project, confined, digest

MAX_PENDING = 32
JOB_TTL_SECONDS = 3600


class Job(Contract):
    schema_version: Literal[1, 2] = 1
    id: str
    request_id: str
    action: Literal["ask", "run", "explore", "exploration_propose"]
    arguments: dict[str, Any]
    profile_digest: str
    workspace_snapshot: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled", "interrupted"] = "queued"
    created_at: float
    expires_at: float
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_requested: bool = False


    @model_validator(mode="after")
    def action_version(self):
        if self.action in ("explore", "exploration_propose") and self.schema_version != 2:
            raise ValueError("exploration jobs require Job schema v2")
        return self


class JobQueue:
    @storage_constructor
    def __init__(self, project: Project):
        assert_ready(project)
        self.project = project
        project.runtime.mkdir(parents=True, exist_ok=True)
        path = confined(project.root, ".orchestrator/runtime/jobs.sqlite3")
        for suffix in ("-wal", "-shm", "-journal"):
            confined(project.root, f".orchestrator/runtime/jobs.sqlite3{suffix}")
        self.db = sqlite3.connect(path, timeout=5)
        bind_storage(self, path)
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        try:
            validate_database_version("job", version, JOB_DB_READABLE_VERSIONS)
        except OrchestratorError:
            self.db.close()
            raise
        if version == JOB_DB_VERSION and not self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='request_receipts'"
        ).fetchone():
            self.db.close()
            raise OrchestratorError("jobs v2 is missing request_receipts; refusing implicit repair")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                fingerprint TEXT NOT NULL, action TEXT NOT NULL,
                target TEXT NOT NULL, status TEXT NOT NULL,
                data TEXT NOT NULL, cancel_requested INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS job_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL, kind TEXT NOT NULL, created_at REAL NOT NULL
            );
        """)
        from . import receipts
        if version < JOB_DB_VERSION:
            with self.db:
                self.db.execute("BEGIN IMMEDIATE")
                receipts.initialize(self.db)
                self.db.execute(f"PRAGMA user_version={JOB_DB_VERSION}")

    def close(self) -> None:
        self.db.close()

    def _event(self, job_id: str, kind: str) -> None:
        self.db.execute("INSERT INTO job_events(job_id,kind,created_at) VALUES (?,?,?)", (job_id, kind, time.time()))

    def get(self, job_id: str) -> Job:
        assert_storage_current(self)
        identifier(job_id)
        row = self.db.execute("SELECT data,cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise OrchestratorError(f"unknown job: {job_id}")
        job = Job.model_validate_json(row[0])
        job.cancel_requested = bool(row[1])
        return job

    def existing(self, request_id: str, action: str, arguments: dict[str, Any]) -> Job | None:
        assert_storage_current(self)
        identifier(request_id)
        from .receipts import decode, RequestRetired
        receipt_row = self.db.execute(
            "SELECT request_id,job_id,fingerprint,data FROM request_receipts WHERE request_id=?", (request_id,)).fetchone()
        if receipt_row:
            receipt = decode(receipt_row)
            if receipt.fingerprint != digest({"action": action, "arguments": arguments}):
                raise OrchestratorError("request_id was already used with different arguments")
            raise RequestRetired(receipt)
        row = self.db.execute("SELECT id,fingerprint FROM jobs WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            return None
        if row[1] != digest({"action": action, "arguments": arguments}):
            raise OrchestratorError("request_id was already used with different arguments")
        return self.get(row[0])

    @serialized
    def enqueue(self, action: Literal["ask", "run", "explore", "exploration_propose"], arguments: dict[str, Any], request_id: str, profile_digest: str, snapshot: str) -> Job:
        identifier(request_id)
        target = arguments.get("exploration_id") or arguments.get("task_id") or arguments.get("reply_to") or request_id
        timestamp = time.time()
        job = Job(schema_version=2 if action in ("explore", "exploration_propose") else 1, id="J-" + uuid.uuid4().hex[:12], request_id=request_id, action=action, arguments=arguments, profile_digest=profile_digest, workspace_snapshot=snapshot, created_at=timestamp, expires_at=timestamp + JOB_TTL_SECONDS)
        try:
            self.db.execute("BEGIN IMMEDIATE")
            old = self.existing(request_id, action, arguments)
            if old is not None:
                self.db.rollback()
                return old
            pending = self.db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
            if pending >= MAX_PENDING:
                raise OrchestratorError("job queue is full; inspect/cancel pending jobs")
            if self.db.execute("SELECT 1 FROM jobs WHERE action=? AND target=? AND status IN ('queued','running')", (action, target)).fetchone():
                raise OrchestratorError("a job for this target is already queued/running; inspect it instead of resubmitting")
            self.db.execute("INSERT INTO jobs(id,request_id,fingerprint,action,target,status,data) VALUES (?,?,?,?,?,?,?)", (job.id, request_id, digest({"action": action, "arguments": arguments}), action, target, job.status, job.model_dump_json()))
            self._event(job.id, "queued")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return job

    @serialized
    def claim(self) -> Job | None:
        try:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            if row is None:
                self.db.rollback()
                return None
            job = self.get(row[0])
            job.status = "running"
            self.db.execute("UPDATE jobs SET status=?,data=? WHERE id=?", (job.status, job.model_dump_json(), job.id))
            self._event(job.id, "started")
            self.db.commit()
            return job
        except Exception:
            self.db.rollback()
            raise

    @serialized
    def finish(self, job: Job) -> None:
        if job.status not in ("succeeded", "failed", "cancelled", "interrupted"):
            raise OrchestratorError("invalid terminal job status")
        if len(job.model_dump_json().encode()) > 1024 * 1024:
            job.result, job.status, job.error = None, "failed", "job result exceeds 1 MiB; inspect persisted task/intake state"
        with self.db:
            cursor = self.db.execute("UPDATE jobs SET status=?,data=? WHERE id=? AND status='running'", (job.status, job.model_dump_json(), job.id))
            if cursor.rowcount != 1:
                raise OrchestratorError("job is not running; refusing to overwrite terminal state")
            self._event(job.id, job.status)

    @cancellation_mutation
    def cancel(self, job_id: str) -> Job:
        assert_ready(self.project)
        try:
            self.db.execute("BEGIN IMMEDIATE")
            job = self.get(job_id)
            if job.status not in ("queued", "running"):
                self.db.rollback()
                return job
            job.cancel_requested = True
            if job.status == "queued":
                job.status = "cancelled"
            self.db.execute("UPDATE jobs SET status=?,data=?,cancel_requested=1 WHERE id=?", (job.status, job.model_dump_json(), job.id))
            self._event(job.id, "cancel_requested")
            self.db.commit()
            return self.get(job_id)
        except Exception:
            self.db.rollback()
            raise

    def cancelled(self, job_id: str) -> bool:
        assert_storage_current(self)
        row = self.db.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
        return bool(row and row[0])

    @serialized
    def interrupt_stale(self) -> int:
        """Only the exclusive worker owner calls this; never replay an interrupted job."""
        rows = self.db.execute("SELECT id FROM jobs WHERE status='running'").fetchall()
        for row in rows:
            job = self.get(row[0])
            job.status, job.error = "interrupted", "Previous worker stopped unexpectedly. Inspect task/intake/worktree; no automatic replay."
            self.finish(job)
        return len(rows)
