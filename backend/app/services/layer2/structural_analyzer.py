"""
MINDYARD - Structural Analyzer
Layer 2: 文脈依存型・構造的理解アップデート機能

過去の会話履歴と直前の構造的理解（仮説）を踏まえ、
新しいログが「追加情報」「並列（亜種）」「訂正」「新規」のいずれかを判定し、
構造的理解を動的に更新する。

高感情スコア時は構造分析をスキップし共感メッセージを返す。

深い思考が必要なため、DEEPモデル（reasoning model）を使用。
"""
from typing import Dict, List, Optional
from enum import Enum
import re

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger

logger = get_traced_logger("StructuralAnalyzer")

# 感情スコアがこの閾値以上の場合、構造分析をスキップして共感モードに入る
_EMPATHY_THRESHOLD = 0.6


class RelationshipType(str, Enum):
    """
    ログの関係性タイプ
    """
    ADDITIVE = "ADDITIVE"      # 深化: 同じ構造的課題に対する追加情報・詳細
    PARALLEL = "PARALLEL"      # 並列・亜種: 同じカテゴリの課題だが、別の事例・側面
    CORRECTION = "CORRECTION"  # 訂正: 以前の仮説が間違っていた、あるいは状況が変化
    NEW = "NEW"                # 新規: 全く新しいトピック


