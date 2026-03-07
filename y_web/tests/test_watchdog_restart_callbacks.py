"""
Regression tests for watchdog restart callback and fixed-port behavior.
"""

import inspect

from y_web.utils import external_processes


def test_server_restart_callback_uses_captured_app_context():
    """Server restart callback must not instantiate a new default app."""
    source = inspect.getsource(external_processes._register_server_with_watchdog)
    assert "current_app._get_current_object()" in source
    assert "create_app()" not in source


def test_client_restart_callback_uses_captured_app_context():
    """Client restart callback must not instantiate a new default app."""
    source = inspect.getsource(external_processes._register_client_with_watchdog)
    assert "current_app._get_current_object()" in source
    assert "create_app()" not in source


def test_postgresql_start_server_keeps_assigned_port():
    """PostgreSQL start path should keep experiment-assigned port stable."""
    source = inspect.getsource(external_processes.start_server)
    assert "stable-port mode" in source
    assert "_update_server_port_in_configs(exp, old_port, force=True)" in source
    assert "refusing to rotate ports" in source
