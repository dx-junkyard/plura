"""
MINDYARD - Conversation Context Utilities
LangGraph ノードが共通で利用するコンテキスト構築ヘルパー

ConversationAgent にあった文脈ロード・フォーマット機能を再利用可能な関数群として抽出。
各ノードはこのモジュールを通じてスレッド履歴・みんなの知恵・ユーザープロファイルを
システムプロンプトに注入する。
"""
import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.raw_log import RawLog
from app.models.user import User
from app.services.layer3.knowledge_store import knowledge_store
from app.services.layer1.user_profiler import user_profiler

logger = logging.getLogger(__name__)

# スレッド内の履歴取得上限
CONVERSATION_HISTORY_LIMIT = 10


# ════════════════════════════════════════
# コンテキスト読み込み（DB / Qdrant アクセス）
# ════════════════════════════════════════

async def load_thread_history(
    session: AsyncSession,
    user_id: object,
    exclude_log_id: object,
    thread_id: Optional[object] = None,
) -> List[Tuple[str, Optional[str]]]:
    """
    会話履歴を時系列で取得する。
    1. まず同一スレッド内の履歴を探す。
    2. スレッド内に履歴がなければ、ユーザーの直近ログをスレッド横断で取得。
    各ログの (user_content, assistant_reply) のペアを返す。
    """
    if thread_id is not None:
        q_thread = (
            select(RawLog)
            .where(
                RawLog.user_id == user_id,
                RawLog.thread_id == thread_id,
                RawLog.id != exclude_log_id,
            )
            .order_by(desc(RawLog.created_at))
            .limit(CONVERSATION_HISTORY_LIMIT)
        )
        result = await session.execute(q_thread)
        logs = list(result.scalars().all())
        if logs:
            logs.reverse()
            return [(log.content, log.assistant_reply) for log in logs]

    # フォールバック: スレッド横断で直近ログを取得
    q_global = (
        select(RawLog)
        .where(
            RawLog.user_id == user_id,
            RawLog.id != exclude_log_id,
        )
        .order_by(desc(RawLog.created_at))
        .limit(CONVERSATION_HISTORY_LIMIT)
    )
    result = await session.execute(q_global)
    logs = list(result.scalars().all())
    logs.reverse()
    return [(log.content, log.assistant_reply) for log in logs]


async def search_collective_wisdom(
    user_content: str,
    limit: int = 3,
    score_threshold: float = 0.35,
) -> List[Dict]:
    """
    ユーザーの入力を使って Qdrant（みんなの知恵）を検索する。
    関連度が高く、品質が十分なインサイトだけを返す。
    """
    if len(user_content.strip()) < 10:
        return []

    try:
        results = await knowledge_store.search_similar(
            query=user_content,
            limit=limit * 2,
            score_threshold=score_threshold,
        )

        filtered = []
        for ins in results:
            summary = (ins.get("summary") or "").strip()
            solution = (ins.get("solution") or "").strip()
            if len(summary) < 20 and len(solution) < 20:
                continue
            filtered.append(ins)
            if len(filtered) >= limit:
                break

        if filtered:
            logger.info(
                "Collective wisdom: found %d/%d insights for: %.30s...",
                len(filtered), len(results), user_content,
            )
        return filtered
    except Exception as e:
        logger.warning("Collective wisdom search failed: %s", e)
        return []


async def get_profile_summary(
    session: AsyncSession,
    user_id: object,
) -> Optional[str]:
    """User.profile_data からプロファイル要約テキストを取得する。"""
    try:
        user = await session.get(User, user_id)
        if not user or not user.profile_data:
            return None
        return user_profiler.generate_context_summary(user.profile_data)
    except Exception as e:
        logger.debug("Failed to get profile summary: %s", e)
        return None


# ════════════════════════════════════════
# プロンプト用フォーマッター
# ════════════════════════════════════════

