"""Tests for experiment clock configuration helpers."""

from datetime import date, datetime

import pytest

from y_web.utils.experiment_clock import (
    apply_clock_to_client_simulation,
    ensure_experiment_clock,
    parse_anchor_date,
    validate_clock_mode,
    validate_feed_refresh,
    validate_timezone,
    wall_clock_slot,
)


def test_validate_clock_mode():
    assert validate_clock_mode("simulated") == "simulated"
    assert validate_clock_mode("REAL_TIME") == "real_time"

    with pytest.raises(ValueError):
        validate_clock_mode("fast")


def test_validate_feed_refresh():
    assert validate_feed_refresh("hourly") == "hourly"

    with pytest.raises(ValueError):
        validate_feed_refresh("daily")


def test_validate_timezone():
    assert validate_timezone("Europe/Belgrade") == "Europe/Belgrade"

    with pytest.raises(ValueError):
        validate_timezone("Invalid/TZ")


def test_ensure_experiment_clock_defaults():
    config = {"name": "Experiment A"}
    clock = ensure_experiment_clock(config)

    assert clock["mode"] == "simulated"
    assert clock["timezone"] == "Europe/Belgrade"
    assert clock["feed_refresh"] == "hourly"
    assert "clock" in config


def test_ensure_experiment_clock_keeps_anchor_date():
    config = {
        "clock": {
            "mode": "real_time",
            "timezone": "Europe/Belgrade",
            "feed_refresh": "hourly",
            "anchor_date": "2026-02-14",
        }
    }
    clock = ensure_experiment_clock(config)
    assert clock["anchor_date"] == "2026-02-14"


def test_apply_clock_to_client_simulation():
    simulation = {"name": "client1"}
    apply_clock_to_client_simulation(
        simulation,
        {
            "mode": "real_time",
            "timezone": "Europe/Belgrade",
            "feed_refresh": "hourly",
            "anchor_date": "2026-02-14",
        },
    )

    assert simulation["clock_mode"] == "real_time"
    assert simulation["timezone"] == "Europe/Belgrade"
    assert simulation["feed_refresh"] == "hourly"
    assert simulation["clock_anchor_date"] == "2026-02-14"


def test_parse_anchor_date():
    assert parse_anchor_date("2026-02-14") == date(2026, 2, 14)
    assert parse_anchor_date("") is None
    assert parse_anchor_date("bad-date") is None


def test_wall_clock_slot_with_anchor():
    now_local = datetime(2026, 2, 16, 13, 5, 0)
    day, hour = wall_clock_slot(now_local, date(2026, 2, 14))
    assert day == 2
    assert hour == 13
