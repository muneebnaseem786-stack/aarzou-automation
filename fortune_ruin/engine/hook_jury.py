"""
Jury of agents that evaluate generated hooks in parallel.

Flow:
  1. generate_hooks() produces 5-7 raw hooks (expanded from 3)
  2. run_jury() fires 3 specialist agents concurrently against all hooks
  3. aggregate_verdicts() merges scores and ranks
  4. Returns top 3 hooks with full jury breakdown
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from .claude_client import load_prompt, call_claude_json

JUROR_PROMPTS = [
    ("hook_architect",    "jury_hook_architect"),
    ("algorithm_analyst", "jury_algorithm_analyst"),
    ("audience_advocate", "jury_audience_advocate"),
]

JUROR_LABELS = {
    "hook_architect":    "🏗️ Hook Architect",
    "algorithm_analyst": "📊 Algorithm Analyst",
    "audience_advocate": "👥 Audience Advocate",
}


def _build_hooks_block(hooks: list[dict]) -> str:
    lines = []
    for i, h in enumerate(hooks):
        lines.append(f"HOOK {i} [{h.get('hook_type', 'unknown').upper()}]:")
        lines.append(h["hook_text"])
        lines.append("")
    return "\n".join(lines)


def _call_juror(juror_name: str, prompt_name: str, topic: str, fr_angle: str, hooks_block: str) -> tuple[str, list]:
    template = load_prompt(prompt_name)
    prompt = template.format(topic=topic, fr_angle=fr_angle, hooks_block=hooks_block)
    result = call_claude_json(prompt, max_tokens=3000)
    if not isinstance(result, list):
        raise ValueError(f"Juror {juror_name} returned non-list: {type(result)}")
    return juror_name, result


def run_jury(hooks: list[dict], topic: str, fr_angle: str) -> list[dict]:
    """
    Run all 3 jurors in parallel against the hooks list.
    Returns merged list of hook dicts, each with 'jury' key containing per-juror scores.
    """
    hooks_block = _build_hooks_block(hooks)
    juror_results: dict[str, list] = {}

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_call_juror, juror_name, prompt_name, topic, fr_angle, hooks_block): juror_name
            for juror_name, prompt_name in JUROR_PROMPTS
        }
        for future in as_completed(futures):
            juror_name = futures[future]
            try:
                name, verdicts = future.result()
                juror_results[name] = verdicts
            except Exception as e:
                # If a juror fails, fill with zeros so ranking still works
                juror_results[juror_name] = [
                    {"hook_index": i, "total": 0, "verdict": f"Juror failed: {e}", "improvement": "", "scores": {}}
                    for i in range(len(hooks))
                ]

    # Merge jury verdicts into hook objects
    enriched = []
    for i, hook in enumerate(hooks):
        hook_copy = dict(hook)
        hook_copy["jury"] = {}
        aggregate = 0

        for juror_name, _ in JUROR_PROMPTS:
            verdicts = juror_results.get(juror_name, [])
            # Find the verdict for this hook index (juror might return them out of order)
            verdict = next((v for v in verdicts if v.get("hook_index") == i), None)
            if verdict is None and i < len(verdicts):
                verdict = verdicts[i]  # Fallback: positional
            if verdict:
                hook_copy["jury"][juror_name] = verdict
                aggregate += verdict.get("total", 0)
            else:
                hook_copy["jury"][juror_name] = {"total": 0, "verdict": "No verdict", "improvement": "", "scores": {}}

        hook_copy["aggregate_score"] = aggregate
        hook_copy["max_possible"] = 30  # 3 jurors × 10 points each
        enriched.append(hook_copy)

    return enriched


def select_top_3(enriched_hooks: list[dict]) -> list[dict]:
    """Sort by aggregate score descending, return top 3."""
    ranked = sorted(enriched_hooks, key=lambda h: h["aggregate_score"], reverse=True)
    return ranked[:3]


def generate_and_evaluate_hooks(topic: str, fr_angle: str) -> list[dict]:
    """
    Full pipeline:
      1. Generate 5 hooks (broader search space for jury to rank)
      2. Run jury in parallel
      3. Return top 3 with jury verdicts
    """
    from .hook_generator import generate_hooks_extended
    raw_hooks = generate_hooks_extended(topic, fr_angle, count=5)
    enriched = run_jury(raw_hooks, topic, fr_angle)
    top3 = select_top_3(enriched)
    return top3
