# v0.7 isolated parallel execution

v0.7 permits concurrent **writable** workflow nodes only when the trusted
workflow gives each node a private Git worktree and an exact ownership contract.
Existing workflows remain shared and sequential.

## Configuration

Parallelism has two independent opt-ins.

First, the trusted profile must permit more than one provider worker:

```yaml
policy:
  max_parallel_workers: 2
```

The default is `1`.

Second, every writable node that may run concurrently must declare an isolated
workspace and exact project-relative files:

```yaml
- id: backend
  kind: agent
  role: implementer
  run_for: write
  depends_on: [plan]
  inputs:
    - artifact: plan
      type: plan
  outputs:
    - name: backend_implementation
      type: implementation
    - name: backend_write_set
      type: write_set
  gate_before: execution
  writes: task_allowed_paths
  workspace: isolated
  write_paths:
    - src/backend.py

- id: frontend
  kind: agent
  role: implementer
  run_for: write
  depends_on: [plan]
  inputs:
    - artifact: plan
      type: plan
  outputs:
    - name: frontend_implementation
      type: implementation
    - name: frontend_write_set
      type: write_set
  gate_before: execution
  writes: task_allowed_paths
  workspace: isolated
  write_paths:
    - src/frontend.py
```

The workflow compiler rejects overlapping `write_paths` for independent
isolated nodes. At task preflight, every owned path must also be present in that
task's exact `allowed_paths`.

## Execution sequence

For one ready isolated batch the controller:

1. verifies a Git `HEAD` exists;
2. creates a disposable local `git clone --shared` under
   `.orchestrator/runtime/worktrees/<task>/attempt-<n>/integration`, removes its
   origin, and keeps all new Git metadata inside runtime;
3. materializes the current project snapshot directly (without checkout filters)
   and creates a temporary seed commit in that disposable clone;
4. creates one detached, no-checkout worktree per ready isolated node from the
   seed and materializes the exact seed payload;
5. starts provider calls with a bounded thread pool; those threads call only the
   provider adapter and never mutate controller SQLite/TaskState;
6. verifies each worker changed only its declared `write_paths`, did not change
   protected/control files, and records a binary patch hash;
7. applies branch patches to the integration worktree in compiled workflow order;
8. rechecks the user's project snapshot, protected paths and control files;
9. applies one aggregate patch to the project worktree;
10. runs downstream registered validators and the independent reviewer against
    that integrated project state;
11. removes temporary worktrees.

The temporary seed commit exists only inside the disposable runtime clone to
give every worker an identical Git base. It is not pushed, does not move the
user's branch, and does not register worktrees or write seed objects into the
user's `.git` directory.

## HumanGate and provenance

The execution approval scope includes the complete ready isolated batch,
`write_paths` for every node, and `max_parallel_workers`. A changed batch or
ownership contract therefore requires a new approval scope.

Events record workspace preparation, provider starts, per-node patch hashes,
integration preparation/application, cleanup and failures. Each isolated
`write_set` artifact records the owned paths, actual changed paths, seed and
integrated snapshots, and patch provenance.

## Failure, cancellation and recovery

A provider failure or ownership violation cancels sibling provider calls where
their adapter/process honors cancellation. Successful sibling patches are not
applied to the project worktree unless the entire batch reaches the integration
stage successfully.

An integration conflict fails before the project worktree is touched. A user or
other process changing the project/control/protected state while workers run also
invalidates integration.

Normal failure/cancellation removes temporary worktrees. If the controller
process itself is interrupted, `recover` removes stale worktrees and marks the
task failed. It never replays the interrupted batch automatically.

## Boundaries

- This is Git-worktree isolation between cooperating workers, not an OS sandbox.
  Workers still run as the same local user.
- Isolated execution requires at least one existing Git commit.
- Git-ignored project content is not copied into isolated worktrees. Protected
  ignored files such as `.env` therefore remain unavailable to workers, which
  is intentional.
- Validators still run in the integrated project worktree under the existing
  trusted-local validator boundary.
- Shared writable nodes retain v0.6 behavior and never execute concurrently.
- Automatic conflict repair/rebase is deliberately unsupported; conflicts fail
  closed and require a new inspected task/attempt.
