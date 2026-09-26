"""Background job that checks for due reminders.

Run exactly one scheduler per deployment. Under gunicorn it is started once
in the master process (see gunicorn.conf.py), never inside workers, which
is what caused duplicate emails in INC-004.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .delivery import process_due_reminders

log = logging.getLogger(__name__)


def _run(app) -> None:
    try:
        process_due_reminders(app)
    except Exception:  # keep the scheduler alive whatever happens
        log.exception("Reminder check failed")


def start_scheduler(app) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _run,
        "interval",
        seconds=app.config["SCHEDULER_INTERVAL_SECONDS"],
        args=[app],
        id="check_reminders",
        max_instances=1,  # never overlap two checks
        coalesce=True,
    )
    scheduler.start()
    log.info("Reminder scheduler started")
    return scheduler
