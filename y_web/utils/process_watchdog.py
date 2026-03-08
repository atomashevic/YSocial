"""
Process watchdog for monitoring and restarting hung/dead processes.

This module provides a lightweight watchdog that monitors server and client
processes using log file modifications as heartbeat indicators. When a process
appears hung (no log activity) or dead, it can be automatically restarted.

The watchdog runs periodically (default every 1 minute), performs its check,
restarts any hung/dead processes, and terminates until the next scheduled run.
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import psutil
import requests

logger = logging.getLogger(__name__)

# Default watchdog settings
DEFAULT_RUN_INTERVAL_MINUTES = 1
MAX_RUN_INTERVAL_MINUTES = 1440  # 24 hours
DEFAULT_SERVER_HEARTBEAT_TIMEOUT = 300  # seconds
DEFAULT_CLIENT_HEARTBEAT_TIMEOUT = 300  # seconds
DEFAULT_HEARTBEAT_TIMEOUT = (
    DEFAULT_SERVER_HEARTBEAT_TIMEOUT  # backward compatible alias
)
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 60
DEFAULT_MAX_RESTART_ATTEMPTS = 3
DEFAULT_RESTART_COOLDOWN = 60  # seconds
MAX_RESTART_BACKOFF_SECONDS = 1800  # 30 minutes
SERVER_RESTART_DELAY = (
    30  # seconds to wait after restarting servers before restarting clients
)
SERVER_STATUS_CHECK_TIMEOUT = 5  # seconds for each status check attempt
SERVER_STATUS_MAX_RETRIES = 6  # number of retries to check server status
SERVER_STATUS_RETRY_DELAY = 5  # seconds between status check retries


def check_server_status(server_url: str) -> bool:
    """
    Check if a server is ready by calling its /status endpoint.

    Args:
        server_url: The base URL of the server (e.g., "http://localhost:5000")

    Returns:
        True if the server is ready (status 200), False otherwise
    """
    try:
        response = requests.get(
            f"{server_url}/status", timeout=SERVER_STATUS_CHECK_TIMEOUT
        )
        if response.status_code == 200:
            data = response.json()
            # Check if the response indicates the server is running
            if data.get("status") == 200:
                return True
            else:
                logger.warning(
                    f"Server at {server_url} returned error: {data.get('message')}"
                )
                return False
        return False
    except requests.exceptions.RequestException as e:
        logger.debug(f"Server status check failed for {server_url}: {e}")
        return False


def wait_for_servers_ready(server_urls: List[str]) -> bool:
    """
    Wait for all servers to become ready by polling their /status endpoints.

    Args:
        server_urls: List of server base URLs to check

    Returns:
        True if all servers are ready, False if timeout reached
    """
    if not server_urls:
        return True

    for attempt in range(SERVER_STATUS_MAX_RETRIES):
        all_ready = True
        for url in server_urls:
            if not check_server_status(url):
                all_ready = False
                break

        if all_ready:
            logger.info(f"Watchdog: All {len(server_urls)} server(s) are ready")
            return True

        if attempt < SERVER_STATUS_MAX_RETRIES - 1:
            logger.info(
                f"Watchdog: Waiting for servers... (attempt {attempt + 1}/{SERVER_STATUS_MAX_RETRIES})"
            )
            time.sleep(SERVER_STATUS_RETRY_DELAY)

    logger.warning(
        f"Watchdog: Timeout waiting for servers after {SERVER_STATUS_MAX_RETRIES} attempts"
    )
    return False


class ProcessWatchdog:
    """
    A lightweight watchdog that monitors processes using log files as heartbeats.

    The watchdog periodically checks:
    1. If the process is still running (using PID)
    2. If the log file has been modified recently (heartbeat check)

    If a process is detected as hung or dead, it calls a restart callback.

    The watchdog runs on a schedule (default every 1 minute), performs its
    check/restart cycle, and terminates until the next scheduled run.
    """

    def __init__(
        self,
        run_interval_minutes: int = DEFAULT_RUN_INTERVAL_MINUTES,
        heartbeat_timeout: int = DEFAULT_HEARTBEAT_TIMEOUT,
        max_restart_attempts: int = DEFAULT_MAX_RESTART_ATTEMPTS,
        restart_cooldown: int = DEFAULT_RESTART_COOLDOWN,
        server_heartbeat_timeout: Optional[int] = None,
        client_heartbeat_timeout: Optional[int] = None,
        heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        enabled: bool = True,
    ):
        """
        Initialize the watchdog.

        Args:
            run_interval_minutes: How often to run the watchdog check (in minutes)
            heartbeat_timeout: Max time without log activity before considering hung (seconds)
            max_restart_attempts: Maximum restart attempts before giving up
            restart_cooldown: Minimum time between restart attempts (seconds)
            server_heartbeat_timeout: Optional override for server heartbeat timeout (seconds)
            client_heartbeat_timeout: Optional override for client heartbeat timeout (seconds)
            heartbeat_interval_seconds: Expected client heartbeat write interval (seconds)
            enabled: Whether watchdog scheduling is enabled
        """
        self._run_interval_minutes = max(
            1, min(run_interval_minutes, MAX_RUN_INTERVAL_MINUTES)
        )
        self._server_heartbeat_timeout = int(
            server_heartbeat_timeout
            if server_heartbeat_timeout is not None
            else heartbeat_timeout
        )
        self._client_heartbeat_timeout = int(
            client_heartbeat_timeout
            if client_heartbeat_timeout is not None
            else heartbeat_timeout
        )
        # Legacy/global field retained for backward compatibility and status payloads.
        self._heartbeat_timeout = self._server_heartbeat_timeout
        self._max_restart_attempts = max(1, int(max_restart_attempts))
        self._restart_cooldown = max(0, int(restart_cooldown))
        self._heartbeat_interval_seconds = max(1, int(heartbeat_interval_seconds))
        self._enabled = bool(enabled)

        # Tracked processes: {process_id: ProcessInfo}
        self._processes: Dict[str, "ProcessInfo"] = {}
        self._lock = threading.RLock()

        # Scheduler thread
        self._scheduler_running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._last_run: Optional[datetime] = None
        self._next_run: Optional[datetime] = None

    @property
    def run_interval_minutes(self) -> int:
        """Get the current run interval in minutes."""
        return self._run_interval_minutes

    @run_interval_minutes.setter
    def run_interval_minutes(self, value: int) -> None:
        """Set the run interval in minutes."""
        if value < 1:
            value = 1
        if value > MAX_RUN_INTERVAL_MINUTES:
            value = MAX_RUN_INTERVAL_MINUTES
        self._run_interval_minutes = value
        # Update next run time based on now if scheduler is running
        if self._scheduler_running:
            self._next_run = datetime.now() + timedelta(minutes=value)
        elif self._last_run:
            self._next_run = self._last_run + timedelta(minutes=value)

    @property
    def max_restart_attempts(self) -> int:
        """Get max restart attempts."""
        return self._max_restart_attempts

    @max_restart_attempts.setter
    def max_restart_attempts(self, value: int) -> None:
        """Set max restart attempts."""
        self._max_restart_attempts = max(1, int(value))

    @property
    def restart_cooldown(self) -> int:
        """Get restart cooldown in seconds."""
        return self._restart_cooldown

    @restart_cooldown.setter
    def restart_cooldown(self, value: int) -> None:
        """Set restart cooldown in seconds."""
        self._restart_cooldown = max(0, int(value))

    @property
    def server_heartbeat_timeout(self) -> int:
        """Get server heartbeat timeout in seconds."""
        return self._server_heartbeat_timeout

    @server_heartbeat_timeout.setter
    def server_heartbeat_timeout(self, value: int) -> None:
        """Set server heartbeat timeout in seconds."""
        self._server_heartbeat_timeout = max(1, int(value))
        self._heartbeat_timeout = self._server_heartbeat_timeout

    @property
    def client_heartbeat_timeout(self) -> int:
        """Get client heartbeat timeout in seconds."""
        return self._client_heartbeat_timeout

    @client_heartbeat_timeout.setter
    def client_heartbeat_timeout(self, value: int) -> None:
        """Set client heartbeat timeout in seconds."""
        self._client_heartbeat_timeout = max(1, int(value))

    @property
    def heartbeat_interval_seconds(self) -> int:
        """Get expected client heartbeat interval in seconds."""
        return self._heartbeat_interval_seconds

    @heartbeat_interval_seconds.setter
    def heartbeat_interval_seconds(self, value: int) -> None:
        """Set expected client heartbeat interval in seconds."""
        self._heartbeat_interval_seconds = max(1, int(value))

    @property
    def enabled(self) -> bool:
        """Get watchdog enabled state."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Set watchdog enabled state."""
        self._enabled = bool(value)

    def _heartbeat_timeout_for_type(self, process_type: str) -> int:
        """Resolve heartbeat timeout by process type."""
        if process_type == "client":
            return self._client_heartbeat_timeout
        if process_type == "server":
            return self._server_heartbeat_timeout
        return self._heartbeat_timeout

    def refresh_registered_timeouts(self) -> None:
        """Apply current timeout policy to all currently tracked processes."""
        with self._lock:
            for info in self._processes.values():
                info.heartbeat_timeout = self._heartbeat_timeout_for_type(
                    info.process_type
                )

    def register_process(
        self,
        process_id: str,
        pid: int,
        log_file: str,
        restart_callback: Callable[[], Optional[int]],
        process_type: str = "unknown",
        server_url: Optional[str] = None,
        heartbeat_timeout: Optional[int] = None,
    ) -> None:
        """
        Register a process for monitoring.

        Args:
            process_id: Unique identifier for the process (e.g., "server_1" or "client_5")
            pid: Process ID
            log_file: Path to the log file used as heartbeat indicator
            restart_callback: Callback function to restart the process, returns new PID
            process_type: Type of process ("server" or "client")
            server_url: For server processes, the base URL for status checks (e.g., "http://localhost:5000")
            heartbeat_timeout: Optional timeout override (seconds) for this specific process
        """
        effective_timeout = (
            max(1, int(heartbeat_timeout))
            if heartbeat_timeout is not None
            else self._heartbeat_timeout_for_type(process_type)
        )
        with self._lock:
            self._processes[process_id] = ProcessInfo(
                process_id=process_id,
                pid=pid,
                log_file=log_file,
                restart_callback=restart_callback,
                process_type=process_type,
                registered_at=datetime.now(),
                last_heartbeat=datetime.now(),
                restart_count=0,
                last_restart_at=None,
                server_url=server_url,
                heartbeat_timeout=effective_timeout,
                last_restart_error=None,
            )
            logger.info(
                f"Watchdog: Registered {process_type} process {process_id} (PID: {pid})"
            )

    def unregister_process(self, process_id: str) -> None:
        """
        Unregister a process from monitoring.

        Args:
            process_id: Unique identifier for the process
        """
        with self._lock:
            if process_id in self._processes:
                del self._processes[process_id]
                logger.info(f"Watchdog: Unregistered process {process_id}")

    def update_pid(self, process_id: str, new_pid: int) -> None:
        """
        Update the PID for a tracked process.

        Args:
            process_id: Unique identifier for the process
            new_pid: New process ID
        """
        with self._lock:
            if process_id in self._processes:
                self._processes[process_id].pid = new_pid
                self._processes[process_id].last_heartbeat = datetime.now()

    def start_scheduler(self) -> None:
        """Start the watchdog scheduler that runs periodically."""
        with self._lock:
            if not self._enabled:
                logger.info("Watchdog: Scheduler start skipped (disabled)")
                return
            if self._scheduler_running:
                return

            self._scheduler_running = True
            self._shutdown_event.clear()
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop, daemon=True
            )
            self._scheduler_thread.start()
            logger.info(
                f"Watchdog: Started scheduler (runs every {self._run_interval_minutes} minutes)"
            )

    def stop_scheduler(self) -> None:
        """Stop the watchdog scheduler."""
        with self._lock:
            self._scheduler_running = False
            self._shutdown_event.set()  # Signal shutdown
            if self._scheduler_thread:
                self._scheduler_thread.join(timeout=10)
                self._scheduler_thread = None
            logger.info("Watchdog: Stopped scheduler")

    # Backward compatibility aliases
    def start(self) -> None:
        """Start the watchdog scheduler (alias for start_scheduler)."""
        self.start_scheduler()

    def stop(self) -> None:
        """Stop the watchdog scheduler (alias for stop_scheduler)."""
        self.stop_scheduler()

    def _scheduler_loop(self) -> None:
        """Scheduler loop that triggers watchdog runs at the configured interval."""
        while self._scheduler_running:
            now = datetime.now()

            # Determine if it's time to run
            should_run = False
            if self._next_run is None:
                # First run - schedule for interval from now
                self._next_run = now + timedelta(minutes=self._run_interval_minutes)
            elif now >= self._next_run:
                should_run = True

            if should_run:
                try:
                    self.run_once()
                    # run_once() already updates _last_run and _next_run
                except Exception as e:
                    logger.error(f"Watchdog: Error in scheduled run: {e}")
                    # Update timestamps even on error
                    self._last_run = datetime.now()
                    self._next_run = self._last_run + timedelta(
                        minutes=self._run_interval_minutes
                    )

            # Wait for shutdown signal or timeout (10 seconds)
            # Using Event.wait() is more efficient than polling with sleep
            if self._shutdown_event.wait(timeout=10):
                break  # Shutdown was signaled

    def run_once(self) -> Dict:
        """
        Run the watchdog check once and return results.

        This method checks all registered processes, restarts any that are
        hung or dead, and returns a summary of the results.

        Returns:
            Dictionary with results of the watchdog run
        """
        logger.info("Watchdog: Running process check...")
        results = {
            "run_time": datetime.now().isoformat(),
            "processes_checked": 0,
            "processes_restarted": 0,
            "processes_healthy": 0,
            "details": [],
        }

        try:
            self._check_all_processes(results)
        except Exception as e:
            logger.error(f"Watchdog: Error during check: {e}")
            results["error"] = str(e)

        # Update last_run timestamp (for both manual and scheduled runs)
        self._last_run = datetime.now()

        # Persist last_run to database
        _save_watchdog_last_run(self._last_run)

        # Update next_run if scheduler is running
        if self._scheduler_running:
            self._next_run = self._last_run + timedelta(
                minutes=self._run_interval_minutes
            )

        logger.info(
            f"Watchdog: Check complete - {results['processes_checked']} checked, "
            f"{results['processes_restarted']} restarted, "
            f"{results['processes_healthy']} healthy"
        )

        return results

    def _check_all_processes(self, results: Dict) -> None:
        """Check all registered processes.

        Servers are checked and restarted before clients to ensure proper
        dependency order - if all clients attached to a server hung, the
        issue is likely in the server, so restart the server first.

        After restarting any servers, polls their /status endpoints to verify
        they are ready before proceeding to restart clients. Falls back to
        a fixed delay if status checks are not available.
        """
        with self._lock:
            # Separate processes by type and sort: servers first, then clients
            server_ids = [
                pid
                for pid, info in self._processes.items()
                if info.process_type == "server"
            ]
            client_ids = [
                pid
                for pid, info in self._processes.items()
                if info.process_type == "client"
            ]

        # Process servers first and collect URLs of restarted servers
        servers_restarted = 0
        restarted_server_urls: List[str] = []

        for process_id in server_ids:
            with self._lock:
                if process_id not in self._processes:
                    continue
                process_info = self._processes[process_id]

            restarted = self._check_process(process_info, results)
            if restarted:
                servers_restarted += 1
                # Collect server URL for status checking
                if process_info.server_url:
                    restarted_server_urls.append(process_info.server_url)

        # If any servers were restarted, wait for them to become ready
        # before restarting clients
        if servers_restarted > 0 and len(client_ids) > 0:
            if restarted_server_urls:
                # Use status endpoint to check if servers are ready
                logger.info(
                    f"Watchdog: Waiting for {len(restarted_server_urls)} restarted "
                    f"server(s) to become ready..."
                )
                if not wait_for_servers_ready(restarted_server_urls):
                    # Status check failed, fall back to fixed delay
                    logger.warning(
                        f"Watchdog: Server status checks failed, waiting "
                        f"{SERVER_RESTART_DELAY}s before checking clients..."
                    )
                    time.sleep(SERVER_RESTART_DELAY)
            else:
                # No server URLs available, use fixed delay
                logger.info(
                    f"Watchdog: Waiting {SERVER_RESTART_DELAY}s after restarting "
                    f"{servers_restarted} server(s) before checking clients..."
                )
                time.sleep(SERVER_RESTART_DELAY)

        # Process clients after servers are ready
        for process_id in client_ids:
            with self._lock:
                if process_id not in self._processes:
                    continue
                process_info = self._processes[process_id]

            self._check_process(process_info, results)

    def _check_process(self, process_info: "ProcessInfo", results: Dict) -> bool:
        """
        Check a single process and restart if needed.

        Args:
            process_info: Information about the process to check
            results: Results dictionary to update

        Returns:
            True if the process was restarted, False otherwise
        """
        results["processes_checked"] += 1
        pid = process_info.pid
        log_file = process_info.log_file
        timeout_seconds = max(
            1,
            int(
                process_info.heartbeat_timeout
                if process_info.heartbeat_timeout is not None
                else self._heartbeat_timeout_for_type(process_info.process_type)
            ),
        )

        # Check if process is running
        is_running = self._is_process_running(pid)

        # Check log file heartbeat
        last_modified = self._get_log_mtime(log_file)

        if last_modified:
            process_info.last_heartbeat = last_modified

        now = datetime.now()
        time_since_heartbeat = now - process_info.last_heartbeat

        # Determine if process needs restart
        needs_restart = False
        reason = ""

        if not is_running:
            needs_restart = True
            reason = "process not running"
        elif (
            time_since_heartbeat.total_seconds() > timeout_seconds
            and last_modified is not None
        ):
            # Only consider hung if we've seen the log file before
            needs_restart = True
            reason = f"no heartbeat for {time_since_heartbeat.total_seconds():.0f}s"

        process_detail = {
            "process_id": process_info.process_id,
            "process_type": process_info.process_type,
            "pid": pid,
            "is_running": is_running,
            "needs_restart": needs_restart,
            "reason": reason,
            "restarted": False,
            "heartbeat_timeout_seconds": timeout_seconds,
            "heartbeat_age_seconds": int(time_since_heartbeat.total_seconds()),
            "quarantined": process_info.quarantined,
            "next_restart_at": (
                process_info.next_restart_at.isoformat()
                if process_info.next_restart_at
                else None
            ),
        }

        restarted = False
        if needs_restart:
            restarted = self._handle_restart(process_info, reason)
            process_detail["restarted"] = restarted
            if restarted:
                results["processes_restarted"] += 1
                process_detail["new_pid"] = process_info.pid
            elif process_info.last_restart_error:
                process_detail["restart_error"] = process_info.last_restart_error
            process_detail["quarantined"] = process_info.quarantined
            process_detail["next_restart_at"] = (
                process_info.next_restart_at.isoformat()
                if process_info.next_restart_at
                else None
            )
        else:
            # Process recovered: clear restart attempt state so a later incident can recover.
            with self._lock:
                if (
                    process_info.restart_count > 0
                    or process_info.last_restart_error
                    or process_info.quarantined
                ):
                    logger.info(
                        f"Watchdog: Resetting restart counter for {process_info.process_id} "
                        f"after healthy heartbeat"
                    )
                process_info.restart_count = 0
                process_info.last_restart_at = None
                process_info.last_restart_error = None
                process_info.next_restart_at = None
                process_info.quarantined = False
                process_info.quarantined_at = None
                process_info.quarantine_reason = None
            results["processes_healthy"] += 1

        results["details"].append(process_detail)
        return restarted

    def _is_process_running(self, pid: int) -> bool:
        """
        Check if a process is running.

        Args:
            pid: Process ID to check

        Returns:
            True if process is running, False otherwise
        """
        if pid is None:
            return False

        try:
            proc = psutil.Process(pid)
            status = proc.status()
            # Consider zombie processes as not running
            return status != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def _get_log_mtime(self, log_file: str) -> Optional[datetime]:
        """
        Get the last modification time of a log file.

        Supports rotating log files (e.g., _server.log, _server.log.1, _server.log.2).
        Returns the most recent mtime across all rotating log files.

        Args:
            log_file: Path to the main log file

        Returns:
            Last modification time, or None if no files exist
        """
        try:
            # Get the most recent mtime from all rotating log files
            log_dir = os.path.dirname(log_file)
            base_name = os.path.basename(log_file)
            most_recent_mtime = None

            if os.path.exists(log_dir):
                for filename in os.listdir(log_dir):
                    # Check main file and rotated files (e.g., _server.log, _server.log.1)
                    if filename == base_name or (
                        filename.startswith(base_name + ".")
                        and filename[len(base_name) + 1 :].isdigit()
                    ):
                        file_path = os.path.join(log_dir, filename)
                        try:
                            mtime = os.path.getmtime(file_path)
                            if most_recent_mtime is None or mtime > most_recent_mtime:
                                most_recent_mtime = mtime
                        except OSError:
                            pass

            if most_recent_mtime is not None:
                return datetime.fromtimestamp(most_recent_mtime)
        except OSError:
            pass
        return None

    def _compute_restart_backoff_seconds(self, attempt_count: int) -> int:
        """
        Compute exponential backoff delay for the next retry window.

        Args:
            attempt_count: Number of restart attempts already made for this incident.

        Returns:
            Backoff delay in seconds, capped at MAX_RESTART_BACKOFF_SECONDS.
        """
        if self._restart_cooldown <= 0:
            return 0
        if attempt_count <= 0:
            return 0
        delay = self._restart_cooldown * (2 ** (attempt_count - 1))
        return int(min(delay, MAX_RESTART_BACKOFF_SECONDS))

    def _mark_quarantined(
        self,
        process_info: "ProcessInfo",
        now: datetime,
        reason: str,
    ) -> None:
        """Mark a process as quarantined to suppress repeated failed restarts."""
        with self._lock:
            if process_info.quarantined:
                return
            process_info.quarantined = True
            process_info.quarantined_at = now
            process_info.quarantine_reason = reason
            process_info.last_restart_error = reason
            process_info.next_restart_at = None

        logger.warning(
            f"Watchdog: Quarantining {process_info.process_id} after repeated restart "
            f"failures ({reason})"
        )

    def _handle_restart(self, process_info: "ProcessInfo", reason: str) -> bool:
        """
        Handle restarting a process.

        Args:
            process_info: Information about the process to restart
            reason: Reason for restart

        Returns:
            True if restart was successful, False otherwise
        """
        now = datetime.now()

        with self._lock:
            if process_info.quarantined:
                return False

        # Check max restart attempts before trying another restart.
        if process_info.restart_count >= self._max_restart_attempts:
            error = (
                f"max restart attempts reached ({self._max_restart_attempts}) for "
                f"{process_info.process_id}"
            )
            self._mark_quarantined(process_info, now, error)
            return False

        # Exponential cooldown between restart attempts.
        if process_info.last_restart_at and process_info.restart_count > 0:
            required_delay = self._compute_restart_backoff_seconds(
                process_info.restart_count
            )
            next_restart_at = process_info.last_restart_at + timedelta(
                seconds=required_delay
            )
            with self._lock:
                process_info.next_restart_at = next_restart_at
            if now < next_restart_at:
                remaining = int((next_restart_at - now).total_seconds())
                logger.debug(
                    f"Watchdog: Skipping restart for {process_info.process_id}, "
                    f"backoff window active ({remaining}s remaining)"
                )
                return False

        logger.warning(
            f"Watchdog: Restarting {process_info.process_type} "
            f"{process_info.process_id} (reason: {reason})"
        )

        try:
            # Call the restart callback
            new_pid = process_info.restart_callback()

            if new_pid:
                with self._lock:
                    process_info.pid = new_pid
                    process_info.restart_count += 1
                    process_info.last_restart_at = now
                    process_info.last_heartbeat = now
                    process_info.last_restart_error = None
                    process_info.quarantined = False
                    process_info.quarantined_at = None
                    process_info.quarantine_reason = None
                    next_delay = self._compute_restart_backoff_seconds(
                        process_info.restart_count
                    )
                    process_info.next_restart_at = (
                        now + timedelta(seconds=next_delay) if next_delay > 0 else None
                    )

                logger.info(
                    f"Watchdog: Successfully restarted {process_info.process_id} "
                    f"(new PID: {new_pid}, attempt {process_info.restart_count})"
                )
                return True
            else:
                error = f"restart callback returned None for {process_info.process_id}"
                logger.error(
                    f"Watchdog: Failed to restart {process_info.process_id} "
                    f"(callback returned None)"
                )
                with self._lock:
                    process_info.restart_count += 1
                    process_info.last_restart_at = now
                    process_info.last_restart_error = error
                    next_delay = self._compute_restart_backoff_seconds(
                        process_info.restart_count
                    )
                    process_info.next_restart_at = (
                        now + timedelta(seconds=next_delay) if next_delay > 0 else None
                    )
                if process_info.restart_count >= self._max_restart_attempts:
                    quarantine_error = (
                        f"max restart attempts reached ({self._max_restart_attempts}) for "
                        f"{process_info.process_id}"
                    )
                    self._mark_quarantined(process_info, now, quarantine_error)
                return False

        except Exception as e:
            logger.error(f"Watchdog: Error restarting {process_info.process_id}: {e}")
            with self._lock:
                process_info.restart_count += 1
                process_info.last_restart_at = now
                process_info.last_restart_error = str(e)
                next_delay = self._compute_restart_backoff_seconds(
                    process_info.restart_count
                )
                process_info.next_restart_at = (
                    now + timedelta(seconds=next_delay) if next_delay > 0 else None
                )
            if process_info.restart_count >= self._max_restart_attempts:
                quarantine_error = (
                    f"max restart attempts reached ({self._max_restart_attempts}) for "
                    f"{process_info.process_id}"
                )
                self._mark_quarantined(process_info, now, quarantine_error)
            return False

    def get_status(self) -> Dict:
        """
        Get the current status of all monitored processes and watchdog.

        Returns:
            Dictionary with status information
        """
        with self._lock:
            processes = {}
            latest_restart_error = None
            latest_restart_at = None
            quarantined_processes_count = 0
            for process_id, info in self._processes.items():
                is_running = self._is_process_running(info.pid)
                last_modified = self._get_log_mtime(info.log_file)
                if info.last_restart_error and info.last_restart_at:
                    if (
                        latest_restart_at is None
                        or info.last_restart_at > latest_restart_at
                    ):
                        latest_restart_at = info.last_restart_at
                        latest_restart_error = {
                            "process_id": info.process_id,
                            "error": info.last_restart_error,
                            "at": info.last_restart_at.isoformat(),
                        }
                if info.quarantined:
                    quarantined_processes_count += 1

                processes[process_id] = {
                    "pid": info.pid,
                    "process_type": info.process_type,
                    "is_running": is_running,
                    "log_file": info.log_file,
                    "last_heartbeat": (
                        info.last_heartbeat.isoformat() if info.last_heartbeat else None
                    ),
                    "log_last_modified": (
                        last_modified.isoformat() if last_modified else None
                    ),
                    "restart_count": info.restart_count,
                    "last_restart_at": (
                        info.last_restart_at.isoformat()
                        if info.last_restart_at
                        else None
                    ),
                    "heartbeat_timeout_seconds": info.heartbeat_timeout,
                    "last_restart_error": info.last_restart_error,
                    "next_restart_at": (
                        info.next_restart_at.isoformat()
                        if info.next_restart_at
                        else None
                    ),
                    "quarantined": info.quarantined,
                    "quarantined_at": (
                        info.quarantined_at.isoformat() if info.quarantined_at else None
                    ),
                    "quarantine_reason": info.quarantine_reason,
                }

            return {
                "enabled": self._enabled,
                "scheduler_running": self._scheduler_running,
                "run_interval_minutes": self._run_interval_minutes,
                "last_run": self._last_run.isoformat() if self._last_run else None,
                "next_run": self._next_run.isoformat() if self._next_run else None,
                "heartbeat_timeout": self._server_heartbeat_timeout,
                "server_heartbeat_timeout": self._server_heartbeat_timeout,
                "client_heartbeat_timeout": self._client_heartbeat_timeout,
                "heartbeat_interval_seconds": self._heartbeat_interval_seconds,
                "max_restart_attempts": self._max_restart_attempts,
                "restart_cooldown": self._restart_cooldown,
                "latest_restart_error": latest_restart_error,
                "quarantined_processes_count": quarantined_processes_count,
                "processes": processes,
            }

    @property
    def is_running(self) -> bool:
        """Check if the watchdog scheduler is running."""
        return self._scheduler_running