class StructuralAnalyzer:
    """
    Structural Analyzer (構造的分析エンジン)

    機能:
    - 関係性判定: 新しいログが過去の仮説に対してどのような関係にあるか判定
    - 構造的理解の統合・更新: 判定結果に基づき構造的課題を更新
    - 問いの生成: 更新された理解に基づき深掘り質問を作成

    DEEPモデル（reasoning model）を使用して深い思考で分析を行う。
    """

    def __init__(self):
        self._provider: Optional[LLMProvider] = None

    def _get_provider(self) -> Optional[LLMProvider]:
        """LLMプロバイダーを取得（遅延初期化）"""
        if self._provider is None:
            try:
                self._provider = llm_manager.get_client(LLMUsageRole.DEEP)
            except Exception:
                pass
        return self._provider

    async def analyze(
        self,
        current_log: str,
        recent_history: Optional[List[str]] = None,
        previous_hypothesis: Optional[str] = None,
        max_emotion_score: float = 0.0,
    ) -> Dict:
        """
        コンテキストを踏まえた構造的分析を実行

        感情スコアが高い場合（>= _EMPATHY_THRESHOLD）は構造分析をスキップし、
        共感メッセージを返す。

        Args:
            current_log: 今回の入力内容
            recent_history: 直近（過去3〜5件分）のログの要約リスト
            previous_hypothesis: 直前のログで導き出された「構造的課題の仮説」
            max_emotion_score: emotion_scoresの最大値（0.0〜1.0）

        Returns:
            {
                "relationship_type": "ADDITIVE" | "PARALLEL" | "CORRECTION" | "NEW",
                "relationship_reason": str,
                "updated_structural_issue": str,
                "probing_question": str,
                "model_info": dict  # 使用したモデル情報
            }
        """
        # 高感情スコア時は共感モード: 構造分析をスキップ
        if max_emotion_score >= _EMPATHY_THRESHOLD:
            logger.info(
                "Empathy mode activated, skipping structural analysis",
                metadata={"max_emotion_score": max_emotion_score},
            )
            return await self._generate_empathy_response(
                current_log, previous_hypothesis, max_emotion_score
            )

        provider = self._get_provider()
        if not provider:
            return self._fallback_analyze(current_log, previous_hypothesis)

        prompt = self._build_analysis_prompt(
            current_log, recent_history, previous_hypothesis
        )

        try:
            await provider.initialize()
            result = await provider.generate_json(
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
            )

            validated = self._validate_result(result)
            # モデル情報を追加（UIで表示用）
            validated["model_info"] = provider.get_model_info()
            return validated

        except Exception as e:
            return self._fallback_analyze(current_log, previous_hypothesis)

    # --- 状態ログ用マイクロフィードバック ---

    _STATE_FEEDBACK_PROMPT = """あなたはMINDYARDの記録パートナーです。
ユーザーが「眠い」「疲れた」「今日は良い天気」のような短い状態・コンディションを記録しました。
分析や質問は不要です。「受け取ったこと」と「軽い共感」を1〜2文で伝えてください。

ルール:
- 40文字以内で簡潔に
- 質問しない
- アドバイスしない
- ポジティブなら一緒に喜ぶ、ネガティブなら労う
- 日本語で応答する
"""

    # 感情タグ → フォールバックメッセージのマッピング
    _STATE_FALLBACK_MAP = {
        "frustrated": "お疲れさまです。無理せず、ご自身のペースで。",
        "angry": "記録しました。少し気持ちを落ち着ける時間が取れるといいですね。",
        "achieved": "記録しました。いい調子ですね！",
        "anxious": "記録しました。少しでも気持ちが軽くなりますように。",
        "confused": "記録しました。整理したくなったら声をかけてくださいね。",
        "relieved": "記録しました。ほっとしますね。",
        "excited": "記録しました。いいエネルギーですね！",
        "neutral": "記録しました。",
    }

    _STATE_FALLBACK_DEFAULT = "記録しました。お疲れさまです。"

    async def generate_state_feedback(
        self,
        content: str,
        emotions: Optional[list] = None,
    ) -> Dict:
        """
        STATE ログ用のマイクロフィードバックを生成

        構造分析は行わず、ログ内容と感情に基づいた
        短い共感メッセージを probing_question に格納して返す。

        Args:
            content: ユーザーの入力内容
            emotions: Context Analyzer が検出した感情タグのリスト

        Returns:
            structural_analysis 互換の dict
        """
        feedback = None

        # LLMで自然なフィードバックを生成
        provider = self._get_provider()
        if provider:
            try:
                await provider.initialize()
                result = await provider.generate_text(
                    messages=[
                        {"role": "system", "content": self._STATE_FEEDBACK_PROMPT},
                        {"role": "user", "content": content},
                    ],
                    temperature=0.5,
                )
                feedback = result.content
                logger.info(
                    "State feedback generated via LLM",
                    metadata={"response_preview": feedback[:100]},
                )
            except Exception as e:
                logger.warning(
                    "State feedback LLM generation failed, using fallback",
                    metadata={"error": str(e)},
                )

        # フォールバック: 感情タグに基づくテンプレート
        if not feedback:
            primary_emotion = emotions[0] if emotions else None
            feedback = self._STATE_FALLBACK_MAP.get(
                primary_emotion, self._STATE_FALLBACK_DEFAULT
            )

        return {
            "relationship_type": RelationshipType.NEW.value,
            "relationship_reason": "状態記録（STATE）のためマイクロフィードバックを返却",
            "updated_structural_issue": "",
            "probing_question": feedback,
        }

    # --- 共感モード ---

    _EMPATHY_SYSTEM_PROMPT = """あなたはMINDYARDの共感パートナーです。
ユーザーは感情的な状態にあります。分析や質問ではなく、共感メッセージを返してください。

ルール:
- まずユーザーの気持ちを受け止める（「〜ですよね」「大変でしたね」等）
- アドバイスや分析はしない
- 「無理しなくていい」「話してくれてありがとう」のような安心感を与える
- 2〜3文で簡潔に
- 日本語で応答する
"""

    async def _generate_empathy_response(
        self,
        current_log: str,
        previous_hypothesis: Optional[str],
        max_emotion_score: float,
    ) -> Dict:
        """
        高感情スコア時の共感レスポンス生成

        LLMが利用可能ならLLMで自然な共感メッセージを生成し、
        利用不可の場合はテンプレートフォールバック。
        """
        # LLMで共感メッセージを生成
        provider = self._get_provider()
        empathy_message = None

        if provider:
            try:
                await provider.initialize()
                result = await provider.generate_text(
                    messages=[
                        {"role": "system", "content": self._EMPATHY_SYSTEM_PROMPT},
                        {"role": "user", "content": current_log},
                    ],
                    temperature=0.5,
                )
                empathy_message = result.content
                logger.info(
                    "Empathy message generated via LLM",
                    metadata={"response_preview": empathy_message[:100]},
                )
            except Exception as e:
                logger.warning(
                    "Empathy LLM generation failed, using template",
                    metadata={"error": str(e)},
                )

        # テンプレートフォールバック
        if not empathy_message:
            empathy_message = self._empathy_fallback_message(current_log)

        # 構造的課題は前回の仮説をそのまま維持（感情時に書き換えない）
        structural_issue = previous_hypothesis or self._extract_simple_issue(current_log)

        return {
            "relationship_type": RelationshipType.ADDITIVE.value,
            "relationship_reason": f"高感情スコア（{max_emotion_score:.2f}）のため共感モードで応答",
            "updated_structural_issue": structural_issue,
            "probing_question": empathy_message,
        }

    def _empathy_fallback_message(self, current_log: str) -> str:
        """テンプレートベースの共感メッセージ"""
        # ユーザーの言葉から一部を拾って共感に反映する
        preview = current_log[:30].replace("\n", " ").strip()
        if len(current_log) > 30:
            preview += "..."

        # ネガティブ感情キーワードの検出
        high_stress_keywords = ["疲れ", "辛", "つら", "しんど", "無理", "限界", "もうダメ", "嫌"]
        is_high_stress = any(kw in current_log for kw in high_stress_keywords)

        if is_high_stress:
            return (
                f"「{preview}」…大変な状況の中、話してくれてありがとうございます。"
                "無理に整理しなくても大丈夫です。まずはお気持ちをそのまま吐き出してくださいね。"
            )

        return (
            f"「{preview}」…気持ちが揺れているんですね。"
            "その感覚、大切にしてください。落ち着いたら、一緒に整理していきましょう。"
        )

    def _get_system_prompt(self) -> str:
        return """あなたはMINDYARDの構造的分析エンジンです。
ユーザーの入力を、過去の会話コンテキストを踏まえて分析し、
「構造的課題」を特定・更新していきます。

分析は以下の手順で行ってください:

## Step 0: インタラクション判定
今回の入力が以下のどれに当たるか判断してください（複数可だが主要なものを1つ選ぶ）:
- QUESTION: 具体的な情報ややり方を尋ねている
- BRAINSTORM: アイデア出し・検討・選択肢を探している
- REFLECTION: 思考整理・振り返り・自分の考えを深めたい
- OTHER: 上記以外

## Step 1: 関係性判定 (Relationship Classification)
今回の入力は、直前の仮説に対してどのような関係にあるか判定してください。

- ADDITIVE (深化): 同じ構造的課題に対する追加情報・詳細を提供している
- PARALLEL (並列・亜種): 同じカテゴリの課題だが、別の事例・側面を示している
  例: Aさんとのトラブル → Bさんとも同様のトラブル
- CORRECTION (訂正): 以前の仮説が間違っていた、あるいは状況が変化したことを示唆
- NEW (新規): 全く新しいトピック、以前の議論と無関係

## Step 2: 構造的理解の統合・更新 (Update Understanding)
判定結果に基づき、「現在の構造的課題（Current Structural Issue）」を書き換えてください。

- ADDITIVEの場合: より詳細・具体的な課題定義に更新
- PARALLELの場合: 個別の事象を包含する、より抽象度の高い課題名に更新
  例：「A課長の承認フロー」→「組織全体の権限委譲の欠如」
- CORRECTIONの場合: 新しい情報に基づいて課題を再定義
- NEWの場合: 新しい構造的課題を定義

## Step 3: 問いの生成
更新された理解に基づき、さらに深掘りするための質問を1つ作成してください。
質問は、ユーザーの思考を促し、構造的な問題をより明確にするものにしてください。

必ず以下のJSON形式で応答してください:
{
    "relationship_type": "ADDITIVE" | "PARALLEL" | "CORRECTION" | "NEW",
    "relationship_reason": "判定理由の説明",
    "updated_structural_issue": "更新された構造的課題の定義",
    "probing_question": "QUESTIONの場合はできる限り具体的な回答、もしくは3つ以内の調査手順。その他の場合は深掘りのための問い。"
}

重要: 「問い」を作る際は次を守ってください。
- 決まり文句を避け、ユーザーの言葉や話題を1つ以上含める。
- 指示語だけにせず、何についての問い/回答かを明示する。
- 共感的で圧迫感のないトーンにする。
- QUESTIONの場合: まず簡潔に答えられる範囲で答える。確信が持てないときは「今すぐできる調べ方」を2〜3個、具体的キーワード付きで提案する。
- BRAINSTORM/REFLECTIONの場合: 新しい洞察が出るように理由・背景・具体的状況を尋ねる。
"""

    def _build_analysis_prompt(
        self,
        current_log: str,
        recent_history: Optional[List[str]],
        previous_hypothesis: Optional[str],
    ) -> str:
        prompt_parts = []

        # 過去の履歴がある場合
        if recent_history and len(recent_history) > 0:
            prompt_parts.append("## 直近の会話履歴（要約）:")
            for i, history in enumerate(recent_history, 1):
                prompt_parts.append(f"{i}. {history}")
            prompt_parts.append("")

        # 前回の仮説がある場合
        if previous_hypothesis:
            prompt_parts.append("## 直前の構造的課題（仮説）:")
            prompt_parts.append(previous_hypothesis)
            prompt_parts.append("")
        else:
            prompt_parts.append("## 直前の構造的課題（仮説）:")
            prompt_parts.append("（初回の入力のため、仮説なし）")
            prompt_parts.append("")

        # 今回のログ
        prompt_parts.append("## 今回の入力:")
        prompt_parts.append("---")
        prompt_parts.append(current_log)
        prompt_parts.append("---")
        prompt_parts.append("")
        prompt_parts.append("上記を分析し、JSON形式で結果を返してください。")

        return "\n".join(prompt_parts)

    def _validate_result(self, result: Dict) -> Dict:
        """結果の検証と正規化"""
        # relationship_type の検証
        relationship_type = result.get("relationship_type", "NEW")
        if relationship_type not in [e.value for e in RelationshipType]:
            relationship_type = RelationshipType.NEW.value
        probing = result.get("probing_question") or ""
        issue = result.get("updated_structural_issue") or ""

        return {
            "relationship_type": relationship_type,
            "relationship_reason": result.get("relationship_reason", ""),
            "updated_structural_issue": issue,
            "probing_question": probing,
        }

    def _is_question(self, text: str) -> bool:
        """簡易的に質問かどうかを判定"""
        text = text.strip()
        if not text:
            return False
        question_mark = "?" in text or "？" in text
        question_words = ["何", "なに", "どう", "どのよう", "なぜ", "教えて", "方法", "手順", "とは", "仕組み", "使い方"]
        has_word = any(w in text for w in question_words)
        return question_mark or has_word

    def _fallback_analyze(
        self,
        current_log: str,
        previous_hypothesis: Optional[str],
    ) -> Dict:
        """LLMが利用できない場合のフォールバック"""
        # シンプルなルールベース分析＋質問時のガイド
        is_q = self._is_question(current_log)

        if not previous_hypothesis:
            # 初回の場合は NEW
            simple_issue = self._extract_simple_issue(current_log)
            probing = (
                f"「{simple_issue}」について、今いちばん知りたいことや困っている場面はどこですか？"
                if not is_q
                else f"今すぐできる調べ方:\n1) 公式/信頼できるドキュメントで「{simple_issue}」を検索\n2) 事例ブログで『{simple_issue} とは』『{simple_issue} 仕組み』を調べる\n3) わかったことを一文でまとめてから次の疑問を洗い出す"
            )
            return {
                "relationship_type": RelationshipType.NEW.value,
                "relationship_reason": "初回の入力のため新規トピックとして扱う",
                "updated_structural_issue": simple_issue,
                "probing_question": probing,
            }

        # 簡単なキーワードマッチング
        parallel_keywords = ["同じよう", "他にも", "別の", "も同様", "も起きている", "B課", "Bさん", "Cさん"]
        correction_keywords = ["違った", "間違い", "実は", "訂正", "変わった", "勘違い"]

        current_lower = current_log.lower()

        for kw in correction_keywords:
            if kw in current_log:
                simple_issue = self._extract_simple_issue(current_log)
                return {
                    "relationship_type": RelationshipType.CORRECTION.value,
                    "relationship_reason": f"訂正を示唆するキーワード「{kw}」が検出された",
                    "updated_structural_issue": simple_issue,
                    "probing_question": (
                        f"「{simple_issue}」になった背景やきっかけを教えてもらえますか？"
                        if not is_q
                        else f"変化のポイントをもう少し教えてください。何が変わり、どこで困っていますか？"
                    ),
                }

        for kw in parallel_keywords:
            if kw in current_log:
                expanded = f"複数の事例に共通する構造的課題（{previous_hypothesis}の拡張）" if previous_hypothesis else self._extract_simple_issue(current_log)
                return {
                    "relationship_type": RelationshipType.PARALLEL.value,
                    "relationship_reason": f"並列事例を示唆するキーワード「{kw}」が検出された",
                    "updated_structural_issue": expanded,
                    "probing_question": (
                        f"似たケースが他にもあるとのことですが、「{expanded}」で共通して困る場面は何でしょう？"
                        if not is_q
                        else f"複数ケースで共通する論点を1つ挙げるなら何ですか？それを手がかりに調べてみましょう。"
                    ),
                }

        # デフォルトは ADDITIVE
        simple_issue = self._extract_simple_issue(current_log)
        return {
            "relationship_type": RelationshipType.ADDITIVE.value,
            "relationship_reason": "前回の話題に関連する追加情報と判断",
            "updated_structural_issue": previous_hypothesis or simple_issue,
            "probing_question": (
                f"「{previous_hypothesis or simple_issue}」をもう少し具体的にするなら、どんな状況・登場人物が関わっていますか？"
                if not is_q
                else f"今わかっていることを一文でまとめるとどうなりますか？次に調べるキーワードを2つ挙げてみてください。"
            ),
        }

    def _extract_simple_issue(self, content: str) -> str:
        """コンテンツからシンプルな課題を抽出"""
        # 最初の50文字を課題として使用
        issue = content[:50].replace("\n", " ").strip()
        if len(content) > 50:
            issue += "..."
        return issue


# シングルトンインスタンス
structural_analyzer = StructuralAnalyzer()
