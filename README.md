# MINDYARD

**「自分だけのノートから、みんなの集合知へ」**

MINDYARDは、個人が自分のために行う「記録（Log）」を、組織全体の「集合知（Wisdom of Crowds）」へと自然に変換するナレッジ共創プラットフォームです。

## アーキテクチャ

### 3層構造（The 3-Layer Architecture）

```
┌─────────────────────────────────────────────────────────────┐
│                Layer 3: Public Plaza                         │
│                  (共創の広場)                                │
│   Knowledge Graph Store / Serendipity Matcher               │
├─────────────────────────────────────────────────────────────┤
│                Layer 2: Gateway Refinery                     │
│                  (情報の関所)                                │
│   Privacy Sanitizer / Insight Distiller / Sharing Broker    │
├─────────────────────────────────────────────────────────────┤
│                Layer 1: Private Safehouse                    │
│                  (思考の私有地)                              │
│   ThoughtStream (Input UI) / Context Analyzer               │
└─────────────────────────────────────────────────────────────┘
```

## 技術スタック

- **Frontend**: Next.js 14 (App Router), React, TypeScript, Tailwind CSS
- **Backend**: FastAPI, Python 3.11, SQLAlchemy
- **Database**: PostgreSQL (RDB), Qdrant (Vector DB)
- **Queue**: Celery, Redis
- **LLM**: マルチプロバイダー対応（OpenAI / Google Cloud Vertex AI）

### LLMアーキテクチャ

MINDYARDは用途に応じて最適なLLMプロバイダーとモデルを選択できるマルチプロバイダー設計を採用しています。

| 用途 | 使用箇所 | デフォルトモデル | 特徴 |
|------|----------|------------------|------|
| **FAST** | Layer 1 (Context Analyzer) | gpt-5-nano | 低レイテンシ優先、リアルタイム解析 |
| **BALANCED** | Layer 2 (Privacy Sanitizer, Insight Distiller, Sharing Broker) | gpt-5-mini | バランス重視、標準的な処理 |
| **DEEP** | Layer 2 (Structural Analyzer) | gpt-5.2 | 品質優先、深い洞察・構造化 |

プロバイダーは環境変数で柔軟に切り替え可能です（OpenAI ↔ Vertex AI）。

### Embeddingアーキテクチャ

ベクトル検索（Knowledge Store）で使用するEmbeddingもマルチプロバイダー対応です。

| プロバイダー | モデル | 次元数 | 特徴 |
|-------------|--------|--------|------|
| **OpenAI** | text-embedding-3-small | 1536 | 推奨、高速 |
| **OpenAI** | text-embedding-3-large | 3072 | 高精度 |
| **Vertex AI** | text-embedding-004 | 768 | Google Cloud統合 |
| **Vertex AI** | text-multilingual-embedding-002 | 768 | 多言語対応 |

## 開発環境のセットアップ

### 前提条件

- Docker & Docker Compose
- (オプション) OpenAI API Key

### クイックスタート

```bash
# リポジトリのクローン
git clone https://github.com/your-org/mindyard.git
cd mindyard

# 環境変数の設定
cp .env.example .env
# .env ファイルを編集し、OPENAI_API_KEY を設定

# Docker Compose で起動
docker-compose up -d

# アプリケーションにアクセス
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/api/v1/docs
```

### LLMプロバイダーの設定

#### OpenAI（デフォルト）

`.env` ファイルに以下を設定：

```bash
OPENAI_API_KEY=your-openai-api-key

# 用途別モデル設定（JSON形式）
LLM_CONFIG_FAST='{"provider": "openai", "model": "gpt-5-nano"}'
LLM_CONFIG_BALANCED='{"provider": "openai", "model": "gpt-5-mini"}'
LLM_CONFIG_DEEP='{"provider": "openai", "model": "gpt-5.2"}'

# Embedding設定（JSON形式）
EMBEDDING_CONFIG='{"provider": "openai", "model": "text-embedding-3-small"}'
```

#### Google Cloud Vertex AI（Gemini）

Vertex AI を使用する場合は、以下の手順で設定してください。

**1. Google Cloud プロジェクトの準備**

