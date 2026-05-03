"""
Generates daily reply suggestions for @FortuneAndRuin.

PIPELINE (per batch of 3):
  Pulls recent tweets from a curated pool of ~210 finance/macro/history accounts.
  Each run: shuffles the pool, applies a 14-day per-author cooldown, picks 3 fresh
  authors. Each suggestion gets a randomly assigned reply style (witty / hot take /
  historical parallel / specific number / reframe) so the brand doesn't sound like
  a single AI template.

Each suggestion arrives as 2 Telegram messages:
  1. Context — original post + author + x.com link
  2. Pure reply text only (so user can long-press copy on mobile)

Topic-based discovery is deferred until the X API Basic tier is in use — Nitter
search and profile scraping are too unreliable to depend on right now.

Usage:
    python fortune_ruin/scripts/generate_reply_suggestions.py
"""

import sys
import os
import json
import re
import random
import xml.etree.ElementTree as ET
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)


# ── Config ────────────────────────────────────────────────────────────────────

# Curated quality list — guarantees Slot 1 lands on a high-reach account.
# Also provides the source material for theme detection (Slots 2-3).
TARGET_ACCOUNTS = [
    # ── Macro & monetary policy ─────────────────────────────────────────────
    "morganhousel", "kylascanlon", "LynAldenContact", "RaoulGMI", "Nouriel",
    "Convertbond", "NorthmanTrader", "JosephPolitano", "BobEUnlimited",
    "Schuldensuehner", "michaelpettis", "CullenRoche", "ProfSteveKeen",
    "Frances_Coppola", "ojblanchard1", "paulkrugman", "michaelxpettis",
    "ScottMinerd_GIM", "ProfShiller", "RobertJShiller", "MerrynSW",
    # ── Fed / rates / data journalists ──────────────────────────────────────
    "NickTimiraos", "Greg_Ip", "bencasselman", "WSJecon", "M_McDonough",
    "EconomicsPics", "financialjuice", "carlquintanilla", "gunjan_jb",
    "lisaabramowicz1", "matt_levine", "bopinion", "RobinWigg",
    "izakaminska", "JamesEMack", "jamie_mcgeever",
    # ── Independent analysts / fund managers ────────────────────────────────
    "DiMartinoBooth", "profplum99", "RudyHavenstein",
    "kyledbass", "MarkYusko", "hedgeye", "charliebilello", "RyanDetrick",
    "modestproposal1", "jposhaughnessy", "hempton", "AlphaArchitect",
    "PauloMacro", "INArteCarloDoss", "saxena_puru", "biancoresearch",
    "LizAnnSonders", "LarryMcDonald", "dampedspring", "CoreyHoffstein",
    "hkuppy", "TheBubbleBubble", "JackForehand",
    # ── Financial historians & academics ────────────────────────────────────
    "adam_tooze", "AswathDamodaran", "rcwhalen", "R_Thaler",
    "NorbertHaering", "MartinSchmalz", "Jesse_Livermore",
    "Conviction_VC", "burgisjon", "JustinWolfers",
    # ── Markets / charts / commentary ───────────────────────────────────────
    "TheStalwart", "tracyalloway", "bespokeinvest", "Ole_S_Hansen",
    "WallStreetSilv", "quantian1", "dollarsanddata", "amlivemon",
    "carl_b_weinberg", "ParikPatel", "ZeroPointZero_99",
    # ── Geopolitical / realpolitik finance ──────────────────────────────────
    "JonathanFerro", "MikeBird24", "EdwardLuce", "TheRaoulPal",
    "RushDoshi", "noahpinion", "DavidBeckworth",
    # ── Financial crime / forensic (closer to F&R angle) ────────────────────
    "TomWright_1", "DanMcCrum", "BradleyHope",
    "JonathanRMiller", "ProfDavidEnrich",
    # ── MENA / emerging markets / global south ──────────────────────────────
    "OmarAlUbaydli", "TimAshUKR", "YasarYakis", "Tellimer",
    "rohan_grey", "TheBahrainiAna1", "robinbrooksiif",
    # ── Inflation / sovereign debt / commodities ────────────────────────────
    "JulianMI2", "AnnaSWong", "jeffweniger", "BarchartTrading",
    "ZeroHedge", "Lawrence_Lepard", "PeterSchiff",

    # ── Round 2 expansion (May 2026) ────────────────────────────────────────
    # More macro voices
    "TaviCosta", "dlacalle_IA", "JimRickards", "conorsen", "bradsetser",
    "AndrewPolk6", "RealEJAntoni", "AndreasSteno", "JulianBrigden",
    "MichaelKantro", "KobeissiLetter", "jessefelder", "MebFaber",
    "GregMankiw", "StephanieKelton", "JoeBrusuelas", "JeffSnider_AIP",
    "alfonso_peccatiello", "BillMitchell_", "NomiPrins",

    # Top finance journalists (added breadth)
    "SteveLiesman", "michaelsantoli", "JackFarley96", "byHeatherLong",
    "neil_irwin", "RanaForoohar", "JonHilsenrath", "JoeWeisenthal",
    "JavierBlas", "JohnKemp_Reuters", "AmyMyersJaffe", "JohnAuthers",
    "JosephSternberg", "patti_d_olympia", "AdamSamson",

    # Independent / hot-take analysts
    "balajis", "TylerCowen", "LarrySummers", "RobertBReich", "IanBremmer",
    "neelkashkari", "paulkedrosky", "mjmauboussin", "profgalloway",
    "EpsilonTheory", "The_Compounding", "Halsrethink", "ChrisDeMuth_2",
    "MarkRalle", "WilliamHobbs", "DanielleDiMartino", "RyanReynolds",

    # Crypto / digital macro
    "saifedean", "TFTC21", "NickCarter_", "parkerlewis", "greg_foss",
    "PrestonPysh", "TuurDemeester",

    # Central banks & institutions
    "federalreserve", "USTreasury", "ecb", "BIS_org", "IMFNews",
    "WorldBank", "newyorkfed", "Atlanta_Fed", "stlouisfed", "ChicagoFed",
    "BostonFed", "minneapolisfed", "PhilFed", "KCFed", "DallasFed",
    "bankofengland", "bankofcanada", "OECD", "PIIE", "NBERnews",
    "brookings", "CFR_org",

    # Energy / commodities (financial angle)
    "DanYergin", "chigrl", "Mayhem4Markets",

    # Markets / charts breadth
    "BloombergMarkets", "FT", "Reuters", "WSJ", "TheEconomist",
    "Wolfstreet1", "DataLikeMe", "nautiluscap", "valuewalk",

    # MENA / global south / EM
    "aliahmedfayyaz", "CharlieRobertson_", "amareebOmar",
    "ananthn", "PuneetDalmia", "Yashar_Mehrabian",

    # Specific known finance Twitter voices
    "MaynardKeynesMD", "_Investorsage",
    "DonRJohnson_", "Inverted_Curve", "LongConvexity", "MarcusOlofsson93",
    "GarrettCWatts", "MitchellHartman_",
]

