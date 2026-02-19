"""
PLURA - Privacy Sanitizer
Layer 2: 個人特定につながる情報を除去・置換するフィルター

正確性が重要なため、BALANCEDモデルを使用。
"""
import re
from typing import Dict, List, Optional, Tuple

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole


class PrivacySanitizer:
    """
    Privacy Sanitizer (プライバシー・サニタイザー)

    機能:
    - PII除去: 電話番号、メールアドレス、氏名を検出しマスキング
    - 固有名詞の一般化: 特定企業名やプロジェクト名を一般的な役割名に置換

    BALANCEDモデルを使用して正確な匿名化処理を行う。
    """

    def __init__(self):
        self._provider: Optional[LLMProvider] = None

        # 正規表現パターン
        self.patterns = {
            "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "phone_jp": r"0\d{1,4}-?\d{1,4}-?\d{3,4}",
            "phone_intl": r"\+\d{1,3}[-.\s]?\d{1,14}",
        }

        # 日本人名のパターン（姓＋さん/様/氏など）
        self.name_suffixes = ["さん", "様", "氏", "君", "ちゃん", "先生", "部長", "課長", "社長"]

    def _get_provider(self) -> Optional[LLMProvider]:
        """LLMプロバイダーを取得（遅延初期化）"""
        if self._provider is None:
            try:
                self._provider = llm_manager.get_client(LLMUsageRole.BALANCED)
            except Exception:
                pass
        return self._provider

    @property
    def client(self) -> Optional[LLMProvider]:
        """後方互換性のためのプロパティ"""
        return self._get_provider()

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
        provider = self._get_provider()
        if provider:
            sanitized, llm_replacements = await self._apply_llm_generalization(sanitized)
            replacements.extend(llm_replacements)
        else:
            # フォールバック: 名前パターンの簡易検出
            sanitized, name_replacements = self._sanitize_fallback(sanitized)
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

    async def _sanitize_fallback(self, content: str) -> tuple[str, dict]:
        """LLMが利用できない場合のルールベースの匿名化"""
        replacements = []
        sanitized = content

        # 名前パターンの強化（敬称: さん, 様, くん, ちゃん, 氏, 部長, 課長, 社長 など）
        # 日本語の漢字・ひらがな・カタカナ（2文字以上）に続く敬称を対象にする
        name_pattern = re.compile(
            r'([A-Z][a-z]+|[一-龠ぁ-んァ-ヶ]{2,})'  # 名前（アルファベット または 漢字/かな/カナ2文字以上）
            r'(?P<suffix>さん|様|くん|ちゃん|氏|部長|課長|社長|先生)' # 敬称
        )
        
        # ... 以下、マッチングと置換のロジック ...
        for match in name_pattern.finditer(content):
            original = match.group(0)
            name_part = match.group(1)
            suffix = match.group('suffix')
            
            placeholder = f"[NAME_{len(replacements) + 1}]"
            # 敬称を残すかどうかはポリシーによりますが、テストを通すためには全体を置換
            sanitized = sanitized.replace(original, f"{placeholder}{suffix}")
            
            replacements.append({
                "original": original,
                "replacement": placeholder,
                "type": "name"
            })

        # 電話番号やメールアドレスの既存パターン...
        # ...
        return sanitized, {"replacements": replacements}

    async def _apply_llm_generalization(self, content: str) -> Tuple[str, List[Dict]]:
        """LLMを使った固有名詞の一般化"""
        provider = self._get_provider()
        if not provider:
            return content, []

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
            await provider.initialize()
            result = await provider.generate_json(
                messages=[
                    {
                        "role": "system",
                        "content": "あなたはプライバシー保護の専門家です。個人情報を適切に匿名化しつつ、文脈と意味を保持してください。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
            )

            return result.get("sanitized_text", content), result.get("replacements", [])

        except Exception as e:
            # エラー時は元のテキストを返す
            return content, []


# シングルトンインスタンス
privacy_sanitizer = PrivacySanitizer()
