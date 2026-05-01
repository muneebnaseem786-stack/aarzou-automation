"""
X Hook Jury — generates 3 hook options then runs 3 parallel agents to pick and improve the best one.

Pipeline:
  1. generate_x_hooks(post_type, context)  →  [hook1, hook2, hook3]
  2. run_x_jury(hooks, post_type, context)  →  winning_hook (str)
  3. get_best_hook(post_type, context)       →  winning_hook (str)  [full pipeline]
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from .claude_client import load_prompt, call_claude, call_claude_json

JURORS = [
    "x_jury_scroll_stopper",
    "x_jury_curiosity_engine",
    "x_jury_universal_trap",
]


def generate_x_hooks(post_type: str, context: str) -> list[str]:
    """Generate 3 hook options using the x_hook_prompt."""
    template = load_prompt("x_hook_prompt")
    prompt = template.format(post_type=post_type, context=context)
    result = call_claude_json(prompt, max_tokens=800)
    if isinstance(result, list):
        return [str(h) for h in result[:3]]
    raise ValueError(f"Hook prompt returned unexpected format: {type(result)}")


def _run_juror(juror_name: str, hooks: list[str], post_type: str, context: str) -> dict:
    """Run one juror agent. Returns its verdict dict."""
    template = load_prompt(juror_name)
    hooks_block = "\n\n".join(f"Hook {i+1}: {h}" for i, h in enumerate(hooks))
    prompt = template.format(post_type=post_type, context=context, hooks=hooks_block)
    try:
        return call_claude_json(prompt, max_tokens=600)
    except Exception as e:
        # Return neutral scores on failure so the pipeline doesn't break
        return {"scores": [5, 5, 5], "best_index": 0, "improved_hook": hooks[0]}


def run_x_jury(hooks: list[str], post_type: str, context: str) -> str:
    """
    Run all 3 jurors in parallel. Aggregate scores to find the best hook index,
    then pick the improved_hook from the juror who scored it highest.
    Returns the winning hook string.
    """
    verdicts = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_run_juror, name, hooks, post_type, context): name
            for name in JURORS
        }
        for future in as_completed(futures):
            try:
                verdicts.append(future.result())
            except Exception:
                pass

    if not verdicts:
        return hooks[0]

    # Aggregate scores across all jurors
    n = len(hooks)
    totals = [0.0] * n
    for verdict in verdicts:
        scores = verdict.get("scores", [])
        for i in range(min(n, len(scores))):
            totals[i] += scores[i]

    best_idx = totals.index(max(totals))

    # Find the juror who scored the winning hook highest — use their improved_hook
    best_juror_verdict = max(
        verdicts,
        key=lambda v: v.get("scores", [0] * n)[best_idx] if len(v.get("scores", [])) > best_idx else 0,
    )
    improved = best_juror_verdict.get("improved_hook", "").strip()
    return improved if improved else hooks[best_idx]


def get_best_hook(post_type: str, context: str) -> str:
    """Full pipeline: generate 3 hooks → jury → return winning hook."""
    hooks = generate_x_hooks(post_type, context)
    return run_x_jury(hooks, post_type, context)
