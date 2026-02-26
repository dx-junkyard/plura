# Mindyard Project Context (Second Brain)

## Core Vision
個人の「迷い・プロセス・文脈」を記録し、自己記録の「副作用」として組織の知恵へ昇華させるプラットフォーム。
マッチングは目的ではなく、記録の結果として生じる「セレンディピティ」である。

## Architecture Map (3-Story Structure) 
1. **Layer 1 (Private Space):** `backend/app/services/layer1`
   - Role: Raw thought capture. No constraints.
   - Tech: Context Analyzer. Handle messy, unstructured data.
2. **Layer 2 (Gateway):** `backend/app/services/layer2`
   - Role: The Filter. Privacy protection & Distillation.
   - Tech: Insight Distiller, Privacy Sanitizer. **CRITICAL SECURITY AREA.**
3. **Layer 3 (Public Plaza):** `backend/app/services/layer3`
   - Role: Connection. Semantic search & Rule generation.
   - Tech: Serendipity Matcher, Knowledge Store.

## Developer Rules
- **Privacy First:** Never commit code that bypasses `PrivacySanitizer` in Layer 2.
- **Sync Types:** When modifying Pydantic models (`backend`), update TypeScript types (`frontend`) immediately.
- **Test Distillation:** Use the `note-structurer` skill to verify how raw logs are processed.

## Skills

### Self-Optimization（テスト・評価・プロンプト最適化）
テスト追加、Golden Dataset 構築、LLM-as-a-Judge 評価、プロンプト改善時は
`.claude/skills/plura-self-optimization/SKILL.md` を参照すること。

### Policy Weaver（ポリシーモデル設計・実装・評価）
Policy Weaver関連のデータモデル設計、ポリシー判定ロジック実装、TTL管理、Override記録の実装時は
`.claude/skills/plura-policy-weaver/SKILL.md` を参照すること。

### Async Architecture（非同期タスク・Celery設計）
新規Celeryタスク追加、LLM呼び出しの非同期化、バックグラウンド処理の設計・実装時は
`.claude/skills/plura-async-architecture/SKILL.md` を参照すること。
```

### 3. 確認

Claude Code で以下のように指示して、スキルが認識されることを確認：

```
> テスト環境をセットアップしたい。Self-Optimizationスキルを読んで進めて。
```

---

## 使い方（Claude Code への指示例）

### Phase 1: Golden Dataset と単体テスト

```
IntentRouter の Golden Dataset を作成して。
SKILL.md の Section 3 のフォーマットに従って、最低20件のテストケースを作って。
```

```
PrivacySanitizer の単体テストを書いて。
SKILL.md の Section 3.3 の2層テスト（フォールバック + LLMモック）パターンで。
```

### Phase 2: LLM-as-a-Judge

```
PrivacyEvaluator を実装して。
SKILL.md の Section 4 の BaseEvaluator を継承して、
PII除去率・文脈維持率・自然さの3軸で採点するように。
```

### Phase 3: プロンプト最適化

```
IntentRouter の失敗ケースを分析して改善案を出して。
SKILL.md の Section 5 の prompt_optimizer パターンで。
```

### Phase 4: Policy Weaverの評価実装

```
PolicyWeaver の Golden Dataset を作成して。
plura-policy-weaver スキルに定義されている3つの評価軸（ジレンマ、境界条件、TTL）で評価できるようにして。
```

---

## ディレクトリ構成（完成時）

```
project-root/
├── CLAUDE.md                          # ← スキル参照を追記
├── .claude/
│   └── skills/
│       └── plura-self-optimization.md # ← このファイル
├── backend/
│   ├── app/
│   │   └── services/                 # 既存コンポーネント
│   └── tests/
│       ├── conftest.py               # 共通フィクスチャ
│       ├── golden_datasets/          # Phase 1
│       │   ├── intent_router.json
│       │   ├── privacy_sanitizer.json
│       │   └── ...
│       ├── unit/                     # Phase 1
│       │   ├── test_intent_router.py
│       │   └── ...
│       ├── evaluators/               # Phase 2
│       │   ├── base_evaluator.py
│       │   ├── privacy_evaluator.py
│       │   └── run_evaluation.py
│       ├── optimization/             # Phase 3
│       │   ├── failure_cases.json
│       │   ├── prompt_optimizer.py
│       │   └── ab_test_runner.py
│       └── integration/
│           └── test_layer2_pipeline.py
└── .github/
    └── workflows/
        └── quality-gate.yml          # CI/CD
```

---

## 推奨進行順序

| Step | やること | 所要時間目安 |
|------|---------|-------------|
| 1 | SKILL.md を `.claude/skills/` に配置 | 1分 |
| 2 | `backend/tests/conftest.py` 作成（SKILL.md §3.4） | 15分 |
| 3 | IntentRouter の Golden Dataset 20件作成 | 30分 |
| 4 | IntentRouter の単体テスト作成・実行 | 30分 |
| 5 | PrivacySanitizer → InsightDistiller と横展開 | 各30分 |
| 6 | BaseEvaluator + PrivacyEvaluator 実装 | 1時間 |
| 7 | 評価CLI で全コンポーネントスコア確認 | 30分 |
| 8 | 失敗ケース蓄積 → prompt_optimizer 実行 | 1時間 |

**推奨**: まず IntentRouter か PrivacySanitizer の1コンポーネントで Phase 1→2 を
通しで完了させ、パターンを確立してから他コンポーネントに横展開する。

