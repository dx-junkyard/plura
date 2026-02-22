"""
PLURA - Celery Application
非同期タスク処理の設定

キュー設計:
  - fast_queue (layer1, layer2, celery): リアルタイム応答に影響するタスク
  - heavy_queue: LLM長文処理・バッチ処理（Policy Weaver等）
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "mindyard",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks", "app.workers.policy_tasks"],
)

# Celery設定
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5分 (fast_queue)
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

# タスクルーティング
# fast_queue: 既存のリアルタイム処理（layer1, layer2, celery キューへ）
# heavy_queue: Policy Weaver 等の重いLLM処理
celery_app.conf.task_routes = {
    # 既存タスク → fast_queue 系キュー
    "app.workers.tasks.process_log_for_insight": {"queue": "layer2"},
    "app.workers.tasks.analyze_log_context": {"queue": "layer1"},
    "app.workers.tasks.analyze_log_structure": {"queue": "layer2"},
    "app.workers.tasks.deep_research_task": {"queue": "layer1"},
    # Policy Weaver タスク → heavy_queue
    "app.workers.policy_tasks.extract_policies_task": {"queue": "heavy_queue"},
    "app.workers.policy_tasks.expire_stale_policies_task": {"queue": "heavy_queue"},
}

# heavy_queue のタスクはタイムリミットを長くする
celery_app.conf.task_annotations = {
    "app.workers.policy_tasks.extract_policies_task": {
        "time_limit": 600,  # 10分
        "soft_time_limit": 540,
    },
}

# Celery Beat スケジュール
celery_app.conf.beat_schedule = {
    "expire-stale-policies-daily": {
        "task": "app.workers.policy_tasks.expire_stale_policies_task",
        "schedule": crontab(hour=3, minute=0),  # 毎日 03:00 UTC
    },
}
