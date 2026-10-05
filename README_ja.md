# AI Orchestrator

[English README](README.md)

既存の AI クライアントから使える、**プロジェクト駆動・プロバイダー中立**のローカル実行コントロールプレーンです。

**v0.16.0 alpha** では、仕様が曖昧な段階を扱う Exploration / Deliberation Sessions を追加しました。
repository の read-only 調査、仮説・選択肢・未確定事項の整理、方針変更を複数ターンで継続できます。
探索だけでは task や実行承認は作られません。明示的な提案遷移で具体的な intake を生成し、
既存の Start / Execution / Acceptance HumanGate を経て実行します。

探索の usage / budget は提案・task へ引き継ぎます。履歴は hash 検証可能な artifact として保持し、
次の prompt には直近の理解を決定的に選択します。中断した session を自動 replay せず、
探索結果を accepted knowledge や project trust に自動昇格させません。

このプロジェクトは **trusted-local alpha** です。認証済みの人間本人性、provider 側の請求証明、汎用 OS sandbox、production 向けの独立 security boundary を提供するものではありません。

```text
User <-> Claude Code / Codex + portable Skill
                    |
                 MCP serve
                    |
       propose -> Supervisor -> task proposal
                    |
             Start HumanGate
                    |
                 Planner
                    |
          Execution HumanGate
                    |
       Implementer -> validators -> fresh Reviewer
                    |
         Acceptance HumanGate
                    |
                 succeeded
```

通常の single-terminal mode では、worker は会話中の agent session とは別の managed process で動きます。MCP client が interactive form elicitation をサポートしていれば、初期 setup と trust 後の通常操作は同じクライアント terminal 内で完結できます。

No / cancel / timeout / disconnect / scope drift は自動承認されません。

## v0.16 Exploration / Deliberation Sessions

通常は host へ「まだ実装せず、選択肢を比較して方針を相談したい」と依頼できます。
MCP `explore` で開始・更新し、`get_exploration` で状態を確認します。
更新には exact `expected_revision` が必要です。方針が決まったときだけ
`propose_from_exploration` で task proposal に移行し、通常の Start HumanGate へ進みます。

提案後に探索をやり直すと古い intake は superseded になります。
`abandon_exploration` は未消費の探索・提案を終了し、履歴は削除しません。
Start 後の task authority を探索側から巻き戻すことはできません。

詳細: [Exploration sessions](docs/EXPLORATION.md)

## v0.15 Operational Hardening

v0.15 では、diagnosis と maintenance authority を分離します。

```text
read-only integrity diagnosis
  -> backup / retention preview
  -> operator が exact scope を確認
  -> explicit restore / cleanup
  -> maintenance provenance
```

`orchestrator doctor` は、runtime SQLite の version/integrity、TaskState /
IntakeState、参照 artifact の SHA-256 と evidence schema、stale job、
HumanGate ledger、disposable worktree を read-only で診断します。診断のために
古い row を書き換えたり、gate を expire したり、job/workspace を削除したりは
しません。

backup は 2 種類です。

```bash
orchestrator --project "$PROJECT" backup create --mode runtime --output runtime.zip
orchestrator --project "$PROJECT" backup create --mode full --output full.zip
orchestrator backup inspect full.zip
```

- `runtime`: durable controller evidence のみ
- `full`: 上記に加えて config、policies、skills、accepted knowledge、
  trusted workflow configuration などの project authority

restore は、検証済み archive の exact scope、`--replace`、quiescent な
project を要求します。full restore では authority を復元し得るため、
さらに `--ack-authority-restore` が必要です。current controller/authority
state が読めない場合、それを verified backup で置換するには
`--ack-unreadable-current-state` も必要です。

physical cleanup も preview-first です。

```bash
orchestrator --project "$PROJECT" retention --days 30
orchestrator --project "$PROJECT" cleanup \
  --before "<exact-cutoff>" --scope "<exact-scope>" --by "$USER"
```

cleanup は TaskState / IntakeState / runtime event / HumanGate history、
TaskState または IntakeState が参照する artifact（Supervisor evidence を含む）、
accepted/candidate Project Learning が参照する
型付き evidence を保持します。初期 v0.15 で削除対象になるのは、古い stale
disposable worktree、terminal job/job-event、参照されていない古い
Artifact-v2-shaped runtime JSON に限定されます。legacy/untyped evidence は
推測で削除せず保守的に保持します。

成功した restore / cleanup は
`.orchestrator/runtime/maintenance.jsonl` に provenance を残します。
agent-facing MCP は `inspect_project` から read-only diagnosis を確認できますが、
backup / restore / cleanup / database repair の mutation tool は持ちません。

