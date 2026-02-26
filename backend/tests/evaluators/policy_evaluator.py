"""
PolicyWeaver Evaluator (Layer 3)

非構造化ログからのポリシー抽出品質を評価する。

評価軸 (Policy Weaver スキル定義に準拠):
- heuristic_compliance: 二段階制度化の遵守（Suggest→Warn→Block の段階的強制力）
- boundary_clarity: 境界条件 (applies_when / except_when) の明確さ・具体性
- ttl_appropriateness: TTL（再評価期限）の妥当性
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from tests.evaluators.base_evaluator import BaseEvaluator


class PolicyEvaluator(BaseEvaluator):
    def __init__(self, pass_threshold: float = 6.0):
        super().__init__("PolicyWeaver", pass_threshold=pass_threshold)
        self._weaver = None

    def _get_weaver(self):
        if self._weaver is None:
            from app.services.layer3.policy_weaver import PolicyWeaver
            self._weaver = PolicyWeaver()
        return self._weaver

    @property
    def scoring_dimensions(self) -> List[Dict[str, str]]:
        return [
            {
                "name": "heuristic_compliance",
                "description": (
                    "二段階制度化の遵守。"
                    "生成されたポリシーが Suggest→Warn→Block の段階的強制力の原則に従っているか。"
                    "初期段階で BLOCK を前提とした記述が含まれていないか。"
                ),
            },
            {
                "name": "boundary_clarity",
                "description": (
                    "境界条件の明確さ。"
                    "applies_when と except_when が具体的な条件で記述されており、"
                    "曖昧さや解釈の余地が最小化されているか。"
                    "dilemma_context がなぜこのポリシーが存在するかの背景を説明しているか。"
                ),
            },
            {
                "name": "ttl_appropriateness",
                "description": (
                    "TTL（再評価期限）の妥当性。"
                    "ポリシーの性質・リスク・変化速度に対して適切な再評価期限が想定されるか。"
                    "永続的・無期限のルールになっていないか。"
                ),
            },
        ]

    async def run_component(self, input_data: Dict) -> Dict:
        weaver = self._get_weaver()
        logs = input_data.get("logs", [])
        project_context = input_data.get("project_context")

        result = await weaver.extract_policies(
            logs=logs,
            project_context=project_context,
        )

        policies = []
        for p in result.policies:
            policies.append(p.model_dump())

        return {
            "policies": policies,
            "policy_count": len(policies),
        }

    def build_judge_prompt(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> str:
        logs_str = "\n---\n".join(input_data.get("logs", []))
        project_ctx = input_data.get("project_context", "なし")

        policies_str = ""
        for i, p in enumerate(output.get("policies", []), 1):
            bc = p.get("boundary_conditions", {})
            applies = bc.get("applies_when", [])
            excepts = bc.get("except_when", [])
            policies_str += (
                f"### ポリシー {i}\n"
                f"- **ジレンマの背景:** {p.get('dilemma_context', '未記述')}\n"
                f"- **原則:** {p.get('principle', '未記述')}\n"
                f"- **適用条件 (applies_when):** {applies}\n"
                f"- **例外条件 (except_when):** {excepts}\n\n"
            )
        if not policies_str:
            policies_str = "（ポリシーなし）\n"

        expected_has = expected.get("has_policies", False)
        expected_keywords = expected.get("expected_principle_keywords", [])
        expected_section = (
            f"- ポリシー抽出期待: {'あり' if expected_has else 'なし'}\n"
        )
        if expected_keywords:
            expected_section += (
                f"- 期待されるキーワード: {', '.join(expected_keywords)}\n"
            )

        return (
            f"## プロジェクトログ\n{logs_str}\n\n"
            f"## プロジェクトコンテキスト\n{project_ctx}\n\n"
            f"## 抽出されたポリシー\n{policies_str}\n"
            f"## 期待される結果\n{expected_section}\n"
            "上記のポリシー抽出結果を、二段階制度化の遵守・境界条件の明確さ・TTLの妥当性の3軸で評価してください。\n\n"
            "注意:\n"
            "- ポリシーが期待通りに抽出されていない（抽出すべきなのに空、または不要なのに抽出）場合は全軸低スコア\n"
            "- BLOCK を前提とした強制的な記述がある場合は heuristic_compliance を低スコアに\n"
            "- applies_when / except_when が抽象的すぎる場合は boundary_clarity を低スコアに\n"
            "- TTL・再評価の概念が全く示唆されていない場合は ttl_appropriateness を低スコアに"
        )

    def _rule_based_check(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> Tuple[Dict[str, float], str]:
        """ルールベースの評価（LLMなし）"""
        scores: Dict[str, float] = {}
        reasons: List[str] = []

        expected_has = expected.get("has_policies", False)
        actual_count = output.get("policy_count", 0)
        policies = output.get("policies", [])

        # --- ポリシー存在チェック ---
        if expected_has and actual_count == 0:
            # ポリシーがあるべきなのに空
            scores["heuristic_compliance"] = 2.0
            scores["boundary_clarity"] = 2.0
            scores["ttl_appropriateness"] = 2.0
            reasons.append("ポリシーが抽出されるべきだが0件")
            return scores, "; ".join(reasons)

        if not expected_has and actual_count > 0:
            # ポリシー不要なのに抽出された
            scores["heuristic_compliance"] = 3.0
            scores["boundary_clarity"] = 3.0
            scores["ttl_appropriateness"] = 3.0
            reasons.append(
                f"ポリシー不要だが{actual_count}件抽出された"
            )
            return scores, "; ".join(reasons)

        if not expected_has and actual_count == 0:
            # 正しくポリシーなし
            scores["heuristic_compliance"] = 10.0
            scores["boundary_clarity"] = 10.0
            scores["ttl_appropriateness"] = 10.0
            return scores, "OK: ポリシー不要で正しく空"

        # --- ポリシーが抽出された場合の詳細評価 ---
        min_count = expected.get("min_policies", 1)
        max_count = expected.get("max_policies", 5)

        # 件数チェック
        if actual_count < min_count:
            reasons.append(
                f"抽出件数不足: {actual_count} < 最低{min_count}"
            )
        if actual_count > max_count:
            reasons.append(
                f"抽出件数過多: {actual_count} > 最大{max_count}"
            )

        # === heuristic_compliance ===
        heuristic_score = self._check_heuristic_compliance(policies, reasons)
        scores["heuristic_compliance"] = heuristic_score

        # === boundary_clarity ===
        boundary_score = self._check_boundary_clarity(
            policies, expected, reasons
        )
        scores["boundary_clarity"] = boundary_score

        # === ttl_appropriateness ===
        ttl_score = self._check_ttl_appropriateness(policies, reasons)
        scores["ttl_appropriateness"] = ttl_score

        return scores, "; ".join(reasons) if reasons else "OK"

    def _check_heuristic_compliance(
        self, policies: List[Dict], reasons: List[str]
    ) -> float:
        """
        二段階制度化の遵守チェック。

        PolicyWeaver はポリシーの「抽出」を行い、enforcement_level は
        DB保存時に SUGGEST がデフォルト設定される。
        抽出結果自体に BLOCK 的な強制記述がないかをチェックする。
        """
        score = 10.0

        block_patterns = [
            r"ブロック",
            r"禁止する",
            r"絶対に.*しない",
            r"必ず.*しなければ.*ない",
            r"違反した場合.*処罰",
            r"block",
            r"BLOCK",
            r"forbidden",
            r"must\s+not",
        ]

        for policy in policies:
            principle = policy.get("principle", "")
            dilemma = policy.get("dilemma_context", "")
            combined_text = f"{principle} {dilemma}"

            for pattern in block_patterns:
                if re.search(pattern, combined_text):
                    score = min(score, 5.0)
                    reasons.append(
                        f"BLOCK的表現を検出: '{pattern}' in principle/dilemma"
                    )
                    break

            # principle が空または非常に短い場合
            if len(principle.strip()) < 5:
                score = min(score, 4.0)
                reasons.append("principle が短すぎるか空")

        return score

    def _check_boundary_clarity(
        self, policies: List[Dict], expected: Dict, reasons: List[str]
    ) -> float:
        """境界条件の明確さチェック"""
        if not policies:
            return 2.0

        total_score = 0.0

        for policy in policies:
            policy_score = 0.0
            bc = policy.get("boundary_conditions", {})
            applies = bc.get("applies_when", [])
            excepts = bc.get("except_when", [])
            dilemma = policy.get("dilemma_context", "")

            # dilemma_context が記述されているか
            if len(dilemma.strip()) >= 10:
                policy_score += 3.0
            elif len(dilemma.strip()) > 0:
                policy_score += 1.5
                reasons.append("dilemma_context が短い")
            else:
                reasons.append("dilemma_context が空")

            # applies_when が存在し具体的か
            if applies:
                avg_len = sum(len(a) for a in applies) / len(applies)
                if avg_len >= 10:
                    policy_score += 3.5
                elif avg_len >= 5:
                    policy_score += 2.0
                    reasons.append("applies_when の記述が短い")
                else:
                    policy_score += 1.0
                    reasons.append("applies_when が抽象的")
            else:
                reasons.append("applies_when が空")

            # except_when の存在
            if excepts:
                avg_len = sum(len(e) for e in excepts) / len(excepts)
                if avg_len >= 10:
                    policy_score += 3.5
                elif avg_len >= 5:
                    policy_score += 2.0
                else:
                    policy_score += 1.0
            else:
                # except_when が必須かどうかは expected に依存
                expected_except = expected.get("expected_except_when_count", 0)
                if expected_except > 0:
                    reasons.append("except_when が期待されるが空")
                else:
                    policy_score += 2.0  # 例外不要の場合はペナルティなし

            total_score += min(policy_score, 10.0)

        avg = total_score / len(policies)
        return min(avg, 10.0)

    def _check_ttl_appropriateness(
        self, policies: List[Dict], reasons: List[str]
    ) -> float:
        """
        TTL の妥当性チェック。

        PolicyWeaver の extract_policies はポリシーの「構造」を返すのみで、
        ttl_expires_at は DB 保存時に compute_ttl_expiry() で付与される。
        ここでは、ポリシーの内容がTTL付き運用に適しているか
        （永続的・絶対的なルールとして記述されていないか）をチェックする。
        """
        score = 8.0  # 基本はデフォルトTTL(30日)が適用されるため高め

        perpetual_patterns = [
            r"永久に",
            r"永遠に",
            r"恒久的",
            r"変更不可",
            r"永続",
            r"forever",
            r"permanent",
            r"immutable",
        ]

        for policy in policies:
            principle = policy.get("principle", "")
            dilemma = policy.get("dilemma_context", "")
            combined = f"{principle} {dilemma}"

            for pattern in perpetual_patterns:
                if re.search(pattern, combined, re.IGNORECASE):
                    score = min(score, 4.0)
                    reasons.append(
                        f"永続的ルールの示唆を検出: '{pattern}'"
                    )
                    break

            # ポリシー内に再評価・見直しへの言及があればボーナス
            review_patterns = [
                r"見直し",
                r"再評価",
                r"定期的に",
                r"ヶ月後",
                r"月後に",
                r"四半期",
                r"年次",
            ]
            has_review = any(
                re.search(p, combined) for p in review_patterns
            )
            if has_review:
                score = min(score + 1.0, 10.0)

        return score
