# DV-04B — Devin Provider実効設定・権限境界の非課金検証

状態：**SYNTHETIC TESTED / NATIVE BOUNDARIES UNKNOWN / PROVIDER EXECUTION BLOCKED**。
対象は独立した`ai-orchestrator-provider-devin` prototypeであり、公開済み
v1.0.1 artifact、trust/profile、HumanGate、Devin実行hostは変更しません。

## 何をテストしたか

`integrations/devin_provider/tools/dv04b_fixture.py`は、OSの一時領域だけに
専用workspace、HOME、XDG config/cache/data、dummy fileを作り、**自作の
fake Python subprocessのみ**を実行します。Devin CLI、ネットワーク、
AI provider、トークン、ownerの実workspaceは利用しません。

合成プローブでは、以下の観測が得られます。

- subprocessに渡す`HOME`と`XDG_*`は一時ディレクトリを指す
- 認証情報や`DEVIN_PERMISSION_MODE`などの環境変数は継承されない
- fake subprocessが`cwd=workspace`で起動する
- native OS sandboxのないfake subprocessは**同じ一時領域内のworkspace外の兄弟ファイルを書き換えられる**
- 操作終了後、一時ディレクトリは削除される
- provider_calls=0、task_or_gate_mutations=0、execution_authorized=falseを常に保持する

workspace外への書き込み試験は、破棄可能な一時ファイルだけを対象にした
**negative control**です。これはDevin固有のバグやsandbox bypassが証明
されたという意味ではありません。逆に、HOME/XDGや環境変数を隔離しても
実効的なwrite sandboxの保証にはならないことを示します。

`ProtocolHarness`の**fake専用**実行経路も、一時HOMEでsubprocessを起動し、
親のcredentials/permission overrideを渡さないようにしました。symlink化
されたworkspaceも拒否します。fake用設定には8つのimport元をfalseで
記載しますが、**実際のDevin native configが隔離されたとは主張しません**。

## ローカルでの実施方法

GitHub draft PR #63ブランチのcleanなコピーで、通常のTerminalを使用します。
Python 3.11以上でのSDKテストとは別に、次のstandalone fixtureは標準ライブラリ
だけで実行できます。

```bash
cd "$HOME/ai-orchestrator-devin-provider-probe"
python3 integrations/devin_provider/tools/dv04b_fixture.py
```

期待値：

```text
"status": "REVIEW_REQUIRED"
"result": "PASS_SYNTHETIC_DETECTION_ONLY"
"execution_authorized": false
"provider_calls": 0
"synthetic_outside_write_observed": true
```

`synthetic_outside_write_observed=true`は **negative controlが実際に危険な
操作可能性を検出した**という意味です。これをnative sandbox PASSと
解釈してはいけません。出力に実パス、token、promptは含めません。

## nativeで未検証の境界

以下は今回のfixtureでは証明できないため、すべてUNKNOWNのままです。

1. 実際のDevin CLIでのdirect edit/write toolのwrite_scope
2. team/session/global/project/local policyの実効的な優先順位とhooks
3. 他クライアント設定importやMCPの起動時隔離
4. network egressとcloud handoffの影響
5. headless workspace trustとpermission modalの挙動
6. `devin --print`のschema拘束された最終出力
7. provider cancel/timeout後のremote effectsの有無

既存のowner preflightでも、8種類のimport設定、subagents、direct write、
network、headless、team/session policyの保証が不足していました。
`Adapter.capabilities`は空、`Adapter.execute()`は起動前に拒否します。
この結果を理由にcapabilityを付与・profileをtrustしないでください。

## DV-04Cへ進むための独立した承認

まずownerの通常Terminalでread-only metadata/config監査を更新し、次に
scratch projectでnative sandboxや結果形式の**限定live実験**を設計します。
実験には別途、対象CLI version、入力内容、書き込み許可範囲、料金上限、
timeout、承認方式、外部effectsの有無を指定したowner承認が必要です。

有料実験を行うまではDevinをImplementerへ設定しません。PR #63はdraft、
本streamとv1.0.1本番releaseは分離します。
