# ksj-browser Constitution

QGIS 3.x プラグイン開発プロジェクトの統治文書

## Core Principles

### I. QGIS Plugin Architecture

QGIS プラグインは QGIS UI フレームワークに統合された拡張機能として構成されます。

- プラグインはメタデータファイル (`metadata.txt`) でメインクラスを宣言する MUST
- `classFactory()` 関数は QGIS によって呼び出され、プラグインオブジェクトを返す MUST
- UI 要素（ダイアログ、ツール）は Qt フレームワークで実装する MUST
- プラグインはインストール後、QGIS の Plugins メニューに登録される MUST

### II. Modular Design (関心の分離)

コードは機能ごとにモジュール化し、単一の責任を持つ構造を採用します。

- `ui/` モジュール：ダイアログ、ウィジェット
- `ksj/` モジュール：データ処理、ビジネスロジック
- `tests/`：pytest によるテスト（pytest-qgis を含む）
- 各モジュールは独立してテスト可能な構造を MUST

### III. Test-First Development (NON-NEGOTIABLE)

テスト駆動開発を厳格に実施します。

- テスト作成 → ユーザー承認 → テスト失敗 → 実装 → テスト成功のサイクルを MUST
- `pytest` で全テストを実行可能にする MUST
- 主要な機能と回帰点をカバーするテストを維持する MUST

### IV. Relative Imports (互換性重視)

Plugin Reloader との互換性を確保するため、相対インポートを使用します。

- モジュール間のインポートは `from .module import name` 形式を MUST
- 絶対パスによるインポート（`from module import name`）は避ける MUST
- 子モジュールが孫モジュールをインポートする際も相対インポートを MUST

### V. Type Safety (保守性向上)

型定義を活用して保守性と IDE サポートを向上させます。

- UI ファイル（`.ui`）から生成されるインスタンスに対して型定義クラスを定義する MUST
- `cast()` を使用して型キャストを行い、IDE の自動補完を有効にする MUST
- 型定義は開発者の責任で手動作成する（生成 AI の補助可）

## Technology Stack & Environment

**Language/Version**: Python 3.9+ (QGIS 3.28 同梱)
**Primary Framework**: Qt (QGIS UI フレームワーク)
**Package Manager**: uv
**Virtual Environment**: `.venv` (プロジェクトルート)
**System Site Packages**: 必須（QGIS ライブラリアクセス）
**Testing Framework**: pytest + pytest-qgis
**Type Checking**: cast(), type hints (standard library)

### Environment Setup (MUST)

- `uv venv --python [QGIS_PYTHON_PATH] --system-site-packages` で仮想環境を作成
- VSCode の Python インタプリタを仮想環境に指定
- `system-site-packages` フラグは QGIS ライブラリアクセスの為に MUST

## Development Workflow

### Virtual Environment Management

- 仮想環境はプロジェクトルートに `.venv` として作成する MUST
- Platform-specific Python パスを使用：macOS は `/Applications/QGIS.app/Contents/MacOS/bin/python3`、Windows は QGIS インストールディレクトリ参照
- VSCode は自動的に `.venv` を検出するが、手動選択が必要な場合は [Python: Select Interpreter] コマンドで指定

### Code Organization & Imports

- 相対インポートを徹底して使用し、Plugin Reloader で正常に反映される構造を保つ
- モジュール内の import 順序：標準ライブラリ → サードパーティ → ローカルモジュール（相対）

### UI Type Definitions

- UI ファイル（`.ui`）から `uic.loadUi()` で生成されるインスタンスに対して、対応する型定義クラス（`TypeDict` または `Protocol`）を定義
- 型定義はダイアログクラス内またはモジュール先頭に配置
- `cast()` を使用して型キャストし、IDE のインテリセンスを活用

### Testing Requirements

- テストは `pytest` および `pytest-qgis` を使用することを MUST
- テスト実行は `pytest` に統一し、単一の実行経路を維持する MUST
- QGIS 依存のテストは `pytest-qgis` の仕組みを利用する MUST
- macOS では `source setup_qgis_env.sh` で QGIS 環境変数を設定してから pytest を実行する MUST

## Governance

### Amendment Process

1. 憲法変更は個別のドキュメント PR として提案される
2. 変更の影響範囲を Sync Impact Report として記録する
3. MAJOR/MINOR/PATCH バージョニング規則に従う
4. 変更承認後、依存テンプレート（plan-template.md, tasks-template.md, spec-template.md）の整合性を確認

### Versioning Policy

- **MAJOR**: 原則の削除、大幅な再定義、互換性破壊
- **MINOR**: 新規セクション追加、指針の実質的な拡張
- **PATCH**: 表現の明確化、タイプミス修正、非実質的な改善

### Compliance Review

- 全 PR は本憲法との整合性を確認される MUST
- 複雑性は正当化が求められる MUST
- `README.md` は開発実装ガイダンスとしての機能を保つ

**Version**: 1.0.3 | **Ratified**: 2026-01-11 | **Last Amended**: 2026-01-11
