"""Cost tracker for migration runs.

Calculates costs based on model pricing and writes a local cost report.
Not committed — lives in migration-orchestrator/costs/.

DeepSeek V4 Flash pricing (public, 2025):
  Input:      $0.07  per 1M tokens
  Output:     $0.28  per 1M tokens
  Cache read: $0.014 per 1M tokens (80% discount)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

# Model pricing: (input_per_1m, output_per_1m, cache_read_per_1m)
MODEL_PRICING = {
    "deepseek/deepseek-v4-flash": (0.07, 0.28, 0.014),
    "deepseek/deepseek-v4-pro": (0.27, 1.10, 0.07),
    "anthropic/claude-sonnet-4-5": (3.00, 15.00, 0.30),
}

DEFAULT_PRICING = (0.07, 0.28, 0.014)  # DeepSeek V4 Flash


def calculate_cost(tokens_in: int, tokens_out: int, tokens_cache: int = 0,
                   model: str = "deepseek/deepseek-v4-flash") -> dict:
    """Calculate cost for a step/run based on token counts."""
    pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)
    input_rate, output_rate, cache_rate = pricing

    cost_in = (tokens_in / 1_000_000) * input_rate
    cost_out = (tokens_out / 1_000_000) * output_rate
    cost_cache = (tokens_cache / 1_000_000) * cache_rate
    total = cost_in + cost_out + cost_cache

    return {
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_cache": tokens_cache,
        "cost_input": round(cost_in, 6),
        "cost_output": round(cost_out, 6),
        "cost_cache": round(cost_cache, 6),
        "cost_total": round(total, 6),
        "model": model,
        "pricing": {
            "input_per_1m": input_rate,
            "output_per_1m": output_rate,
            "cache_read_per_1m": cache_rate,
        }
    }


def write_run_cost(run_id: str, model: str, steps: list[dict],
                   cost_dir: str | Path = "migration-orchestrator/costs") -> dict:
    """Write a cost report for a completed run.

    Args:
        run_id: The run ID
        model: Model identifier (e.g. "deepseek/deepseek-v4-flash")
        steps: List of step dicts with tokens_in, tokens_out, tokens_cache, duration_ms
        cost_dir: Directory to write cost files

    Returns:
        The cost report dict
    """
    cost_dir = Path(cost_dir)
    cost_dir.mkdir(parents=True, exist_ok=True)

    # Calculate per-step costs
    step_costs = []
    total_in = 0
    total_out = 0
    total_cache = 0

    for step in steps:
        tokens_in = step.get("tokens_in", 0)
        tokens_out = step.get("tokens_out", 0)
        tokens_cache = step.get("tokens_cache", 0)

        total_in += tokens_in
        total_out += tokens_out
        total_cache += tokens_cache

        step_cost = calculate_cost(tokens_in, tokens_out, tokens_cache, model)
        step_cost["step_id"] = step.get("step_id", "?")
        step_cost["story_id"] = step.get("story_id", "?")
        step_cost["epic_id"] = step.get("epic_id", "?")
        step_cost["duration_ms"] = step.get("duration_ms")
        step_costs.append(step_cost)

    # Calculate total
    total_cost = calculate_cost(total_in, total_out, total_cache, model)

    report = {
        "run_id": run_id,
        "model": model,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": {
            "tokens_in": total_in,
            "tokens_out": total_out,
            "tokens_cache": total_cache,
            **total_cost,
        },
        "steps": step_costs,
        "step_count": len(step_costs),
    }

    # Write to file
    filename = f"{run_id}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    filepath = cost_dir / filename
    with open(filepath, "w") as f:
        json.dump(report, f, indent=2)

    return report


def format_cost_summary(report: dict) -> str:
    """Format a human-readable cost summary."""
    total = report["total"]
    lines = [
        f"=== RUN COST: {report['run_id']} ===",
        f"Model: {report['model']}",
        f"Steps: {report['step_count']}",
        "",
        f"Tokens input:  {total['tokens_in']:>12,}",
        f"Tokens output: {total['tokens_out']:>12,}",
        f"Tokens cache:  {total['tokens_cache']:>12,}",
        "",
        f"Cost input:    ${total['cost_input']:>10.4f}",
        f"Cost output:   ${total['cost_output']:>10.4f}",
        f"Cost cache:    ${total['cost_cache']:>10.4f}",
        f"─────────────────────────",
        f"TOTAL:         ${total['cost_total']:>10.4f}",
    ]

    # Per-step breakdown if interesting
    if report["steps"]:
        expensive = sorted(report["steps"], key=lambda s: s["cost_total"], reverse=True)[:3]
        if expensive and expensive[0]["cost_total"] > 0:
            lines.append("")
            lines.append("Most expensive steps:")
            for s in expensive:
                if s["cost_total"] > 0:
                    lines.append(f"  {s['step_id']:30s} ${s['cost_total']:.4f}  ({s['tokens_in']:,} in / {s['tokens_out']:,} out)")

    return "\n".join(lines)
