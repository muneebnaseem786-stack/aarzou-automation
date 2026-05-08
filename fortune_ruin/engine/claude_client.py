import os
import json
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv

# Load .env from the fortune_ruin root folder
load_dotenv(Path(__file__).parent.parent / ".env")

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

SYSTEM_PROMPT = "You are a professional content creator for Fortune & Ruin, a forensic financial history YouTube channel."

_model = None


def get_model() -> genai.GenerativeModel:
    global _model
    if _model is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY not set. Add it to your environment or .env file."
            )
        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=SYSTEM_PROMPT,
        )
    return _model


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def call_claude(prompt: str, max_tokens: int = 4096, model: str = None) -> str:
    response = get_model().generate_content(
        prompt,
        generation_config=genai.GenerationConfig(max_output_tokens=max_tokens),
    )
    return response.text


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
