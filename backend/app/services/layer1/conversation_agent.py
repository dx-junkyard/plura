"""
MINDYARD - Conversation Agent (DEPRECATED)
Layer 1: 自然な人間らしい会話返答を生成する

⚠️ DEPRECATED: このモジュールは LangGraph 統合により非推奨です。
新しい会話生成は conversation_graph.py + 各ノード (nodes/) が担当します。
コンテキスト読み込みユーティリティは conversation_context.py に移設済み。

このファイルはフォールバック用途として残していますが、
新規開発では conversation_graph.run_conversation() を使用してください。
"""
import logging
from typing import Optional, List, Tuple, Dict, TYPE_CHECKING

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.models.raw_log import RawLog
from app.models.user import User
from app.services.layer3.knowledge_store import knowledge_store
from app.services.layer1.user_profiler import user_profiler

if TYPE_CHECKING:
    from app.services.layer1.situation_router import SituationResult

logger = logging.getLogger(__name__)

# スレッド内の履歴を多めに取得（会話の流れを把握する）
CONVERSATION_HISTORY_LIMIT = 10

# ════════════════════════════════════════
# Talk モード: 思考パートナー（対話・共感・整理）
# ════════════════════════════════════════
_TALK_SYSTEM_PROMPT = """\
あなたは知的好奇心旺盛な「思考パートナー」です。
相手の話に真剣に向き合い、自分の知識も活かしながら対話します。

## 応答の核心ルール
0. **共感フェーズ必須**: 悩み・課題・困難の話題では、回答の冒頭に必ず共感を入れる。
   「それは難しい問題ですよね」「多くの人がそこで躓きます」「お気持ちわかります」等。
   すぐに解決策や手順に入らず、まず気持ちを受け止める。
1. 相手の発言の「核」を正確に捉え、**具体的な言葉やキーワード**で応答する。
2. 自分の知識を惜しまず使い、相手が言及した分野の**具体的な概念・事例・最新動向**に触れる。
3. 返答は2〜3文。「受け止め＋洞察 or 具体的な切り口の提示」の構成にする。
4. 相手の思考を**一歩先に進める何か**を必ず含める（新しい視点、関連する論点、具体例）。
5. 会話履歴を踏まえ、文脈を発展させる。同じ質問を繰り返さない。
6. 感情的な話題では共感を最優先し、分析モードに入らない。

## 絶対禁止（これをやると低品質になる）
- 「どのような分野に興味がありますか？」「どの側面を〜」のような**汎用テンプレート質問**
- 相手の発言をオウム返しして「〜なんですね！」とだけ返す
- 具体性ゼロの抽象的な返答（「面白いですね」「興味深いですね」で止まる）
- 「〜について教えてください」と丸投げする質問

## 良い応答と悪い応答の具体例

悪い例:
  入力「発電について研究している」
  →「発電の研究をされているんですね！どのような分野に興味がありますか？」
  （汎用質問。誰でも言える。知識ゼロの応答）

良い例:
  入力「発電について研究している」
  →「発電の研究ですか。今は脱炭素の流れでペロブスカイト太陽電池やSMR（小型モジュール炉）、洋上風力あたりが注目されていますが、どのあたりのテーマですか？」
  （具体的な技術名を挙げ、相手が答えやすい選択肢を示している）

悪い例:
  入力「チームの雰囲気が悪い」
  →「それは大変ですね。どんな状況ですか？」

良い例:
  入力「チームの雰囲気が悪い」
  →「それは気になりますね。何か特定のきっかけがあったのか、それとも徐々にそうなっていった感じですか？」
  （二択を提示して答えやすくしている。共感しつつ具体化を促す）

悪い例:
  入力「新しいプロジェクトを任された」
  →「新しいプロジェクトですね！どんなプロジェクトですか？」

良い例:
  入力「新しいプロジェクトを任された」
  →「おめでとうございます。任されるということは期待の表れですね。今の段階で一番気になっているのは、技術的な部分ですか？それともチーム編成や進め方の部分ですか？」

## みんなの知恵（チームの過去の知見）が提供された場合
- システムメッセージに【みんなの知恵】セクションが含まれることがある。
- その場合、会話の流れに自然に溶け込む形で**さりげなく言及**する。
- 「似た経験をした方がいて〜」「チーム内でこんな知見があるのですが〜」のように、
  押し付けず、会話の中で自然に共有する。具体的な内容（解決策やポイント）を含めること。
- 関連度が低い場合や会話の流れに合わない場合は無理に言及しない。
- 「誰が」とは言わない（匿名）。

## ユーザー理解（プロファイル）が提供された場合
- 【ユーザー理解】セクションには、このユーザーの最近の傾向が書かれている。
- これは**暗黙的に活かす**ものであり、直接言及してはならない。
  ×「プロファイルを見ると疲れているようですね」
  ○ ストレスが多そうなら自然に気遣い、まず聞く姿勢を見せる
  ○ 特定トピックで悩んでいる傾向があるなら、そこを具体的に掘り下げる
- カウンセラー的に「言外のサイン」を汲み取り、安心して話せる空気を作る。

## 文体
です・ます調。知的で親しみやすく、対等な立場で。"""


