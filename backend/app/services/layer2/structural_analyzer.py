"""
PLURA - Structural Analyzer
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

    _STATE_FEEDBACK_PROMPT = """あなたはPLURAの記録パートナーです。
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

    _EMPATHY_SYSTEM_PROMPT = """あなたはPLURAの共感パートナーです。
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

        # ポジティブ感情の検出
        if self._is_positive_sentiment(current_log):
            return (
                f"「{preview}」…いい感じですね！"
                "その気持ち、大切にしてくださいね。"
            )

        return (
            f"「{preview}」…お気持ち、受け止めました。"
            "落ち着いたら、一緒に整理していきましょう。"
        )

    def _get_system_prompt(self) -> str:
        return """あなたはPLURAの構造的分析エンジンです。
ユーザーの入力を、過去の会話コンテキストを踏まえて分析し、
「構造的課題」を特定・更新していきます。

分析は以下の手順で行ってください:

## Step 0: インタラクション判定
今回の入力が以下のどれに当たるか判断してください（複数可だが主要なものを1つ選ぶ）:
- QUESTION: 具体的な情報ややり方を尋ねている（ただし、ドキュメントの要約やファイル操作を求められた場合は TASK_REQUEST として扱うこと）
- TASK_REQUEST: AIに対するタスク・作業の依頼（例：「要約して」「まとめて」「翻訳して」「ファイルを分析して」「データを整理して」など、具体的な作業の実行を求めている）
- BRAINSTORM: アイデア出し・検討・選択肢を探している
- REFLECTION: 思考整理・振り返り・自分の考えを深めたい
- CONTINUATION: 「じゃあ続きから」「続きで」「続きお願い」など、前の話題の続きを希望するだけの短い発話（新しいテーマを述べていない）
- COLLABORATIVE: 「困っていない」「一緒に考察しよう」「一緒に考えよう」など、問題枠を否定し前の話題を一緒に考えたい発話（新しいテーマの提示ではない）
- OTHER: 上記以外

**TASK_REQUEST の場合**: AIはここでタスクを実行しない。ユーザーのタスクの目的や背景を深掘りする問いを probing_question として生成する。例：「この要約はどのような場面で活用されますか？」「資料の中で特に重視したい観点はありますか？」「どの程度の粒度でまとめると使いやすいですか？」など。updated_structural_issue にはタスクのテーマ（例：「ドキュメントの要約」）を簡潔に設定する。「ファイルが見られません」「対応できません」のような謝罪文は絶対に出力しないこと。
**CONTINUATION の場合**: updated_structural_issue は直前の仮説をそのまま返す。probing_question はその話題の続きについての問いにすること。入力文を課題にしない。
**COLLABORATIVE の場合**: updated_structural_issue は直前の仮説をそのまま返す。ユーザー発言を構造的課題にしない。probing_question は前のテーマで協働を促す問いにする。
**訂正・補足（「〇〇は関係ない」「違う」）の場合**: updated_structural_issue は直前の仮説のまま。ユーザー発言を課題にしない。直前の問いを繰り返さず、別の切り口で probing_question を作る（例: 「人物は関係ない」→ 登場人物を聞かず「テーマや状況の観点から、どこから深めますか？」）。

## Step 1: 関係性判定 (Relationship Classification)
今回の入力は、直前の仮説に対してどのような関係にあるか判定してください。

- ADDITIVE (深化): 同じ構造的課題に対する追加情報・詳細を提供している
- PARALLEL (並列・亜種): 同じカテゴリの課題だが、別の事例・側面を示している
  例: Aさんとのトラブル → Bさんとも同様のトラブル
- CORRECTION (訂正): 以前の仮説が間違っていた、あるいは状況が変化したことを示唆
- NEW (新規): 全く新しいトピック、以前の議論と無関係

## Step 2: 構造的理解の統合・更新 (Update Understanding)
判定結果に基づき、「現在の構造的課題（Current Structural Issue）」を書き換えてください。

- 重要: ユーザーが「聞き方・質問がおかしい」「変だ」などと批判している場合、または「〇〇について考察したい」と話題を指定している場合は、批判文やメタ発言そのものではなく、「ユーザーがこれから扱いたいテーマ」だけを構造的課題として抽出する。例: 「その聞き方おかしいな。ブランド力について考察しよう」→ 課題は「ブランド力についての考察」であり、「その聞き方おかしいな」は課題に含めない。
- ADDITIVEの場合: より詳細・具体的な課題定義に更新
- PARALLELの場合: 個別の事象を包含する、より抽象度の高い課題名に更新
  例：「A課長の承認フロー」→「組織全体の権限委譲の欠如」
- CORRECTIONの場合: 新しい情報に基づいて課題を再定義
- NEWの場合: 新しい構造的課題を定義（ユーザーが話題にしたいテーマを短いフレーズで）

