"""Background research runs (S9): a run outlives the browser session that started it.

A Streamlit session ends when its websocket drops (Cloud Run closes it at the request timeout,
or the browser sleeps). A run inside the page script dies with it and its result is lost. Here a
run executes on a background thread; its progress and result are written to <base_dir>/<job_id>.json,
so any later session can pick the run up by id (the page keeps it in the URL as ?run=<job_id>).

Only one run executes at a time per process: runs are long, spend model quota, and the runner
holds per-run state.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_JOB_ID = re.compile(r"^job_[0-9a-f]{12}$")

ProgressFn = Callable[[int, str, float], None]


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


class RunJobs:
    def __init__(self, base_dir: str | Path, error_formatter: Optional[Callable[[Exception], Dict[str, str]]] = None):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.error_formatter = error_formatter or (lambda exc: {"title": "Run failed", "what_happened": str(exc)})
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}  # this process's jobs, results kept as live objects
        self._running: Optional[str] = None

    # -- state -----------------------------------------------------------------
    def _path(self, job_id: str) -> Path:
        return self.base_dir / f"{job_id}.json"

    def _save(self, job: Dict[str, Any]) -> None:
        path = self._path(job["job_id"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job, default=str), encoding="utf-8")
        tmp.replace(path)

    def _update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(fields)
            snapshot = dict(job)
        self._save(snapshot)

    # -- API -------------------------------------------------------------------
    def start(self, target: Callable[[ProgressFn], Dict[str, Any]], meta: Optional[Dict[str, Any]] = None) -> str:
        """Start target(on_progress) on a background thread; return its job id. While a run is
        executing, return that run's id instead of starting a second one."""
        with self._lock:
            if self._running:
                return self._running
            job_id = f"job_{uuid.uuid4().hex[:12]}"
            job = {"job_id": job_id, "state": "running", "stage": 0, "message": "Starting…", "progress": 0.0,
                   "meta": dict(meta or {}), "started_at": _now(), "finished_at": None, "error": None, "results": None}
            self._jobs[job_id] = job
            self._running = job_id
        self._save(dict(job))

        def on_progress(stage: int, message: str, progress: float) -> None:
            self._update(job_id, stage=int(stage), message=str(message), progress=float(progress))

        def work() -> None:
            try:
                results = target(on_progress)
                self._update(job_id, state="done", progress=1.0, results=results, finished_at=_now())
            except Exception as exc:  # the page shows the error; the run must not vanish
                logger.exception("Background run %s failed", job_id)
                self._update(job_id, state="failed", error=self.error_formatter(exc), finished_at=_now())
            finally:
                with self._lock:
                    if self._running == job_id:
                        self._running = None

        threading.Thread(target=work, name=f"research-{job_id}", daemon=True).start()
        return job_id

    def running(self) -> Optional[str]:
        with self._lock:
            return self._running

    def get(self, job_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """The job, from this process if it ran here, else from disk. None for an unknown id."""
        if not job_id or not _JOB_ID.match(str(job_id)):
            return None
        with self._lock:
            if job_id in self._jobs:
                return dict(self._jobs[job_id])
        path = self._path(job_id)
        if not path.exists():
            return None
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if job.get("state") == "running":
            # Written by a process that is gone (container restart): the run cannot finish.
            job.update(state="failed", error={"title": "Run interrupted",
                                              "what_happened": "The server restarted while this run was in progress."})
        return job

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Finished runs, newest first, without their results (they load when opened)."""
        out = []
        for path in self.base_dir.glob("job_*.json"):
            job = self.get(path.stem)
            if job and job.get("state") == "done":
                out.append({k: v for k, v in job.items() if k != "results"})
        out.sort(key=lambda j: j.get("finished_at") or "", reverse=True)
        return out[:limit]