```bash
# 認証情報を保存するフォルダを作成
mkdir -p .gcp

# CPUの種類に依存して、A, Bのどちらかを実行
# A. 作業用コンテナを起動（対話モード）
docker run -it --rm \
  -v "$(pwd)/.gcp:/root/.config/gcloud" \
  google/cloud-sdk:alpine \
  /bin/bash

# B. 作業用コンテナを起動（対話モード）: MacのM1/M2/M3以降
docker run -it --rm \
  --platform linux/arm64 \
  -v "$(pwd)/.gcp:/root/.config/gcloud" \
  google/cloud-sdk:alpine \
  /bin/bash

# 認証
gcloud auth login
gcloud auth application-default login

# プロジェクトの設定
gcloud config set project YOUR_PROJECT_ID

# Vertex AI API の有効化
gcloud services enable aiplatform.googleapis.com

# アプリケーション用の認証ファイル(ADC)を作成（再度URL認証が必要な場合があります）
gcloud auth application-default login
```

**2. 環境変数の設定**

`.env` ファイルに以下を追加：

```bash
# Google Cloud 設定
GOOGLE_CLOUD_PROJECT=your-gcp-project-id

# 例: BALANCED に Gemini を使用
LLM_CONFIG_BALANCED='{"provider": "vertex", "model": "gemini-1.5-flash"}'

# 例: DEEP に Gemini Pro を使用
LLM_CONFIG_DEEP='{"provider": "vertex", "model": "gemini-1.5-pro"}'

# 例: Vertex AI Embedding を使用
EMBEDDING_CONFIG='{"provider": "vertex", "model": "text-embedding-004"}'
```

**3. サービスアカウント認証（本番環境向け）**

```bash
# サービスアカウントの作成
gcloud iam service-accounts create mindyard-llm \
    --display-name="MINDYARD LLM Service Account"

# 必要な権限の付与
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:mindyard-llm@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"

# キーファイルの生成
gcloud iam service-accounts keys create ./credentials.json \
    --iam-account=mindyard-llm@YOUR_PROJECT_ID.iam.gserviceaccount.com

# 環境変数でキーファイルを指定
export GOOGLE_APPLICATION_CREDENTIALS="./credentials.json"
```

**利用可能なGeminiモデル（LLM）:**
- `gemini-1.5-flash` - 高速、コスト効率重視
- `gemini-1.5-pro` - 高品質、複雑なタスク向け
- `gemini-1.0-pro` - 汎用モデル

**利用可能なVertex AIモデル（Embedding）:**
- `text-embedding-004` - 推奨、768次元
- `text-embedding-005` - 最新、768次元
- `text-multilingual-embedding-002` - 多言語対応、768次元

### ローカル開発（Docker不使用）

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

## API ドキュメント

起動後、以下のURLでAPIドキュメントにアクセスできます：

- Swagger UI: http://localhost:8000/api/v1/docs
- ReDoc: http://localhost:8000/api/v1/redoc

## 主要機能

### Layer 1: Private Safehouse（思考の私有地）

- **ThoughtStream**: チャット形式の入力UI
- **Context Analyzer**: 感情・トピック・インテントの自動解析 `[FAST モデル]`
- ノン・ジャッジメンタル応答（受容的な相槌のみ）

### Layer 2: Gateway Refinery（情報の関所）

- **Privacy Sanitizer**: PII除去、固有名詞の一般化 `[BALANCED モデル]`
- **Insight Distiller**: 構造化（Context/Problem/Solution） `[BALANCED モデル]`
- **Structural Analyzer**: パターン分析、仮説更新 `[DEEP モデル]`
- **Sharing Broker**: 共有価値スコアリング、承認フロー `[BALANCED モデル]`

### Layer 3: Public Plaza（共創の広場）

- **Knowledge Graph Store**: ベクトル検索、意味的類似検索 `[Embeddings]`
- **Serendipity Matcher**: 入力中のリアルタイム推奨

## 開発ロードマップ

- [x] Phase 1: 最高の「独り言ツール」の構築
- [ ] Phase 2: 「精製所」の稼働
- [ ] Phase 3: 「偶然の結合」の実現

## ライセンス

MIT License
