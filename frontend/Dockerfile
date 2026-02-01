# MINDYARD Frontend Dockerfile
FROM node:20-alpine

# 作業ディレクトリ
WORKDIR /app

# 依存関係のインストール
COPY package.json package-lock.json* ./
RUN npm ci

# アプリケーションのコピー
COPY . .

# 非rootユーザーの設定
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs && \
    chown -R nextjs:nodejs /app
USER nextjs

# ポート
EXPOSE 3000

# 環境変数
ENV PORT=3000 \
    HOSTNAME="0.0.0.0"

# デフォルトコマンド（開発用）
CMD ["npm", "run", "dev"]
