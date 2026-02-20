"""
SerendipityMatcher Evaluator (Layer 3)

Flash Team 結成の補完性、シナジースコア、役割分散を評価する。

評価軸:
- team_formation: チーム結成判定の正確性（成立/不成立の判定）
- role_complementarity: Hacker/Hustler/Hipster の役割が適切に分散しているか
- synergy_quality: 提案されたチームが課題に対して補完的・効果的か
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from tests.evaluators.base_evaluator import BaseEvaluator


class SerendipityEvaluator(BaseEvaluator):
    def __init__(self, pass_threshold: float = 6.0):
        super().__init__("SerendipityMatcher", pass_threshold=pass_threshold)
        self._matcher = None

    def _get_matcher(self):
        if self._matcher is None:
            from app.services.layer3.serendipity_matcher import SerendipityMatcher
            self._matcher = SerendipityMatcher()
        return self._matcher

    @property
    def scoring_dimensions(self) -> List[Dict[str, str]]:
        return [
            {
                "name": "team_formation",
                "description": (
                    "チーム結成/不成立の判定が正確か。"
                    "補完的な候補がいる場合はチーム結成、"
                    "類似した候補しかいない場合は不成立と判定されるべき。"
                ),
            },
            {
                "name": "role_complementarity",
                "description": (
                    "ハッカー/ヒップスター/ハスラーの役割が適切に分散しているか。"
                    "似た役割の人ばかりでは低評価。"
                ),
            },
            {
                "name": "synergy_quality",
                "description": (
                    "提案されたチームが、ユーザーの課題に対して具体的な"
                    "解決アプローチを持つ補完的な構成か。"
                ),
            },
        ]

    async def run_component(self, input_data: Dict) -> Dict:
        matcher = self._get_matcher()
        candidates = input_data.get("candidates", [])

        # SerendipityMatcher は knowledge_store 経由で候補を取得するが、
        # 評価時は Golden Dataset の候補を直接使う。
        # _evaluate_team_synergy を直接呼ぶ。
        if len(candidates) >= 3 and len(input_data.get("text", "")) >= 50:
            result = await matcher._evaluate_team_synergy(
                current_input=input_data["text"],
                candidates=candidates,
            )
            if result:
                return {
                    "team_found": True,
                    "recommendations": result.get("recommendations", []),
                    "trigger_reason": result.get("trigger_reason", ""),
                }

        return {
            "team_found": False,
            "recommendations": [],
            "trigger_reason": "no_team",
        }

    def build_judge_prompt(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> str:
        candidates_str = ""
        for i, c in enumerate(input_data.get("candidates", []), 1):
            candidates_str += (
                f"{i}. [{c.get('insight_id', '?')}] {c.get('title', '不明')}\n"
                f"   要約: {c.get('summary', '情報なし')}\n"
                f"   トピックス: {', '.join(c.get('topics', []))}\n"
                f"   期待される役割: {c.get('user_role', '不明')}\n\n"
            )

        team_output = ""
        if output.get("team_found"):
            recs = output.get("recommendations", [])
            if recs:
                rec = recs[0]
                members_str = ""
                for m in rec.get("team_members", []):
                    members_str += (
                        f"  - {m.get('display_name', '?')}: "
                        f"{m.get('role', '?')}\n"
                    )
                team_output = (
                    f"- プロジェクト名: {rec.get('project_name', '不明')}\n"
                    f"- 理由: {rec.get('reason', '不明')}\n"
                    f"- メンバー:\n{members_str}"
                )
        else:
            team_output = "- チーム不成立\n"

        expected_team = expected.get("team_found", False)
        expected_roles = expected.get("expected_roles", [])
        expected_section = (
            f"- チーム結成期待: {'成立' if expected_team else '不成立'}\n"
        )
        if expected_roles:
            expected_section += (
                f"- 期待される役割: {', '.join(expected_roles)}\n"
            )

        return (
            f"## ユーザーの課題\n{input_data['text']}\n\n"
            f"## 候補者リスト\n{candidates_str}\n"
            f"## システムの提案\n{team_output}\n"
            f"## 期待される結果\n{expected_section}\n"
            f"上記のFlash Team結成結果を評価してください。"
        )

    def _rule_based_check(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> Tuple[Dict[str, float], str]:
        scores: Dict[str, float] = {}
        reasons: List[str] = []

        expected_team = expected.get("team_found", False)
        actual_team = output.get("team_found", False)

        # --- team_formation ---
        if actual_team == expected_team:
            scores["team_formation"] = 10.0
        else:
            scores["team_formation"] = 2.0
            reasons.append(
                f"チーム結成判定: 期待={expected_team}, 実際={actual_team}"
            )

        # --- role_complementarity ---
        if actual_team:
            recs = output.get("recommendations", [])
            if recs:
                members = recs[0].get("team_members", [])
                roles = [m.get("role", "") for m in members]
                unique_roles = set(roles)
                expected_roles = set(expected.get("expected_roles", []))

                if len(unique_roles) >= 3:
                    scores["role_complementarity"] = 10.0
                elif len(unique_roles) == 2:
                    scores["role_complementarity"] = 6.0
                    reasons.append(f"役割が2種類のみ: {unique_roles}")
                else:
                    scores["role_complementarity"] = 3.0
                    reasons.append(f"役割の多様性不足: {unique_roles}")

                # 期待される役割との一致をチェック
                if expected_roles:
                    matched = unique_roles & expected_roles
                    if len(matched) == len(expected_roles):
                        pass  # 全一致
                    elif len(matched) > 0:
                        scores["role_complementarity"] = min(
                            scores["role_complementarity"], 7.0
                        )
                    else:
                        scores["role_complementarity"] = min(
                            scores["role_complementarity"], 4.0
                        )
                        reasons.append(
                            f"期待役割との一致なし: "
                            f"期待={expected_roles}, 実際={unique_roles}"
                        )
            else:
                scores["role_complementarity"] = 3.0
                reasons.append("チーム成立だがメンバー情報なし")
        else:
            if not expected_team:
                scores["role_complementarity"] = 8.0  # 不成立は期待通り
            else:
                scores["role_complementarity"] = 2.0

        # --- synergy_quality ---
        if actual_team:
            recs = output.get("recommendations", [])
            if recs:
                rec = recs[0]
                has_reason = bool(rec.get("reason"))
                has_project = bool(rec.get("project_name"))
                has_members = len(rec.get("team_members", [])) >= 2

                synergy_score = 4.0
                if has_reason:
                    synergy_score += 2.0
                if has_project:
                    synergy_score += 2.0
                if has_members:
                    synergy_score += 2.0
                scores["synergy_quality"] = min(synergy_score, 10.0)
            else:
                scores["synergy_quality"] = 3.0
        else:
            if not expected_team:
                scores["synergy_quality"] = 8.0
            else:
                scores["synergy_quality"] = 2.0

        return scores, "; ".join(reasons) if reasons else "OK"