## Step 3: 構造的な問いの生成
更新された理解に基づき、ユーザーの思考を**構造的に深める**問いを1つ作成してください。
**会話相手（チャットボット）が既に表面的な返答をしているため、ここではより深い分析的な問いを出す。**

### この問いの役割（会話返答との差別化）
- 会話返答は「共感・受け止め」を担当する。
- ここで出す問いは「思考の構造化・深掘り・パターン発見」を担当する。
- したがって「どんな分野に興味がありますか？」のような**表面的な質問は絶対に出さない**。

### 問いの品質基準
1. **具体的な切り口を含む**: テーマに関連する具体的な概念・フレームワーク・対比軸を提示する
2. **思考を構造化する**: 「なぜ」「どの条件で」「何と比較して」など、分析の軸を示す
3. **ユーザーが自分でも気づいていない論点を提示する**: 表面に出ていない前提や暗黙の仮定を引き出す

### 感情方向性への配慮（質問の出し分け）
- **パターンA（課題・悩み・ネガティブ）**: 「ボトルネックはどこですか？」「まず何から着手しますか？」「根本原因は人・仕組み・環境のどれに近いですか？」のように、解決の入口を探る問いにする。「うまくいった要因は？」は絶対に聞かない。
- **パターンB（成果・報告・ポジティブ）**: 「うまくいった要因は何ですか？」「再現性はありますか？」「同じやり方で他のケースにも使えそうですか？」のように、成功の分析や拡張に踏み込む。「ボトルネックは？」は絶対に聞かない。
- **中立**: 事実の背後にある意思決定や優先順位の構造に踏み込む。

### 良い問いと悪い問いの例

悪い例（汎用テンプレート — 禁止）:
  「発電のどの側面について特に研究を進めたいと考えていますか？」
  「〇〇について、今いちばん知りたいことはどこですか？」

良い例（構造的な問い）:
  「発電の研究で、今いちばんブレイクスルーが必要だと感じているのは、効率の壁ですか？それともコストやインフラの制約ですか？」
  「その課題は、技術的なボトルネックと組織的なボトルネック、どちらの比重が大きいですか？」
  「もし制約が一つだけ外せるとしたら、何を外しますか？」

### その他ルール
- ユーザーの発言全文をそのまま問いに埋め込まない。
- 同じ話題が続いているとき、前回と同じ形式の問いを繰り返さず、別の分析軸から切り込む。
- 訂正・補足があったら、その要素を避けて別の切り口で問う。
- 決まり文句を避け、テーマ固有の具体的な言葉を使う。

必ず以下のJSON形式で応答してください:
{
    "relationship_type": "ADDITIVE" | "PARALLEL" | "CORRECTION" | "NEW",
    "relationship_reason": "判定理由の説明",
    "updated_structural_issue": "更新された構造的課題の定義",
    "probing_question": "TASK_REQUESTの場合はタスクの目的・背景を深掘りする問い。QUESTIONの場合はできる限り具体的な回答、もしくは3つ以内の調査手順（ただしドキュメントの要約やファイル操作を求められた場合はQUESTIONではなくTASK_REQUESTとして扱い、活用目的を問うこと）。その他の場合は感情方向性に適した問い。"
}

