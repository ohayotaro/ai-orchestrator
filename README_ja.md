# AI Orchestrator

[English](README.md) · [PyPI](https://pypi.org/project/ai-orchestrator-kernel/) · [Release](https://github.com/ohayotaro/ai-orchestrator/releases) · [対応状況](docs/SUPPORT.md)

**いつものAI開発ツールに、計画・承認・実装・テスト・レビュー・受入を分担させます。**

AI Orchestratorは、新しいモデルやホスト型エージェントサービスではなく、ローカルで動く調整役です。対応クライアントと対話すると、オーケストレーターが別プロセスのworkerへ作業を委任します。初期設定ではClaudeが推論・計画・レビュー、Codexが実装を担当します。設定後の通常作業で、毎回workflowやDAGを書いたり、providerを指定したりする必要はありません。

**v1.0.1はv1 Stable Control Planeのdocumentation/packaging maintenance releaseです。** v1.0.0後に整理したこのREADMEを配布物へ反映し、license metadataとPyPI公開経路を更新します。control-planeのruntime behavior・public contracts・supported live baselineはv1.0.0から拡張しません。まずは以下のClaude Code向け手順から始めてください。他のhost/providerの組み合わせまで検証済みという意味ではありません。[対応範囲と制限](docs/SUPPORT.md)を参照してください。

## 何ができるか

- **作業と承認を分離する。** 提案、実行計画、完了した結果を、独立した3つの確認フォームで判断できます。
- **「できました」ではなく証拠を確認する。** 実測したテスト結果、新しい独立レビュー、変更ファイルの記録、取得可能なusageを確認できます。
- **理解を蓄積しても権限は増やさない。** 曖昧な要件は実装前に相談し、プロジェクト知識の採用は明示的な手続きで行います。

変更範囲と受入条件を明確にでき、テストを実行できるリポジトリ作業に適しています。実装前の相談も扱えます。ただし、これは**信頼したローカル環境で使うソフトウェア**です。同じOSユーザーの悪意あるプロセスから隔離するsandboxや、本番deployment・外部取引の承認サービスではありません。

## クイックスタート：Claude Code + Codex

### 始める前に

エージェント内のshellではなく、通常のターミナルを使います。Git、Python 3.11以上、個別にインストール・認証済みのClaude CodeとCodex CLIが必要です。以下は`python3.13`を使用します。必要に応じてインストール済みの対応Pythonへ読み替えてください。自動テストの対象はLinux Python 3.11/3.12/3.13とmacOS Python 3.13です。実ホストで検証した構成は、それより狭い[macOS / Claude Code 2.1.284 / Codex 0.160.0](docs/SUPPORT.md)です。

オーケストレーター専用のAPIキーやsource checkoutは**不要**です。providerの認証・契約は各CLI側で管理します。委任した推論・計画・実装・レビューにはprovider側の料金が発生し得ます。Startを拒否しても、提案生成に使った料金は消えません。料金の未計測は0円ではありません。

各ブロックを同じターミナルで順番に実行し、エラーが出たら停止してください。以下の2つのパスは新規作成用です。既存環境では再初期化せず、[更新・既存プロジェクトの手順](docs/SINGLE_TERMINAL.md#upgrading-and-existing-projects)を使用してください。

### 1. 専用の実行環境へインストール

```bash
VENV="$HOME/.venvs/ai-orchestrator-demo"
PROJECT="$HOME/ai-orchestrator-demo"
```

```bash
test ! -e "$VENV" && python3.13 -m venv "$VENV" && "$VENV/bin/python" -m pip install 'ai-orchestrator-kernel[interop]==1.0.1' 'pytest>=8,<10'
```

```bash
ORCH="$VENV/bin/orchestrator"
"$ORCH" --version
```

期待値は`1.0.1`です。配布名は`ai-orchestrator-kernel`、実行コマンドは`orchestrator`です。extraには相互運用に使用するMCP SDKを含めています。pytestはこのサンプルのvalidator用です。venvの絶対パスを使うため、activateは不要です。

### 2. 小さなGitプロジェクトを作成

```bash
mkdir "$PROJECT" && cd "$PROJECT" && git init -b main
```

```bash
printf 'def add(a, b):\n    return a + b\n' > calculator.py
mkdir tests
printf 'from calculator import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n' > tests/test_calculator.py
printf '__pycache__/\n.pytest_cache/\n.DS_Store\n' > .gitignore
```

```bash
"$ORCH" --project "$PROJECT" init --name calculator-demo
```

期待値は`initialized: true`、`trusted: false`です。`.orchestrator/`を作成しますが、作業を承認する操作ではありません。初期のrole設定は既にClaudeとCodexを選択しています。

### 3. validatorを登録し、内容を確認してtrust

```bash
"$ORCH" --project "$PROJECT" validator add pytest --timeout 120 -- "$VENV/bin/python" -m pytest -q
```

```bash
cat .orchestrator/config.yaml
cat .orchestrator/policies/baseline.md
```

providerの割当、コマンド、policyを確認してからtrustしてください。validator登録は設定であり、まだ実行しません。trustはこのローカル設定の使用を認める操作で、すべてのtaskを一括承認するものではありません。

```bash
git add .gitignore calculator.py tests/test_calculator.py .orchestrator/config.yaml .orchestrator/.gitignore .orchestrator/policies/baseline.md && git commit -m "demo: initial calculator and orchestration profile"
```

Gitにはauthorの設定が必要です。commitが失敗した場合は自分の名前・メールアドレスを設定し、commitを完了してから進んでください。他人のidentityをコピーしないでください。

```bash
"$ORCH" --project "$PROJECT" trust --by "$USER" --ack-local-execution
```

```bash
"$ORCH" --project "$PROJECT" validator check pytest
```

期待値は`ok: true`、`exit_code: 0`、実測したvalidator出力の**1 passed**です。ここではローカルのテストを明示実行し、検証証拠を保存します。モデル呼び出しはありません。

### 4. Claude Codeへ接続し、Skillを配置

```bash
cd "$PROJECT" && claude mcp add --transport stdio --scope local ai-orchestrator -- "$ORCH" --project "$PROJECT" serve
```

```bash
"$ORCH" skill --output "$HOME/.claude/skills/ai-orchestrator/SKILL.md"
```

既存のSkillは上書きしません。先に内容を確認し、意図して置き換える場合のみ`--replace`でバックアップ付き置換を行います。既存のMCP登録も無条件に削除せず確認してください。local scopeのMCP登録は**このプロジェクト専用**です。会話中にディレクトリを変えても、稼働中サーバーの接続先変更にはなりません。[接続手順](docs/SINGLE_TERMINAL.md)を参照してください。

```bash
"$ORCH" --project "$PROJECT" identity --skill "$HOME/.claude/skills/ai-orchestrator/SKILL.md"
"$ORCH" --project "$PROJECT" doctor --operational-only
```

loaded/disk buildが一致し、`matches_packaged: true`であることを確認します。新規プロジェクトのjobs/gates DBは未作成でも正常です。providerを呼ばずに診断するのは`doctor --operational-only`です。通常の`doctor`ではproviderのprobeが行われる場合があります。

このプロジェクトで開いている古いClaude Codeを終了し、新しいセッションを起動します。

```bash
cd "$PROJECT" && claude
```

### 5. 最初の依頼

shellではなく、Claude Codeに以下を貼り付けてください。

```text
ai-orchestratorのsingle-terminal modeを使い、calculator.pyにsubtract(a, b)を追加し、
tests/test_calculator.pyにpytestテストを追加してください。
add(a, b)は維持し、変更はこの2ファイルだけに限定してください。
登録済みのpytest validatorを使い、直接編集せず作業を委任してください。
開始・実行・受入はそれぞれ独立したhost確認フォームを使用してください。
私の代わりにフォームへ回答したり、CLI承認で代替したりしないでください。
```

各フォームの内容を読み、表示された範囲を承認するときだけYesを選びます。期待する結果は、実測したテスト成功と独立レビューの承認を伴う`succeeded` taskです。workerのjob完了やモデルの「完了しました」だけでは、taskの受入完了とは限りません。HumanGateへ自動回答するhookを設定しないでください。

## 3つの確認で何を承認するか

```text
依頼 -> 提案 -> [Start] -> 計画 -> [Execution]
     -> 実装 -> テスト -> 新しい独立レビュー -> [Acceptance]
     -> succeeded
```

| Gate | Yesで許可すること |
| --- | --- |
| Start | 提案taskの登録とplanningのqueue投入。提案生成には既に料金が発生している場合があります。 |
| Execution | 今回の実装attemptと検証の実行。root worktreeのファイルが変更され得ます。 |
| Acceptance | レビュー済み結果の受入とtask成功の記録。最初の書き込みをここまで保留するgateではありません。 |

**Acceptanceより前にファイルが変更される場合があります。** フォームの拒否、taskのcancel、cancelのfinalizeは、統合済み変更の自動rollbackを行いません。No/cancel/未選択/timeout/staleの応答から新たな権限は付与しません。通常のtool permissionやチャット上の返答はHumanGate応答とは別です。これらのgateはcommit・push・deployment・任意の外部操作を許可しません。

初期設定、trust、validator登録、cancel/finalize、maintenanceは明示的なCLI操作として残ります。「single-terminal」は通常の提案から受入までを指し、すべての管理操作が対話だけで完結する意味ではありません。[詳細](docs/RC_OPERATIONS.md)。

## 探索・workflow・学習

要件が曖昧なら「まだ実装せず、ai-orchestratorで選択肢を調べて相談したい」と依頼できます。複数ターンで前提を修正し、方針決定後に明示的な遷移で提案へ進みます。3つのgateは省略されません。

信頼済みworkflowや範囲を限定したtask固有DAGの提案により、毎回ユーザーが実行構造を設計せずに作業できます。書き込みの並列化は分離worktreeを使うopt-inであり、共有worktreeへの無条件な同時書き込みではありません。provider・model・effortの変更は明示的に扱い、隠れたfallbackは行いません。

Project Learningは履歴から知識候補を抽出します。候補が増えても権限やtrustは変わりません。採用はoperatorが行い、再trustが必要です。[探索](docs/EXPLORATION.md)、[workflow](docs/WORKFLOWS.md)、[並列実行](docs/PARALLEL_EXECUTION.md)、[Project Learning](docs/PROJECT_LEARNING.md)を参照してください。

## 対応状況と安全性の境界

v1.0.0の実ホスト検証構成は、Claude Code 2.1.284、Claudeによる推論・計画・レビュー、Codex CLI 0.160.0による実装、MCP 2025-06-18、macOS 26.6.2 arm64、Python 3.13.12です。model/effortはadapter defaultで、実際に解決されたモデル名を保証したものではありません。providerとしての実行と、hostとしての確認フォーム対応は別です。Codex・Antigravity hostを今回のリリースで対応済みに昇格していません。[対応表と証拠の限界](docs/SUPPORT.md)。

HumanGate応答はclient-mediatedであり、人が押したことの暗号学的証明ではありません。No-firstの並び順はhostのfocusや誤クリック防止を保証しません。プロセス内provider pluginは信頼するcontroller codeです。取得できないusageはunknownのまま扱い、不確実な処理をrecoveryで自動再実行しません。契約の安定化は、全構成の相互運用や新しいsecurity boundaryの保証ではありません。[Security](docs/SECURITY.md)。

## ドキュメントと開発

| 目的 | 参照先 |
| --- | --- |
| 接続・既存project・更新 | [Single-terminal guide](docs/SINGLE_TERMINAL.md) |
| 実行ファイルがない・接続先違い・shell継続待ち・フォーム失敗 | [Troubleshooting](docs/TROUBLESHOOTING.md) |
| backup・cancel・maintenance・recovery | [Operations](docs/OPERATIONS.md)、[RC operations](docs/RC_OPERATIONS.md)、[Recovery](docs/RECOVERY.md) |
| 公開API・永続化・SemVer | [Public contracts](docs/PUBLIC_CONTRACTS.md)、[Persistence](docs/PERSISTENCE.md)、[Migration](docs/MIGRATION.md) |
| adapter拡張・host連携 | [Provider SDK](docs/PROVIDER_SDK.md)、[MCP](docs/MCP.md)、[Architecture](docs/ARCHITECTURE.md) |
| リリース証拠と履歴 | [v1検証記録](docs/V1_VERIFICATION.md)、[live E2E](docs/E2E_V1.md)、[Changelog](CHANGELOG.md)、[Roadmap](ROADMAP.md) |

開発には通常利用と**別の**source checkoutと環境を用意し、`.[dev,interop]`をインストールして、`python tools/check_contracts.py`と`python -m pytest -q`を実行します。6つのCI構成はreference・minimum・core-onlyの依存関係を区別しています。editable checkoutや公開後mainのCIから生成した配布物は、version文字列が同じでも公開済みv1.0.0 artifactそのものではありません。

## ライセンスとリリース

[Apache License 2.0](LICENSE)です。[GitHub Releases](https://github.com/ohayotaro/ai-orchestrator/releases/tag/v1.0.0)を公開リリースの正式記録とし、PyPIには同じ検証済みwheel/sdistを配布します。[リリース記録](docs/releases/v1.0.0.json)に完全なhashと承認済みmanifestの参照を記載しています。

このREADMEは公開後に再構成したものです。公開済みv1.0.0のpackageに含まれるREADME、tag、artifactを差し替える変更ではありません。
