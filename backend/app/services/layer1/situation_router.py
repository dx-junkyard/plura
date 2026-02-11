"""
MINDYARD - Situation Router
Layer 1: 発話をコードで分類し、会話エージェントに渡す状況を決める

LLM に全部任せず、キーワード・正規表現で判定して再現性を高める。
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class SituationResult:
    """状況分類の結果"""
    situation_type: str  # continuation, same_topic_short, topic_switch, criticism_then_topic, vent, question, generic
    resolved_topic: Optional[str] = None  # 会話で触れるべきテーマ（前の課題 or 抽出した本題）


# 続き希望の表現（「続ける」「続けて」も短いときは続き希望）
CONTINUATION_PHRASES = (
    "続きから", "続きで", "続きを", "続きお願い", "続き", "つづきから", "つづきで",
    "じゃあ続きから", "じゃあ続き", "では続き", "それでは続き", "続きからお願い",
    "続ける", "続けて", "つづける", "つづけて",
)


def _is_continuation(text: str) -> bool:
    t = text.replace("\n", " ").strip()
    if not t or len(t) > 50:
        return False
    if t in ("続き", "つづき", "続ける", "続けて", "つづける", "つづけて"):
        return True
    return any(c in t for c in CONTINUATION_PHRASES)


def _extract_topic_after_criticism(text: str) -> Optional[str]:
    """「その聞き方おかしい。ブランド力について考察しよう」→ 後ろの話題を返す"""
    text = text.replace("\n", " ").strip()
    if "。" not in text:
        return None
    first, rest = text.split("。", 1)
    rest = rest.strip()
    if not rest or len(first) > 40:
        return None
    if first.startswith(("その", "この", "あの", "その聞き", "その質問")) or "おかしい" in first or "変だ" in first:
        return rest[:80].strip()
    return None


def _is_topic_switch(text: str) -> bool:
    """「〇〇について考察したい」「〇〇を考えよう」"""
    t = text.replace("\n", " ").strip()
    if len(t) > 100:
        return False
    return bool(re.search(r"(について|を)\s*(考察|考えよう|考えたい|話そう|話したい)", t))


def _is_vent_like(text: str) -> bool:
    """愚痴・感情っぽいキーワード"""
    vent_words = ("つらい", "嫌", "イヤ", "疲れ", "大変", "不安", "怒", "悲しい", "辛い", "困った", "どうしよう")
    return any(w in text for w in vent_words)


def _is_question(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if "?" in t or "？" in t:
        return True
    q_words = ["何", "なに", "どう", "なぜ", "教えて", "方法", "手順", "とは", "使い方", "どうやって"]
    return any(w in text for w in q_words)


def _same_topic_short(current: str, previous_topic: Optional[str]) -> bool:
    """短い発話で、前の課題とトークンが重なっている"""
    if not previous_topic or len(current.strip()) > 30:
        return False
    curr = set(re.findall(r"[ぁ-んァ-ン一-龥a-zA-Z0-9]{2,}", current))
    prev = set(re.findall(r"[ぁ-んァ-ン一-龥a-zA-Z0-9]{2,}", previous_topic))
    return bool(curr & prev)


def _is_collaborative_or_rejecting_problem(text: str) -> bool:
    """「困っていない」「一緒に考察しよう」など、問題枠を否定して前の話題を一緒に考えたい発話"""
    t = text.replace("\n", " ").strip()
    if not t or len(t) > 80:
        return False
    phrases = (
        "困っていない", "困ってない", "一緒に考察", "一緒に考え", "一緒に話そう", "一緒に話し",
        "考察しよう", "考えよう", "考えていこう", "深めよう",
    )
    return any(p in t for p in phrases)


def _is_correction_or_clarification(text: str) -> bool:
    """「〇〇は関係ない」「違う」「そうじゃない」など、直前の問いへの訂正・補足"""
    t = text.replace("\n", " ").strip()
    if not t or len(t) > 100:
        return False
    phrases = (
        "関係ない", "関係なく", "そうじゃない", "そうではない", "違う", "ちがう",
        "人物は関係", "状況は関係", "それは関係",
    )
    return any(p in t for p in phrases)


class SituationRouter:
    """発話を状況タイプに分類する"""

    def classify(
        self,
        content: str,
        previous_topic: Optional[str] = None,
    ) -> SituationResult:
        """
        発話内容と前の話題から状況を分類する。
        previous_topic: 同一スレッドの直前の構造的課題（あれば）
        """
        text = (content or "").strip()

        if _is_continuation(text):
            return SituationResult(
                situation_type="continuation",
                resolved_topic=previous_topic,
            )

        # 「人物は関係ない」など直前の問いへの訂正・補足 → 受け止めて問いを変える
        if _is_correction_or_clarification(text) and previous_topic:
            return SituationResult(
                situation_type="correction",
                resolved_topic=previous_topic,
            )

        topic_after_criticism = _extract_topic_after_criticism(text)
        if topic_after_criticism is not None:
            return SituationResult(
                situation_type="criticism_then_topic",
                resolved_topic=topic_after_criticism,
            )

        if _is_topic_switch(text):
            # テーマは発話から抽出（短く）
            resolved = text[:60].strip()
            if "。" in resolved:
                resolved = resolved.split("。")[-1].strip()
            return SituationResult(
                situation_type="topic_switch",
                resolved_topic=resolved or None,
            )

        if _is_vent_like(text):
            return SituationResult(situation_type="vent", resolved_topic=None)

        if _is_question(text):
            return SituationResult(situation_type="question", resolved_topic=previous_topic)

        # 「困っていない、一緒に考察しよう」など → 前の話題のまま、一緒に考える返答にする
        if _is_collaborative_or_rejecting_problem(text) and previous_topic:
            return SituationResult(
                situation_type="same_topic_short",
                resolved_topic=previous_topic,
            )

        if _same_topic_short(text, previous_topic):
            return SituationResult(
                situation_type="same_topic_short",
                resolved_topic=previous_topic,
            )

        return SituationResult(situation_type="generic", resolved_topic=previous_topic)


situation_router = SituationRouter()
