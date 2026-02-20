#!/usr/bin/env python3
"""
OpenAPIスキーマ抽出スクリプト
BackendのFastAPIアプリからOpenAPIスキーマをJSONとして出力します。

使用方法:
    # プロジェクトルートから実行
    python backend/scripts/extract_openapi.py

    # 出力ファイルを指定する場合
    python backend/scripts/extract_openapi.py --output backend/openapi.json
"""
import argparse
import json
import os
import sys

# プロジェクトルートから実行されることを想定し、backendディレクトリをパスに追加
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)

sys.path.insert(0, BACKEND_DIR)

# 環境変数のデフォルト設定（DB接続不要なのでダミー値でOK）
# settings のインポート時にバリデーションが走るため最低限の設定が必要
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://dummy:dummy@localhost/dummy")
os.environ.setdefault("SECRET_KEY", "dummy-secret-key-for-schema-extraction-only")
os.environ.setdefault("ENVIRONMENT", "development")

# CI環境など依存パッケージが不完全な場合、スキーマ生成に不要なモジュールをモックする。
# app.openapi() はルート定義の静的解析のみで、認証・DB処理は実行しない。
from unittest.mock import MagicMock  # noqa: E402

_MOCK_MODULES = [
    "jose", "jose.jwt", "jose.jws", "jose.jwk", "jose.backends",
    "jose.backends.base", "jose.backends.cryptography_backend",
    "passlib", "passlib.context",
    "celery", "redis",
    "openai", "langchain", "langchain_openai", "langchain_community",
    "langgraph", "langgraph.graph", "langgraph.graph.state",
    "tiktoken",
    "google", "google.genai",
    "spacy",
    "presidio_analyzer", "presidio_anonymizer",
    "whisper",
    "qdrant_client",
    "qdrant_client.http",
    "qdrant_client.http.models",
    "qdrant_client.http.exceptions",
    "asyncpg",
]
for _mod in _MOCK_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# FastAPIアプリのインポート（lifespanは起動しない）
from app.main import app  # noqa: E402


def extract_openapi(output_path: str | None = None) -> dict:
    """
    FastAPIアプリからOpenAPIスキーマを取得する。

    app.openapi() はルート定義からスキーマを生成するだけで、
    DBや外部サービスへの接続は行わない。

    Returns:
        OpenAPIスキーマの辞書
    """
    schema = app.openapi()
    return schema


def main():
    parser = argparse.ArgumentParser(
        description="FastAPIアプリからOpenAPIスキーマを抽出します"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="出力先ファイルパス（省略時は標準出力）",
    )
    args = parser.parse_args()

    schema = extract_openapi()
    json_output = json.dumps(schema, ensure_ascii=False, indent=2)

    if args.output:
        # 相対パスはプロジェクトルートを基準に解決
        output_path = os.path.join(PROJECT_ROOT, args.output) if not os.path.isabs(args.output) else args.output
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_output)
        print(f"OpenAPIスキーマを {output_path} に出力しました", file=sys.stderr)
    else:
        print(json_output)


if __name__ == "__main__":
    main()