class ProcessInfo:
    """Information about a monitored process."""

    def __init__(
        self,
        process_id: str,
        pid: int,
        log_file: str,
        restart_callback: Callable[[], Optional[int]],
        process_type: str,
        registered_at: datetime,
        last_heartbeat: datetime,
        restart_count: int,
        last_restart_at: Optional[datetime],
        server_url: Optional[str] = None,
        heartbeat_timeout: Optional[int] = None,
        last_restart_error: Optional[str] = None,
        next_restart_at: Optional[datetime] = None,
        quarantined: bool = False,
        quarantined_at: Optional[datetime] = None,
        quarantine_reason: Optional[str] = None,
    ):
        self.process_id = process_id
        self.pid = pid
        self.log_file = log_file
        self.restart_callback = restart_callback
        self.process_type = process_type
        self.registered_at = registered_at
        self.last_heartbeat = last_heartbeat
        self.restart_count = restart_count
        self.last_restart_at = last_restart_at
        self.server_url = server_url
        self.heartbeat_timeout = heartbeat_timeout
        self.last_restart_error = last_restart_error
        self.next_restart_at = next_restart_at
        self.quarantined = quarantined
        self.quarantined_at = quarantined_at
        self.quarantine_reason = quarantine_reason


def _save_watchdog_last_run(last_run: datetime) -> None:
    """
    Save the watchdog last_run timestamp to the database.

    Args:
        last_run: The timestamp of the last watchdog run
    """
    try:
        from flask import current_app

        # Only save if we're in an application context
        if current_app:
            from y_web import db
            from y_web.models import WatchdogSettings

            settings = WatchdogSettings.query.first()
            if settings:
                settings.last_run = last_run
                db.session.commit()
            else:
                # Create settings row if it doesn't exist
                settings = WatchdogSettings(
                    enabled=True,
                    run_interval_minutes=DEFAULT_RUN_INTERVAL_MINUTES,
                    server_heartbeat_timeout_sec=DEFAULT_SERVER_HEARTBEAT_TIMEOUT,
                    client_heartbeat_timeout_sec=DEFAULT_CLIENT_HEARTBEAT_TIMEOUT,
                    heartbeat_interval_sec=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
                    max_restart_attempts=DEFAULT_MAX_RESTART_ATTEMPTS,
                    restart_cooldown_sec=DEFAULT_RESTART_COOLDOWN,
                    last_run=last_run,
                )
                db.session.add(settings)
                db.session.commit()
    except Exception as e:
        logger.debug(f"Could not save watchdog last_run to database: {e}")


