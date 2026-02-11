"""
MINDYARD - Conversation Agent
Layer 1: 自然な人間らしい会話返答を生成する

ai-agent-playground-101 方式: シンプルなプロンプト + 会話履歴 → 自然な応答
ルールは最小限にし、LLM の自然な対話能力に任せる。
"""
import logging
from typing import Optional, List, Tuple, TYPE_CHECKING

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.models.raw_log import RawLog

if TYPE_CHECKING:
    from app.services.layer1.situation_router import SituationResult

logger = logging.getLogger(__name__)

# スレッド内の履歴を多めに取得（会話の流れを把握する）
CONVERSATION_HISTORY_LIMIT = 10

# ────────────────────────────────────────
# シンプルで人格ベースのシステムプロンプト
# ai-agent-playground-101 の設計思想を採用:
#   ルールを山ほど書く → 簡潔に人格を定義し、LLM の対話能力に委ねる
# ────────────────────────────────────────
_CONVERSATION_SYSTEM_PROMPT = """\
あなたは「聞き上手な友人」です。
相手が考えていることを、安心して話せる場を作ります。

会話の原則:
1. 返答は1〜2文で短く。長くても3文まで。
2. 相手の言葉を軽く受け止めてから、1つだけ自然に問いかける。
3. アドバイス・べき論・説教はしない。聞き役に徹する。
4. 「記録しました」「受け取りました」だけで終わらない。必ず会話が続く返しをする。
5. 相手が訂正したら（「違う」「関係ない」等）、素直に受け入れて別の角度から聞く。
6. 会話履歴をよく読み、前の話題や文脈を踏まえて返す。同じ質問を繰り返さない。

文体: です・ます調。親しみやすく、自然に。"""


