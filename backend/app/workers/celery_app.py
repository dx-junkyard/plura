"""
MINDYARD - Celery Application
非同期タスク処理の設定
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "mindyard",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

# Celery設定
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5分
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

# タスクルーティング
celery_app.conf.task_routes = {
    "app.workers.tasks.process_log_for_insight": {"queue": "layer2"},
    "app.workers.tasks.analyze_log_context": {"queue": "layer1"},
    "app.workers.tasks.analyze_log_structure": {"queue": "layer2"},
    "app.workers.tasks.deep_research_task": {"queue": "layer1"},
}