def _upgrade_legacy_watchdog_defaults(settings) -> None:
    """
    Upgrade untouched legacy watchdog defaults to the new run interval.

    Only updates rows that still match the historical default tuple to avoid
    overriding operator-customized values.
    """
    try:
        from y_web import db

        legacy_defaults = (
            int(getattr(settings, "run_interval_minutes", DEFAULT_RUN_INTERVAL_MINUTES))
            == 15
            and int(
                getattr(
                    settings,
                    "server_heartbeat_timeout_sec",
                    DEFAULT_SERVER_HEARTBEAT_TIMEOUT,
                )
            )
            == 300
            and int(
                getattr(
                    settings,
                    "client_heartbeat_timeout_sec",
                    DEFAULT_CLIENT_HEARTBEAT_TIMEOUT,
                )
            )
            == 300
            and int(
                getattr(
                    settings,
                    "heartbeat_interval_sec",
                    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
                )
            )
            == 60
            and int(
                getattr(settings, "max_restart_attempts", DEFAULT_MAX_RESTART_ATTEMPTS)
            )
            == 3
            and int(getattr(settings, "restart_cooldown_sec", DEFAULT_RESTART_COOLDOWN))
            == 60
        )

        if legacy_defaults:
            settings.run_interval_minutes = DEFAULT_RUN_INTERVAL_MINUTES
            db.session.commit()
            logger.info(
                "Watchdog: upgraded legacy default interval from 15m to "
                f"{DEFAULT_RUN_INTERVAL_MINUTES}m"
            )
    except Exception as e:
        logger.debug(f"Could not upgrade legacy watchdog defaults: {e}")


