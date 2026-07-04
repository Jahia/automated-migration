#!/usr/bin/env python3
"""smoke_llm.py — one tiny REAL call to prove the direct LLM client works.

Runs OUTSIDE pytest (pytest never touches the network). It reads the engine
config (ORCHESTRATOR_LLM_* from migration-orchestrator/.env or the process env),
makes ONE minimal chat() call, and prints ONLY the model and the usage block.

It NEVER prints the API key. If ORCHESTRATOR_LLM_API_KEY is absent it prints a
notice and exits 0 (so CI without a key is a no-op, not a failure).

    cd migration-orchestrator && .venv/bin/python scripts/smoke_llm.py
"""
from __future__ import annotations

import asyncio
import os
import sys

# Make `import src...` work when run from the package root.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from src.config import settings  # noqa: E402
from src.llm_client import LLMClient, LLMError  # noqa: E402


async def _main() -> int:
    if not settings.llm_configured:
        print("ORCHESTRATOR_LLM_API_KEY not set — skipping smoke test (no-op).")
        return 0

    client = LLMClient()
    try:
        message, usage = await client.chat(
            messages=[{"role": "user", "content": "Reply with the single word: pong"}],
            timeout=60.0,
        )
    except LLMError as e:
        # Never prints the key; the message may include a provider error body.
        print(f"SMOKE FAILED: {e}")
        return 1
    finally:
        await client.aclose()

    # Print ONLY model + usage (never the key, never the full message content to
    # keep the output boring/safe — a short content flag is fine).
    print(f"model={client.model}")
    print(f"usage={usage}")
    print(f"got_content={bool((message or {}).get('content'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
