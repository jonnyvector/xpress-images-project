"""Shared helpers for the onboarding driver scripts."""

import os

from dotenv import load_dotenv


def read_api_key() -> str:
    """GEMINI_API_KEY from the project .env, overriding any stale shell export
    (zshrc shadows .env — see the gemini-key-gotchas memory)."""
    load_dotenv(override=True)
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise SystemExit("GEMINI_API_KEY not found in .env")
    return key