詳細: [Operational Hardening](docs/OPERATIONS.md)

## v0.14.1 Project Learning

v0.14 では、次の状態を明確に分離します。

```text
controller-owned historical evidence
  -> non-authoritative candidate
  -> operator による明示的 promotion
  -> accepted project context
  -> profile digest change / re-trust
  -> intake/task ごとの bounded ContextInfluence
```

Project Learning が扱う主な evidence:

- task / intake state
- write-set
- validation
- independent review
- recovery
- provider provenance
- usage
- budget
- runtime event

Proposal schema v2 は、`EvidenceRef`、support count、canonical key、polarity、evidence digest、supersession、contradiction などを保持します。

candidate は `.orchestrator/knowledge/candidates/` に置かれ、profile fingerprint には入りません。candidate が増えても、それだけでは trust や provider routing は変わりません。

promotion された knowledge / policy / skill Markdown は project authority です。そのため profile digest が変わり、明示的な re-trust が必要になります。

### accepted universe と selected context

accepted context 全体と、1つの intake/task に実際に渡す context は別です。

- accepted universe: 最大 4 MiB / 2048 Markdown items
- 1 intake/task の deterministic selection budget: 24 KiB
- complete prompt ceiling: 64 KiB

新しい IntakeState v5 / TaskState v8 は `ContextInfluence` を保持します。これにより、どの accepted context が選ばれ、その entry がどの historical evidence に支えられていたかを後から追跡できます。

accepted knowledge が後から削除されても、完了済み TaskState に記録された historical ContextInfluence は残ります。

### Project Learning の inspection

```bash
orchestrator --project "$PROJECT" learning report
orchestrator --project "$PROJECT" learning context --query "update parser behavior"
```

candidate 生成:

```bash
orchestrator --project "$PROJECT" learning distill
```

candidate inspection / governance:

```bash
orchestrator --project "$PROJECT" proposal P-...

orchestrator --project "$PROJECT" promote P-... \
  --scope <exact-scope> --by "$USER"

orchestrator --project "$PROJECT" proposal-reject P-... \
  --scope <exact-scope> --by "$USER" --reason "..."

orchestrator --project "$PROJECT" proposal-revise P-... \
  --scope <exact-scope> --by "$USER" --statement "..."
```

MCP からは read-only の以下が利用できます。

- `inspect_project.project_learning`
- `list_learning_candidates`
- `get_learning_candidate`
- `preview_learning_context`
- `get_task`
- `get_artifact(kind=context_influence)`

promotion / reject / revise / distill / trust は operator action のままです。

詳細: [Project Learning](docs/PROJECT_LEARNING.md)

## v0.13 Provider Adapter / Plugin SDK

外部 provider adapter は `ai_orchestrator.providers` Python entry-point group で discovery できます。

ただし **package install は authority ではありません**。

外部 plugin が load されるには、少なくとも以下が必要です。

1. distribution が install 済み
2. project profile に exact pin がある
3. distribution/version/entry-point が exact match
4. その profile digest が operator により明示的に trust 済み
5. Provider SDK / Adapter API conformance に合格

install 済みでも unpinned なら inert、pin 済みでも untrusted なら inert です。

また、

```text
loaded != selected != dispatched
```

です。

in-process plugin は controller と同じ Python process / OS user で動く trusted controller code であり、worker sandbox の中に閉じ込められるわけではありません。

詳細: [Provider Adapter / Plugin SDK](docs/PROVIDER_SDK.md)

## Persistence / migration

v0.16.0 時点の主要 persisted contract:

- Runtime SQLite: user_version 3
- HumanGate SQLite: user_version 1
- Jobs SQLite: user_version 1
- TaskState: readable v1-v9 / new writes v9
- IntakeState: readable v1-v6 / new writes v6
- Artifact metadata: readable v1-v2 / new writes v2
- ProjectLearningCandidate: readable v1-v2 / new writes v2
- ContextInfluence: v1
- ExplorationState / turn / transition evidence: v1
- Job: readable v1-v2（exploration job は v2）

古い supported state は read 時に書き換えません。unknown / future schema は fail closed です。

詳細:

- [Persistence contracts](docs/PERSISTENCE.md)
- [Migration](docs/MIGRATION.md)

## Recovery

durable `running` task は、process/host loss 後に自動 replay しません。

retry-safe と判定できるのは、guarded / isolated execution が provider dispatch 前で、root snapshot が変わっていないことを controller が証明できる場合だけです。

