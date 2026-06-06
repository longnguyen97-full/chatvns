from __future__ import annotations

import os
from datetime import timedelta

from celery import Celery


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "stock_raw_data_collector",
    broker=os.getenv("CELERY_BROKER_URL", REDIS_URL),
    backend=os.getenv("CELERY_RESULT_BACKEND", REDIS_URL),
    include=["tasks"],
)

app.conf.timezone = os.getenv("CELERY_TIMEZONE", "Asia/Ho_Chi_Minh")
app.conf.enable_utc = True
app.conf.beat_schedule = {
    "crawl-and-index-default-tickers-hourly": {
        "task": "tasks.crawl_default_tickers_and_index",
        "schedule": timedelta(hours=1),
    },
    "crawl-and-index-market-news-daily": {
        "task": "tasks.crawl_market_news_and_index",
        "schedule": timedelta(days=1),
    },
}
