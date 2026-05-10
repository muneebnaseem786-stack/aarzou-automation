import os
import json
import time
from pathlib import Path
import requests
from dotenv import load_dotenv

# Load .env from the fortune_ruin root folder
load_dotenv(Path(__file__).parent.parent / ".env")

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

SYSTEM_PROMPT = "You are a professional content creator for Fortune & Ruin, a forensic financial history YouTube channel."

GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash"


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def _call_groq(prompt: str, max_tokens: int = 4096) -> str:
    """Call Groq Llama 3.3 70B (free tier, 1000 RPD). Raises on failure."""
    api_key = os.environ["GROQ_API_KEY"]
    last_error = None
    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                },
                timeout=90,
            )
            if resp.status_code == 429 and attempt < 2:
                wait = 30 * (attempt + 1)
                print(f"[llm] Groq 429, retrying in {wait}s (attempt {attempt + 1}/3)")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last_error = e
            if attempt < 2:
                time.sleep(5)
                continue
    raise last_error or RuntimeError("Groq call failed")


def _call_gemini(prompt: str, max_tokens: int = 4096) -> str:
    """Call Gemini 2.0 Flash. Raises on failure."""
    import google.generativeai as genai
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set (Gemini fallback unavailable).")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name=GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)
    for attempt in range(3):
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(max_output_tokens=max_tokens),
            )
            return response.text
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                wait = 60 * (attempt + 1)
                print(f"[llm] Gemini 429, retrying in {wait}s (attempt {attempt + 1}/3)")
                time.sleep(wait)
                continue
            raise


def call_claude(prompt: str, max_tokens: int = 4096, model: str = None) -> str:
    """Call LLM. Gemini primary (better quality on these nuanced prompts),
    Groq fallback when Gemini 429s or is unavailable."""
    if os.environ.get("GEMINI_API_KEY"):
        try:
            return _call_gemini(prompt, max_tokens=max_tokens)
        except Exception as e:
            print(f"[llm] Gemini failed: {e}, falling back to Groq")
    return _call_groq(prompt, max_tokens=max_tokens)


def call_claude_json(prompt: str, max_tokens: int = 4096) -> list | dict:
    raw = call_claude(prompt, max_tokens=max_tokens)
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        inner = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        text = inner.strip()
    return json.loads(text)
