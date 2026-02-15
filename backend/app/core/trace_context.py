"""
PLURA - Request Trace Context
contextvars を使用したリクエストスコープの trace_id 管理

リクエスト単位で一意のIDを割り当て、ログから処理フローを追跡可能にする。
"""
import uuid
from contextvars import ContextVar

# リクエストスコープで共有される trace_id
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="no-trace")


def get_trace_id() -> str:
    """現在のリクエストスコープの trace_id を取得"""
    return _trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
    """現在のリクエストスコープに trace_id を設定"""
    _trace_id_var.set(trace_id)


def generate_trace_id() -> str:
    """新しい trace_id を生成して設定し、返す"""
    trace_id = uuid.uuid4().hex[:12]
    set_trace_id(trace_id)
    return trace_id
