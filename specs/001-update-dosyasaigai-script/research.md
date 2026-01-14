# Research: 土砂災害警戒区域データ更新スクリプト

## HTML 取得とパース方式

- Decision: `urllib.request` + `html.parser.HTMLParser` を使い、追加依存を導入しない
- Rationale: 既存の `update_gyousei_kuiki.py` が同じ手法で安定稼働しており、QGIS 同梱 Python だけで実行できる。社内配布ツールとしても依存管理が最小になる。
- Alternatives considered: `requests` + BeautifulSoup (依存追加が必要)、Selenium 等のヘッドレスブラウザ（過剰で実行環境の再現が難しい）、正規表現のみ（HTML 変更に脆い）。

## 対象テーブルの同定

- Decision: `class="mb30 responsive-table"` を持つテーブルの `tbody` を探索し、列インデックスで「地域/年/ファイル名」を抽出する
- Rationale: A33 ページでは該当テーブルに固有のクラスが付いており、列順も固定。クラス名が変わらない限り堅牢に抽出できる。
- Alternatives considered: 最初の `table` を採用（ノイズを誤取得する可能性）、列ヘッダ文字列で判定（HTML に存在しない場合がある）。

## 年度・地域名の正規化

- Decision: 年度は `YYYY年` へ統一し、地域は `北海道` 以外で都道府県サフィックスを除去する
- Rationale: 既存の `dosyasaigai_keikai_kuiki.json` と同じキー形式を維持することでブラウザツリーの整合性が保てる。年キーはソートや比較がしやすい。
- Alternatives considered: 表示文字列をそのまま使用（年度キーが冗長で比較困難）、都道府県コード（既存 UI 改修が必要）。

## ファイル形式の優先順位

- Decision: 同一年・同一地域で `*_SHP.zip` があればそれを採用し、無い場合のみ `*_GML.zip` を選択する
- Rationale: 2024 年以降は SHP が提供されており Shapefile が最も互換性が高い。旧年度では GML のみでも動作させる必要がある。
- Alternatives considered: 常に GML（SHP 提供が無視される）、両形式を保持（JSON 構造が複雑化し URL 生成が煩雑）。

## CLI オプションと優先順位

- Decision: `--html-file` が指定された場合はローカル HTML を唯一の入力とし、`--url` を無視する（警告は表示）。指定がない場合のみ `--url`/デフォルト URL から取得する
- Rationale: テスト・再現フローでネットワークに依存しないことが最優先であり、利用者が `--html-file` を明示した時に意図しないネットワークアクセスが走ると再現性が損なわれる。
- Alternatives considered: `--url` を優先（オフライン再現と矛盾）、両指定をエラーにする（利便性低下）。

## 終了コードポリシー

- Decision: 0=成功, 1=ネットワーク失敗, 2=テーブル未検出/パース失敗, 3=書込み失敗を踏襲する
- Rationale: 行政区域ツールと同じコード体系の方が運用/CI 監視で共通化しやすい。
- Alternatives considered: 例外メッセージのみ（CI で検知しづらい）、より細かいコード体系（複雑になる）。
