from .claude_client import load_prompt, call_claude_json


def extract_shorts(topic: str, full_script: str) -> list[dict]:
    """
    Returns 4-5 Short concept dicts:
      { title, script_text, visual_note, source_chapter }
    """
    prompt_template = load_prompt("shorts_prompt")
    prompt = prompt_template.format(topic=topic, full_script=full_script)
    shorts = call_claude_json(prompt, max_tokens=4000)
    if not isinstance(shorts, list):
        raise ValueError(f"Expected list from shorts extractor, got: {type(shorts)}")
    return shorts
