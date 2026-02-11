"""
MINDYARD - Structured Tracing Logger
trace_id を自動付与する構造化ロガーと、処理の開始/終了を記録するデコレータ

ログ出力項目: timestamp, level, trace_id, module, message, metadata
"""
import functools
import time
from typing import Any, Callable, Dict, Optional

import structlog

from app.core.trace_context import get_trace_id


def get_traced_logger(module: str) -> "TracedLogger":
    """モジュール名を紐づけた TracedLogger を取得"""
    return TracedLogger(module)


class TracedLogger:
    """
    trace_id を自動注入する構造化ロガー

    structlog をラップし、全てのログ出力に trace_id と module を付与する。
    """

    def __init__(self, module: str):
        self._module = module
        self._logger = structlog.get_logger()

    def _build_event(
        self,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        event: Dict[str, Any] = {
            "trace_id": get_trace_id(),
            "module": self._module,
        }
        if metadata:
            event["metadata"] = metadata
        return event

    def info(
        self,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._logger.info(message, **self._build_event(message, metadata), **kwargs)

    def warning(
        self,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._logger.warning(message, **self._build_event(message, metadata), **kwargs)

    def error(
        self,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._logger.error(message, **self._build_event(message, metadata), **kwargs)

    def debug(
        self,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._logger.debug(message, **self._build_event(message, metadata), **kwargs)

    def exception(
        self,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """ERROR レベルでログ出力し、現在の例外のスタックトレースを含める"""
        self._logger.exception(message, **self._build_event(message, metadata), **kwargs)


def trace_execution(
    module: str,
    name: Optional[str] = None,
):
    """
    非同期関数の開始/終了を自動ログするデコレータ

    使い方:
        @trace_execution("Router", "classify")
        async def classify(self, input_text, ...):
            ...

    ログ出力:
        [INFO] [trace_id] [Router] classify started  metadata={...}
        [INFO] [trace_id] [Router] classify completed metadata={duration_ms=123, ...}
    """
    def decorator(func: Callable) -> Callable:
        operation = name or func.__name__
        traced_logger = get_traced_logger(module)

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            traced_logger.info(
                f"{operation} started",
            )
            start = time.monotonic()
            try:
                result = await func(*args, **kwargs)
                duration_ms = round((time.monotonic() - start) * 1000, 1)
                traced_logger.info(
                    f"{operation} completed",
                    metadata={"duration_ms": duration_ms},
                )
                return result
            except Exception as e:
                duration_ms = round((time.monotonic() - start) * 1000, 1)
                traced_logger.error(
                    f"{operation} failed",
                    metadata={"duration_ms": duration_ms, "error": str(e)},
                )
                raise

        return wrapper
    return decorator
