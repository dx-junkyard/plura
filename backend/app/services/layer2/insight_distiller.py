"""
MINDYARD - Insight Distiller
Layer 2: 個別の事象を汎用的な「教訓」や「パターン」に昇華させる
"""
import json
from typing import Dict, Optional

from openai import AsyncOpenAI

from app.core.config import settings


class InsightDistiller:
    """
    Insight Distiller (知見抽出・蒸留器)

    処理フロー:
    1. 要約: 長文のログから要点を抜き出す
    2. 構造化: Context / Problem / Solution/Result の形式に整形
    3. 抽象化: 具体的経験を抽象的なタイトルに変換
    """

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def distill(self, sanitized_content: str, metadata: Optional[Dict] = None) -> Dict:
        """
        匿名化済みコンテンツからインサイトを抽出

        Returns:
            {
                "title": str,
                "context": str,
                "problem": str,
                "solution": str,
                "summary": str,
                "topics": List[str],
                "tags": List[str],
            }
        """
        if not self.client:
            return self._fallback_distill(sanitized_content)

        prompt = self._build_distill_prompt(sanitized_content)

        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
            )

            result = json.loads(response.choices[0].message.content)
            return self._validate_result(result)

        except Exception as e:
            return self._fallback_distill(sanitized_content)

    def _get_system_prompt(self) -> str:
        return """あなたはMINDYARDのインサイト蒸留器です。
ユーザーの経験や気づきを、組織全体で共有可能な汎用的な知見に変換してください。

変換のポイント:
1. 具体的な状況を抽象化する（「あの会議で怒られた」→「ステークホルダーとの期待値調整の失敗事例」）
2. 個人的な感情は取り除き、事実とパターンに焦点を当てる
3. 他の人が同様の状況に直面したときに役立つ形式にする
4. 教訓やベストプラクティスとして活用できる形に整理する

必ず以下のJSON形式で応答してください:
{
    "title": "簡潔で汎用的なタイトル（30文字以内）",
    "context": "背景・状況の説明",
    "problem": "直面した課題や問題",
    "solution": "対処法や結果、学び",
    "summary": "1-2文での要約",
    "topics": ["関連トピック1", "関連トピック2"],
    "tags": ["タグ1", "タグ2", "タグ3"]
}

topics の例: プロジェクト管理、コミュニケーション、技術選定、チームビルディング
tags の例: 失敗事例、成功事例、Tips、教訓、ベストプラクティス
"""

    def _build_distill_prompt(self, content: str) -> str:
        return f"""以下の記録を、組織で共有可能なインサイトカードに変換してください:

---
{content}
---

注意:
- 既に匿名化処理済みです
- 汎用的で再利用可能な知見として構造化してください
- タイトルは他の人が検索や一覧で見つけやすいものにしてください"""

    def _validate_result(self, result: Dict) -> Dict:
        """結果の検証と正規化"""
        return {
            "title": result.get("title", "無題のインサイト")[:255],
            "context": result.get("context", ""),
            "problem": result.get("problem", ""),
            "solution": result.get("solution", ""),
            "summary": result.get("summary", result.get("title", "")),
            "topics": result.get("topics", [])[:10],
            "tags": result.get("tags", [])[:10],
        }

    def _fallback_distill(self, content: str) -> Dict:
        """LLMが利用できない場合のフォールバック"""
        # コンテンツの最初の50文字をタイトルに
        title = content[:50].replace("\n", " ").strip()
        if len(content) > 50:
            title += "..."

        return {
            "title": title,
            "context": "",
            "problem": "",
            "solution": "",
            "summary": content[:200],
            "topics": [],
            "tags": [],
        }


# シングルトンインスタンス
insight_distiller = InsightDistiller()