NITTER_INSTANCES = [
    "nitter.poast.org",
    "nitter.privacydev.net",
    "nitter.net",
    "nitter.it",
]

MIN_POST_CHARS              = 60
MAX_POSTS_PER_ACCOUNT       = 3
MAX_SUGGESTIONS             = 3
RECENT_AUTHORS_FILE         = Path(__file__).parent.parent / ".recent_reply_authors.json"
RECENT_AUTHORS_WINDOW_DAYS  = 14


# ── Reply style pool ──────────────────────────────────────────────────────────

REPLY_STYLES = [
    {
        "name": "historical_parallel",
        "instructions": (
            "Drop a specific historical parallel. Name a year, person, or amount the "
            "original post didn't mention. Present tense. Sounds like someone who reads "
            "primary sources, not a textbook. End on a flat statement that lands."
        ),
        "example": "1873. Jay Cooke's bank fails on a Thursday. Same week, the NYSE shuts for ten days. Nobody calls it a panic until the railroads stop paying.",
    },
    {
        "name": "hot_take",
        "instructions": (
            "Punchy contrarian read on what the post implies. Take a side. No hedging, "
            "no 'arguably', no 'perhaps'. Sound confident without being smug. One or two "
            "short sentences. The kind of reply a smart finance person fires off between meetings."
        ),
        "example": "This is the Fed setting up another EM crisis. Same playbook as '97. Spread shoe leather, blame the foreigners.",
    },
    {
        "name": "witty_observation",
        "instructions": (
            "Dry, slightly amused. Notices the pattern everyone's pretending not to see. "
            "Doesn't try to be funny — is funny because it's accurate. Conversational, "
            "almost throwaway. No exclamation points. No emojis."
        ),
        "example": "Funny how the 'unprecedented' liquidity event happens every eight years like clockwork.",
    },
    {
        "name": "specific_number",
        "instructions": (
            "Drop one jaw-dropping specific number that recontextualises the original post. "
            "Just the fact, no setup. Add one short clause of why it matters. "
            "Ends without a question."
        ),
        "example": "Bondholders made $47B the last time this happened in 2020. The same desks are already positioned.",
    },
    {
        "name": "reframe",
        "instructions": (
            "Take the post's framing and flip it. State what the situation looks like from "
            "the OTHER side of the trade — the BIS, the central bank, the bondholder, the "
            "winner nobody's naming. Sounds like someone who's read the minutes."
        ),
        "example": "From the BIS side this looks fine. They wanted exactly this duration mismatch in the periphery.",
    },
]


