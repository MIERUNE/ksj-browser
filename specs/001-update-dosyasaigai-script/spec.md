# Feature Specification: 土砂災害警戒区域データ更新スクリプト

**Feature Branch**: `001-update-dosyasaigai-script`  
**Created**: 2026-01-14  
**Status**: Draft  
**Input**: User description: "scripts/update_gyousei_kuiki.pyを参考に、ksj/data_collections/dosyasaigai_keikai_kuiki.jsonを更新するスクリプトを作成してください"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 一括更新を一度のコマンドで完了したい保守担当 (Priority: P1)

保守担当者として、MLIT が土砂災害警戒区域（A33）の最新版を公開したタイミングで、1 回のコマンド実行だけで `ksj/data_collections/dosyasaigai_keikai_kuiki.json` を最新状態へ差し替えたい。Web ページの目視確認や手作業のコピペをなくし、更新漏れを防ぎたい。

**Why this priority**: JSON が古いままだとブラウザ項目から取得できる ZIP が欠落し、ユーザーへ直結する不具合になるため。

**Independent Test**: 実サイトから A33 の HTML を取得し、スクリプト実行後に JSON が最新版（全年度×都道府県値）へ置き換わるかを検証するだけで価値を確認できる。

**Acceptance Scenarios**:

1. **Given** デフォルト URL と出力先を指定せずにスクリプトを起動した状態、**When** ネットワーク越しに A33 公開ページを取得して解析すると、**Then** JSON が全都道府県分の最新ファイル名を含む構造で保存され終了コード 0 を返す。
2. **Given** 既存 JSON が古い年度のまま、**When** スクリプトを実行すると、**Then** 年度キーがサイト掲載内容と一致する（例: 「2025年」が追加され「2022年」までが残る）ことを diff で確認できる。

---

### User Story 2 - オフライン検証を行う QA エンジニア (Priority: P2)

QA エンジニアとして、ネットワークに依存せず保存済みの A33 HTML を入力に使って回帰テストを再現したい。過去に問題のあった HTML を使っても安定して JSON を再生成できるようにしたい。

**Why this priority**: pytest で HTML パーサーをユニットテストするための `--html-file` サポートがないと、自動テストや障害再現が困難になる。

**Independent Test**: 既知の HTML ファイルを渡して JSON が期待構造になるか、ネットワークアクセスなしで検証するだけで成立する。

**Acceptance Scenarios**:

1. **Given** `--html-file sample.html --output tmp.json` を指定して実行した状態、**When** ファイル内テーブルを解析すると、**Then** tmp.json に年度×都道府県マッピングが出力されネットワークへアクセスしない。

---

### User Story 3 - 自動化パイプラインを監視するリリース担当 (Priority: P3)

リリース担当として、CI やローカルスクリプトが誤った入力を受け取った場合でも即座に検知したい。ネットワーク失敗やテーブル構造の破壊が起きた際に異常終了コードで通知されることで、間違った JSON がコミットされないようにしたい。

**Why this priority**: 静かに空 JSON が上書きされると、後段のブラウザ・テストまで異常が伝達せず大きな不具合になるため。

**Independent Test**: 意図的に無効 URL・空 HTML・書込み失敗を起こして正しい非ゼロ終了コードになるか確認できれば価値がある。

**Acceptance Scenarios**:

1. **Given** 存在しない URL を `--url` で渡した状態、**When** スクリプトが HTTP 取得に失敗すると、**Then** エラーを表示し終了コード 1 を返す。
2. **Given** テーブルを含まない HTML ファイルを `--html-file` で指定した状態、**When** 解析を行うと、**Then** エラー内容を表示して終了コード 2 を返し JSON を書き換えない。

---

### Edge Cases

