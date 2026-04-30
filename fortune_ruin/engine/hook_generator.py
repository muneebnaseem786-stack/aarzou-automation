from .claude_client import load_prompt, call_claude_json


def generate_hooks(topic: str, fr_angle: str) -> list[dict]:
    """
    Returns a list of 3 hook dicts:
      { hook_type, hook_text, trap_check }
    """
    prompt_template = load_prompt("hook_prompt")
    prompt = prompt_template.format(topic=topic, fr_angle=fr_angle)
    hooks = call_claude_json(prompt, max_tokens=3000)
    if not isinstance(hooks, list):
        raise ValueError(f"Expected list from hook generator, got: {type(hooks)}")
    for i, h in enumerate(hooks):
        if "hook_text" not in h or "hook_type" not in h:
            raise ValueError(f"Hook {i} missing required fields: {h.keys()}")
    return hooks