# ── JSON cache helpers ────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

def _save_json(path: Path, data: dict):
    try:
        path.write_text(json.dumps(data, indent=2))
    except Exception as e:
        print(f"[replies] Could not persist {path.name}: {e}")

def load_recent_authors() -> dict[str, str]:
    """{author_lower: ISO date last replied} — drops anything older than window."""
    raw = _load_json(RECENT_AUTHORS_FILE)
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_AUTHORS_WINDOW_DAYS)
    fresh = {}
    for a, iso in raw.items():
        try:
            if datetime.fromisoformat(iso.replace("Z", "+00:00")) >= cutoff:
                fresh[a.lower()] = iso
        except Exception:
            continue
    return fresh

def save_recent_authors(recent: dict[str, str], new_authors: list[str]):
    now_iso = datetime.now(timezone.utc).isoformat()
    for a in new_authors:
        recent[a.lower()] = now_iso
    _save_json(RECENT_AUTHORS_FILE, recent)

# ── Nitter: fetch a user's recent posts ───────────────────────────────────────

def fetch_recent_posts(username: str) -> list[dict]:
    for instance in NITTER_INSTANCES:
        try:
            url = f"https://{instance}/{username}/rss"
            resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            channel = root.find("channel")
            if channel is None:
                continue
            posts = []
            for item in channel.findall("item")[:MAX_POSTS_PER_ACCOUNT]:
                title = item.findtext("title", "")
                link  = item.findtext("link", "")
                desc  = item.findtext("description", "")
                text = re.sub(r"<[^>]+>", "", desc).strip() or title
                x_link = link.replace(f"https://{instance}/", "https://x.com/")
                if len(text) < MIN_POST_CHARS or "RT by" in title:
                    continue
                posts.append({
                    "text": text[:300],
                    "url": x_link,
                    "author": username,
                })
            if posts:
                return posts
        except Exception:
            continue
    return []


# ── Reply generation ──────────────────────────────────────────────────────────

