"""
MINDYARD - Context Analyzer
Layer 1: 入力された生ログを解析し、メタデータを付与する

素早いレスポンスが必要なため、FASTモデルを使用。
"""
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.llm import LLMClient, ModelTier
from app.models.raw_log import LogIntent, EmotionTag


class ContextAnalyzer:
    """
    Context Analyzer (文脈解析エンジン)

    機能:
    - 感情分析: テキストから感情タグを付与
    - トピック抽出: 議論されている主題を特定
    - インテント分類: ユーザーの意図を判別

    FASTモデルを使用して素早いレスポンスを提供。
    """

    def __init__(self):
        # FASTモデルを使用（素早い応答が求められるため）
        self.llm_client = LLMClient(tier=ModelTier.FAST) if settings.openai_api_key else None

    async def analyze(self, content: str) -> Dict:
        """
        コンテンツを解析してメタデータを生成

        Returns:
            {
                "intent": LogIntent,
                "emotions": List[str],
                "emotion_scores": Dict[str, float],
                "topics": List[str]
            }
        """
        if not self.llm_client:
            # OpenAI APIキーがない場合はダミー解析
            return self._fallback_analyze(content)

        prompt = self._build_analysis_prompt(content)

        try:
            result = await self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                json_response=True,
            )

            return self._parse_analysis_result(result)

        except Exception as e:
            # エラー時はフォールバック
            return self._fallback_analyze(content)

    def _get_system_prompt(self) -> str:
        return """あなたはMINDYARDの文脈解析エンジンです。
ユーザーの入力テキストを解析し、以下の情報を抽出してください。

必ず以下のJSON形式で応答してください:
{
    "intent": "log" | "vent" | "structure",
    "emotions": ["emotion1", "emotion2"],
    "emotion_scores": {"emotion1": 0.8, "emotion2": 0.5},
    "topics": ["topic1", "topic2"]
}

intent の判定基準:
- "log": 単に記録・メモしたい（事実の記述、淡々とした報告）
- "vent": 愚痴・不満を吐き出したい（感情的な表現、不満、フラストレーション）
- "structure": 整理・分析したい（「どうすれば」「なぜ」などの思考整理）

emotions の選択肢:
- frustrated (焦り)
- angry (怒り)
- achieved (達成感)
- anxious (不安)
- confused (困惑)
- relieved (安堵)
- excited (興奮)
- neutral (中立)

topics はビジネス・業務に関連するトピックを抽出してください。
例: プロジェクト管理、人事評価、技術的負債、顧客対応、チームコミュニケーションなど
"""

    def _build_analysis_prompt(self, content: str) -> str:
        return f"""以下のテキストを解析してください:

---
{content}
---

JSON形式で解析結果を返してください。"""

    def _parse_analysis_result(self, result: Dict) -> Dict:
        """LLMの解析結果をパース・正規化"""
        # インテントのパース
        intent_str = result.get("intent", "log").lower()
        intent_map = {
            "log": LogIntent.LOG,
            "vent": LogIntent.VENT,
            "structure": LogIntent.STRUCTURE,
        }
        intent = intent_map.get(intent_str, LogIntent.LOG)

        # 感情のパース
        emotions = result.get("emotions", ["neutral"])
        emotion_scores = result.get("emotion_scores", {})

        # トピックのパース
        topics = result.get("topics", [])

        return {
            "intent": intent,
            "emotions": emotions,
            "emotion_scores": emotion_scores,
            "topics": topics,
        }

    def _fallback_analyze(self, content: str) -> Dict:
        """APIがない場合のシンプルなルールベース解析"""
        # シンプルなキーワードベースの感情検出
        emotions = []
        emotion_scores = {}

        negative_keywords = ["困った", "大変", "疲れた", "うまくいかない", "最悪", "つらい"]
        positive_keywords = ["できた", "成功", "うまくいった", "嬉しい", "良かった"]
        anxiety_keywords = ["不安", "心配", "どうしよう", "間に合う"]

        content_lower = content.lower()

        for kw in negative_keywords:
            if kw in content:
                if "frustrated" not in emotions:
                    emotions.append("frustrated")
                    emotion_scores["frustrated"] = 0.7

        for kw in positive_keywords:
            if kw in content:
                if "achieved" not in emotions:
                    emotions.append("achieved")
                    emotion_scores["achieved"] = 0.7

        for kw in anxiety_keywords:
            if kw in content:
                if "anxious" not in emotions:
                    emotions.append("anxious")
                    emotion_scores["anxious"] = 0.7

        if not emotions:
            emotions = ["neutral"]
            emotion_scores["neutral"] = 0.5

        # インテント判定
        if any(kw in content for kw in ["！", "...", "なんで", "ひどい"]):
            intent = LogIntent.VENT
        elif any(kw in content for kw in ["どうすれば", "整理", "まとめ", "なぜ"]):
            intent = LogIntent.STRUCTURE
        else:
            intent = LogIntent.LOG

        return {
            "intent": intent,
            "emotions": emotions,
            "emotion_scores": emotion_scores,
            "topics": [],  # シンプル解析ではトピック抽出なし
        }


# シングルトンインスタンス
context_analyzer = ContextAnalyzer()
