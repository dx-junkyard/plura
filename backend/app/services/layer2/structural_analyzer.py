"""
MINDYARD - Structural Analyzer
Layer 2: 文脈依存型・構造的理解アップデート機能

過去の会話履歴と直前の構造的理解（仮説）を踏まえ、
新しいログが「追加情報」「並列（亜種）」「訂正」「新規」のいずれかを判定し、
構造的理解を動的に更新する。

深い思考が必要なため、DEEPモデル（reasoning model）を使用。
"""
from typing import Dict, List, Optional
from enum import Enum
import re

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole


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
    ) -> Dict:
        """
        コンテキストを踏まえた構造的分析を実行

        Args:
            current_log: 今回の入力内容
            recent_history: 直近（過去3〜5件分）のログの要約リスト
            previous_hypothesis: 直前のログで導き出された「構造的課題の仮説」

        Returns:
            {
                "relationship_type": "ADDITIVE" | "PARALLEL" | "CORRECTION" | "NEW",
                "relationship_reason": str,
                "updated_structural_issue": str,
                "probing_question": str,
                "model_info": dict  # 使用したモデル情報
            }
        """
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