ambiguous effect がある場合は fail closed し、root worktree を自動 rollback しません。

詳細: [Recovery & Durability](docs/RECOVERY.md)

## Capability / workflow / runtime selection

Provider Resolution と Model Variant Resolution は分離されています。

```text
task / workflow node
  -> semantic capabilities
  -> Provider Resolution
  -> Model Variant Resolution
  -> adapter execution
```

model / effort の precedence:

```text
task/node explicit override
  > trusted profile model/effort
  > adapter default
```

自動「best model」ranking はありません。

Workflow Schema v1 では、trusted workflow と task-scoped adaptive workflow を扱えます。adaptive workflow は intake/task 内に固定される ephemeral authority で、勝手に provider や validator や policy を install できません。

詳細:

- [Capabilities](docs/CAPABILITIES.md)
- [Workflows](docs/WORKFLOWS.md)
- [Adaptive orchestration](docs/ADAPTIVE_ORCHESTRATION.md)
- [Parallel execution](docs/PARALLEL_EXECUTION.md)

## Usage / budget

usage は推定値ではなく evidence として扱います。

missing telemetry は `unknown` / `unsupported` のまま保持され、prompt/response length から token を推定したり、欠損値を 0 に置き換えたりしません。

trusted policy は provider call 数、controller/provider elapsed、token dimension、provider/model call count、attributable cost などを制限できます。

strict budget が必要とする telemetry を provider/model が証明できない場合は dispatch 前に fail closed します。budget に合わせて provider/model/effort/workflow を勝手に変える fallback はありません。

詳細: [Usage observability and budgets](docs/USAGE_BUDGETS.md)

## HumanGate と approval の区別

single-terminal confirmation は通常の tool permission prompt ではなく MCP `elicitation/create` を使います。

HumanGate:

- Start
- Execution
- Acceptance
- bounded provider-adapter change
- binding cleanup
- task/attempt-scoped AGY broad permission

host の form response は client-mediated であり、暗号学的に「本人がクリックした」と証明するものではありません。

必要なら approval automation / hook を無効にした interactive client を使用してください。

詳細: [Single-terminal design/setup](docs/SINGLE_TERMINAL.md)

## インストール / 更新

Python 3.11+、Linux/macOS を対象にしています。

既存環境を更新する前に active controller / worker を止め、project の `.orchestrator/` 全体をバックアップしてください。v0.15 導入後は、その後の運用 backup に versioned `backup create` を使用できます。

```bash
cd "$HOME/ai-orchestrator"

git pull --ff-only

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev,interop]'

.venv/bin/python -m pytest -q
.venv/bin/orchestrator --version  # 0.16.0
```

新規 checkout の場合:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,interop]'
```

Claude Code / Codex / Antigravity CLI は別途 install / authenticate してください。

built-in adapters:

- Claude Code
- Codex CLI
- Antigravity CLI (`agy`)

## project 用 host setup

以下は例です。ローカル username や project path は各自の環境に置き換えてください。

```bash
ORCH="$HOME/ai-orchestrator/.venv/bin/orchestrator"
PROJECT="/path/to/your/project"
```

### Claude Code

```bash
cd "$PROJECT"

claude mcp remove ai-orchestrator --scope local
claude mcp add --transport stdio --scope local ai-orchestrator -- \
  "$ORCH" --project "$PROJECT" serve

"$ORCH" skill \
  --output "$HOME/.claude/skills/ai-orchestrator/SKILL.md" \
  --replace
```

MCP registration / Skill を変更した後は Claude Code を再起動または reload してください。

### Codex

```bash
cd "$PROJECT"

codex mcp remove ai-orchestrator
codex mcp add ai-orchestrator -- \
  "$ORCH" --project "$PROJECT" serve

"$ORCH" skill \
  --output "$HOME/.agents/skills/ai-orchestrator/SKILL.md" \
  --replace
```

### Antigravity / AGY

project Skill:

```bash
cd "$PROJECT"

"$ORCH" skill \
  --output .agents/skills/ai-orchestrator/SKILL.md \
  --replace
