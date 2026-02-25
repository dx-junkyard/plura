"""
IntentRouter Evaluator (Layer 1)

意図分類の正確性と、曖昧入力に対する Probe 発動の適切性を評価する。

評価軸:
- intent_accuracy: 正しい意図に分類されているか
- confidence_calibration: 確信度が入力の曖昧さに対して適切か
- probe_appropriateness: 曖昧入力に対して適切に Probe が発動されるか
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from tests.evaluators.base_evaluator import BaseEvaluator


class IntentEvaluator(BaseEvaluator):
    def __init__(self, pass_threshold: float = 6.0):
        super().__init__("IntentRouter", pass_threshold=pass_threshold)
        self._router = None

    def _get_router(self):
        if self._router is None:
            from app.services.layer1.intent_router import IntentRouter
            self._router = IntentRouter()
        return self._router

    @property
    def scoring_dimensions(self) -> List[Dict[str, str]]:
        return [
            {
                "name": "intent_accuracy",
                "description": (
                    "入力テキストの意図が正しく分類されているか。"
                    "期待される intent と一致すれば高評価。"
                ),
            },
            {
                "name": "confidence_calibration",
                "description": (
                    "確信度スコアが入力の明確さに対して適切に調整されているか。"
                    "明確な入力には高い確信度、曖昧な入力には低い確信度が期待される。"
                ),
            },
            {
                "name": "probe_appropriateness",
                "description": (
                    "曖昧な入力に対して適切に needs_probing=true が設定されるか。"
                    "明確な入力に対して不必要な Probe が発動されていないか。"
                ),
            },
        ]

    async def run_component(self, input_data: Dict) -> Dict:
        router = self._get_router()
        result = await router.classify(
            input_text=input_data["text"],
            prev_context=input_data.get("prev_context"),
        )
        # ConversationIntent enum を文字列に変換
        return {
            "intent": result["intent"].value,
            "confidence": result["confidence"],
            "primary_intent": result["primary_intent"].value,
            "secondary_intent": result["secondary_intent"].value,
            "primary_confidence": result["primary_confidence"],
            "secondary_confidence": result["secondary_confidence"],
            "needs_probing": result["needs_probing"],
            "reasoning": result["reasoning"],
        }

    def build_judge_prompt(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> str:
        prev_ctx = input_data.get("prev_context")
        prev_section = ""
        if prev_ctx:
            prev_section = (
                f"## 前回のコンテキスト\n"
                f"- 前回の意図: {prev_ctx.get('previous_intent', 'なし')}\n"
                f"- 前回の応答: {prev_ctx.get('previous_response', 'なし')}\n\n"
            )

        should_not_be = expected.get("should_not_be", [])
        should_not_section = ""
        if should_not_be:
            should_not_section = (
                f"- **絶対に選んではいけない意図:** {', '.join(should_not_be)}\n"
            )

        return (
            f"## ユーザー入力\n{input_data['text']}\n\n"
            f"{prev_section}"
            f"## システムの分類結果\n"
            f"- 主意図: {output['primary_intent']} (確信度: {output['primary_confidence']:.2f})\n"
            f"- 副意図: {output['secondary_intent']} (確信度: {output['secondary_confidence']:.2f})\n"
            f"- Probe 発動: {output['needs_probing']}\n"
            f"- 推論理由: {output['reasoning']}\n\n"
            f"## 期待される結果\n"
            f"- 期待される主意図: {expected.get('primary_intent', '不明')}\n"
            f"- 最低確信度: {expected.get('min_confidence', '指定なし')}\n"
            f"{should_not_section}\n"
            f"上記の意図分類結果を評価してください。"
        )

    def _rule_based_check(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> Tuple[Dict[str, float], str]:
        scores: Dict[str, float] = {}
        reasons: List[str] = []

        # --- intent_accuracy ---
        expected_intent = expected.get("primary_intent", "")
        actual_intent = output.get("primary_intent", "")
        should_not_be = expected.get("should_not_be", [])

        if actual_intent == expected_intent:
            scores["intent_accuracy"] = 10.0
        elif actual_intent in should_not_be:
            scores["intent_accuracy"] = 1.0
            reasons.append(
                f"分類 {actual_intent} は禁止意図に含まれる"
            )
        else:
            # 部分的に近い場合
            scores["intent_accuracy"] = 4.0
            reasons.append(
                f"期待: {expected_intent}, 実際: {actual_intent}"
            )

        # --- confidence_calibration ---
        min_conf = expected.get("min_confidence", 0.0)
        actual_conf = output.get("primary_confidence", 0.0)
        if actual_conf >= min_conf:
            scores["confidence_calibration"] = 8.0
        elif actual_conf >= min_conf * 0.8:
            scores["confidence_calibration"] = 6.0
            reasons.append(
                f"確信度 {actual_conf:.2f} が最低値 {min_conf:.2f} をやや下回る"
            )
        else:
            scores["confidence_calibration"] = 3.0
            reasons.append(
                f"確信度 {actual_conf:.2f} が最低値 {min_conf:.2f} を大幅に下回る"
            )

        # --- probe_appropriateness ---
        needs_probing = output.get("needs_probing", False)
        expected_probing = expected.get("needs_probing")
        if expected_probing is not None:
            if needs_probing == expected_probing:
                scores["probe_appropriateness"] = 10.0
            else:
                scores["probe_appropriateness"] = 3.0
                reasons.append(
                    f"Probe: 期待={expected_probing}, 実際={needs_probing}"
                )
        else:
            # probing の期待が明示されていない場合はデフォルトで OK
            scores["probe_appropriateness"] = 7.0

        return scores, "; ".join(reasons) if reasons else "OK"