def _load_watchdog_settings() -> Dict:
    """
    Load watchdog settings from the database.

    Returns:
        Dictionary with watchdog settings
    """
    try:
        from flask import current_app

        if current_app:
            from y_web.models import WatchdogSettings

            settings = WatchdogSettings.query.first()
            if settings:
                _upgrade_legacy_watchdog_defaults(settings)
                return {
                    "loaded": True,
                    "enabled": settings.enabled,
                    "run_interval_minutes": settings.run_interval_minutes,
                    "last_run": settings.last_run,
                    "server_heartbeat_timeout_sec": getattr(
                        settings,
                        "server_heartbeat_timeout_sec",
                        DEFAULT_SERVER_HEARTBEAT_TIMEOUT,
                    ),
                    "client_heartbeat_timeout_sec": getattr(
                        settings,
                        "client_heartbeat_timeout_sec",
                        DEFAULT_CLIENT_HEARTBEAT_TIMEOUT,
                    ),
                    "heartbeat_interval_sec": getattr(
                        settings,
                        "heartbeat_interval_sec",
                        DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
                    ),
                    "max_restart_attempts": getattr(
                        settings,
                        "max_restart_attempts",
                        DEFAULT_MAX_RESTART_ATTEMPTS,
                    ),
                    "restart_cooldown_sec": getattr(
                        settings,
                        "restart_cooldown_sec",
                        DEFAULT_RESTART_COOLDOWN,
                    ),
                }
    except Exception as e:
        logger.debug(f"Could not load watchdog settings from database: {e}")

    return {
        "loaded": False,
        "enabled": True,
        "run_interval_minutes": DEFAULT_RUN_INTERVAL_MINUTES,
        "last_run": None,
        "server_heartbeat_timeout_sec": DEFAULT_SERVER_HEARTBEAT_TIMEOUT,
        "client_heartbeat_timeout_sec": DEFAULT_CLIENT_HEARTBEAT_TIMEOUT,
        "heartbeat_interval_sec": DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        "max_restart_attempts": DEFAULT_MAX_RESTART_ATTEMPTS,
        "restart_cooldown_sec": DEFAULT_RESTART_COOLDOWN,
    }


