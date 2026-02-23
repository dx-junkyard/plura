"""
PLURA - Summarize Node
ユーザーがアップロードしたドキュメントをRAGで取得し、LLMで要約するノード

フロー:
1. PrivateRAG でユーザーのドキュメントチャンクを広範囲に取得
2. チャンクをファイルごとにグループ化してコンテキストを構築
3. コンテキストが短い場合は1回のLLM呼び出しで要約（Fast Path）
4. 長い場合はMap-Reduceフローで分割要約 → 統合要約を実行

ドキュメントが見つからない場合はアップロードを促すメッセージを返す。
"""
import asyncio
from typing import Any, Dict, List, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger

logger = get_traced_logger("SummarizeNode")

# Fast path threshold (characters).
# コンテキストがこの文字数以下なら Map-Reduce をスキップして1回のLLM呼び出しで要約する。
# 目安: ~8000 chars ≈ 2000 tokens (日本語では概ね1文字2〜3トークン)
_FAST_PATH_CHAR_LIMIT = 8_000

# Map フェーズでの1バッチあたりの最大文字数。
# システムプロンプト・テンプレート分のトークンを考慮して余裕を持たせる。
_BATCH_CHAR_LIMIT = 6_000

# ── Prompts ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """あなたはPLURAのドキュメントアシスタントです。
提供されたドキュメントの内容を、わかりやすく要約してください。

ルール:
- 提供されたドキュメントの内容のみを根拠にして要約する
- 重要なポイントを箇条書きで整理する
- 専門用語は簡潔に補足する
- 日本語で回答する
- ドキュメントが複数ある場合は、ファイルごとに分けて要約する
"""

_MAP_SYSTEM_PROMPT = """あなたはPLURAのドキュメントアシスタントです。
以下はドキュメント全体の一部（セクション）です。
このセクション内の重要な文脈・論理構造・キーポイントを維持したまま、簡潔な中間要約を生成してください。

ルール:
- このセクションに含まれる内容のみを根拠にする
- 重要な事実・数値・結論は必ず保持する
- ドキュメントの論理展開（AだからB、ゆえにC）を保持する
- 日本語で回答する
"""

_REDUCE_SYSTEM_PROMPT = """あなたはPLURAのドキュメントアシスタントです。
以下は、長いドキュメントを複数のセクションに分割して生成した中間要約のリストです。
これらの中間要約を統合し、ドキュメント全体の最終的な要約を生成してください。

ルール:
- 全セクションの中間要約を網羅的に統合する
- ドキュメント全体の構成・論理展開・結論を明確に示す
- 重要なポイントを箇条書きで整理する
- 重複する内容は統合・簡潔化する
- 日本語で回答する
- ドキュメントが複数ある場合は、ファイルごとに分けて要約する
"""

_SUMMARIZE_PROMPT_TEMPLATE = """以下のドキュメントの内容を要約してください。

{doc_context}

---
上記のドキュメントを要約してください。重要なポイントを整理してわかりやすくまとめてください。"""

_MAP_PROMPT_TEMPLATE = """以下はドキュメントの一部です。中間要約を生成してください。

{section_text}

---
上記のセクションの中間要約を生成してください。"""

_REDUCE_PROMPT_TEMPLATE = """以下は複数のセクションに分割して生成した中間要約です。
これらを統合して最終要約を作成してください。

{partial_summaries}

