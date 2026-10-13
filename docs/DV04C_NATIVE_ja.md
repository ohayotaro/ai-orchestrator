# DV-04C — Devin CLI限定native境界テスト（owner実機用）

## 実験の範囲

このフェーズはDevin CLI 3000.11.3 (`9c803229faa4`)の**最小のread-only headlessプロトコル試験**です。
既存の[DV-04B非課金fixture](DV04B_BOUNDARY_ja.md)や[PR #63](https://github.com/ohayotaro/ai-orchestrator/pull/63)
のProvider SDK prototypeと分離されています。DevinをHost/Implementerとして有効化しません。

`integrations/devin_provider/tools/dv04c_native.py`は標準実行では、
Devinの`--version`と`--help`を検査するだけです。**provider callはありません**。
`--live`を明示した場合のみ、費用および未確定のnative隔離について警告し、
operatorが特定の確認文を直接入力した場合に**1回だけ**モデルを呼び出します。

- **呼び出し**：`--print --prompt-file <一時プロンプト> --config <一時設定> --sandbox --permission-mode auto --respect-workspace-trust true`
- **作業場所**：OSが生成する使い捨てworkspace。parentのHOME/設定を引き継がず、`HOME`、`XDG_*`、`TMPDIR`も一時領域にする
- **要求**：ツール実行・読み取り・書き込みなし、決まったJSONオブジェクトの返答のみ
- **上限**：CLI subprocessは1回、90秒のローカルタイムアウト（15〜180秒の範囲で変更可能）
- **検査**：scratchのworkspace marker・workspace外scratch sentinelの変更有無、終了コード、stdout/stderrサイズ、stdout SHA-256、厳密JSON構文と値
- **公開情報**：raw stdout、stderr、token、API key、プロンプト全文は報告しない
- **中止**：CLI不一致、spawn error、timeout、output overflow、trust/auth拒否、scratch marker変更は成功として扱わない
- **未保証**：モデル課金額、native直接write制限、外部ネットワーク、remote/cloud effects、remote cancellation、モデルのJSON Schema強制

**重要**：`--sandbox`はexec-toolに限定され、Devinのdirect edit/write toolを包括的に閉じ込める保証はありません。
非対話モードではworkspace trustの確認UIを出せません。未trustなら拒否される可能性があり、
**`--respect-workspace-trust false`へ切り替えてはいけません**。
この試験はheadless trust/auth障害を確かめるための第一段階です。
一時HOMEを使うため既存のDevin認証セッションが利用できず、認証失敗になる可能性もあります。
いずれも正当なBLOCKED結果であり、勝手に認証設定をコピーしません。

## 通常Terminalでの実行

```bash
cd "$HOME/ai-orchestrator-devin-provider-probe"
git status --short
git pull --ff-only origin feature/devin-provider-sdk-prototype
python3 integrations/devin_provider/tools/dv04c_native.py
```

期待されるdry-runは`READY_FOR_EXPLICIT_OPERATOR_CONSENT`か、
CLI contract不一致による`BLOCKED_CLI_CONTRACT`です。
前者でも実効的な権限がPASSしたわけではありません。

### ownerが別途、課金と未確定の外部effectsを容認する場合のみ

```bash
python3 integrations/devin_provider/tools/dv04c_native.py --live --timeout-seconds 90
```

標準出力に費用と権限の警告が出ます。operatorが
`RUN ONE DEVIN CALL`と直接入力しない限り実モデルを呼びません。
**金額ベースの支出上限はこのツールでは設定・保証できません。**
起動後の実課金はプロセスを停止しても取り消せない場合があります。

`native_calls_attempted=1`はCLIの起動を試みたことを示すだけで、
課金確定、成功、隔離、JSON出力契約を意味しません。
`prompt_json_conformant=true`は「この1回の応答が指定JSONと一致した」
という観測に過ぎず、CLIがschema-constrained structured outputを
ネイティブに保証する証拠ではありません。

## 停止・次の判断

- `BLOCKED_CLI_CONTRACT`：実機バージョン・help driftを調査。更新やバイパスを勝手に行わない
- `READY_FOR_EXPLICIT_OPERATOR_CONSENT`：dry-runのみ完了。モデルは未実行
- `OPERATOR_DECLINED`：実行せず終了
- `REVIEW_NATIVE_RESULT`：プロセスとscratchの観測結果を人が評価。**合格判定ではない**
- `STOP_FIXTURE_MODIFIED`：scratch sentinelの変更を検出。Provider実装は解放しない
- `BLOCKED_NATIVE_EXIT`：CLI異常終了（認証/trustなど原因は未分類）。確認の迂回は禁止
- `BLOCKED_NATIVE_RESULT`：exit zeroでも正確な最終JSONを取得できなかった
- `STOP_NATIVE_PROCESS`：timeout、output limitまたはprocess terminationの不確実性
- `BLOCKED_NATIVE_SPAWN` / `BLOCKED_PROBE_ERROR`：修正する前に失敗状況を確認

この試験ではwriteを依頼しません。**write scope、network confinement、
課金/remote cancellation、HumanGateを検証済みと記録しないでください。**
追加の書き込み境界試験は、成果物が完全に隔離された新規fixtureに対して
別のowner承認を得た上で設計します。

結果JSONのみ共有してください。元のstdout/stderrや個人の設定・認証情報は
貼り付けないでください。
