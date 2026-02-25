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

---

## ⚖️ LLM-as-a-Judge 評価軸 (Evaluation Metrics)

`PolicyEvaluator`（`BaseEvaluator` を継承）では、以下の3軸で1〜10点採点する。

| 軸名 | 説明 | 合格閾値 |
|------|------|---------|
| `heuristic_compliance` | 二段階制度化の遵守: 出力ポリシーが絶対的な`BLOCK`ではなく、`Suggest`または`Warn`（Prompt as Code）として定義されているか。`enforcement_level` フィールドが `suggest` / `warn` のいずれかであれば高スコア。 | 7.0 |
| `boundary_clarity` | 境界条件の明確さ: `applies_when` / `except_when` の条件が、入力の `dilemma_context` に記述されたジレンマを正確に反映しているか。曖昧・過度に広い条件は減点。 | 6.0 |
| `ttl_appropriateness` | TTLの妥当性: `ttl_expires_at` が設定されており、ポリシーの性質に応じた合理的な再評価期限（例: 人事系なら6ヶ月、技術系なら3ヶ月）になっているか。未設定・遠すぎる日付は低スコア。 | 7.0 |

### Golden Dataset JSONイメージ

`backend/tests/golden_datasets/policy_weaver.json` の形式:

```json
{
  "component": "PolicyWeaver",
  "version": "1.0",
  "description": "PolicyWeaverのルール抽出・構造化テストケース",
  "cases": [
    {
      "id": "PW-001",
      "input": {
        "dilemma_context": "新メンバーが既存の設計ドキュメントを読まずにPRを出し続けている。指摘するとモチベーションが下がる可能性があるが、放置するとコード品質が低下する。",
        "override_history": []
      },
      "expected": {
        "expected_policy_structure": {
          "principle": "新規参加者の自律性を尊重しつつ、チームの設計標準への段階的な誘導を優先する",
          "enforcement_level": "suggest",
          "applies_when": ["新メンバーが設計ドキュメントへの参照なしにPRを作成した場合"],
          "except_when": ["緊急のバグ修正の場合", "メンバーが既存ドキュメントを参照した旨をPRに明記している場合"],
          "ttl_expires_at": "6ヶ月以内の日付"
        }
      },
      "tags": ["onboarding", "code_review", "gradual_guidance"],
      "difficulty": "medium"
    },
    {
      "id": "PW-002",
      "input": {
        "dilemma_context": "深夜にSlackで質問が来ることが多く、即答しないと翌日の作業がブロックされる。しかし対応を続けると自分が疲弊する。",
        "override_history": [
          {"reason": "緊急リリース前は対応せざるを得なかった"}
        ]
      },
      "expected": {
        "expected_policy_structure": {
          "principle": "持続可能な応答習慣を維持し、深夜対応をデフォルト化しない",
          "enforcement_level": "warn",
          "applies_when": ["22時〜7時の時間帯にSlackへの即時返信が発生した場合"],
          "except_when": ["本番障害など定義済みのインシデント対応プロセスが発動している場合"],
          "ttl_expires_at": "3ヶ月以内の日付"
        }
      },
      "tags": ["work_life_balance", "communication", "boundary"],
      "difficulty": "hard"
    }
  ]
}
```

### PolicyEvaluator 実装の骨格

```python
# tests/evaluators/policy_evaluator.py
from typing import Dict, List
from tests.evaluators.base_evaluator import BaseEvaluator


class PolicyEvaluator(BaseEvaluator):
    def __init__(self):
        # heuristic_compliance と ttl_appropriateness の閾値が高め
        super().__init__("PolicyWeaver", pass_threshold=6.5)

    @property
    def scoring_dimensions(self) -> List[Dict[str, str]]:
        return [
            {
                "name": "heuristic_compliance",
                "description": (
                    "ポリシーの enforcement_level が 'suggest' または 'warn' であるか。"
                    "'block' や強制停止ロジックが含まれていれば低スコア。"
                ),
            },
            {
                "name": "boundary_clarity",
                "description": (
                    "applies_when / except_when の条件が入力ジレンマを正確に反映しているか。"
                    "過度に曖昧な条件や、ジレンマと無関係な条件は減点。"
                ),
            },
            {
                "name": "ttl_appropriateness",
                "description": (
                    "ttl_expires_at が設定されており、ポリシー内容に対して合理的な期限か。"
                    "未設定・無期限・過度に遠い日付は低スコア。"
                ),
            },
        ]

    async def run_component(self, input_data: Dict) -> Dict:
        # Celeryタスクとして実装されているため、テスト時は同期的に呼び出す
        # plura-self-optimization.md §3.3 末尾のCelery非同期テスト指針を参照
        from app.services.layer3.policy_weaver import policy_weaver
        result = await policy_weaver.extract_policy(
            dilemma_context=input_data["dilemma_context"],
            override_history=input_data.get("override_history", []),
        )
        return result

    def build_judge_prompt(self, input_data: Dict, output: Dict, expected: Dict) -> str:
        return (
            f"## ジレンマの文脈\n{input_data['dilemma_context']}\n\n"
            f"## 抽出されたポリシー\n{output}\n\n"
            f"## 期待されるポリシー構造\n{expected.get('expected_policy_structure', '指定なし')}\n\n"
            "上記のポリシー抽出結果を評価してください。"
        )
```