def _save_watchdog_settings(
    enabled: bool = None,
    run_interval_minutes: int = None,
    server_heartbeat_timeout_sec: int = None,
    client_heartbeat_timeout_sec: int = None,
    heartbeat_interval_sec: int = None,
    max_restart_attempts: int = None,
    restart_cooldown_sec: int = None,
) -> None:
    """
    Save watchdog settings to the database.

    Args:
        enabled: Whether the watchdog is enabled
        run_interval_minutes: The interval between watchdog runs
        server_heartbeat_timeout_sec: Server heartbeat timeout in seconds
        client_heartbeat_timeout_sec: Client heartbeat timeout in seconds
        heartbeat_interval_sec: Expected client heartbeat interval in seconds
        max_restart_attempts: Max restart attempts per incident
        restart_cooldown_sec: Restart cooldown in seconds
    """
    try:
        from flask import current_app

        if current_app:
            from y_web import db
            from y_web.models import WatchdogSettings

            settings = WatchdogSettings.query.first()
            if settings:
                if enabled is not None:
                    settings.enabled = enabled
                if run_interval_minutes is not None:
                    settings.run_interval_minutes = run_interval_minutes
                if server_heartbeat_timeout_sec is not None:
                    settings.server_heartbeat_timeout_sec = server_heartbeat_timeout_sec
                if client_heartbeat_timeout_sec is not None:
                    settings.client_heartbeat_timeout_sec = client_heartbeat_timeout_sec
                if heartbeat_interval_sec is not None:
                    settings.heartbeat_interval_sec = heartbeat_interval_sec
                if max_restart_attempts is not None:
                    settings.max_restart_attempts = max_restart_attempts
                if restart_cooldown_sec is not None:
                    settings.restart_cooldown_sec = restart_cooldown_sec
                db.session.commit()
            else:
                # Create settings row if it doesn't exist
                settings = WatchdogSettings(
                    enabled=enabled if enabled is not None else True,
                    run_interval_minutes=(
                        run_interval_minutes
                        if run_interval_minutes is not None
                        else DEFAULT_RUN_INTERVAL_MINUTES
                    ),
                    server_heartbeat_timeout_sec=(
                        server_heartbeat_timeout_sec
                        if server_heartbeat_timeout_sec is not None
                        else DEFAULT_SERVER_HEARTBEAT_TIMEOUT
                    ),
                    client_heartbeat_timeout_sec=(
                        client_heartbeat_timeout_sec
                        if client_heartbeat_timeout_sec is not None
                        else DEFAULT_CLIENT_HEARTBEAT_TIMEOUT
                    ),
                    heartbeat_interval_sec=(
                        heartbeat_interval_sec
                        if heartbeat_interval_sec is not None
                        else DEFAULT_HEARTBEAT_INTERVAL_SECONDS
                    ),
                    max_restart_attempts=(
                        max_restart_attempts
                        if max_restart_attempts is not None
                        else DEFAULT_MAX_RESTART_ATTEMPTS
                    ),
                    restart_cooldown_sec=(
                        restart_cooldown_sec
                        if restart_cooldown_sec is not None
                        else DEFAULT_RESTART_COOLDOWN
                    ),
                )
                db.session.add(settings)
                db.session.commit()
    except Exception as e:
        logger.debug(f"Could not save watchdog settings to database: {e}")


