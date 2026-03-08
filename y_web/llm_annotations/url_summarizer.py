"""
URL summarization using text-capable LLMs.

This module provides a small helper around AutoGen's AssistantAgent to produce
short summaries for externally shared links. It is designed to be optional:
if no LLM backend is configured, callers should treat summarization as disabled.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests
from autogen import AssistantAgent
from bs4 import BeautifulSoup


def _normalize_llm_base_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"http://{url}"
    if not url.endswith("/v1"):
        url = url.rstrip("/") + "/v1"
    return url


def _default_base_url_from_env() -> str:
    base_url = os.getenv("LLM_URL") or ""
    if base_url:
        return base_url
    backend = os.getenv("LLM_BACKEND")
    if backend == "vllm":
        return "http://127.0.0.1:8000/v1"
    if backend == "ollama":
        return "http://127.0.0.1:11434/v1"
    if backend and ":" in backend and backend not in {"ollama", "vllm"}:
        return _normalize_llm_base_url(backend)
    return ""


def extract_readable_text(html: str) -> str:
    """
    Extract human-readable page text from HTML.

    We intentionally keep this very simple (no extra dependencies like readability-lxml).
    """
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "canvas"]):
        try:
            tag.decompose()
        except Exception:
            pass

    def clean(s: str) -> str:
        return re.sub(r"\s+", " ", s or "").strip()

    article = soup.find("article")
    if article:
        text = clean(article.get_text(" ", strip=True))
        if len(text) >= 200:
            return text

    parts: list[str] = []
    h1 = soup.find("h1")
    if h1:
        parts.append(clean(h1.get_text(" ", strip=True)))

    for p in soup.find_all("p"):
        t = clean(p.get_text(" ", strip=True))
        if len(t) >= 60:
            parts.append(t)
        if len(parts) >= 30:
            break

    if not parts:
        return clean(soup.get_text(" ", strip=True))

    return "\n".join([p for p in parts if p])


@dataclass(frozen=True)
class SummarizerConfig:
    model: str
    base_url: str


class UrlSummarizer:
    """LLM-backed URL summarizer."""

    def __init__(self, cfg: SummarizerConfig):
        self.cfg = cfg

        self._agent = AssistantAgent(
            name="url-summarizer",
            llm_config={
                "cache_seed": None,
                "config_list": [
                    {
                        "model": cfg.model,
                        "base_url": cfg.base_url,
                        "timeout": 10000,
                        "api_type": "open_ai",
                        "api_key": "NULL",
                        "price": [0, 0],
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 250,
            },
            system_message=(
                "You summarize web pages.\n"
                "Return 2-4 neutral sentences, no markdown, no quotes.\n"
                "Keep it under 500 characters.\n"
            ),
            max_consecutive_auto_reply=1,
        )

        self._user = AssistantAgent(
            name="url-summarizer-user", max_consecutive_auto_reply=0
        )

    @staticmethod
    def is_enabled(model: Optional[str], base_url: Optional[str]) -> bool:
        return bool((model or "").strip()) and bool((base_url or "").strip())

    @staticmethod
    def build_config(
        model: Optional[str], base_url: Optional[str]
    ) -> Optional[SummarizerConfig]:
        model = (model or "").strip()
        if not model:
            return None

        url = _normalize_llm_base_url(base_url or "") if base_url else ""
        if not url:
            url = _default_base_url_from_env()
        url = _normalize_llm_base_url(url)
        if not url:
            return None

        return SummarizerConfig(model=model, base_url=url)

    def summarize_url(self, url: str, *, timeout_s: int = 10) -> Optional[str]:
        url = (url or "").strip()
        if not url:
            return None
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return None

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=timeout_s)
        resp.raise_for_status()

        text = extract_readable_text(resp.text).strip()
        if not text:
            return None

        text = text[:12000]

        self._user.initiate_chat(
            self._agent,
            silent=True,
            message=(
                "Summarize the page content below.\n\n"
                "##BEGIN PAGE TEXT##\n"
                f"{text}\n"
                "##END PAGE TEXT##\n"
            ),
        )

        try:
            content = self._agent.chat_messages[self._user][-1]["content"]
        except Exception:
            return None

        summary = re.sub(r"\s+", " ", (content or "").strip()).strip()
        if not summary:
            return None
        if len(summary) > 500:
            summary = summary[:497].rstrip() + "..."
        return summary
