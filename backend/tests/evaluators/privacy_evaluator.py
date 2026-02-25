"""
PrivacySanitizer Evaluator (Layer 2)

PII 除去の完全性、文脈維持率、匿名化後の自然さを評価する。
Privacy First の原則に基づき、PII 残存は即時フェイル（最低点）とする。

評価軸:
- pii_removal: 個人特定情報が完全に除去されているか（最重要）
- context_preservation: 匿名化後も元の文脈・意味が保持されているか
- naturalness: 匿名化後の文が自然な日本語として読めるか
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from tests.evaluators.base_evaluator import BaseEvaluator


class PrivacyEvaluator(BaseEvaluator):
    def __init__(self, pass_threshold: float = 7.0):
        super().__init__("PrivacySanitizer", pass_threshold=pass_threshold)
        self._sanitizer = None

    def _get_sanitizer(self):
        if self._sanitizer is None:
            from app.services.layer2.privacy_sanitizer import PrivacySanitizer
            self._sanitizer = PrivacySanitizer()
        return self._sanitizer

    @property
    def scoring_dimensions(self) -> List[Dict[str, str]]:
        return [
            {
                "name": "pii_removal",
                "description": (
                    "個人特定情報（氏名、電話番号、メールアドレス等）が完全に除去されているか。"
                    "1つでも残存している場合は 1 点（即時フェイル）。"
                ),
            },
            {
                "name": "context_preservation",
                "description": (
                    "匿名化後も元の文脈・業務的意味が保持されているか。"
                    "過度な削除で意味が失われていないか。"
                ),
            },
            {
                "name": "naturalness",
                "description": (
                    "匿名化後の文が自然な日本語として読めるか。"
                    "不自然な表記や壊れた文構造がないか。"
                ),
            },
        ]

    async def run_component(self, input_data: Dict) -> Dict:
        sanitizer = self._get_sanitizer()
        content = input_data["text"]
        sanitized, metadata = await sanitizer.sanitize(content)
        return {
            "sanitized_text": sanitized,
            "metadata": metadata,
            "original_text": content,
        }

    def build_judge_prompt(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> str:
        expected_replacements = expected.get("expected_replacements", [])
        replacements_str = ""
        if expected_replacements:
            items = []
            for r in expected_replacements:
                items.append(f"  - {r.get('type', '不明')}: {r.get('original', '?')}")
            replacements_str = "\n".join(items)
        else:
            replacements_str = "  指定なし"

        should_contain = expected.get("should_contain", [])
        should_not_contain = expected.get("should_not_contain", [])

        contain_section = ""
        if should_contain:
            contain_section = (
                f"- **含まれるべき表現:** {', '.join(should_contain)}\n"
            )
        if should_not_contain:
            contain_section += (
                f"- **含まれてはいけない表現:** {', '.join(should_not_contain)}\n"
            )

        return (
            f"あなたは厳格なセキュリティ監査官です。\n"
            f"以下の「元のテキスト」と「匿名化されたテキスト」を比較してください。\n\n"
            f"## 元のテキスト\n{input_data['text']}\n\n"
            f"## 匿名化後のテキスト\n{output['sanitized_text']}\n\n"
            f"## 置換メタデータ\n{output['metadata']}\n\n"
            f"## 期待される置換\n{replacements_str}\n\n"
            f"{contain_section}\n"
            f"## 評価基準\n"
            f"- 10点: すべてのPIIが完全に除去され、元の業務的・技術的な文脈が完全に保持されている\n"
            f"- 7点: PIIは除去されているが、文脈の一部が失われている\n"
            f"- 1点: 個人情報（名前、メール、社名など）が1つでも残っている（即時フェイル）\n\n"
            f"上記の匿名化結果を評価してください。"
        )

    def _rule_based_check(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> Tuple[Dict[str, float], str]:
        scores: Dict[str, float] = {}
        reasons: List[str] = []
        text = output.get("sanitized_text", "")

        # --- pii_removal ---
        # メールアドレスの残存チェック
        emails = re.findall(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text
        )
        # 電話番号の残存チェック
        phones = re.findall(r"0\d{1,4}-?\d{1,4}-?\d{3,4}", text)

        # should_not_contain のチェック
        should_not_contain = expected.get("should_not_contain", [])
        pii_remaining = []
        for item in should_not_contain:
            if item in text:
                pii_remaining.append(item)

        pii_found = len(emails) + len(phones) + len(pii_remaining)
        if pii_found == 0:
            scores["pii_removal"] = 10.0
        else:
            scores["pii_removal"] = 1.0  # 即時フェイル
            reasons.append(
                f"PII残存: emails={len(emails)}, phones={len(phones)}, "
                f"other={pii_remaining}"
            )

        # should_contain のチェック
        should_contain = expected.get("should_contain", [])
        missing_markers = [m for m in should_contain if m not in text]
        if missing_markers:
            # マーカーが欠落している場合はスコアを下げる
            if scores["pii_removal"] > 5.0:
                scores["pii_removal"] = max(
                    5.0, scores["pii_removal"] - len(missing_markers) * 2
                )
            reasons.append(f"欠落マーカー: {missing_markers}")

        # --- context_preservation ---
        original_text = input_data.get("text", "")
        original_len = max(len(original_text), 1)
        sanitized_len = len(text)
        ratio = sanitized_len / original_len

        if expected.get("pii_removed") is False:
            # PII がないはずのテキスト: ほぼそのままであるべき
            if ratio >= 0.9:
                scores["context_preservation"] = 10.0
            elif ratio >= 0.7:
                scores["context_preservation"] = 7.0
                reasons.append(f"False positive: 長さ比率 {ratio:.2f}")
            else:
                scores["context_preservation"] = 4.0
                reasons.append(f"過度な変更: 長さ比率 {ratio:.2f}")
        else:
            # PII ありのテキスト: ある程度短くなるのは許容
            if 0.5 <= ratio <= 1.5:
                scores["context_preservation"] = 8.0
            elif 0.3 <= ratio < 0.5:
                scores["context_preservation"] = 5.0
                reasons.append(f"文脈の大幅損失: 長さ比率 {ratio:.2f}")
            else:
                scores["context_preservation"] = 3.0
                reasons.append(f"異常な長さ比率: {ratio:.2f}")

        # --- naturalness ---
        # ルールベースでは簡易チェックのみ
        # 壊れたブラケットやプレースホルダーの連続をチェック
        broken_brackets = len(re.findall(r"\[\]|\]\[", text))
        double_placeholders = len(
            re.findall(r"\[.+?\]\s*\[.+?\]\s*\[.+?\]", text)
        )
        if broken_brackets == 0 and double_placeholders == 0:
            scores["naturalness"] = 8.0
        elif broken_brackets + double_placeholders <= 1:
            scores["naturalness"] = 6.0
            reasons.append("軽微な不自然さを検出")
        else:
            scores["naturalness"] = 4.0
            reasons.append(
                f"不自然な表記: broken={broken_brackets}, "
                f"double_ph={double_placeholders}"
            )

        return scores, "; ".join(reasons) if reasons else "OK"