```

global Skill の例:

```text
~/.gemini/config/skills/ai-orchestrator/SKILL.md
```

MCP config には固定 project で次を起動するよう設定します。

```text
$ORCH --project $PROJECT serve
```

現状、Antigravity host -> ai-orchestrator MCP tools は live-verified です。一方、tested client の HumanGate form elicitation は `action=cancel` を返す既知の interoperability limitation があります。

## 通常の使い方

ユーザーは workflow / DAG / worker 起動 / provider を毎回意識する必要はありません。

例:

```text
ai-orchestratorを使って、calculator.pyにsquare(value)を追加し、
pytestテストも追加してください。実装はClaudeに担当させてください。
```

host agent は通常:

1. `inspect_project`
2. Supervisor に task proposal を依頼
3. Start HumanGate
4. Planner
5. Execution HumanGate
6. Implementer
7. registered validators
8. fresh independent Reviewer
9. Acceptance HumanGate

の順で処理します。

主要 request tools:

| Tool | Yes が許可するもの |
| --- | --- |
| `request_start` | proposed task の登録と planning の queue |
| `request_execution` | exact implementation attempt + validators の実行 |
| `request_acceptance` | exact reviewed result の受入れ |

HumanGate の Yes は commit / push / deployment / arbitrary external action を許可しません。

## 診断

主な inspection:

```bash
"$ORCH" --project "$PROJECT" doctor
"$ORCH" --project "$PROJECT" capabilities
"$ORCH" --project "$PROJECT" workflows
"$ORCH" --project "$PROJECT" persistence
"$ORCH" --project "$PROJECT" provider-plugins
"$ORCH" --project "$PROJECT" learning report
```

MCP `inspect_project` でも主要な profile / capability / workflow / plugin / persistence / budget / learning 情報を確認できます。

## Security / limitations

AI Orchestrator は trusted-local alpha です。

主な境界:

- agent intent は human authorization ではない
- candidate / model confidence は authority ではない
- validator output は、validator が実際に検証した範囲の evidence
- provider family label は provider/model の暗号学的証明ではない
- HumanGate response は client-mediated
- in-process external provider plugin は trusted controller code
- OS-level hostile same-user process から controller state を保護する sandbox ではない
- production deployment / trading / publication / regulated-data control plane を主目的としていない

詳細: [Security boundaries](docs/SECURITY.md)

## live E2E

owner-reported live E2E は [docs/E2E.md](docs/E2E.md) に記録しています。

v0.14/v0.14.1 では、Project Learning について次の lifecycle を確認しています。

```text
historical evidence
  -> deterministic candidates
  -> idempotent distillation
  -> exact promotion
  -> automatic untrusted
  -> explicit trust
  -> IntakeState v5 / TaskState v8 ContextInfluence
  -> normal execution / validation / review / acceptance
  -> post-Acceptance new candidates / supersession
  -> promotion cleanup
  -> original digest restored
  -> explicit re-trust
```

確認された中心的 invariant:

> learning accumulates; authority does not

> historical influence provenance survives even after current accepted context changes

v0.15.1 では、v0.15.0 live E2E で発見された IntakeState の Supervisor artifact
retention 欠陥を修正したうえで、doctor、full/runtime backup、exact-scope restore、
unreadable-state restore、runtime-only authority separation、retention/cleanup、
agent authority boundary、original project 非変更を含む live E2E がすべて PASS しました。


## Roadmap

v0.15.1 の live Operational Hardening E2E まで完了し、v0.15.x はクローズしています。

次の主な milestone:

- v0.16 Exploration / Deliberation Sessions（v0.16.0 で live closure 済み）
- v0.17 Release Candidate Hardening
- v1.0 Stable Kernel Contracts

v0.16 では、仕様が曖昧な段階で repository を調べ、仮説・選択肢・未確定事項を
何度も更新できる non-authoritative な探索 session を実装しました。
offline / subprocess wire に加えて、実ユーザー環境の live E2E でも multi-turn
探索、方向転換、stale revision 拒否、明示 transition、3 HumanGate、abandonment、
usage 引き継ぎ、運用 evidence 保持を確認し、v0.16.0 でクローズしました。
探索結果だけでは実行 authority は増えず、具体的な TaskSpec への明示的 transition
と通常の Start HumanGate を経て初めて実行可能になります。

中心原則:

> 探索は理解を変えてよいが、権限を変えるには明示的な遷移が必要。

詳細: [ROADMAP.md](ROADMAP.md)

## 関連ドキュメント

- [Operational Hardening](docs/OPERATIONS.md)
- [Project Learning](docs/PROJECT_LEARNING.md)
- [Provider SDK](docs/PROVIDER_SDK.md)
- [Persistence](docs/PERSISTENCE.md)
- [Migration](docs/MIGRATION.md)
- [Recovery](docs/RECOVERY.md)
- [Security](docs/SECURITY.md)
- [MCP](docs/MCP.md)
- [Single-terminal](docs/SINGLE_TERMINAL.md)
- [E2E evidence](docs/E2E.md)
- [Changelog](CHANGELOG.md)
