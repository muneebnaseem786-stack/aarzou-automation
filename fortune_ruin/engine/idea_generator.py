"""
Idea Generation Engine — Fortune & Ruin

How this works:
  1. Claude Code (this session) gathers signals using VidIQ MCP + Chrome browser
  2. Those signals are passed to generate_ideas_from_signals() as plain text
  3. Claude synthesises 8 ranked F&R episode ideas and returns them
  4. Ideas are inserted into the DB — they appear in the dashboard pipeline

No external API keys or credentials required.
"""

from .claude_client import load_prompt, call_claude_json

# ── REFERENCE DATA ────────────────────────────────────────────────────────────

COVERED_TOPICS = [
    "Jekyll Island 1910 / Fed founding",
    "Rockefeller / Standard Oil / Gilded Age",
    "Spanish Empire / Price Revolution / silver debasement",
    "Operation Bernhard / WWII counterfeiting",
    "City of London / financial sovereignty",
    "Iran shadow economy / IRGC",
    "BIS / supranational banking / Basel",
    "Dollar reserve status / petrodollar / de-dollarization",
    "Japan 1989 bubble / Nikkei / Plaza Accord",
    "South Sea Company 1720 / Isaac Newton",
    "FDR Executive Order 6102 / 1933 gold seizure",
    "British colonial drain / EIC / home charges",
    "2008 crash mechanics / Lehman / Goldman",
    "Jakob Fugger / Holy Roman Emperor",
]

TIER1_BACKLOG = [
    "Richard Cantillon / The Cantillon Effect",
    "JP Morgan WWI loan 1915",
    "John Law and the Mississippi Bubble 1720",
    "The 1946 Anglo-American Loan",
    "The Swiss Banking Secrecy Act 1934",
]


# ── SYNTHESIS ─────────────────────────────────────────────────────────────────

def generate_ideas_from_signals(signals_text: str, progress_callback=None) -> list[dict]:
    """
    Generate ranked F&R episode ideas from pre-gathered research signals.

    signals_text: raw text from VidIQ keyword data + YouTube video research +
                  any other signals gathered in the Claude Code session.

    Returns a list of up to 8 idea dicts, each with:
      rank, topic, fr_angle, suggested_title, source_signals,
      keyword_demand, competition_score, fit_score, why_now
    """
    if progress_callback:
        progress_callback("Synthesising signals with Claude — generating ranked ideas…")

    prompt_template = load_prompt("idea_generator_prompt")
    prompt = prompt_template.format(
        covered_topics="\n".join(f"- {t}" for t in COVERED_TOPICS),
        tier1_backlog="\n".join(f"- {t}" for t in TIER1_BACKLOG),
        signals=signals_text,
    )
    ideas = call_claude_json(prompt, max_tokens=4000)
    if not isinstance(ideas, list):
        raise ValueError(f"Expected list from idea generator, got: {type(ideas)}")
    return ideas
