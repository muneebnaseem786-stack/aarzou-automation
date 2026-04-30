import os
import json
from pathlib import Path
import anthropic
from dotenv import load_dotenv

# Load .env from the fortune_ruin root folder
load_dotenv(Path(__file__).parent.parent / ".env")

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not set. Add it to your environment or .env file."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def call_claude(prompt: str, max_tokens: int = 4096, model: str = "claude-sonnet-4-6") -> str:
    client = get_client()
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system="You are a professional content creator for Fortune & Ruin, a forensic financial history YouTube channel.",
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def call_claude_json(prompt: str, max_tokens: int = 4096) -> list | dict:
    raw = call_claude(prompt, max_tokens=max_tokens)
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        inner = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        text = inner.strip()
    return json.loads(text)
