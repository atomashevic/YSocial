"""Helpers for memory run identifier normalization."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

MAX_MEMORY_RUN_ID_LEN = 64


def normalize_memory_run_id(
    raw_value: Any,
    *,
    max_len: int = MAX_MEMORY_RUN_ID_LEN,
) -> Optional[str]:
    """Return a DB-safe memory run id or None when input is empty."""
    value = str(raw_value or "").strip()
    if not value:
        return None
    if len(value) <= max_len:
        return value

    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:24]
    return f"run_{digest}"


def build_memory_run_seed(exp_uid: str, client_name: str, population_name: str) -> str:
    """Build deterministic seed used to derive a stable run id."""
    return (
        f"exp:{str(exp_uid).strip()}:"
        f"client:{str(client_name).strip().replace(' ', '_')}:"
        f"population:{str(population_name).strip().replace(' ', '_')}"
    )


def normalize_client_config_memory_run_id(
    client_config: Dict[str, Any],
    *,
    fallback_seed: Optional[str] = None,
) -> bool:
    """
    Normalize `agents.memory_run_id` in a client config payload.

    Returns True if payload was modified.
    """
    if not isinstance(client_config, dict):
        return False

    agents = client_config.get("agents")
    if not isinstance(agents, dict):
        return False

    current = agents.get("memory_run_id")
    normalized = normalize_memory_run_id(current)
    if not normalized and fallback_seed:
        normalized = normalize_memory_run_id(fallback_seed)

    if not normalized or normalized == current:
        return False

    agents["memory_run_id"] = normalized
    return True
