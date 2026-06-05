"""F&R LLM helper. Thin wrapper around the unified llm.py provider chain.

Public API preserved for backward compatibility:
    call_claude(prompt, max_tokens=4096, model=None) -> str
    call_claude_json(prompt, max_tokens=4096) -> list | dict
    SYSTEM_PROMPT, PROMPTS_DIR, load_prompt(name)

Provider chain (Kimi K2 → Llama 3.3 → Gemini Flash → OpenRouter Kimi K2.6 →
OpenRouter Nemotron 550B) lives in llm.py.
"""

from pathlib import Path
from dotenv import load_dotenv

# Load .env from the fortune_ruin root folder
load_dotenv(Path(__file__).parent.parent / ".env")

from .llm import call_llm, parse_json_response  # noqa: E402

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

SYSTEM_PROMPT = (
    "You are a professional content creator for Fortune & Ruin, "
    "a forensic financial history YouTube channel."
)


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def call_claude(prompt: str, max_tokens: int = 4096, model: str = None) -> str:
    """Call LLM with F&R system prompt. `model` argument accepted for backward
    compat but ignored (provider chain decides)."""
    return call_llm(prompt, max_tokens=max_tokens, temperature=0.7, system=SYSTEM_PROMPT)


def call_claude_json(prompt: str, max_tokens: int = 4096):
    """Call LLM and parse JSON response, stripping markdown fences if present."""
    return parse_json_response(call_claude(prompt, max_tokens=max_tokens))
