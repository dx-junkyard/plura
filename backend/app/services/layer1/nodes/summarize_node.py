"""
PLURA - Summarize Node
ユーザーがアップロードしたドキュメントをRAGで取得し、LLMで要約するノード

フロー:
1. PrivateRAG でユーザーのドキュメントチャンクを広範囲に取得
2. チャンクをファイルごとにグループ化してコンテキストを構築
3. LLMに要約を依頼し、結果を返す

ドキュメントが見つからない場合はアップロードを促すメッセージを返す。
"""
from typing import Any, Dict, List, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger

logger = get_traced_logger("SummarizeNode")

_SYSTEM_PROMPT = """あなたはPLURAのドキュメントアシスタントです。
提供されたドキュメントの内容を、わかりやすく要約してください。

ルール:
- 提供されたドキュメントの内容のみを根拠にして要約する
- 重要なポイントを箇条書きで整理する
- 専門用語は簡潔に補足する
- 日本語で回答する
- ドキュメントが複数ある場合は、ファイルごとに分けて要約する
"""

_SUMMARIZE_PROMPT_TEMPLATE = """以下のドキュメントの内容を要約してください。

{doc_context}

---
上記のドキュメントを要約してください。重要なポイントを整理してわかりやすくまとめてください。"""

_NO_DOCUMENT_RESPONSE = (
    "要約できるドキュメントが見つかりませんでした。\n\n"
    "PDFをアップロードしてからもう一度「要約して」とお伝えください。\n"
    "アップロードはサイドバーの「ドキュメント」から行えます。"
)


def _get_provider() -> Optional[LLMProvider]:
    try:
        return llm_manager.get_client(LLMUsageRole.BALANCED)
    except Exception:
        return None


async def _retrieve_document_chunks(user_id: str) -> List[Dict]:
    """
    PrivateRAG からユーザーの最新ドキュメントのチャンクをメタデータ抽出で取得する。

    類似度検索ではなく、直近にアップロードされた READY ドキュメントのチャンクを
    Qdrant の Payload フィルタで直接取得する（limit_docs=1: 最新1ファイルのみ）。
    """
    try:
        from app.services.layer1.private_rag import private_rag

        results = await private_rag.get_recent_document_chunks(
            user_id=user_id,
            limit_docs=1,
        )
        return results
    except Exception as e:
        logger.warning(
            "Private RAG chunk retrieval failed", metadata={"error": str(e)}
        )
        return []


def _build_doc_context(chunks: List[Dict]) -> str:
    """
    チャンクリストをファイルごとにグループ化し、要約プロンプト用のコンテキスト文字列を構築する。
    """
    # ファイル名でグループ化
    grouped: Dict[str, List[Dict]] = {}
    for chunk in chunks:
        filename = chunk.get("filename", "不明なファイル")
        grouped.setdefault(filename, []).append(chunk)

    parts = []
    for filename, file_chunks in grouped.items():
        # chunk_index 順にソート
        sorted_chunks = sorted(file_chunks, key=lambda c: c.get("chunk_index", 0))
        text_parts = [c["text"] for c in sorted_chunks if c.get("text")]
        combined_text = "\n".join(text_parts)
        parts.append(f"【ファイル: {filename}】\n{combined_text}")

    return "\n\n".join(parts)


async def run_summarize_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    要約ノード: PrivateRAG からドキュメントを取得し、LLM で要約する

    1. PrivateRAG で直近の READY ドキュメントのチャンクをメタデータフィルタで取得
       （類似度検索は使用しない。limit_docs=1 で最新1ファイルのみを対象とする）
    2. チャンクをファイルごとに整理してコンテキストを構築
    3. LLM に要約を依頼
    4. ドキュメントが存在しない場合はアップロード案内を返す
    """
    input_text = state["input_text"]
    user_id = state.get("user_id", "")

    logger.info(
        "SummarizeNode started",
        metadata={"user_id": user_id, "input_preview": input_text[:80]},
    )

    # 1. PrivateRAG からドキュメントチャンクを取得
    # 意図が SUMMARIZE の場合は類似度検索を行わず、
    # 直近にアップロードされた READY ドキュメントのチャンクをメタデータフィルタで取得する。
    chunks = await _retrieve_document_chunks(user_id)

    if not chunks:
        logger.info(
            "SummarizeNode: no document chunks found",
            metadata={"user_id": user_id},
        )
        return {"response": _NO_DOCUMENT_RESPONSE}

    logger.info(
        "SummarizeNode: document chunks retrieved",
        metadata={"chunk_count": len(chunks)},
    )

    # 2. チャンクをコンテキスト文字列に変換
    doc_context = _build_doc_context(chunks)

    provider = _get_provider()
    if not provider:
        # LLM が利用できない場合、取得したテキストをそのまま返す（フォールバック）
        logger.warning("SummarizeNode: LLM provider unavailable, returning raw context")
        return {
            "response": f"ドキュメントの内容を取得しました:\n\n{doc_context[:2000]}"
        }

    # 3. LLM で要約
    try:
        await provider.initialize()
        user_message = _SUMMARIZE_PROMPT_TEMPLATE.format(doc_context=doc_context)

        logger.info(
            "SummarizeNode: calling LLM",
            metadata={"context_length": len(doc_context)},
        )
        result = await provider.generate_text(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
        )
        summary = result.content
        logger.info(
            "SummarizeNode: LLM response received",
            metadata={"response_preview": summary[:100]},
        )
        return {"response": summary}

    except Exception as e:
        logger.warning("SummarizeNode: LLM call failed", metadata={"error": str(e)})
        # フォールバック: 取得できたチャンクの先頭部分を返す
        return {
            "response": (
                "要約処理中にエラーが発生しました。\n\n"
                "取得できたドキュメントの冒頭部分:\n\n"
                f"{doc_context[:1500]}"
            )
        }
