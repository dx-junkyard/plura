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
- **LLM**: OpenAI API (GPT-4, Embeddings)

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
- **Context Analyzer**: 感情・トピック・インテントの自動解析
- ノン・ジャッジメンタル応答（受容的な相槌のみ）

### Layer 2: Gateway Refinery（情報の関所）

- **Privacy Sanitizer**: PII除去、固有名詞の一般化
- **Insight Distiller**: 構造化（Context/Problem/Solution）
- **Sharing Broker**: 共有価値スコアリング、承認フロー

### Layer 3: Public Plaza（共創の広場）

- **Knowledge Graph Store**: ベクトル検索、意味的類似検索
- **Serendipity Matcher**: 入力中のリアルタイム推奨

## 開発ロードマップ

- [x] Phase 1: 最高の「独り言ツール」の構築
- [ ] Phase 2: 「精製所」の稼働
- [ ] Phase 3: 「偶然の結合」の実現

## ライセンス

MIT License