def generate_reply(original_post: str, author: str, style: dict) -> str:
    from engine.claude_client import call_claude
    prompt = f"""You write replies for @FortuneAndRuin on X — a forensic financial history account building from zero followers. These replies go on posts from established finance accounts.

ORIGINAL POST by @{author}:
"{original_post}"

REPLY STYLE: {style['name']}
{style['instructions']}

EXAMPLE of this style (for tone reference, NOT to copy):
"{style['example']}"

HARD RULES (apply to every reply, regardless of style):
- Under 240 characters
- Sounds like a person, not a brand. No "as a financial history account..."
- No em-dashes — use periods
- No negative constructions ("it wasn't X, it was Y")
- No emojis
- No hashtags
- Does not start with "I", "We", "Great point", "Actually", "This"
- Does not ask the original poster a direct question ("what do you think?")
- Specific over vague — real numbers, real names, real years

Return ONLY the reply text. No quotes, no preamble, no style label."""
    return call_claude(prompt, max_tokens=200).strip().strip('"')


# ── Telegram ──────────────────────────────────────────────────────────────────

def _tg_token() -> str:    return os.environ["TELEGRAM_BOT_TOKEN"]
def _tg_chat_id() -> str:  return os.environ["YOUR_TELEGRAM_CHAT_ID"]

def send_telegram(text: str):
    requests.post(
        f"https://api.telegram.org/bot{_tg_token()}/sendMessage",
        json={"chat_id": _tg_chat_id(), "text": text},
        timeout=15,
    )

def send_suggestion(post: dict, reply: str, style_name: str, index: int, total: int):
    send_telegram(
        f"💬 {index}/{total} — @{post['author']} · {style_name}\n"
        f"\"{post['text'][:250]}\"\n"
        f"{post['url']}"
    )
    send_telegram(reply)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    uae = datetime.now(timezone.utc) + timedelta(hours=4)
    print(f"[replies] {uae.strftime('%d %b %H:%M UAE')} | pool: {len(TARGET_ACCOUNTS)} accounts")

    recent = load_recent_authors()
    print(f"[replies] {len(recent)} authors in 14-day cooldown")

    # Shuffle pool — fair coverage across days
    accounts = TARGET_ACCOUNTS.copy()
    random.shuffle(accounts)

    # Pass 1: only fresh authors (not in cooldown)
    selected = []
    seen_authors = set()
    for username in accounts:
        if len(selected) >= MAX_SUGGESTIONS:
            break
        if username.lower() in recent or username.lower() in seen_authors:
            continue
        posts = fetch_recent_posts(username)
        if posts:
            selected.append(posts[0])
            seen_authors.add(username.lower())

    # Pass 2 (fallback): if cooldown filtered too aggressively, allow recent
    if len(selected) < MAX_SUGGESTIONS:
        print(f"[replies] Only {len(selected)} fresh authors. Falling back to recent...")
        for username in accounts:
            if len(selected) >= MAX_SUGGESTIONS:
                break
            if username.lower() in seen_authors:
                continue
            posts = fetch_recent_posts(username)
            if posts:
                selected.append(posts[0])
                seen_authors.add(username.lower())

    if not selected:
        send_telegram("💬 Could not fetch posts from any target accounts today. Try again later.")
        print("[replies] No posts fetched.")
        return

    selected = selected[:MAX_SUGGESTIONS]

    # Random reply style per suggestion (no repeats within batch if pool large enough)
    if len(REPLY_STYLES) >= len(selected):
        styles = random.sample(REPLY_STYLES, len(selected))
    else:
        styles = random.choices(REPLY_STYLES, k=len(selected))

    send_telegram(
        f"💬 Fortune & Ruin — Reply Suggestions\n"
        f"{uae.strftime('%d %b')} · {len(selected)} replies, mixed styles"
    )

    new_author_picks = []
    for i, (post, style) in enumerate(zip(selected, styles), 1):
        print(f"[replies] {i}/{len(selected)} @{post['author']} · {style['name']}")
        try:
            reply = generate_reply(post["text"], post["author"], style)
            send_suggestion(post, reply, style["name"], i, len(selected))
            new_author_picks.append(post["author"])
        except Exception as e:
            print(f"[replies] Error: {e}")
            continue

    save_recent_authors(recent, new_author_picks)
    print(f"[replies] Done. Sent {len(new_author_picks)} suggestions.")


if __name__ == "__main__":
    main()
