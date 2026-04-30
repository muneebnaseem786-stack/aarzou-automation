from .claude_client import load_prompt, call_claude_json


def _generate(topic: str, fr_angle: str, count: int) -> list[dict]:
    prompt_template = load_prompt("hook_prompt")
    prompt = prompt_template.format(topic=topic, fr_angle=fr_angle, count=count)
    hooks = call_claude_json(prompt, max_tokens=4000)
    if not isinstance(hooks, list):
        raise ValueError(f"Expected list from hook generator, got: {type(hooks)}")
    for i, h in enumerate(hooks):
        if "hook_text" not in h or "hook_type" not in h:
            raise ValueError(f"Hook {i} missing required fields: {list(h.keys())}")
    return hooks


def generate_hooks(topic: str, fr_angle: str) -> list[dict]:
    """Generate 3 hooks (legacy — used when jury is skipped)."""
    return _generate(topic, fr_angle, count=3)


def generate_hooks_extended(topic: str, fr_angle: str, count: int = 5) -> list[dict]:
    """Generate a larger pool for the jury to evaluate."""
    return _generate(topic, fr_angle, count=count)
