"""A17 non-production continuous watchdog with thread-owned SQLite sessions.

The operator supplies an independent fixture SESSION FACTORY (not a package
entry point). It runs in the watchdog thread, creating all A12–A16 SQLite
connections there. No production, private code, plugin payload, network or
automatic restart; no adversarial OS/container sandbox is claimed.
"""
from __future__ import annotations

import fcntl
import os
import queue
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .a16_supervisor import (
    FixtureProcessLimits, OfflineFixtureSupervisor, ServiceRefused,
)


class WatchdogRefused(ServiceRefused):
    """A17 refuses invalid lifecycle, unsafe identity or watchdog state."""


@dataclass(frozen=True, slots=True)
class FixtureSession:
    """Construct entirely inside the watchdog thread, including sqlite handles."""
    supervisor: OfflineFixtureSupervisor
    admission: object
    close_callbacks: tuple[Callable[[], None], ...] = ()


@dataclass(frozen=True, slots=True)
class WatchdogSnapshot:
    service_state: str
    service_revision: int
    owned_child_alive: bool
    monitoring: bool
    completed_health_probes: int
    last_probe_admitted: bool
    fault: str | None
    mock_fixture_only: bool = True
    real_private_engine_running: bool = False
    live_trading_permitted: bool = False


class ContinuousFixtureWatchdog:
    """No auto-restart, no background SQL connection sharing, no production.

    The worker-thread processes *all* supervisor commands and health ticks
    through a single queue. The calling thread NEVER touches the SQLite
    connections opened by session_factory. Revocation is checked on the next
    scheduled probe, not instantaneously.
    """

    def __init__(self, root: str | Path, *, session_factory: Callable[[], FixtureSession],
                 trusted_clock: Callable[[], int],
                 interval_seconds: float = 0.15) -> None:
        root = Path(root)
        temp = Path(tempfile.gettempdir()).resolve()
        if (not root.is_absolute() or root.is_symlink()
                or root.parent.is_symlink() or root.resolve() == temp
                or not root.resolve().is_relative_to(temp)
                or not callable(session_factory) or not callable(trusted_clock)
                or type(interval_seconds) not in (int, float)
                or not 0.05 <= interval_seconds <= 30.0):
            raise WatchdogRefused("A17_TEMP_FACTORY_INTERVAL_REQUIRED")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not root.is_dir() or root.stat().st_mode & 0o077:
            raise WatchdogRefused("A17_UNSAFE_ROOT")
        self._root = root
        self._path = root / "watchdog.lock"
        self._fd = os.open(self._path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(self._fd)
            raise WatchdogRefused("A17_OWNER_ALREADY_ACTIVE") from exc
        self._factory = session_factory
        self._clock = trusted_clock
        self._interval = float(interval_seconds)
        self._queue: queue.Queue = queue.Queue(maxsize=32)
        self._ready: queue.Queue = queue.Queue(maxsize=1)
        self._closed = False
        self._thread = threading.Thread(
            target=self._run, name="a17-fixed-fixture-watchdog", daemon=True,
        )
        self._thread.start()
        try:
            initial = self._ready.get(timeout=5.0)
            if isinstance(initial, BaseException):
                raise WatchdogRefused("A17_SESSION_CREATION_FAILED") from initial
        except BaseException:
            self._release()
            raise

    def _release(self):
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def _call(self, cmd: str):
        if self._closed or not self._thread.is_alive():
            raise WatchdogRefused("A17_OWNER_NOT_LIVE")
        answer: queue.Queue = queue.Queue(maxsize=1)
        try:
            self._queue.put((cmd, answer), timeout=1.0)
            result = answer.get(timeout=5.0)
        except queue.Empty as exc:
            raise WatchdogRefused("A17_COMMAND_TIMEOUT") from exc
        except queue.Full as exc:
            raise WatchdogRefused("A17_COMMAND_QUEUE_FULL") from exc
        if isinstance(result, BaseException):
            raise result
        return result

    def start(self) -> WatchdogSnapshot:
        """Explicit operator start. Crash never triggers an automatic restart."""
        return self._call("START")

    def status(self) -> WatchdogSnapshot:
        return self._call("STATUS")

    def stop(self) -> WatchdogSnapshot:
        """Controlled STOP even with expired/revoked license."""
        return self._call("STOP")

    def reconcile(self) -> WatchdogSnapshot:
        """Manual, exclusive recovery; always requires a new explicit start."""
        return self._call("RECONCILE")

    def crash_fixture_for_test(self) -> WatchdogSnapshot:
        return self._call("CRASH")

    def observed_limits(self):
        """Read actual Linux process rlimits for OWN child; tests only."""
        return self._call("LIMITS")

    def close(self):
        if self._closed:
            return
        try:
            if self._thread.is_alive():
                try:
                    self._call("CLOSE")
                finally:
                    self._thread.join(timeout=5.0)
        finally:
            self._closed = True
            self._release()

    def _run(self):
        try:
            session = self._factory()
            if (not isinstance(session, FixtureSession)
                    or not isinstance(session.supervisor, OfflineFixtureSupervisor)
                    or not isinstance(session.supervisor._process_limits,
                                      FixtureProcessLimits)
                    or not isinstance(session.close_callbacks, tuple)
                    or any(not callable(fn) for fn in session.close_callbacks)):
                raise WatchdogRefused("A17_LIMITED_SIGNED_FIXTURE_SESSION_REQUIRED")
        except BaseException as exc:
            self._ready.put(exc)
            return
        supervisor = session.supervisor
        admission = session.admission
        active = False
        probes = 0
        last_ok = False
        fault: str | None = None

        def snapshot():
            state = supervisor.status()
            return WatchdogSnapshot(
                state.state, state.revision, state.owned_process_alive,
                active and state.state == "RUNNING", probes,
                last_ok and active and state.state == "RUNNING", fault,
            )

        def quarantine():
            nonlocal active, last_ok, fault
            try:
                supervisor.quarantine_owned_for_a17()
            finally:
                active = False
                last_ok = False
                if fault is None:
                    fault = "A17_MONITOR_EXCEPTION"

        self._ready.put(True)
        try:
            while True:
                try:
                    cmd, response = self._queue.get(
                        timeout=self._interval if active else None,
                    )
                except queue.Empty:
                    cmd, response = "TICK", None
                result = None
                try:
                    if cmd == "CLOSE":
                        active = False
                        supervisor.close()
                        result = snapshot()
                    elif cmd == "START":
                        if active:
                            raise WatchdogRefused("A17_ALREADY_MONITORING")
                        before = supervisor.status()
                        supervisor.start(
                            expected_revision=before.revision,
                            admission=admission, now=self._clock(),
                        )
                        active = True
                        fault = None
                        # No false initial health: require a first signed probe.
                        cmd = "TICK"
                    elif cmd == "STOP":
                        active = False
                        state = supervisor.status()
                        if state.state == "RUNNING" and state.owned_process_alive:
                            supervisor.stop(expected_revision=state.revision)
                        last_ok = False
                        result = snapshot()
                    elif cmd == "RECONCILE":
                        if active:
                            raise WatchdogRefused("A17_STOP_MONITOR_BEFORE_RECONCILE")
                        before = supervisor.status()
                        supervisor.reconcile(expected_revision=before.revision)
                        fault = None
                        last_ok = False
                        result = snapshot()
                    elif cmd == "CRASH":
                        if not active:
                            raise WatchdogRefused("A17_NOT_MONITORING")
                        before = supervisor.status()
                        supervisor.crash_fixture_for_test(
                            expected_revision=before.revision)
                        result = snapshot()
                    elif cmd == "STATUS":
                        result = snapshot()
                    elif cmd == "LIMITS":
                        import resource
                        child = supervisor._child
                        if not active or child is None or child.poll() is not None:
                            raise WatchdogRefused("A17_NO_OWNED_LIMITED_CHILD")
                        result = {
                            "memory_bytes": resource.prlimit(child.pid, resource.RLIMIT_AS),
                            "cpu_seconds": resource.prlimit(child.pid, resource.RLIMIT_CPU),
                            "open_files": resource.prlimit(child.pid, resource.RLIMIT_NOFILE),
                            "core_bytes": resource.prlimit(child.pid, resource.RLIMIT_CORE),
                        }
                    if cmd == "TICK":
                        try:
                            health = supervisor.health(
                                admission=admission, now=self._clock())
                            probes += 1
                            last_ok = (health.state == "RUNNING"
                                       and health.signed_and_admitted_now
                                       and health.owned_process_alive)
                            if not last_ok:
                                active = False
                                fault = "A17_FAIL_CLOSED_HEALTH"
                        except Exception:
                            quarantine()
                        result = snapshot()
                except Exception as exc:
                    result = exc
                if response is not None:
                    response.put(result)
                if cmd == "CLOSE":
                    break
        finally:
            active = False
            try:
                supervisor.close()
            finally:
                for fn in reversed(session.close_callbacks):
                    try:
                        fn()
                    except Exception:
                        pass