- ページに同一年度・同一都道府県で `*_SHP.zip` と `*_GML.zip` が並んでいる場合は SHP を優先し、SHP が存在しない場合のみ GML を採用する。
- 一部の都道府県にデータが欠落している場合は、その年度のキーから該当都道府県を削除せず、欠落を警告ログとして出す。
- HTML テーブル内の地域名が「青森県」「京都府」など異なる表記でも JSON では「青森」「京都」のようにサフィックスを除去し、北海道のみ「北海道」を保持する。
- ファイル名に `_SHP` が含まれる年度（例: 2024 年）と `_GML` のみの年度（例: 2023 年）を混在させても、JSON では年度キーごとに混在を許容し URL 生成ロジックに影響しない。
- ダウンロードページのテーブルクラス名が変化・複数存在する場合は、A33 固有のクラス (`responsive-table mb30`) を条件に解析対象を固定し、誤検知を避ける。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `scripts/update_dosyasaigai_keikai_kuiki.py` という CLI スクリプトを追加し、デフォルトで `https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A33-2024.html` を取得して処理できるようにする。
- **FR-002**: スクリプトは `--url`（取得先の上書き）と `--html-file`（保存済み HTML の利用）を提供し、両方指定された場合は `--html-file` を必ず優先してネットワークアクセスを抑止する。
- **FR-003**: HTML から「地域」「年」「ファイル名」列を抽出し、年度は「YYYY年」形式に正規化、地域は都道府県サフィックスを除去（北海道、全国はそのまま保持）する。
- **FR-004**: 同一年度・同一地域で複数ファイル候補がある場合は `_SHP.zip` を優先し、SHP が存在しない場合のみ `_GML.zip` を選択するルールを実装する。
- **FR-005**: 出力 JSON は `ksj/data_collections/dosyasaigai_keikai_kuiki.json` をデフォルトとし、`--output` で任意のパスへ保存できる。年度キーは降順、都道府県キーは 50 音順で並べる。
- **FR-006**: 成功時は終了コード 0 を返し、ネットワーク取得失敗時は 1、テーブル未検出や必須列欠落時は 2、ファイル書き込み失敗時は 3 を返す。ログメッセージで原因を明示する。
- **FR-007**: 実行完了後、更新した年度数・都道府県数を標準出力へサマリ表示し、diff なしでも更新可否を判断できるようにする。
- **FR-008**: pytest から単体テスト可能な形で HTML 解析・データ構築ロジックを個別関数として公開し、`scripts/update_gyousei_kuiki.py` と同水準のカバレッジを確保できる構造にする。

### Key Entities *(include if feature involves data)*

- **A33 データ行**: A33 ページの 1 行を表し、`year_display`（例: "2024年（令和6年）"）、`region_raw`（例: "青森県"）、`filename`（例: "A33-24_02_SHP.zip"）の3属性を持つ。解析関数はこのリストを生成する。
- **土砂災害警戒区域コレクション**: JSON で保持する年度→地域→ファイル名の辞書。年度キーは文字列（"2024年"）、地域キーは正規化済み名称、値は ZIP ファイル名 (SHP/GML)。
- **CLI 実行結果**: 実行コンテキスト（入力 URL / HTML / 出力先 / 終了コード）をまとめた概念。エラー処理要件やサマリ表示の対象となる。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: スクリプトを既定オプションで実行した場合、最新年度を含む 47 都道府県レコードがすべて JSON に出力され、欠落率 0% で完了コード 0 を返す。
- **SC-002**: 自動テストスイートから HTML 解析・構造生成関数の単体テストを実行すると、100% 成功し、`--html-file` フローでネットワークアクセスが 0 回であることを確認できる。
- **SC-003**: エラー誘発テスト（無効 URL、空 HTML、書込み不能パス）で、それぞれ終了コード 1/2/3 が返り、メッセージに原因語（"network", "table", "write" 等）が含まれている。
- **SC-004**: 実行完了ログに「年度数」「都道府県数」が表示され、運用手順書の確認項目を 1 回の実行で満たせることをリリース担当が確認できる。

## Assumptions

- A33 ページ構造は `responsive-table` / `mb30` クラスのテーブルを解析すれば全年度情報を取得できる。
- 行政区域更新ツールと同様に、都道府県サフィックスの除去ルールを流用しても土砂災害データのキーと噛み合う。
- 2024 年以降の SHP ファイルとそれ以前の GML ファイルの混在は仕様であり、URL 生成ロジック（`ksj/data_loader.py`）が既に吸収しているため追加変更は不要。
- 新規年度が公開される頻度は年 1 回程度であり、スクリプト実行時間は数秒～十数秒の範囲を想定する。

## Clarifications

### Session 2026-01-14

- Q: `--url` と `--html-file` を同時指定した場合、どちらを優先するか？ → A: `--html-file` が指定されていれば URL を無視し、HTML のみで処理する。
