"""
MINDYARD - Privacy Sanitizer
Layer 2: 個人特定につながる情報を除去・置換するフィルター

正確性が重要なため、BALANCEDモデルを使用。
"""
import re
from typing import Dict, List, Tuple

from app.core.config import settings
from app.core.llm import LLMClient, ModelTier


class PrivacySanitizer:
    """
    Privacy Sanitizer (プライバシー・サニタイザー)

    機能:
    - PII除去: 電話番号、メールアドレス、氏名を検出しマスキング
    - 固有名詞の一般化: 特定企業名やプロジェクト名を一般的な役割名に置換

    BALANCEDモデルを使用して正確な匿名化処理を行う。
    """

    def __init__(self):
        # BALANCEDモデルを使用
        self.llm_client = LLMClient(tier=ModelTier.BALANCED) if settings.openai_api_key else None

        # 正規表現パターン
        self.patterns = {
            "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "phone_jp": r"0\d{1,4}-?\d{1,4}-?\d{3,4}",
            "phone_intl": r"\+\d{1,3}[-.\s]?\d{1,14}",
        }

        # 日本人名のパターン（姓＋さん/様/氏など）
        self.name_suffixes = ["さん", "様", "氏", "君", "ちゃん", "先生", "部長", "課長", "社長"]

    async def sanitize(self, content: str) -> Tuple[str, Dict]:
        """
        コンテンツを匿名化

        Returns:
            Tuple[sanitized_content, metadata]
            metadata には置換の記録が含まれる
        """
        sanitized = content
        replacements = []

        # Step 1: 正規表現ベースのPII除去
        sanitized, regex_replacements = self._apply_regex_patterns(sanitized)
        replacements.extend(regex_replacements)

        # Step 2: LLMベースの固有名詞一般化
        if self.client:
            sanitized, llm_replacements = await self._apply_llm_generalization(sanitized)
            replacements.extend(llm_replacements)
        else:
            # フォールバック: 名前パターンの簡易検出
            sanitized, name_replacements = self._apply_name_pattern_detection(sanitized)
            replacements.extend(name_replacements)

        metadata = {
            "original_length": len(content),
            "sanitized_length": len(sanitized),
            "replacements": replacements,
            "replacement_count": len(replacements),
        }

        return sanitized, metadata

    def _apply_regex_patterns(self, content: str) -> Tuple[str, List[Dict]]:
        """正規表現パターンによるPII除去"""
        sanitized = content
        replacements = []

        # メールアドレス
        for match in re.finditer(self.patterns["email"], sanitized):
            original = match.group()
            replacement = "[メールアドレス]"
            sanitized = sanitized.replace(original, replacement, 1)
            replacements.append({
                "type": "email",
                "original": original,
                "replacement": replacement,
            })

        # 電話番号（日本）
        for match in re.finditer(self.patterns["phone_jp"], sanitized):
            original = match.group()
            replacement = "[電話番号]"
            sanitized = sanitized.replace(original, replacement, 1)
            replacements.append({
                "type": "phone",
                "original": original,
                "replacement": replacement,
            })

        # 電話番号（国際）
        for match in re.finditer(self.patterns["phone_intl"], sanitized):
            original = match.group()
            replacement = "[電話番号]"
            sanitized = sanitized.replace(original, replacement, 1)
            replacements.append({
                "type": "phone",
                "original": original,
                "replacement": replacement,
            })

        return sanitized, replacements

    def _apply_name_pattern_detection(self, content: str) -> Tuple[str, List[Dict]]:
        """名前パターンの簡易検出"""
        sanitized = content
        replacements = []

        for suffix in self.name_suffixes:
            # 「〇〇さん」パターンを検出
            pattern = rf"([一-龯ぁ-んァ-ン]+){suffix}"
            for match in re.finditer(pattern, sanitized):
                original = match.group()
                name_part = match.group(1)
                if len(name_part) >= 1 and len(name_part) <= 4:  # 妥当な名前長
                    replacement = f"[担当者]{suffix}"
                    sanitized = sanitized.replace(original, replacement, 1)
                    replacements.append({
                        "type": "name",
                        "original": original,
                        "replacement": replacement,
                    })

        return sanitized, replacements

    async def _apply_llm_generalization(self, content: str) -> Tuple[str, List[Dict]]:
        """LLMを使った固有名詞の一般化"""
        prompt = f"""以下のテキストに含まれる個人を特定できる情報を一般化してください。

置換ルール:
- 人名 → [担当者]、[クライアント担当]、[上司] など役割で置換
- 会社名 → [クライアント企業]、[取引先] など
- プロジェクト名 → [プロジェクト]、[案件] など
- 部署名 → [部署]、[チーム] など
- 具体的な日時 → [先日]、[最近] など（必要な場合のみ）

重要: テキストの意味や文脈は保持してください。

入力テキスト:
---
{content}
---

出力形式は必ず以下のJSON形式で:
{{
    "sanitized_text": "置換後のテキスト",
    "replacements": [
        {{"type": "name", "original": "元のテキスト", "replacement": "置換後"}}
    ]
}}"""

        try:
            result = await self.llm_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "あなたはプライバシー保護の専門家です。個人情報を適切に匿名化しつつ、文脈と意味を保持してください。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                json_response=True,
            )

            return result.get("sanitized_text", content), result.get("replacements", [])

        except Exception as e:
            # エラー時は元のテキストを返す
            return content, []


# シングルトンインスタンス
privacy_sanitizer = PrivacySanitizer()
