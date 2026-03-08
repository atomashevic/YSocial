from y_web.routes_api import interview


def test_parse_timeout_series_uses_positive_numbers_only():
    parsed = interview._parse_timeout_series(" 2, bad, 0, -4, 6.5 ", (9.0,))

    assert parsed == (2.0, 6.5)


def test_build_memory_snapshot_legacy_uses_interview_events_timeouts(monkeypatch):
    captured = {}

    def fake_post_server_json(exp, path, payload, *, timeout_s=4.0):
        assert path == "/memory/get_context"
        return {}

    def fake_post_server_json_with_retries(
        exp,
        path,
        payload,
        *,
        timeouts_s,
        require_status_200=False,
    ):
        captured["path"] = path
        captured["timeouts_s"] = timeouts_s
        captured["payload"] = payload
        return {"events": []}

    monkeypatch.setattr(interview, "_post_server_json", fake_post_server_json)
    monkeypatch.setattr(
        interview, "_post_server_json_with_retries", fake_post_server_json_with_retries
    )

    snapshot = interview._build_memory_snapshot_legacy(
        object(), run_id="run_123", agent_user_id=28
    )

    assert snapshot["run_id"] == "run_123"
    assert captured["path"] == "/memory/events_recent"
    assert captured["payload"] == {"run_id": "run_123", "limit": 200}
    assert captured["timeouts_s"] == interview._INTERVIEW_MEMORY_EVENTS_TIMEOUTS


def test_build_memory_snapshot_semantic_uses_interview_search_timeouts(monkeypatch):
    captured = {}

    def fake_post_server_json(exp, path, payload, *, timeout_s=4.0):
        assert path == "/memory/get_context"
        return {}

    def fake_post_server_json_with_retries(
        exp,
        path,
        payload,
        *,
        timeouts_s,
        require_status_200=False,
    ):
        captured["path"] = path
        captured["timeouts_s"] = timeouts_s
        captured["payload"] = payload
        captured["require_status_200"] = require_status_200
        return {"status": 200, "items": [], "memory_brief": "", "retrieval_meta": {}}

    monkeypatch.setattr(interview, "_post_server_json", fake_post_server_json)
    monkeypatch.setattr(
        interview, "_post_server_json_with_retries", fake_post_server_json_with_retries
    )

    snapshot = interview._build_memory_snapshot_semantic(
        object(), run_id="run_456", agent_user_id=28
    )

    assert snapshot["run_id"] == "run_456"
    assert captured["path"] == "/memory/search"
    assert captured["payload"]["run_id"] == "run_456"
    assert captured["payload"]["agent_user_id"] == 28
    assert captured["require_status_200"] is True
    assert captured["timeouts_s"] == interview._INTERVIEW_MEMORY_SEARCH_TIMEOUTS


def test_build_deferred_memory_snapshot_marks_load_state():
    snapshot = interview._build_deferred_memory_snapshot(
        run_id="run_789",
        agent_user_id=28,
        memory_mode="semantic",
    )

    assert snapshot["run_id"] == "run_789"
    assert snapshot["agent_user_id"] == 28
    assert snapshot["memory_mode_requested"] == "semantic"
    assert snapshot["memory_mode_used"] == ""
    assert snapshot["load_state"] == "deferred"
    assert snapshot["relationships"] == []


def test_detect_run_id_from_server_log_can_skip_coverage_probe(monkeypatch):
    monkeypatch.setattr(
        interview,
        "_iter_run_ids_from_server_log",
        lambda exp, agent_user_id=None: ["run_fast"] if agent_user_id == 28 else [],
    )

    def fail_probe(*args, **kwargs):
        raise AssertionError("coverage probe should not run in fast mode")

    monkeypatch.setattr(interview, "_probe_run_memory_coverage", fail_probe)

    out = interview._detect_run_id_from_server_log(
        object(),
        agent_user_id=28,
        probe_memory_coverage=False,
    )

    assert out["run_id"] == "run_fast"
    assert out["source"] == "log_scan_latest"
    assert out["selected_reason"] == "latest_agent_run_unprobed"
    assert out["candidates_checked"] == []