class ConversationAgent:
    """
    会話エージェント

    シンプルなチャット方式で自然な会話を生成する。
    会話履歴（user / assistant の交互メッセージ）を送り、
    LLM の自然な対話能力に委ねる。
    """

    def __init__(self) -> None:
        self._provider: Optional[LLMProvider] = None

    def _get_provider(self) -> Optional[LLMProvider]:
        if self._provider is None:
            try:
                self._provider = llm_manager.get_client(LLMUsageRole.BALANCED)
            except Exception as e:
                logger.warning("ConversationAgent: BALANCED provider unavailable: %s", e)
        return self._provider

    async def generate_reply(
        self,
        session: AsyncSession,
        user_id: object,
        new_log: RawLog,
        situation: Optional["SituationResult"] = None,
    ) -> Optional[str]:
        """
        会話履歴と新しい発話をまとめて LLM に送り、自然な返答を得る。
        ai-agent-playground-101 方式: 履歴 + 発話 → LLM → 返答。シンプル。
        """
        provider = self._get_provider()
        if not provider:
            logger.info("ConversationAgent: no provider, skipping reply")
            return None

        history = await self._load_thread_history(
            session, user_id, new_log.id,
            thread_id=getattr(new_log, "thread_id", None),
        )
        messages = self._build_messages(new_log.content, history, situation)

        try:
            await provider.initialize()
            response = await provider.generate_text(
                messages,
                temperature=0.7,
            )
            reply = (response.content or "").strip()
            if not reply:
                return None

            # LLM が「記録しました。」だけを返した場合のフォールバック
            bare = reply.replace("。", "").replace(".", "").strip()
            if bare in ("記録しました", "受け取りました", "受領しました", "承知しました"):
                # 履歴から話題を推定して会話を続ける
                topic = self._guess_topic(new_log.content, history)
                if topic:
                    reply = f"{topic}ですね。どのあたりから考えたいですか？"
                else:
                    reply = "なるほど。もう少し聞かせてもらえますか？"

            return reply
        except Exception as e:
            logger.warning("ConversationAgent: generate_text failed: %s", e, exc_info=True)
            return None

    async def _load_thread_history(
        self,
        session: AsyncSession,
        user_id: object,
        exclude_log_id: object,
        thread_id: Optional[object] = None,
    ) -> List[Tuple[str, Optional[str]]]:
        """
        同一スレッドの会話履歴を時系列で取得する。
        各ログの (user_content, assistant_reply) のペアを返す。
        """
        q = (
            select(RawLog)
            .where(
                RawLog.user_id == user_id,
                RawLog.id != exclude_log_id,
            )
            .order_by(desc(RawLog.created_at))
            .limit(CONVERSATION_HISTORY_LIMIT)
        )
        if thread_id is not None:
            q = q.where(RawLog.thread_id == thread_id)
        result = await session.execute(q)
        logs = list(result.scalars().all())
        logs.reverse()  # 時系列順にする
        return [(log.content, log.assistant_reply) for log in logs]

    def _build_messages(
        self,
        new_content: str,
        history: List[Tuple[str, Optional[str]]],
        situation: Optional["SituationResult"] = None,
    ) -> List[dict]:
        """
        LLM に送るメッセージ配列を構築する。
        ai-agent-playground-101 方式: system + 過去のやり取り + 今回の発話。
        SituationRouter の結果はシステムプロンプトに短いヒントとして追加し、
        ユーザー発話は一切改変しない（自然さを保つため）。
        """
        # システムプロンプト
        system_prompt = _CONVERSATION_SYSTEM_PROMPT

        # 状況ヒントをシステムプロンプト末尾に追加（ユーザー発話には触れない）
        if situation and situation.situation_type != "generic":
            hint = self._situation_hint(situation)
            if hint:
                system_prompt += f"\n\n【今回の状況ヒント】\n{hint}"

        messages: List[dict] = [{"role": "system", "content": system_prompt}]

        # 会話履歴を user / assistant 交互に追加
        for user_content, assistant_reply in history:
            messages.append({"role": "user", "content": user_content})
            if assistant_reply:
                messages.append({"role": "assistant", "content": assistant_reply})

        # 今回のユーザー発話（改変しない）
        messages.append({"role": "user", "content": new_content})
        return messages

    @staticmethod
    def _situation_hint(situation: "SituationResult") -> Optional[str]:
        """
        状況に応じた短いヒント。
        ユーザー発話を改変するのではなく、システムプロンプトで LLM に気づきを与える。
        """
        st = situation.situation_type
        topic = situation.resolved_topic

        if st == "continuation":
            return f"相手は前の話題の「続き」を希望しています。履歴にある話題を踏まえて返してください。"
        elif st == "correction":
            return f"相手は直前の問いを訂正・否定しています。同じ質問を繰り返さず、別の角度から聞いてください。"
        elif st == "criticism_then_topic":
            return f"相手は批判の後に本題「{topic}」を出しています。批判は1句で受け止め、本題だけに乗ってください。"
        elif st == "topic_switch":
            return f"相手は新しい話題「{topic}」に切り替えたいようです。その話題に自然に乗ってください。"
        elif st == "vent":
            return "相手は感情を吐き出しています。共感だけして、解決策は言わないでください。"
        elif st == "same_topic_short":
            return f"相手は前の話題（{topic}）について短く言及しています。その話題を自然に続けてください。"
        return None

    @staticmethod
    def _guess_topic(
        current_content: str,
        history: List[Tuple[str, Optional[str]]],
    ) -> Optional[str]:
        """
        現在の発話や履歴から話題のキーワードを短く推定する（フォールバック用）。
        """
        import re
        # 「〇〇について」パターン
        m = re.search(r"(.{2,15})について", current_content)
        if m:
            return m.group(1)
        # 履歴の最後のユーザー発話から
        for content, _ in reversed(history):
            m = re.search(r"(.{2,15})について", content)
            if m:
                return m.group(1)
        # 短い発話ならそのまま使う
        stripped = current_content.strip()
        if 2 <= len(stripped) <= 20:
            return stripped
        return None


conversation_agent = ConversationAgent()