# ════════════════════════════════════════
# Do モード: 実行パートナー（結論→手順→コード→罠）
# ════════════════════════════════════════
_DO_SYSTEM_PROMPT = """\
あなたは優秀な「実行パートナー」です。
相手が求めているのは共感ではなく**具体的な成果物**です。
会話履歴の文脈を踏まえ、即座に実行可能な回答を出してください。

## 応答フォーマット（必ずこの順序で）

**1. 結論（1〜2行）**
何をすべきか / 答えは何か を最初に明示。

**2. 手順（番号付き）**
すぐ実行できるステップを具体的に。抽象的な「検討する」は禁止。

**3. すぐ動く最小コード or コマンド**（該当する場合）
コピペで動くものを出す。「イメージとしては〜」のような曖昧な擬似コードは禁止。
技術的な話でない場合はこのセクションを省略してよい。

**4. 失敗しがちな罠と確認方法**
初心者がハマりやすいポイントを1〜2個。
「〜に注意してください」ではなく「〜を確認: コマンド/チェック方法」の形で。

## 核心ルール
1. **聞き返し禁止**: 会話履歴に十分な情報があるなら、聞き返さず即答する。
2. **結論ファースト**: 前置き（「いいですね！」「了解です！」等）は1文以内。すぐ本題に入る。
3. **具体性100%**: 技術名・ツール名・バージョン・コマンドは省略せず書く。
4. 会話履歴に計画・設計・仕様があるなら、それを**そのまま活かして**回答する。
   勝手に別の方針に変えない。
5. 情報が足りないときだけ、「AとBどちらにしますか？」のように**選択肢付き**で1回だけ聞く。

## 絶対禁止
- 「何を作成しますか？」「もう少し教えてください」（履歴に情報があるのに聞く）
- 「〜は重要ですね」「〜を検討しましょう」だけで手を動かさない
- 共感だけの応答（「素晴らしい計画ですね！」で終わる）
- 抽象的なアドバイス（「テストを書きましょう」→ 具体的なテストコードを出す）

## 良い応答と悪い応答の具体例

悪い例:
  履歴「Next.js + Supabase でSNSを作る計画を立てた」
  入力「作成せよ」
  →「具体的に何を作成しますか？」
  （履歴に全部書いてある。聞き返しは最悪の応答）

良い例:
  履歴「Next.js + Supabase でSNSを作る計画を立てた」
  入力「作成せよ」
  →「了解。まず最小構成で動かします。

  1. プロジェクト作成
  ```
  npx create-next-app@latest agent-sns --ts --tailwind --app
  cd agent-sns && npm i @supabase/supabase-js
  ```

  2. Supabase テーブル作成（SQL）
  ```sql
  create table profiles ( ... );
  create table posts ( ... );
  ```

  ⚠️ 罠: Supabase の RLS を忘れると全データ公開になる。
  確認: Supabase ダッシュボード → Authentication → Policies で各テーブルにポリシーがあるか確認。」

## みんなの知恵（チームの過去の知見）が提供された場合
- システムメッセージに【みんなの知恵】セクションが含まれることがある。
- その場合、回答の手順やコード例に**チームの実績として具体的に組み込む**。
- 「チーム内で以前〜で成功した実績があります」のように根拠として使う。
- 知見の解決策やポイントが使える場合は、手順の中で積極的に引用する。
- 関連度が低い場合は無理に言及しない。
- 「誰が」とは言わない（匿名）。

## ユーザー理解（プロファイル）が提供された場合
- 【ユーザー理解】セクションの情報は暗黙的に活かす。直接言及は禁止。
- ユーザーの得意分野・苦手分野に合わせて説明の深さを調整する。
- 特定トピックで繰り返し困っている場合は、根本原因に踏み込む提案をする。

## 文体
です・ます調。簡潔で的確。余計な前置き・感想は最小限に。"""


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

        Layer 3 連携: ユーザーの入力で Qdrant を検索し、
        関連インサイトがあればシステムプロンプトに注入する。
        """
        provider = self._get_provider()
        if not provider:
            logger.info("ConversationAgent: no provider, skipping reply")
            return None

        history = await self._load_thread_history(
            session, user_id, new_log.id,
            thread_id=getattr(new_log, "thread_id", None),
        )

        # ── Layer 3: みんなの知恵を検索 ──
        related_insights = await self._search_collective_wisdom(new_log.content)

        # ── プロファイル情報を取得 ──
        profile_summary = await self._get_profile_summary(session, user_id)

        messages = self._build_messages(
            new_log.content, history, situation,
            related_insights=related_insights,
            profile_summary=profile_summary,
        )

        try:
            await provider.initialize()
            response = await provider.generate_text(
                messages,
                temperature=0.7,
            )
            reply = (response.content or "").strip()
            if not reply:
                return None

            # LLM が定型文だけを返した場合のフォールバック
            bare = reply.replace("。", "").replace(".", "").replace("！", "").strip()
            low_quality_responses = {
                "記録しました", "受け取りました", "受領しました", "承知しました",
                "なるほど", "そうですか", "興味深いですね", "面白いですね",
            }
            # 「〜ですね！」で終わるだけのオウム返しも検出
            is_parrot = (
                reply.endswith("ですね！") or reply.endswith("ですね。")
            ) and len(reply) < 40 and "?" not in reply and "？" not in reply

            if bare in low_quality_responses or is_parrot:
                # 履歴から話題を推定して具体的な切り口で返す
                topic = self._guess_topic(new_log.content, history)
                if topic:
                    reply = f"{topic}について、もう少し詳しく聞かせてもらえますか？今いちばん考えているポイントは何ですか？"
                else:
                    reply = "もう少し詳しく聞かせてもらえますか？何がきっかけでそう感じたのか、気になります。"

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
        会話履歴を時系列で取得する。
        1. まず同一スレッド内の履歴を探す。
        2. スレッド内に履歴がなければ（新規スレッド）、ユーザーの
           直近ログをスレッド横断で取得する（文脈を失わないため）。
        各ログの (user_content, assistant_reply) のペアを返す。
        """
        # ── 1. 同一スレッド内の履歴 ──
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

        # ── 2. フォールバック: スレッド横断で直近ログを取得 ──
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

    def _build_messages(
        self,
        new_content: str,
        history: List[Tuple[str, Optional[str]]],
        situation: Optional["SituationResult"] = None,
        related_insights: Optional[List[Dict]] = None,
        profile_summary: Optional[str] = None,
    ) -> List[dict]:
        """
        LLM に送るメッセージ配列を構築する。
        ai-agent-playground-101 方式: system + 過去のやり取り + 今回の発話。
        SituationRouter の結果はシステムプロンプトに短いヒントとして追加し、
        ユーザー発話は一切改変しない（自然さを保つため）。

        短い発話（命令形など）+ 履歴がある場合は、直近ログの要約を
        システムプロンプトに注入して LLM が文脈を確実に把握できるようにする。

        Layer 3 連携: related_insights が渡された場合、
        「みんなの知恵」としてシステムプロンプトに注入する。
        """
        # ── Do / Talk モード切り替え ──
        is_do = situation.do_mode if situation else False
        system_prompt = _DO_SYSTEM_PROMPT if is_do else _TALK_SYSTEM_PROMPT

        # 状況ヒントをシステムプロンプト末尾に追加（ユーザー発話には触れない）
        if situation and situation.situation_type != "generic":
            hint = self._situation_hint(situation)
            if hint:
                system_prompt += f"\n\n【今回の状況ヒント】\n{hint}"

        # ── 短い発話 + 履歴あり → 直近の会話コンテキストを明示的に要約して注入 ──
        is_short_utterance = len(new_content.strip()) <= 30
        if is_short_utterance and history:
            context_summary = self._summarize_recent_context(history)
            if context_summary:
                system_prompt += (
                    f"\n\n【直近の会話コンテキスト（重要）】\n"
                    f"ユーザーの発話が短いため、直前の会話内容を以下に要約します。"
                    f"この文脈を踏まえて応答してください。"
                    f"「何についてですか？」のような聞き返しは禁止。\n\n"
                    f"{context_summary}"
                )

        # ── ユーザープロファイル注入 ──
        if profile_summary:
            system_prompt += (
                f"\n\n【ユーザー理解（プロファイル）】\n"
                f"以下はこのユーザーの過去の傾向から推定された情報です。\n"
                f"直接「プロファイルによると〜」と言及するのは禁止。\n"
                f"自然な会話の中で、この理解を暗黙的に活かしてください。\n"
                f"例: ストレスが増加傾向なら、解決策よりまず気持ちを聞く。\n"
                f"例: 特定トピックで困っている傾向があるなら、その話題で具体的なサポートを。\n\n"
                f"{profile_summary}"
            )

        # ── Layer 3: みんなの知恵を注入 ──
        if related_insights:
            wisdom_text = self._format_collective_wisdom(related_insights)
            if wisdom_text:
                system_prompt += f"\n\n{wisdom_text}"

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
    def _summarize_recent_context(
        history: List[Tuple[str, Optional[str]]],
        max_chars: int = 1500,
    ) -> Optional[str]:
        """
        直近の会話履歴から要約テキストを生成する。
        LLM を使わず、直近のユーザー発話を連結して文脈として提供する。
        長い発話は冒頭を切り出し、全体で max_chars に収める。
        """
        if not history:
            return None

        parts: List[str] = []
        total = 0
        # 新しい方から辿り、最大 max_chars 分を収集
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

    @staticmethod
    def _situation_hint(situation: "SituationResult") -> Optional[str]:
        """
        状況に応じた具体的なヒント。
        LLM が状況を正しく理解し、適切な深さの応答を生成するための手がかり。
        """
        st = situation.situation_type
        topic = situation.resolved_topic

        if st == "continuation":
            return (
                f"相手は前の話題の「続き」を希望しています。"
                f"履歴にある話題の具体的な内容を踏まえて、前回の会話を発展させてください。"
                f"「その続きですね」のような薄い返答は禁止。前回の具体的な論点に言及すること。"
            )
        elif st == "imperative":
            return (
                f"相手は「{topic}」に関して行動・実行を指示しています。"
                f"履歴に具体的な計画や内容があるはずです。それを踏まえて、"
                f"次の具体的なアクションステップを提示してください。"
                f"「何を作成しますか？」のような聞き返しは絶対に禁止。"
                f"履歴の文脈から何をすべきかは明らかなので、すぐに実行に移る返答をすること。"
            )
        elif st == "correction":
            return (
                f"相手は直前の問いを訂正・否定しています。"
                f"素直に「そうでしたか」と受け入れ、全く別の切り口（技術面↔人間面、短期↔長期、原因↔影響 など）から問いかけてください。"
            )
        elif st == "criticism_then_topic":
            return (
                f"相手は批判の後に本題「{topic}」を出しています。"
                f"批判には「なるほど」程度で、本題「{topic}」に関する具体的な知識や切り口を提示してください。"
            )
        elif st == "topic_switch":
            return (
                f"相手は新しい話題「{topic}」に切り替えたいようです。"
                f"「{topic}」に関する具体的な概念や最新の動向に触れながら、自然に話に乗ってください。"
            )
        elif st == "vent":
            return (
                "相手は感情を吐き出しています。"
                "まず気持ちを受け止めること。解決策やアドバイスは絶対に言わない。"
                "「それは辛いですね」のような薄い共感ではなく、相手の状況の具体的な部分に触れた共感を。"
            )
        elif st == "same_topic_short":
            return (
                f"相手は前の話題（{topic}）について短く言及しています。"
                f"前回の会話内容を踏まえて、まだ掘り下げていない角度から話を広げてください。"
            )
        return None

    # ════════════════════════════════════════
    # ユーザープロファイル
    # ════════════════════════════════════════

    async def _get_profile_summary(
        self,
        session: AsyncSession,
        user_id: object,
    ) -> Optional[str]:
        """
        User.profile_data からプロファイル要約テキストを取得する。
        profile_data が未構築の場合は None を返す（オンデマンド構築はしない）。
        """
        try:
            user = await session.get(User, user_id)
            if not user or not user.profile_data:
                return None
            return user_profiler.generate_context_summary(user.profile_data)
        except Exception as e:
            logger.debug("Failed to get profile summary: %s", e)
            return None

    # ════════════════════════════════════════
    # Layer 3 連携: みんなの知恵
    # ════════════════════════════════════════

    async def _search_collective_wisdom(
        self,
        user_content: str,
        limit: int = 3,
        score_threshold: float = 0.35,
    ) -> List[Dict]:
        """
        ユーザーの入力を使って Qdrant（みんなの知恵）を検索する。
        関連度が高く、かつ品質が十分なインサイトだけを返す。
        """
        # 短すぎる入力では検索しない（ノイズ回避）
        if len(user_content.strip()) < 10:
            return []

        try:
            # 品質フィルタ後に limit 個になるよう、多めに取得
            results = await knowledge_store.search_similar(
                query=user_content,
                limit=limit * 2,
                score_threshold=score_threshold,
            )

            # ── 品質フィルタ: 中身が薄いインサイトを除外 ──
            filtered = []
            for ins in results:
                summary = (ins.get("summary") or "").strip()
                solution = (ins.get("solution") or "").strip()
                title = (ins.get("title") or "").strip()

                # 要約もしくは解決策に実質的な内容がないものは除外
                if len(summary) < 20 and len(solution) < 20:
                    logger.debug(
                        "Collective wisdom: filtered out low-quality insight: %s",
                        title,
                    )
                    continue
                filtered.append(ins)
                if len(filtered) >= limit:
                    break

            if filtered:
                logger.info(
                    "Collective wisdom: found %d/%d insights (after quality filter) for: %.30s...",
                    len(filtered), len(results), user_content,
                )
            return filtered
        except Exception as e:
            logger.warning("Collective wisdom search failed: %s", e)
            return []

    @staticmethod
    def _format_collective_wisdom(insights: List[Dict]) -> Optional[str]:
        """
        検索結果を LLM のシステムプロンプトに注入する形式にフォーマットする。
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
                # 長すぎるサマリーは切り詰め
                if len(summary) > 200:
                    summary = summary[:200] + "…"
                lines.append(f"     要約: {summary}")
            if topics:
                lines.append(f"     トピック: {topics}")
            lines.append("")

        return "\n".join(lines)

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