# Global watchdog instance
_watchdog: Optional[ProcessWatchdog] = None
_watchdog_lock = threading.Lock()


def get_watchdog(
    run_interval_minutes: Optional[int] = None,
    heartbeat_timeout: Optional[int] = None,
    max_restart_attempts: Optional[int] = None,
    restart_cooldown: Optional[int] = None,
    server_heartbeat_timeout: Optional[int] = None,
    client_heartbeat_timeout: Optional[int] = None,
    heartbeat_interval_seconds: Optional[int] = None,
) -> ProcessWatchdog:
    """
    Get or create the global watchdog instance.

    Args:
        run_interval_minutes: How often to run the watchdog check (in minutes)
        heartbeat_timeout: Max time without log activity before considering hung (seconds)
        max_restart_attempts: Maximum restart attempts before giving up
        restart_cooldown: Minimum time between restart attempts (seconds)
        server_heartbeat_timeout: Per-server heartbeat timeout override (seconds)
        client_heartbeat_timeout: Per-client heartbeat timeout override (seconds)
        heartbeat_interval_seconds: Expected heartbeat write interval from clients (seconds)

    Returns:
        The global ProcessWatchdog instance
    """
    global _watchdog

    with _watchdog_lock:
        db_settings = _load_watchdog_settings()
        settings_loaded = bool(db_settings.get("loaded", False))

        if heartbeat_timeout is not None:
            server_heartbeat_timeout = (
                server_heartbeat_timeout
                if server_heartbeat_timeout is not None
                else heartbeat_timeout
            )
            client_heartbeat_timeout = (
                client_heartbeat_timeout
                if client_heartbeat_timeout is not None
                else heartbeat_timeout
            )

        effective_run_interval = (
            run_interval_minutes
            if run_interval_minutes is not None
            else db_settings.get("run_interval_minutes", DEFAULT_RUN_INTERVAL_MINUTES)
        )
        effective_server_timeout = (
            server_heartbeat_timeout
            if server_heartbeat_timeout is not None
            else db_settings.get(
                "server_heartbeat_timeout_sec", DEFAULT_SERVER_HEARTBEAT_TIMEOUT
            )
        )
        effective_client_timeout = (
            client_heartbeat_timeout
            if client_heartbeat_timeout is not None
            else db_settings.get(
                "client_heartbeat_timeout_sec", DEFAULT_CLIENT_HEARTBEAT_TIMEOUT
            )
        )
        effective_max_restarts = (
            max_restart_attempts
            if max_restart_attempts is not None
            else db_settings.get("max_restart_attempts", DEFAULT_MAX_RESTART_ATTEMPTS)
        )
        effective_restart_cooldown = (
            restart_cooldown
            if restart_cooldown is not None
            else db_settings.get("restart_cooldown_sec", DEFAULT_RESTART_COOLDOWN)
        )
        effective_heartbeat_interval = (
            heartbeat_interval_seconds
            if heartbeat_interval_seconds is not None
            else db_settings.get(
                "heartbeat_interval_sec", DEFAULT_HEARTBEAT_INTERVAL_SECONDS
            )
        )
        effective_enabled = bool(db_settings.get("enabled", True))

        if _watchdog is None:
            _watchdog = ProcessWatchdog(
                run_interval_minutes=effective_run_interval,
                heartbeat_timeout=DEFAULT_HEARTBEAT_TIMEOUT,
                max_restart_attempts=effective_max_restarts,
                restart_cooldown=effective_restart_cooldown,
                server_heartbeat_timeout=effective_server_timeout,
                client_heartbeat_timeout=effective_client_timeout,
                heartbeat_interval_seconds=effective_heartbeat_interval,
                enabled=effective_enabled,
            )
            if settings_loaded and db_settings.get("last_run"):
                _watchdog._last_run = db_settings["last_run"]
        else:
            if run_interval_minutes is not None:
                _watchdog.run_interval_minutes = run_interval_minutes
            if max_restart_attempts is not None:
                _watchdog.max_restart_attempts = max_restart_attempts
            if restart_cooldown is not None:
                _watchdog.restart_cooldown = restart_cooldown
            if server_heartbeat_timeout is not None:
                _watchdog.server_heartbeat_timeout = server_heartbeat_timeout
            if client_heartbeat_timeout is not None:
                _watchdog.client_heartbeat_timeout = client_heartbeat_timeout
            if heartbeat_interval_seconds is not None:
                _watchdog.heartbeat_interval_seconds = heartbeat_interval_seconds
            if heartbeat_timeout is not None:
                _watchdog.server_heartbeat_timeout = heartbeat_timeout
                _watchdog.client_heartbeat_timeout = heartbeat_timeout
            if settings_loaded:
                _watchdog.enabled = effective_enabled
                if not effective_enabled and _watchdog.is_running:
                    _watchdog.stop_scheduler()

            if (
                server_heartbeat_timeout is not None
                or client_heartbeat_timeout is not None
                or heartbeat_timeout is not None
            ):
                _watchdog.refresh_registered_timeouts()
        return _watchdog


