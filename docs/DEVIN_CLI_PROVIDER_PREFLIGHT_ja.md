# Devin CLI provider：読み取り専用preflight

状態：**Provider実行は未有効・owner-live未検証**。対象はDevin CLI
3000.11.3（build `9c803229faa4`）を、既存のClaude Code
HumanGate hostから実装担当として呼び出す構成です。Devin自身をhostにする
検証ではありません。直前のhost診断では`form_supported=false`でした。

## 目的とリリース境界

`integrations/devin_provider/`には、Provider SDK v1 / Adapter API v2に
準拠する独立パッケージのprototypeを配置しています。実際の
`Adapter.execute()`は**Devinを起動せず、必ず拒否**します。SDKの
`code_edit`と`write_files`も現時点では広告しません。インストールしても
自動有効化されず、将来の有効化にはpackage/version/entry pointの明示pin、
profileの確認・再trustと別途実機証拠が必要です。

このprototypeをDevin実装担当として設定したり、実タスクを委任したりしないで
ください。テスト用`ProtocolHarness`はfake CLIで起動引数・一時ファイル・
JSON拒否・取消/timeoutを検証するだけで、`Adapter.execute`とは接続して
いません。

v1.0.1の承認済みsource tree、manifest、CI、tag、wheel/sdistを変更しません。

## Phase 0：通常Terminalからread-onlyの仕様確認

新規の使い捨てprojectで行います。過去のv1.0.0/v1.0.1 qualification
fixtureを使用しないでください。Claude/Devin内のagent shellではなく、
通常のTerminalを使います。token、設定ファイル全文、secret値、session
historyを表示・共有しないでください。

次のコマンドはCLIの場所・バージョン・helpとsandbox前提条件だけを確認します。
**`devin -p`やproviderへの有料呼び出しは行いません。**

```bash
command -v devin
devin --version
devin --help
devin sandbox setup
```

前回の観測値は`devin 3000.11.3 (9c803229faa4)`です。`--print`、
`--prompt-file`、`--config`、`--sandbox`、
`--permission-mode`、`--model`、
`--respect-workspace-trust`を確認します。更新によりversion/helpが
変わった場合は、互換と仮定せず**REVIEW REQUIRED**としてください。

Devinの設定はuser/project/localの複数層から統合されます。以下は
**存在の有無とファイル種別だけ**を確認します。内容を`cat`しません。
macOS環境のread-onlyコマンドです。

```bash
for path in \
  "$HOME/.config/devin/config.json" \
  "$HOME/.config/devin/mcp_config.json" \
  ".devin/config.json" \
  ".devin/config.local.json" \
  ".devin/mcp_config.json" \
  ".devin/mcp_config.local.json"; do
  if test -e "$path"; then stat -f '%N %HT' "$path"; else printf '%s absent\n' "$path"; fi
done
```

次の事項はoperator自身が機密値を伏せた上で報告してください。

- user/project/localで有効なpermission設定、特にglobal allowや
  `dangerous`/bypass/外部書き込みの有無
- 他ツールからのconfig import、hooks、MCP server、sandbox exclusionの有無
- worktreeの位置・trust状態（過去の未完了fixtureを混ぜない）
- ネイティブsandboxの前提条件が満たされるか

**一時的な`--config`ファイルを指定しても、優先度の高いproject設定や
加算されるhooksが消えるとは限りません。** 実効権限が確定できない場合は
実行を拒否したままにします。

## 設定リスクの機械可読な照合（read-only）

手作業の確認に加えて、独立したpreflight inspector
[`integrations/devin_provider/tools/inspect_devin.py`](../integrations/devin_provider/tools/inspect_devin.py)
を追加しました。Devinのモデル・MCP・認証・クラウド・既存projectの
stateを呼び出しません。CLIは`--version`と`--help`だけを参照し、
JSONC設定については**生の内容・permission rule文字列・MCP URL・hook
command・secret値を出力せず**、存在・件数・未確認条件だけをJSONで表示します。

最新版のPRを確認した作業用checkoutにスクリプトが存在する場合、通常の
Terminalで次を実行してください。現在の本番リポジトリを上書きせず、
使い捨てprojectを対象にしてください。

```bash
python3 integrations/devin_provider/tools/inspect_devin.py \
  --project "$HOME/ai-orchestrator-devin-host-probe"
```

実際にスクリプトが存在しない場合、別版の`main`から推測して実行せず、
PR #63のファイルを確認してから取得します。`--no-cli-probe`はCLI起動を
完全に避けるオプションです。

結果の`status=REVIEW_REQUIRED`は正常な監査上の分類であり、
**「Devin provider実行OK」ではありません**。特にenterprise policy、
session-level permission、直接`edit`/`write`ツールの範囲、
imported hooksの実効動作、ネットワーク隔離、headless trust、
`--print`の正規化可能性は静的scanだけでは立証できません。
既存projectにMCPが登録されていたり、ユーザー側設定がある場合は
必ず`REVIEW_REQUIRED`を維持します。

**重要なバージョン差**：公式の現行documentationでは
`--sandbox --permission-mode autonomous`が存在しますが、
ownerが提示したDevin CLI 3000.11.3の`--help`には
`autonomous`が列挙されていません。この差異は利用可能性の証明では
ありません。実際に有料の`devin --print`を実行して推測を埋めず、
版固有の契約を別途確認するまで実行側をfail-closedにします。


## 実行対応へ進むために必要な証拠

1. **最終結果の権威性**：`devin --print`の応答に、単一で境界が明確な
   最終結果があることを確認します。完全なJSON Schema検証ができなければ
   成功としません。通常の文章、コードフェンス、途中の会話、exit 0だけでは
   不十分です。存在未確認の`--json-schema`引数を捏造しません。
2. **書き込み隔離**：新規の分離worktreeで実装を行い、root/outside
   worktreeや外部サービスへの影響がないことをnegative evidenceで
   検証します。Devinのsandboxは直接edit/writeツールを同じ形で閉じ込めず、
   network filteringも完全な遮断として立証されていません。
3. **ネイティブ権限**：user/project/localの許可・import・hook・MCPを
   確認します。unattended実行のために`--permission-mode dangerous`や
   `--respect-workspace-trust false`を勝手に付けません。
4. **セッションと再帰防止**：`--continue`、`--resume`、`--cloud`、
   cloud handoff、同一orchestratorのMCPへの再帰、commit/push/deployを
   無断で行わないことを確認します。
5. **拒否・失敗**：timeout/cancel時の子プロセス群停止、permission拒否、
   不正結果、quota/authentication失敗、version driftを確認します。
   暗黙のretry/fallbackは許可しません。取得不能なusage/costはunknownです。
6. **identityとtrust**：plugin distribution/version/entry pointを固定し、
   profile確認・明示的再trust後、正確なkernel/Devin/plugin/configurationで
   owner-live試験を行います。

## この段階で停止

ここまでの作業はread-only preflightです。結果がすべて正常でも、
**`devin -p`の実行やHumanGate/taskの作成を承認したことにはなりません。**
費用と権限を明示した別のowner承認を得てから、限定されたlive probeを設計
してください。承認されるまでは、prototypeの`execute`はfail-closedのまま、
Devin hostもHumanGate非対応のままです。
