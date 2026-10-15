"""In-process scheduler. Runs inside the API server so connectors share its DuckDB connection."""
import logging
import threading

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

from .connectors import REGISTRY
from .connectors.base import execute
from .derived import refresh_derived

log = logging.getLogger("pharmalens.scheduler")
_sched: BackgroundScheduler | None = None
_running: set[str] = set()
_lock = threading.Lock()


def run_now(name: str) -> dict:
    with _lock:
        if name in _running:
            return {"connector": name, "status": "already_running"}
        _running.add(name)
    try:
        res = execute(REGISTRY[name])
        if res.get("rows_new") or res.get("events_new"):
            refresh_derived()
        log.info("connector %s", res)
        return res
    finally:
        with _lock:
            _running.discard(name)


def running() -> list[str]:
    with _lock:
        return sorted(_running)


def start():
    global _sched
    if _sched:
        return _sched
    _sched = BackgroundScheduler(timezone="Asia/Kolkata", executors={"default": ThreadPoolExecutor(3)},
                                 job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600})
    for name, cls in REGISTRY.items():
        _sched.add_job(run_now, args=[name], id=name, name=cls.title, **cls.schedule)
    _sched.start()
    return _sched


def jobs() -> dict[str, str | None]:
    if not _sched:
        return {}
    return {j.id: (j.next_run_time.isoformat() if j.next_run_time else None) for j in _sched.get_jobs()}


def shutdown():
    global _sched
    if _sched:
        _sched.shutdown(wait=False)
        _sched = None