def stop_watchdog() -> None:
    """Stop and clear the global watchdog instance."""
    global _watchdog

    with _watchdog_lock:
        if _watchdog is not None:
            _watchdog.stop()
            _watchdog = None


def run_watchdog_once() -> Dict:
    """
    Run the watchdog check once immediately.

    Returns:
        Dictionary with results of the watchdog run
    """
    watchdog = get_watchdog()
    return watchdog.run_once()


def set_watchdog_interval(minutes: int) -> None:
    """
    Set the watchdog run interval.

    Args:
        minutes: Interval in minutes between watchdog runs
    """
    set_watchdog_settings(run_interval_minutes=minutes)


def set_watchdog_settings(
    run_interval_minutes: Optional[int] = None,
    server_heartbeat_timeout_sec: Optional[int] = None,
    client_heartbeat_timeout_sec: Optional[int] = None,
    heartbeat_interval_sec: Optional[int] = None,
    max_restart_attempts: Optional[int] = None,
    restart_cooldown_sec: Optional[int] = None,
) -> Dict:
    """
    Update watchdog runtime and persisted settings.

    Returns:
        Updated watchdog status
    """
    watchdog = get_watchdog()

    if run_interval_minutes is not None:
        watchdog.run_interval_minutes = max(1, int(run_interval_minutes))
    if server_heartbeat_timeout_sec is not None:
        watchdog.server_heartbeat_timeout = max(1, int(server_heartbeat_timeout_sec))
    if client_heartbeat_timeout_sec is not None:
        watchdog.client_heartbeat_timeout = max(1, int(client_heartbeat_timeout_sec))
    if heartbeat_interval_sec is not None:
        watchdog.heartbeat_interval_seconds = max(1, int(heartbeat_interval_sec))
    if max_restart_attempts is not None:
        watchdog.max_restart_attempts = max(1, int(max_restart_attempts))
    if restart_cooldown_sec is not None:
        watchdog.restart_cooldown = max(0, int(restart_cooldown_sec))

    if (
        server_heartbeat_timeout_sec is not None
        or client_heartbeat_timeout_sec is not None
    ):
        watchdog.refresh_registered_timeouts()

    _save_watchdog_settings(
        run_interval_minutes=(
            watchdog.run_interval_minutes if run_interval_minutes is not None else None
        ),
        server_heartbeat_timeout_sec=(
            watchdog.server_heartbeat_timeout
            if server_heartbeat_timeout_sec is not None
            else None
        ),
        client_heartbeat_timeout_sec=(
            watchdog.client_heartbeat_timeout
            if client_heartbeat_timeout_sec is not None
            else None
        ),
        heartbeat_interval_sec=(
            watchdog.heartbeat_interval_seconds
            if heartbeat_interval_sec is not None
            else None
        ),
        max_restart_attempts=(
            watchdog.max_restart_attempts if max_restart_attempts is not None else None
        ),
        restart_cooldown_sec=(
            watchdog.restart_cooldown if restart_cooldown_sec is not None else None
        ),
    )
    return get_watchdog_status()


def set_watchdog_enabled(enabled: bool) -> Dict:
    """
    Enable/disable the watchdog scheduler and persist the flag.

    Returns:
        Updated watchdog status
    """
    watchdog = get_watchdog()
    watchdog.enabled = bool(enabled)
    _save_watchdog_settings(enabled=watchdog.enabled)

    if watchdog.enabled:
        watchdog.start_scheduler()
    else:
        watchdog.stop_scheduler()

    return get_watchdog_status()


def get_watchdog_status() -> Dict:
    """
    Get the current watchdog status.

    Returns:
        Dictionary with watchdog status information
    """
    watchdog = get_watchdog()
    status = watchdog.get_status()

    # Reconcile last_run with persisted values if missing from in-memory watchdog.
    if status.get("last_run") is None:
        db_settings = _load_watchdog_settings()
        if db_settings.get("last_run"):
            status["last_run"] = (
                db_settings["last_run"].isoformat()
                if hasattr(db_settings["last_run"], "isoformat")
                else db_settings["last_run"]
            )

    return status
