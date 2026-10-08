# Devin CLI host接続: read-only preflight

状態: 検証用プロンプト。Devin CLI対応済みの宣言ではありません。

[対応設計](DEVIN_CLI.md)のDV-01 / DV-02用です。先にoperatorが専用の新規fixtureを作成し、利用するexact orchestrator wheel、profile trust、Devin側のMCP登録とSkill配置を確認してください。旧v1.0.0のE2E fixtureは再利用しません。未設定の場合はその項目を報告して停止し、agentが勝手に設定しないでください。

以下を新しいfixtureで起動したDevin CLIへ投入します。この会話自体のhost料金は発生し得ますが、委任providerやvalidatorの呼び出しは許可しません。

---

ai-orchestratorをDevin CLIから使うため、接続とidentityだけをread-onlyで確認してください。実装・E2Eの実行依頼ではありません。

制約:

- ai-orchestratorのMCPが存在するか確認する。見つからなければそこで停止する。
- proposal/task/job/HumanGateの作成、provider dispatch、validator実行は禁止する。
- request_start / request_execution / request_acceptanceはまだ呼ばない。
- project files、DB、config、trust、Skill、hooks、MCP設定を編集しない。
- 実行権限を増やさず、bypass、CLI承認による代替、フォーム自動回答、cloud handoffを行わない。
- token、credential、任意の環境変数、過去session historyを表示・探索・転載しない。
- 通常のtool permission表示をHumanGateのform対応証拠にしない。

確認するもの:

1. 現在の作業ディレクトリとMCP serverに固定されたproject rootが一致するか。
2. そのprojectが今回用のdisposable fixtureか。過去の未完了taskを持つfixtureを再利用していないか。
3. 実際のDevin CLI version、OS、CPU、Python、orchestrator executable。必要なlocal metadataだけを取得する。
4. 配布名はai-orchestrator-kernel。package version、loaded_build、disk_build、contract inventory file SHAを記録する。metadata取得名をai-orchestratorと取り違えない。
5. 読み込んだSkillの場所、sha256、packaged Skillとの一致。複数のSkillが競合していないか。
6. inspect_project等の公開read APIから、実際にnegotiationされたMCP protocol、form capability、host_confirmation情報を記録する。必要なread APIがない項目は推測しない。
7. trusted profileとprovider割当。最初はClaude reasoning/planning/review、Codex implementationを維持する。Devin providerへの変更は別工程。
8. 未完了task、queued/running job、pending/applying/uncertain gate、maintenance barrier、git status。runtime DBが未作成の項目は未作成と記録し、確認のために新規作成しない。
9. hooks、imported configuration、permission modeについて、人の確認フォームを自動回答しない前提を確認できるか。確認不能は未確認とする。

最後に、PASS / FAIL / NOT CHECKEDを分けて報告してください。form capabilityが見えても「実際のHumanGate往復はNOT TESTED」と明記してください。Devinをsupportedへ昇格させないでください。

異常または設定不足があれば停止してください。すべて確認できた場合も、ここで停止します。別途ownerがライブテストとprovider費用を承認するまで、提案生成やHumanGateの実験に進まないでください。