重要: 「問い」を作る際は次を守ってください。
- updated_structural_issue には「ユーザーが今扱いたいテーマ」だけを入れる。批判・メタ発言（「おかしい」「〇〇しよう」の前の文など）は入れない。
- probing_question は、そのテーマについての深掘り問いにする。ユーザー発言全文を「〇〇について知りたいことは？」の〇〇にしない。
- 同じ話題が続いているとき（ADDITIVEで課題が前回とほぼ同じ）は、同じ長いテンプレ問いを繰り返さず、短い自然な問いにする。
- ユーザーが「〇〇は関係ない」と訂正したら、その要素（例: 登場人物）を聞く問いは繰り返さず、別の切り口（テーマ・状況など）で問う。
- 決まり文句を避け、テーマに関連する言葉を1つ以上含める。
- 指示語だけにせず、何についての問い/回答かを明示する。
- 共感的で圧迫感のないトーンにする。
- ユーザーがポジティブなのに問題を探さない。ネガティブなのに無理に明るくしない。
- TASK_REQUESTの場合: タスクを実行せず、タスクの活用目的・背景・重視する観点を問う。「ファイルが見られません」「対応できません」等の謝罪は絶対に出力しない。
- QUESTIONの場合: まず簡潔に答えられる範囲で答える。確信が持てないときは「今すぐできる調べ方」を2〜3個、具体的キーワード付きで提案する。ただし、ドキュメントの要約・ファイル操作・翻訳など作業実行を求められた場合はTASK_REQUESTと同様に活用目的を問うこと。
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

    # タスク依頼キーワード（要約・翻訳・ファイル操作など）
    _TASK_REQUEST_KEYWORDS = [
        "要約", "まとめて", "サマリー", "概要", "翻訳", "変換",
        "分析して", "整理して", "ファイル", "ドキュメント",
        "データを", "CSV", "PDF", "資料を",
    ]

    def _is_task_request(self, text: str) -> bool:
        """タスク・作業依頼かどうかを簡易判定"""
        return any(kw in text for kw in self._TASK_REQUEST_KEYWORDS)

    def _is_question(self, text: str) -> bool:
        """簡易的に質問かどうかを判定"""
        text = text.strip()
        if not text:
            return False
        question_mark = "?" in text or "？" in text
        question_words = ["何", "なに", "どう", "どのよう", "なぜ", "教えて", "方法", "手順", "とは", "仕組み", "使い方"]
        has_word = any(w in text for w in question_words)
        return question_mark or has_word

    # ポジティブ感情キーワード（フォールバック分析用）
    _POSITIVE_KEYWORDS = [
        "嬉しい", "楽しい", "良い", "いい", "最高", "素晴らしい",
        "できた", "成功", "達成", "うまくいった", "良かった",
        "気持ちいい", "スッキリ", "いい感じ", "頑張った", "天気",
    ]

    def _is_positive_sentiment(self, text: str) -> bool:
        """ポジティブな感情かどうかを簡易判定"""
        negative_keywords = ["困", "大変", "うまくいかない", "最悪", "つらい", "ひどい", "嫌", "不安", "疲れ"]
        has_negative = any(kw in text for kw in negative_keywords)
        has_positive = any(kw in text for kw in self._POSITIVE_KEYWORDS)
        return has_positive and not has_negative

    def _fallback_analyze(
        self,
        current_log: str,
        previous_hypothesis: Optional[str],
    ) -> Dict:
        """LLMが利用できない場合のフォールバック"""
        # 「続きから」「続きで」等のときは前の課題をそのまま使い、その話題で問いを立てる
        if self._is_continuation_phrase(current_log) and previous_hypothesis:
            return {
                "relationship_type": RelationshipType.ADDITIVE.value,
                "relationship_reason": "続きを希望する発話のため、前の話題を維持",
                "updated_structural_issue": previous_hypothesis,
                "probing_question": f"「{previous_hypothesis}」の続きですね。どこから話しますか？",
            }

        # 「困っていない、一緒に考察しよう」等 → 前の話題を維持し、一緒に考える問いにする（発話を課題にしない）
        if self._is_collaborative_or_rejecting_problem(current_log) and previous_hypothesis:
            return {
                "relationship_type": RelationshipType.ADDITIVE.value,
                "relationship_reason": "一緒に考察したい旨のため、前の話題を維持",
                "updated_structural_issue": previous_hypothesis,
                "probing_question": f"では「{previous_hypothesis}」について、一緒に考えていきましょう。どこから深めますか？",
            }

        # 「人物は関係ない」等の訂正 → 前の話題を維持し、登場人物を聞かない問いに変える
        if self._is_correction_or_clarification(current_log) and previous_hypothesis:
            return {
                "relationship_type": RelationshipType.ADDITIVE.value,
                "relationship_reason": "訂正・補足のため前の話題を維持し、問いの角度を変える",
                "updated_structural_issue": previous_hypothesis,
                "probing_question": f"では「{previous_hypothesis}」について、テーマや状況の観点から、どこから深めますか？",
            }

        # タスク依頼（要約・翻訳・ファイル操作等）→ 目的・背景を深掘りする問いを返す
        if self._is_task_request(current_log):
            simple_issue = self._extract_simple_issue(current_log)
            return {
                "relationship_type": RelationshipType.NEW.value,
                "relationship_reason": "タスク依頼のため、目的・背景を深掘りする問いを生成",
                "updated_structural_issue": simple_issue,
                "probing_question": f"「{simple_issue}」について、この作業はどのような場面で活用されますか？特に重視したい観点があれば教えてください。",
            }

        is_q = self._is_question(current_log)
        is_positive = self._is_positive_sentiment(current_log)

        if not previous_hypothesis:
            # 初回の場合は NEW
            simple_issue = self._extract_simple_issue(current_log)
            if is_positive:
                probing = f"「{simple_issue}」がうまくいった要因は何だと思いますか？再現できそうですか？"
            elif is_q:
                probing = f"今すぐできる調べ方:\n1) 公式/信頼できるドキュメントで「{simple_issue}」を検索\n2) 事例ブログで『{simple_issue} とは』『{simple_issue} 仕組み』を調べる\n3) わかったことを一文でまとめてから次の疑問を洗い出す"
            else:
                probing = f"「{simple_issue}」で、今いちばんブレイクスルーが必要だと感じているのはどこですか？技術的な壁？それとも別の制約？"
            return {
                "relationship_type": RelationshipType.NEW.value,
                "relationship_reason": "初回の入力のため新規トピックとして扱う",
                "updated_structural_issue": simple_issue,
                "probing_question": probing,
            }

        # 簡単なキーワードマッチング
        parallel_keywords = ["同じよう", "他にも", "別の", "も同様", "も起きている", "B課", "Bさん", "Cさん"]
        correction_keywords = ["違った", "間違い", "実は", "訂正", "変わった", "勘違い"]

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

        # デフォルトは ADDITIVE（感情方向性を考慮 + 同一話題の繰り返し回避）
        simple_issue = self._extract_simple_issue(current_log)
        topic = previous_hypothesis or simple_issue
        # 同じ話題の短い言及のときは、長いテンプレを繰り返さず短い問いにする
        same_topic = previous_hypothesis and (
            simple_issue in previous_hypothesis or previous_hypothesis in simple_issue
            or (len(simple_issue) <= 20 and any(w in previous_hypothesis for w in simple_issue.split()))
        )

        if is_positive:
            probing = f"「{topic}」がうまくいっている要因を分解すると、何が一番効いていますか？"
        elif same_topic and not is_q:
            probing = f"「{topic}」を別の角度から見ると、一番見落としがちな論点は何でしょう？"
        elif is_q:
            probing = f"今わかっていることを一文でまとめるとどうなりますか？まだ検証できていない仮説があれば、それも一緒に。"
        else:
            probing = f"「{topic}」の根っこにある構造的な原因は何だと思いますか？人の問題？仕組みの問題？環境の問題？"

        return {
            "relationship_type": RelationshipType.ADDITIVE.value,
            "relationship_reason": "前回の話題に関連する追加情報と判断",
            "updated_structural_issue": topic,
            "probing_question": probing,
        }

    def _is_continuation_phrase(self, text: str) -> bool:
        """「続きから」「続きで」「続ける」「続けて」など、前の話題の続きを希望する短い発話かどうか。"""
        t = text.replace("\n", " ").strip()
        if not t or len(t) > 50:
            return False
        continuations = (
            "続きから", "続きで", "続きを", "続きお願い", "続き", "つづきから", "つづきで",
            "じゃあ続きから", "じゃあ続き", "では続き", "それでは続き", "続きからお願い",
            "続ける", "続けて", "つづける", "つづけて",
        )
        if t in ("続き", "つづき", "続ける", "続けて", "つづける", "つづけて"):
            return True
        return any(c in t for c in continuations)

    def _is_collaborative_or_rejecting_problem(self, text: str) -> bool:
        """「困っていない」「一緒に考察しよう」など、問題枠を否定して前の話題を一緒に考えたい発話。"""
        t = (text or "").replace("\n", " ").strip()
        if not t or len(t) > 80:
            return False
        phrases = (
            "困っていない", "困ってない", "一緒に考察", "一緒に考え", "一緒に話そう", "一緒に話し",
            "考察しよう", "考えよう", "考えていこう", "深めよう",
        )
        return any(p in t for p in phrases)

    def _is_correction_or_clarification(self, text: str) -> bool:
        """「〇〇は関係ない」「違う」「そうじゃない」など、直前の問いへの訂正・補足。"""
        t = (text or "").replace("\n", " ").strip()
        if not t or len(t) > 100:
            return False
        phrases = (
            "関係ない", "関係なく", "そうじゃない", "そうではない", "違う", "ちがう",
            "人物は関係", "状況は関係", "それは関係",
        )
        return any(p in t for p in phrases)

    def _extract_simple_issue(self, content: str) -> str:
        """コンテンツからシンプルな課題（テーマ）を抽出。批判・メタ発言は除き、話題部分を優先する。"""
        text = content.replace("\n", " ").strip()
        # 冒頭が批判・メタ発言っぽい場合（「その〜」「この〜」で短い文の後、句点で区切られている）は後ろをテーマとする
        if "。" in text:
            first, rest = text.split("。", 1)
            rest = rest.strip()
            if rest and len(first) <= 30 and (first.startswith(("その", "この", "あの", "その聞き", "その質問")) or "おかしい" in first or "変だ" in first):
                text = rest
        issue = text[:50].strip()
        if len(text) > 50:
            issue += "..."
        return issue or content[:30]


# シングルトンインスタンス
structural_analyzer = StructuralAnalyzer()


def is_continuation_phrase(text: str) -> bool:
    """「続きから」「続きで」など、前の話題の続きを希望する発話かどうか（ワーカー等から利用）"""
    return structural_analyzer._is_continuation_phrase(text)
