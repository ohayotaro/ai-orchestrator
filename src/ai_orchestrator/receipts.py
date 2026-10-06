"""Durable request identity is independent from disposable job result payloads."""
from __future__ import annotations
import sqlite3
import json
import time
from typing import Literal
from pydantic import Field
from .models import Contract, OrchestratorError, identifier
from .project import digest

TERMINAL = ('succeeded', 'failed', 'cancelled', 'interrupted')

class RequestReceipt(Contract):
    schema_version: Literal[1] = 1
    request_id: str
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    job_id: str
    action: Literal['ask', 'run', 'explore', 'exploration_propose']
    outcome: Literal['succeeded', 'failed', 'cancelled', 'interrupted']
    retired_at: float = Field(ge=0, allow_inf_nan=False)

class RequestRetired(OrchestratorError):
    def __init__(self, receipt: RequestReceipt):
        self.details = {'schema_version': 1, 'code': 'request_retired',
                        'request_id': receipt.request_id, 'original_job_id': receipt.job_id,
                        'outcome': receipt.outcome, 'automatic_replay': False}
        super().__init__('request_retired: the original job payload was retired; use a new request ID only for an intentional new operation')


def initialize(db: sqlite3.Connection) -> None:
    db.execute('''CREATE TABLE IF NOT EXISTS request_receipts (
        request_id TEXT PRIMARY KEY, job_id TEXT UNIQUE NOT NULL,
        fingerprint TEXT NOT NULL, data TEXT NOT NULL)''')


def decode(row) -> RequestReceipt:
    try:
        raw = json.loads(row[3])
        if not isinstance(raw, dict):
            raise ValueError('receipt is not an object')
        if type(raw.get('schema_version')) is not int or raw['schema_version'] != 1:
            raise ValueError('unknown receipt version')
        receipt = RequestReceipt.model_validate(raw)
        identifier(receipt.request_id); identifier(receipt.job_id)
        if (receipt.request_id, receipt.job_id, receipt.fingerprint) != tuple(row[:3]):
            raise ValueError('receipt columns disagree')
        return receipt
    except (ValueError, TypeError, KeyError) as exc:
        raise OrchestratorError('invalid or unknown request receipt contract') from exc


def read_all(db: sqlite3.Connection) -> dict[str, RequestReceipt]:
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='request_receipts'").fetchone():
        if db.execute('PRAGMA user_version').fetchone()[0] >= 2:
            raise OrchestratorError('jobs v2 is missing request_receipts')
        return {}
    return {item.request_id: item for item in map(decode, db.execute(
        'SELECT request_id,job_id,fingerprint,data FROM request_receipts'))}


def from_job_row(row, *, interrupted=False) -> RequestReceipt:
    from .jobs import Job
    job_id, request_id, fingerprint, action, status, data = row
    job = Job.model_validate_json(data)
    if (job.id, job.request_id, job.action, job.status) != (job_id, request_id, action, status):
        raise OrchestratorError('job identity/status columns disagree with payload')
    if fingerprint != digest({'action': action, 'arguments': job.arguments}):
        raise OrchestratorError('job fingerprint disagrees with payload')
    return RequestReceipt(request_id=request_id, job_id=job_id, fingerprint=fingerprint,
                          action=action, outcome=status if status in TERMINAL else 'interrupted',
                          retired_at=time.time())


def collect(db: sqlite3.Connection, *, include_jobs=False) -> dict[str, RequestReceipt]:
    items = read_all(db)
    if include_jobs:
        for row in db.execute('SELECT id,request_id,fingerprint,action,status,data FROM jobs'):
            receipt = from_job_row(row)
            if receipt.request_id in items:
                compatible(items[receipt.request_id], receipt)
            else:
                items[receipt.request_id] = receipt
    return items


def compatible(left: RequestReceipt, right: RequestReceipt) -> None:
    if (left.request_id, left.job_id, left.fingerprint, left.action) != (
            right.request_id, right.job_id, right.fingerprint, right.action):
        raise OrchestratorError('request_receipt_conflict: refusing to merge incompatible request history')


def insert(db: sqlite3.Connection, receipt: RequestReceipt) -> None:
    row = db.execute('SELECT request_id,job_id,fingerprint,data FROM request_receipts WHERE request_id=? OR job_id=?',
                     (receipt.request_id, receipt.job_id)).fetchone()
    if row:
        compatible(decode(row), receipt)
        return
    db.execute('INSERT INTO request_receipts VALUES (?,?,?,?)',
               (receipt.request_id, receipt.job_id, receipt.fingerprint, receipt.model_dump_json()))


def retire(db: sqlite3.Connection, job_ids: list[str]) -> int:
    """Caller owns one IMMEDIATE transaction for receipt + payload deletion."""
    initialize(db)
    removed = 0
    for job_id in job_ids:
        row = db.execute('SELECT id,request_id,fingerprint,action,status,data FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None or row[4] not in TERMINAL:
            raise OrchestratorError('retirement target is missing or not terminal')
        insert(db, from_job_row(row))
        # Test seams are monkeypatched in the subprocess, not controlled by a public environment flag.
        checkpoint('receipt_written')
        db.execute('DELETE FROM job_events WHERE job_id=?', (job_id,))
        db.execute('DELETE FROM jobs WHERE id=?', (job_id,))
        removed += 1
    return removed


def checkpoint(phase: str) -> None:
    """Fault-injection seam; intentionally a no-op in installed builds."""