def format_history_messages(
    history: List[Tuple[str, Optional[str]]],
) -> List[Dict[str, str]]:
    """
    スレッド履歴を LLM の messages 配列に変換する。
    user / assistant を交互に並べる。
    """
    messages: List[Dict[str, str]] = []
    for user_content, assistant_reply in history:
        messages.append({"role": "user", "content": user_content})
        if assistant_reply:
            messages.append({"role": "assistant", "content": assistant_reply})
    return messages


def format_collective_wisdom(insights: List[Dict]) -> Optional[str]:
    """
    検索結果を LLM のシステムプロンプトに注入する形式にフォーマット。
    """
    if not insights:
        return None

    lines = [
        "【みんなの知恵 — チーム内の過去の知見】",
        "以下はユーザーの話題に関連する、チーム内の匿名化された知見です。",
        "会話に自然に溶け込む形でさりげなく共有してください。",
        "押し付けず、関連する場合のみ言及すること。\n",
    ]
    for i, ins in enumerate(insights, 1):
        title = ins.get("title", "（タイトルなし）")
        summary = ins.get("summary", "")
        topics = ", ".join(ins.get("topics", []))
        score = round(ins.get("score", 0) * 100)

        lines.append(f"  {i}. 「{title}」（関連度 {score}%）")
        if summary:
            if len(summary) > 200:
                summary = summary[:200] + "…"
            lines.append(f"     要約: {summary}")
        if topics:
            lines.append(f"     トピック: {topics}")
        lines.append("")

    return "\n".join(lines)


def format_profile_section(profile_summary: str) -> str:
    """プロファイル要約をシステムプロンプト注入形式にフォーマット。"""
    return (
        "【ユーザー理解（プロファイル）】\n"
        "以下はこのユーザーの過去の傾向から推定された情報です。\n"
        "直接「プロファイルによると〜」と言及するのは禁止。\n"
        "自然な会話の中で、この理解を暗黙的に活かしてください。\n\n"
        f"{profile_summary}"
    )


def summarize_recent_context(
    history: List[Tuple[str, Optional[str]]],
    max_chars: int = 1500,
) -> Optional[str]:
    """
    直近の会話履歴から要約テキストを生成する。
    短い発話時に LLM が文脈を把握するための補助。
    """
    if not history:
        return None

    parts: List[str] = []
    total = 0
    for user_content, assistant_reply in reversed(history):
        snippet = user_content.strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "…（省略）"
        entry = f"- ユーザー: {snippet}"
        if assistant_reply:
            reply_snippet = assistant_reply.strip()
            if len(reply_snippet) > 200:
                reply_snippet = reply_snippet[:200] + "…"
            entry += f"\n  AI: {reply_snippet}"
        if total + len(entry) > max_chars:
            break
        parts.append(entry)
        total += len(entry)

    if not parts:
        return None
    parts.reverse()
    return "\n".join(parts)


def build_context_prompt_section(
    history: Optional[List[Tuple[str, Optional[str]]]] = None,
    collective_wisdom: Optional[List[Dict]] = None,
    profile_summary: Optional[str] = None,
    input_text: Optional[str] = None,
) -> str:
    """
    全コンテキストをシステムプロンプトの追加セクションとして統合する。
    各ノードは自身の専門プロンプトの末尾にこの結果を追加すればよい。
    """
    sections: List[str] = []

    # 短い発話 + 履歴ありの場合、直近コンテキスト要約を注入
    if input_text and history and len(input_text.strip()) <= 30:
        context_summary = summarize_recent_context(history)
        if context_summary:
            sections.append(
                "【直近の会話コンテキスト（重要）】\n"
                "ユーザーの発話が短いため、直前の会話内容を以下に要約します。"
                "この文脈を踏まえて応答してください。"
                "「何についてですか？」のような聞き返しは禁止。\n\n"
                f"{context_summary}"
            )

    # プロファイル
    if profile_summary:
        sections.append(format_profile_section(profile_summary))

    # みんなの知恵
    if collective_wisdom:
        wisdom_text = format_collective_wisdom(collective_wisdom)
        if wisdom_text:
            sections.append(wisdom_text)

    if not sections:
        return ""
    return "\n\n" + "\n\n".join(sections)
