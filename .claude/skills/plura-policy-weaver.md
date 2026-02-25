# 📂 `.claude/skills/plura-policy-weaver.md`

## 概要
PLURAの「Policy Weaver（共有知のタペストリー化）」機能に関するドメイン知識と実装ガイドライン。

## 🧠 Policy Weaver コア原則 (Core Principles)
ClaudeはPolicy Weaver関連の実装において、以下の原則を絶対に順守すること。

1. **二段階制度化 (Heuristic First):**
   - いきなりシステムを強制ブロックするコード（Strict Policy）は生成しない。
   - まずはLLMが読み込むための `Prompt as Code` (強制力: `Suggest` または `Warn`) として実装する。
2. **ワクチン型ポリシー (TTL Driven):**
   - 永遠に続くルールは組織の官僚的硬直化を招く。すべてのポリシーモデルには必ず `ttl_expires_at` (再評価期限) を設ける。
3. **逸脱の歓迎 (Override as Fuel):**
   - ユーザーがルールを無視（Override）することはエラーではなく「ルールの境界条件を更新するための主燃料」である。
   - Overrideを記録し、それを元にポリシーを再評価するフィードバックループをAPIやデータモデルに組み込むこと。

## 📦 データモデルの制約
- `Policy` 関連のモデルでは、ルールを単一のテキストではなく、`dilemma_context`, `principle`, `boundary_conditions` (applies_when / except_when) のJSONスキーマ（GraphComplianceアプローチ）として構造化して保存すること。

## 🛠️ 禁止事項
- ユーザーのアクションを無条件で `BLOCK` するような静的バリデーションを初期実装から組み込むこと（常に `Suggest` か `Warn` から始める）。
