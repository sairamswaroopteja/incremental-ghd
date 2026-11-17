"""A worker pool with hard per-task deadlines and an RSS watchdog (Windows-safe: spawn).

Each worker is a ``multiprocessing`` process (start method ``spawn`` on every platform, so the
behaviour is the same on Windows and POSIX) that runs one task at a time. The parent:
  * kills the worker (``Process.kill``: TerminateProcess on Windows, SIGKILL on POSIX) when a task
    exceeds its hard deadline, and reports ``{"_killed": "TIMEOUT"}``;
  * samples the worker's resident set size with psutil every ``poll_s`` seconds and kills it when
    the RSS exceeds ``mem_cap_mb``, reporting ``{"_killed": "MEMOUT"}``. This is a SAMPLED cap: an
    allocation spike shorter than ``poll_s`` can overshoot it, and the operating system's own
    memory limits are not used;
  * reports ``{"_died": exitcode}`` if a worker exits on its own (e.g. a C stack overflow);
and then starts a fresh worker. A killed task never produces a solver answer.

Callers must guard their entry point with ``if __name__ == "__main__":`` (spawn re-imports it).
"""

from __future__ import annotations

import multiprocessing as mp
import time
import traceback
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from multiprocessing.connection import wait

import psutil


def _worker_main(conn) -> None:  # pragma: no cover - runs in the child process
    import benchmarks.worker as tasks   # noqa: PLC0415 - import after spawn, then report ready
    conn.send(("__ready__", None))
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            return
        if msg is None:
            return
        tid, fn, payload = msg
        try:
            res = getattr(tasks, fn)(payload)
        except MemoryError:
            res = {"_error": "MemoryError", "_memout": True}
        except BaseException as exc:  # noqa: BLE001
            res = {"_error": f"{type(exc).__name__}: {exc} | {traceback.format_exc(limit=4)[-800:]}"}
        try:
            conn.send((tid, res))
        except Exception as exc:  # noqa: BLE001 - e.g. unpicklable result
            conn.send((tid, {"_error": f"result not sendable: {exc!r}"}))


@dataclass
class Task:
    tid: object
    fn: str              # name of a function in benchmarks.worker
    payload: dict
    deadline_s: float    # hard wall-clock limit for this task


@dataclass
class _Slot:
    proc: object = None
    conn: object = None
    ready: bool = False
    task: Task | None = None
    started: float = 0.0
    rss_peak: int = 0
    ps: object = None
    spawned: int = field(default=0)


class HardPool:
    def __init__(self, jobs: int, mem_cap_mb: float | None = 1024.0, poll_s: float = 0.05) -> None:
        self.jobs = max(1, int(jobs))
        self.mem_cap = None if mem_cap_mb is None else int(mem_cap_mb * 2**20)
        self.poll_s = poll_s
        self.ctx = mp.get_context("spawn")
        self.kills = {"TIMEOUT": 0, "MEMOUT": 0, "DIED": 0}

    def _start(self, s: _Slot) -> None:
        parent, child = self.ctx.Pipe(duplex=True)
        p = self.ctx.Process(target=_worker_main, args=(child,), daemon=True)
        p.start()
        child.close()
        s.proc, s.conn, s.ready, s.task, s.rss_peak = p, parent, False, None, 0
        s.ps = psutil.Process(p.pid)
        s.spawned += 1

    @staticmethod
    def _stop(s: _Slot) -> None:
        try:
            s.proc.kill()
        except Exception:  # noqa: BLE001
            pass
        s.proc.join(timeout=5)
        try:
            s.conn.close()
        except Exception:  # noqa: BLE001
            pass
        s.proc = s.conn = s.ps = None
        s.ready = False

    def run(self, tasks: Iterable[Task], on_result: Callable[[Task, dict, float, int], None]) -> None:
        """Run every task; ``on_result(task, result, elapsed_s, rss_peak_bytes)`` per task.

        ``result`` is the task function's return value, or one of ``{"_killed": "TIMEOUT"|"MEMOUT"}``,
        ``{"_died": exitcode}``, ``{"_error": message}``.
        """
        pending = deque(tasks)
        slots = [_Slot() for _ in range(min(self.jobs, max(1, len(pending))))]
        try:
            while pending or any(s.task is not None for s in slots):
                for s in slots:
                    if s.proc is None and (pending or s.task is not None):
                        self._start(s)
                    if s.ready and s.task is None and pending:
                        s.task = pending.popleft()
                        s.rss_peak = 0
                        s.started = time.perf_counter()
                        s.conn.send((s.task.tid, s.task.fn, s.task.payload))
                live = [s.conn for s in slots if s.conn is not None]
                for conn in wait(live, timeout=self.poll_s) if live else ():
                    s = next(x for x in slots if x.conn is conn)
                    try:
                        tid, res = conn.recv()
                    except (EOFError, OSError):
                        code = s.proc.exitcode
                        self._stop(s)
                        if s.task is not None:
                            self.kills["DIED"] += 1
                            t, s.task = s.task, None
                            on_result(t, {"_died": code}, time.perf_counter() - s.started, s.rss_peak)
                        continue
                    if tid == "__ready__":
                        s.ready = True
                        continue
                    t, s.task = s.task, None
                    on_result(t, res, time.perf_counter() - s.started, s.rss_peak)
                now = time.perf_counter()
                for s in slots:
                    if s.task is None or s.proc is None:
                        continue
                    try:
                        rss = s.ps.memory_info().rss
                    except (psutil.Error, AttributeError):
                        rss = 0
                    s.rss_peak = max(s.rss_peak, rss)
                    why = None
                    if self.mem_cap is not None and rss > self.mem_cap:
                        why = "MEMOUT"
                    elif now - s.started > s.task.deadline_s:
                        why = "TIMEOUT"
                    if why:
                        self.kills[why] += 1
                        t, s.task = s.task, None
                        self._stop(s)
                        on_result(t, {"_killed": why}, now - s.started, s.rss_peak)
        finally:
            for s in slots:
                if s.proc is not None:
                    try:
                        s.conn.send(None)
                    except Exception:  # noqa: BLE001
                        pass
                    s.proc.join(timeout=2)
                    if s.proc.is_alive():
                        self._stop(s)
