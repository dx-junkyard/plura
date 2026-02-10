"""
MINDYARD - Context Analyzer
Layer 1: 入力された生ログを解析し、メタデータを付与する

素早いレスポンスが必要なため、FASTモデルを使用。
"""
from typing import Dict, List, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
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
        self._provider: Optional[LLMProvider] = None

    def _get_provider(self) -> Optional[LLMProvider]:
        """LLMプロバイダーを取得（遅延初期化）"""
        if self._provider is None:
            try:
                self._provider = llm_manager.get_client(LLMUsageRole.FAST)
            except Exception:
                # プロバイダーが利用できない場合はNoneを返す
                pass
        return self._provider

    async def analyze(self, content: str) -> Dict:
        """
        コンテンツを解析してメタデータを生成

        Returns:
            {
                "intent": LogIntent,
                "emotions": List[str],
                "emotion_scores": Dict[str, float],
                "topics": List[str],
                "tags": List[str],
                "metadata_analysis": Dict
            }
        """
        provider = self._get_provider()
        if not provider:
            # プロバイダーがない場合はダミー解析
            return self._fallback_analyze(content)

        prompt = self._build_analysis_prompt(content)

        try:
            await provider.initialize()
            result = await provider.generate_json(
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
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
    "intent": "log" | "vent" | "structure" | "state",
    "emotions": ["emotion1", "emotion2"],
    "emotion_scores": {"emotion1": 0.8, "emotion2": 0.5},
    "topics": ["topic1", "topic2"],
    "tags": ["Work", "Project-A", "Idea"],
    "summary": "1行要約",
    "emotional_score": 0.0
}

intent の判定基準:
- "log": 単に記録・メモしたい（事実の記述、淡々とした報告）
- "vent": 愚痴・不満を吐き出したい（感情的な表現、不満、フラストレーション）
- "structure": 整理・分析したい（「どうすれば」「なぜ」などの思考整理）
- "state": 心身の状態や短い感情の共有（「眠い」「疲れた」「気分が良い」など。分析不要な独り言）

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

tags は再利用可能な短い語を抽出し、カテゴリ（例: Work / Private）と対象（例: Project名 / 技術）を含めてください。
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
            "state": LogIntent.STATE,  # ここで正しくマッピングされます
        }
        intent = intent_map.get(intent_str, LogIntent.LOG)

        # 感情のパース
        emotions = self._normalize_emotions(result.get("emotions", ["neutral"]))
        emotion_scores = result.get("emotion_scores", {})

        # トピックのパース
        topics = self._normalize_string_list(result.get("topics", []), max_items=10)
        tags = self._normalize_tags(result.get("tags", []), topics=topics)
        summary = str(result.get("summary", "")).strip()
        emotional_score = result.get("emotional_score")
        if not isinstance(emotional_score, (int, float)):
            emotional_score = None

        return {
            "intent": intent,
            "emotions": emotions,
            "emotion_scores": emotion_scores,
            "topics": topics,
            "tags": tags,
            "metadata_analysis": {
                "summary": summary,
                "emotional_score": emotional_score,
            },
        }

    def _fallback_analyze(self, content: str) -> Dict:
        """APIがない場合のシンプルなルールベース解析"""
        # シンプルなキーワードベースの感情検出
        emotions = []
        emotion_scores = {}

        negative_keywords = ["困った", "大変", "疲れた", "うまくいかない", "最悪", "つらい"]
        positive_keywords = ["できた", "成功", "うまくいった", "嬉しい", "良かった", "気分よく"]
        anxiety_keywords = ["不安", "心配", "どうしよう", "間に合う"]
        state_keywords = ["眠い", "腹減った", "目覚めた", "気分"]

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
        # 短い文かつ状態キーワードを含む場合はSTATE
        if len(content) < 30 and any(kw in content for kw in state_keywords):
            intent = LogIntent.STATE
        elif any(kw in content for kw in ["！", "...", "なんで", "ひどい"]):
            intent = LogIntent.VENT
        elif any(kw in content for kw in ["どうすれば", "整理", "まとめ", "なぜ"]):
            intent = LogIntent.STRUCTURE
        else:
            intent = LogIntent.LOG

        topics: List[str] = []
        tags = self._fallback_tags(content)

        return {
            "intent": intent,
            "emotions": emotions,
            "emotion_scores": emotion_scores,
            "topics": topics,
            "tags": tags,
            "metadata_analysis": {
                "summary": content[:80].strip(),
                "emotional_score": None,
            },
        }

    def _normalize_string_list(self, values: object, max_items: int = 10) -> List[str]:
        if not isinstance(values, list):
            return []

        normalized: List[str] = []
        for value in values:
            if not isinstance(value, str):
                continue
            item = value.strip()
            if not item:
                continue
            if item not in normalized:
                normalized.append(item)
            if len(normalized) >= max_items:
                break
        return normalized

    def _normalize_emotions(self, values: object) -> List[str]:
        allowed = {emotion.value for emotion in EmotionTag}
        emotions = self._normalize_string_list(values, max_items=3)
        normalized = [emotion for emotion in emotions if emotion in allowed]
        return normalized or ["neutral"]

    def _normalize_tags(self, values: object, topics: List[str]) -> List[str]:
        # トピックをタグの候補に含める
        candidates = list(values) if isinstance(values, list) else []
        
        # トピックもタグとして使える場合は追加（重複排除）
        for topic in topics:
            if topic not in candidates:
                candidates.append(topic)
                
        # ルールベースのタグ付け
        fixed_tags = ["Private"] # デフォルトタグ
        
        for tag in candidates:
            if not isinstance(tag, str):
                continue
            t = tag.strip()
            if t and t not in fixed_tags:
                fixed_tags.append(t)
                
        return fixed_tags[:5]
        
    def _fallback_tags(self, content: str) -> List[str]:
        tags = ["Private"]
        if "仕事" in content or "業務" in content:
            tags.append("Work")
        if "プロジェクト" in content:
            tags.append("Project")
        return tags

# シングルトンインスタンス
context_analyzer = ContextAnalyzer()

