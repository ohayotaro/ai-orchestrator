# v1.0.0 公開後の案内

**2026年10月7日、v1.0.0 Stable Control PlaneはRELEASED / CLOSEDとなりました。** 初めて使う場合は[日本語README](../README_ja.md)の導入手順から始めてください。過去の0.17.2準備版を入れて最終E2Eを再実行する必要はありません。

[検証記録](V1_VERIFICATION.md)にCI、2回のowner-live campaign、承認scope、公開identityをまとめています。[live結果](E2E_V1.md)と[対応状況](SUPPORT.md)は、確認できた範囲と限界を区別しています。

公開済みwheel/sdist、v1.0.0 tag、承認済みmanifestは変更しません。このページやREADMEの更新は公開後の別commitです。mainから新しくbuildした配布物は、versionが1.0.0と表示されても公開済みartifactと同一ではありません。

`contract_inventory_sha256`はcontracts.jsonのファイルbytesのhash、`inventory_digest`はcanonical JSONのhashです。両者を同じものとして比較しないでください。

公開用support-matrixはサマリーです。承認済みの完全なmatrix、ProbeRecord、DBコピー、transcript、計算scriptはowner管理のarchiveにあります。この整理作業では原本を取り込んだことやcheckerを再実行したことにしていません。公開サマリーを元のmanifestへ代入してはいけません。

残る運用事項は、一時PyPI tokenの失効確認、archiveの別媒体への複製、次版でのLicense-Expression・Trusted Publishing・古いhelp文言の整理です。未確認事項を完了扱いにはしていません。[Roadmap](../ROADMAP.md)。
