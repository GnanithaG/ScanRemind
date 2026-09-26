"""Gunicorn settings. Start with: gunicorn -c gunicorn.conf.py wsgi:app"""

import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
timeout = 30
accesslog = "-"
errorlog = "-"

_scheduler = None


def on_starting(server):
    """Start exactly one reminder scheduler, in the master process.

    Workers are forked from the master, but threads don't survive a fork, so
    only the master runs the scheduler, however many workers there are.
    Set RUN_SCHEDULER=false if a separate cron job runs `flask send-due`.
    """
    global _scheduler
    if os.getenv("RUN_SCHEDULER", "true").lower() in {"0", "false", "no", "off"}:
        return
    from scanremind import create_app
    from scanremind.scheduler import start_scheduler

    _scheduler = start_scheduler(create_app())


def on_exit(server):
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