---
上記の中間要約を統合し、ドキュメント全体の最終要約を生成してください。"""

_NO_DOCUMENT_RESPONSE = (
    "要約できるドキュメントが見つかりませんでした。\n\n"
    "PDFをアップロードしてからもう一度「要約して」とお伝えください。\n"
    "アップロードはサイドバーの「ドキュメント」から行えます。"
)

# ── Helpers ───────────────────────────────────────────────────────────────────


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
    grouped: Dict[str, List[Dict]] = {}
    for chunk in chunks:
        filename = chunk.get("filename", "不明なファイル")
        grouped.setdefault(filename, []).append(chunk)

    parts = []
    for filename, file_chunks in grouped.items():
        sorted_chunks = sorted(file_chunks, key=lambda c: c.get("chunk_index", 0))
        text_parts = [c["text"] for c in sorted_chunks if c.get("text")]
        combined_text = "\n".join(text_parts)
        parts.append(f"【ファイル: {filename}】\n{combined_text}")

    return "\n\n".join(parts)


def _split_into_batches(
    doc_context: str, batch_char_limit: int = _BATCH_CHAR_LIMIT
) -> List[str]:
    """
    doc_context を `batch_char_limit` 文字以下のバッチリストに分割する。

    段落（空行区切り）を優先して分割することでドキュメントの論理構造を維持する。
    1つの段落が上限を超える場合のみ強制的に文字数で分割する。
    """
    paragraphs = doc_context.split("\n\n")
    batches: List[str] = []
    current_parts: List[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)

        # 段落自体が上限を超える場合は強制分割してから追加
        if para_len > batch_char_limit:
            if current_parts:
                batches.append("\n\n".join(current_parts))
                current_parts = []
                current_len = 0
            for i in range(0, para_len, batch_char_limit):
                batches.append(para[i : i + batch_char_limit])
            continue

        # 現在のバッチに追加するとサイズを超える場合はバッチを確定
        # +2 は連結時の "\n\n" の分
        if current_len + para_len + 2 > batch_char_limit and current_parts:
            batches.append("\n\n".join(current_parts))
            current_parts = []
            current_len = 0

        current_parts.append(para)
        current_len += para_len + 2

    if current_parts:
        batches.append("\n\n".join(current_parts))

    return batches


async def _map_summarize_batch(
    provider: LLMProvider,
    batch_text: str,
    batch_index: int,
) -> Optional[str]:
    """
    Map フェーズ: 1つのバッチに対してLLMを呼び出し、中間要約を返す。
    失敗時は None を返す（呼び出し元でフィルタリングする）。
    """
    try:
        user_message = _MAP_PROMPT_TEMPLATE.format(section_text=batch_text)
        result = await provider.generate_text(
            messages=[
                {"role": "system", "content": _MAP_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
        )
        logger.info(
            "SummarizeNode: map batch complete",
            metadata={"batch_index": batch_index, "summary_len": len(result.content)},
        )
        return result.content
    except Exception as e:
        logger.warning(
            "SummarizeNode: map batch failed",
            metadata={"batch_index": batch_index, "error": str(e)},
        )
        return None


async def _map_reduce_summarize(provider: LLMProvider, doc_context: str) -> str:
    """
    Map-Reduce 型の要約フロー:

    1. doc_context をバッチに分割
    2. 各バッチを asyncio.gather で並列にLLM呼び出し → 中間要約を生成（Map）
    3. 成功した中間要約を番号付きで結合し、再度LLMに渡して最終要約を生成（Reduce）

    Map フェーズで一部バッチが失敗しても、成功した中間要約のみで Reduce に進む。
    全バッチが失敗した場合は RuntimeError を送出する。
    """
    batches = _split_into_batches(doc_context)
    logger.info(
        "SummarizeNode: starting map-reduce",
        metadata={"batch_count": len(batches)},
    )

    # Map フェーズ: 全バッチを並列実行（return_exceptions=True で部分失敗を許容）
    map_tasks = [
        _map_summarize_batch(provider, batch, i) for i, batch in enumerate(batches)
    ]
    raw_results = await asyncio.gather(*map_tasks, return_exceptions=True)

    # 成功した中間要約のみを収集（None や例外はスキップ）
    partial_summaries: List[str] = [
        r for r in raw_results if isinstance(r, str) and r
    ]

    if not partial_summaries:
        raise RuntimeError("Map フェーズで全バッチの要約に失敗しました")

    logger.info(
        "SummarizeNode: map phase complete",
        metadata={
            "total_batches": len(batches),
            "successful_batches": len(partial_summaries),
        },
    )

    # 中間要約が1件のみの場合は Reduce をスキップ
    if len(partial_summaries) == 1:
        return partial_summaries[0]

    # Reduce フェーズ: 中間要約を統合して最終要約を生成
    numbered_summaries = "\n\n".join(
        f"【セクション {i + 1}】\n{s}" for i, s in enumerate(partial_summaries)
    )
    reduce_message = _REDUCE_PROMPT_TEMPLATE.format(
        partial_summaries=numbered_summaries
    )

    result = await provider.generate_text(
        messages=[
            {"role": "system", "content": _REDUCE_SYSTEM_PROMPT},
            {"role": "user", "content": reduce_message},
        ],
        temperature=0.3,
    )
    logger.info(
        "SummarizeNode: reduce phase complete",
        metadata={"final_summary_len": len(result.content)},
    )
    return result.content


# ── Main Node ─────────────────────────────────────────────────────────────────


async def run_summarize_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    要約ノード: PrivateRAG からドキュメントを取得し、LLM で要約する

    1. PrivateRAG で直近の READY ドキュメントのチャンクをメタデータフィルタで取得
       （類似度検索は使用しない。limit_docs=1 で最新1ファイルのみを対象とする）
    2. チャンクをファイルごとに整理してコンテキストを構築
    3. Fast Path: コンテキストが _FAST_PATH_CHAR_LIMIT 以下なら1回のLLM呼び出しで要約
    4. Map-Reduce Path: それ以上の場合はバッチ分割 → 並列中間要約 → 統合要約
    5. ドキュメントが存在しない場合はアップロード案内を返す
    """
    input_text = state["input_text"]
    user_id = state.get("user_id", "")

    logger.info(
        "SummarizeNode started",
        metadata={"user_id": user_id, "input_preview": input_text[:80]},
    )

    # 1. PrivateRAG からドキュメントチャンクを取得
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
        logger.warning("SummarizeNode: LLM provider unavailable, returning raw context")
        return {
            "response": f"ドキュメントの内容を取得しました:\n\n{doc_context[:2000]}"
        }

    try:
        await provider.initialize()
        context_len = len(doc_context)
        logger.info(
            "SummarizeNode: context ready",
            metadata={
                "context_length": context_len,
                "fast_path_limit": _FAST_PATH_CHAR_LIMIT,
            },
        )

        # 3. Fast Path: コンテキストが閾値以下なら Map-Reduce をスキップ
        if context_len <= _FAST_PATH_CHAR_LIMIT:
            logger.info("SummarizeNode: using fast path (single LLM call)")
            user_message = _SUMMARIZE_PROMPT_TEMPLATE.format(doc_context=doc_context)
            result = await provider.generate_text(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
            )
            summary = result.content
        else:
            # 4. Map-Reduce Path: 長いドキュメントを分割して並列要約 → 統合
            logger.info("SummarizeNode: using map-reduce path")
            summary = await _map_reduce_summarize(provider, doc_context)

        logger.info(
            "SummarizeNode: summarization complete",
            metadata={"response_preview": summary[:100]},
        )
        return {"response": summary}

    except Exception as e:
        logger.warning("SummarizeNode: summarization failed", metadata={"error": str(e)})
        return {
            "response": (
                "要約処理中にエラーが発生しました。\n\n"
                "取得できたドキュメントの冒頭部分:\n\n"
                f"{doc_context[:1500]}"
            )
        }
