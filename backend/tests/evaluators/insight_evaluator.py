"""
InsightDistiller Evaluator (Layer 2)

知見抽出の構造化品質と not_suitable 判定の精度を評価する。

評価軸:
- structure_quality: 構造化された出力（title/context/problem/solution）の品質
- suitability_judgment: not_suitable 判定の正確性
- abstraction_quality: 具体的経験から汎用的な知見への抽象化の質
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from tests.evaluators.base_evaluator import BaseEvaluator


class InsightEvaluator(BaseEvaluator):
    def __init__(self, pass_threshold: float = 6.0):
        super().__init__("InsightDistiller", pass_threshold=pass_threshold)
        self._distiller = None

    def _get_distiller(self):
        if self._distiller is None:
            from app.services.layer2.insight_distiller import InsightDistiller
            self._distiller = InsightDistiller()
        return self._distiller

    @property
    def scoring_dimensions(self) -> List[Dict[str, str]]:
        return [
            {
                "name": "structure_quality",
                "description": (
                    "title/context/problem/solution/summary が適切に構造化されているか。"
                    "各フィールドが空でなく、内容が入力テキストを正しく反映しているか。"
                ),
            },
            {
                "name": "suitability_judgment",
                "description": (
                    "not_suitable 判定が正確か。"
                    "雑談・短文・テスト投稿は not_suitable=true、"
                    "有益な知見は not_suitable=false と判定されるべき。"
                ),
            },
            {
                "name": "abstraction_quality",
                "description": (
                    "具体的な個人経験が、他の人にも適用可能な汎用的知見に抽象化されているか。"
                    "タイトルは検索・一覧で有用か。topics/tags は適切か。"
                ),
            },
        ]

    async def run_component(self, input_data: Dict) -> Dict:
        distiller = self._get_distiller()
        content = input_data["text"]
        metadata = input_data.get("context")
        result = await distiller.distill(content, metadata=metadata)
        return result

    def build_judge_prompt(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> str:
        is_suitable = expected.get("is_suitable", True)
        expected_section = ""
        if is_suitable:
            title_kw = expected.get("expected_title_keywords", [])
            topics = expected.get("expected_topics", [])
            expected_section = (
                f"- 適格な入力（有益な知見として構造化されるべき）\n"
                f"- 期待されるタイトルキーワード: {', '.join(title_kw) if title_kw else '指定なし'}\n"
                f"- 期待されるトピックス: {', '.join(topics) if topics else '指定なし'}\n"
            )
        else:
            expected_section = (
                f"- 不適格な入力（not_suitable=true と判定されるべき）\n"
                f"- 理由: {expected.get('rejection_reason', '雑談・短文・テスト投稿等')}\n"
            )

        not_suitable = output.get("not_suitable", False)
        output_section = ""
        if not_suitable:
            output_section = "- **システム判定: not_suitable (不適格)**\n"
        else:
            output_section = (
                f"- タイトル: {output.get('title', '(空)')}\n"
                f"- コンテキスト: {output.get('context', '(空)')[:200]}\n"
                f"- 課題: {output.get('problem', '(空)')[:200]}\n"
                f"- 解決策: {output.get('solution', '(空)')[:200]}\n"
                f"- 要約: {output.get('summary', '(空)')[:200]}\n"
                f"- トピックス: {output.get('topics', [])}\n"
                f"- タグ: {output.get('tags', [])}\n"
            )

        return (
            f"## 入力テキスト\n{input_data['text']}\n\n"
            f"## システムの出力\n{output_section}\n"
            f"## 期待される結果\n{expected_section}\n"
            f"上記のインサイト抽出結果を評価してください。"
        )

    def _rule_based_check(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> Tuple[Dict[str, float], str]:
        scores: Dict[str, float] = {}
        reasons: List[str] = []

        is_suitable = expected.get("is_suitable", True)
        actual_not_suitable = output.get("not_suitable", False)

        # --- suitability_judgment ---
        if is_suitable and not actual_not_suitable:
            scores["suitability_judgment"] = 10.0
        elif not is_suitable and actual_not_suitable:
            scores["suitability_judgment"] = 10.0
        elif is_suitable and actual_not_suitable:
            scores["suitability_judgment"] = 2.0
            reasons.append(
                "適格な入力が not_suitable と判定された (false negative)"
            )
        else:
            scores["suitability_judgment"] = 2.0
            reasons.append(
                "不適格な入力が suitable と判定された (false positive)"
            )

        # --- structure_quality ---
        if actual_not_suitable:
            if not is_suitable:
                # 正しく不適格と判定: 全フィールドが空であるべき
                title = output.get("title", "")
                if title == "":
                    scores["structure_quality"] = 10.0
                else:
                    scores["structure_quality"] = 6.0
                    reasons.append("not_suitable なのに title が空でない")
            else:
                # 誤判定: 構造化されるべきだったのに不適格判定
                scores["structure_quality"] = 2.0
        else:
            # 適格と判定: 構造の充実度をチェック
            required_fields = ["title", "context", "problem", "solution", "summary"]
            filled = sum(
                1 for f in required_fields
                if output.get(f) and len(str(output[f])) > 0
            )
            ratio = filled / len(required_fields)

            if ratio >= 1.0:
                scores["structure_quality"] = 9.0
            elif ratio >= 0.8:
                scores["structure_quality"] = 7.0
            elif ratio >= 0.6:
                scores["structure_quality"] = 5.0
                reasons.append(f"構造の充実度: {ratio:.0%}")
            else:
                scores["structure_quality"] = 3.0
                reasons.append(f"構造の充実度が低い: {ratio:.0%}")

            # タイトルキーワードのチェック
            title_kw = expected.get("expected_title_keywords", [])
            title = output.get("title", "")
            if title_kw and title:
                matched = sum(1 for kw in title_kw if kw in title)
                if matched == 0:
                    scores["structure_quality"] = max(
                        scores["structure_quality"] - 2, 1.0
                    )
                    reasons.append(f"タイトルに期待キーワードなし: {title_kw}")

        # --- abstraction_quality ---
        if actual_not_suitable:
            if not is_suitable:
                scores["abstraction_quality"] = 8.0  # 不適格判定は抽象化不要
            else:
                scores["abstraction_quality"] = 2.0
        else:
            topics = output.get("topics", [])
            tags = output.get("tags", [])
            title = output.get("title", "")

            topic_score = min(len(topics), 3) * 2  # 最大 6
            tag_score = min(len(tags), 3)  # 最大 3
            title_score = 1 if title and len(title) <= 50 else 0

            raw = topic_score + tag_score + title_score  # 最大 10
            scores["abstraction_quality"] = min(max(raw, 2.0), 10.0)

            expected_topics = expected.get("expected_topics", [])
            if expected_topics and topics:
                matched = sum(
                    1 for et in expected_topics
                    if any(et in t for t in topics)
                )
                if matched == 0:
                    reasons.append(
                        f"期待トピックスとの一致なし: {expected_topics}"
                    )

        return scores, "; ".join(reasons) if reasons else "OK"
