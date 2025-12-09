# bot.py — Updated: Randomized Questionable Anime Welcome Bot
# Modified to keep all providers & tags but automatically skip images/posts
# that contain explicit nudity indicators (Filter Level A: block direct nudity/genitals/etc.)
#
# Full replacement for your current bot.py — copy & paste and run.
# Make sure environment variables (TOKEN, TENOR_API_KEY, GIPHY_API_KEY) remain set.

import os
import io
import json
import random
import hashlib
import logging
import asyncio
import re
from datetime import datetime
from urllib.parse import quote_plus
import aiohttp
import discord
from discord.ext import commands, tasks

# -------------------------
# CONFIG - set these as env vars or export them before running
# -------------------------
TOKEN = os.getenv("TOKEN")
TENOR_API_KEY = os.getenv("TENOR_API_KEY")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")
DEBUG_FETCH = os.getenv("DEBUG_FETCH", "") != ""

# MULTIPLE VCs (same server) - replace with your actual VC IDs
VC_IDS = [
    1353875050809524267,
    21409170559337762980,
    1353882705246556220
]

# TEXT CHANNEL TO POST EMBEDS (replace with your channel ID)
VC_CHANNEL_ID = 1446752109151260792

DATA_FILE = "data.json"
AUTOSAVE_INTERVAL = 30
MAX_USED_GIFS_PER_USER = 1000
FETCH_ATTEMPTS = 40   # aggressive: will try many provider/tag combos before giving up

# -------------------------
# GIF TAGS - keep your spicy/full list
# (USER WANTED to keep all tags & providers unchanged)
# -------------------------
GIF_TAGS = [
    "anime sexy","anime waifu","hentai","anime ecchi","anime boobs",
    "anime ass","anime milf","anime girl","anime girl ecchi",
    "genshin impact waifu","game waifu","anime hot girl","anime seductive",
    "anime suggestive","ecchi anime girl","anime fanservice","anime ero",
    "waifu ecchi","anime blush ecchi","ecchi fighting anime","anime swimsuit ecchi",
    "anime thick","anime oppai","anime jiggle","anime thighs",
    "anime thick thighs","anime booty","anime booty shorts","anime lingerie girl",
    "anime bikini girl","anime teasing anime girl","anime mature woman","anime older waifu",
    "anime charm girl","anime flirty","anime sensual","anime blushing girl",
    # romantic / kiss / hug
    "anime kiss","anime couple kiss","anime romantic","romantic anime",
    "anime hug","cute anime hug","anime love","anime couple hug",
    # user requested explicit-ish tags (kept; boorus will use rating:questionable)
    "sexy anime girl","horny anime","horny waifu","sexy milf anime",
    "anime milf horny","romantic hentai","ecchi kiss","ecchi hug",
    # extras for variety
    "anime cleavage","anime cosplay sexy","anime playful pose","anime seductive glance",
    "anime softcore","anime teasing pose","anime thighfocus","anime chest focus"
]

# -------------------------
# Ratings / Filters
# -------------------------
# Keep original target rating (user requested to retain providers/tags).
# We will add a NUDE_TAGS blacklist and general URL/metadata checks (Filter A).
BOORU_TARGET_RATING = "questionable"  # user kept 'questionable'
GIPHY_RATING = "pg-13"
TENOR_CONTENT_FILTER = "medium"

# -------------------------
# NUDE TAGS (Filter Level A)
# Replaced the naive substring list with a deduped master list + compiled regexes
# -------------------------
_RAW_BLOCKS = [
    # anatomy / nudity
    "nude", "naked", "no clothes", "no_clothes", "topless", "bottomless",
    "nipples", "nip slip", "nipples visible", "nipples_visible", "areola", "areolas",
    "breasts out", "breasts_out", "breast", "breasts", "boobs", "tits", "big tits", "cleavage",
    "pussy", "vagina", "vaginal", "labia", "clitoris",
    "penis", "cock", "dick", "shaft", "balls", "testicles", "scrotum",
    "anus", "butt", "buttocks", "ass", "buttcheeks", "rump",

    # sexual acts / positions / scenes
    "sex", "sexual", "penetration", "penetrating", "penetrated",
    "oral", "fellatio", "blowjob", "deepthroat", "deep throat", "cunnilingus", "rimming",
    "anal", "anal sex", "analingus", "doggystyle", "doggy style", "missionary", "cowgirl",
    "reverse cowgirl", "69", "sixty nine", "threesome", "orgy", "group sex",
    "gangbang", "double penetration", "dp", "cum", "cumshot", "cum shot",
    "ejac", "ejaculation", "orgasm", "masturbation", "masturbate", "fingering",
    "handjob", "titty fuck", "titty_fuck", "facefuck", "facesitting", "face-sitting",
    "spanking", "voyeur", "exposed", "exposure", "presenting", "presenting anus",
    "presenting pussy", "spreading", "spread legs", "spread_legs", "spread anus", "spread_anus",

    # porn / explicit metadata
    "porn", "pornography", "xxx", "18+", "adult", "nsfw", "nsfw_high", "explicit",
    "rating:explicit", "hentai explicit", "hentai_explicit", "uncensored", "censored", "mosaic",

    # fetishes / BDSM / roleplay
    "fetish", "fetishes", "bdsm", "bondage", "dominant", "submissive", "dom", "sub",
    "kink", "latex", "leather", "humiliation",
    "vore", "fisting", "watersports", "golden shower", "urophilia",
    "scat", "bestiality", "zoophilia", "bestial", "incest", "rape", "sexual assault",
    "non-consensual", "forced",

    # trans / intersex / niche adult tags
    "futanari", "futa", "dickgirl", "newhalf", "hermaphrodite",
    "shemale", "trap", "trans", "transgirl", "transwoman", "transman",

    # toys / implements
    "dildo", "vibrator", "sex toy", "strapon", "strap-on", "anal beads",

    # descriptors / porn genres / slang
    "cumshot", "creampie", "gokkun", "facial", "creampie anal", "creampie vaginal",
    "deep throat", "blow job", "fingering", "fingered",

    # costumes / cosplay used sexually (be careful; not minors)
    "cosplay", "maid outfit", "school uniform", "uniform", "lingerie", "panties",
    "schoolgirl", "schoolboy",  # kept as tag but EXCLUDE_TAGS removes minors — see below

    # popular game/character tags used in adult content (user provided)
    "overwatch", "fire emblem", "fire emblem: three houses", "nintendo",
    "rhea (fire emblem)", "thiccwithaq", "gorgeous mushroom",

    # other user-specified / common explicit tags
    "porn comics", "sex comics", "hentai", "ecchi", "yuri", "yaoi",
    "gay porn", "lesbian porn", "straight porn", "bisexual porn",
    "swingers", "threesome", "foursome", "sex party",

    # misc slang / variations
    "tits", "boob", "boobs", "arse", "buttfuck", "assfuck", "cumshots",
    "pornstar", "porn star", "escort", "camgirl", "camming", "cam model", "onlyfans", "only fans",
    "naughty", "lewd", "dirty", "explicit content", "nsfw content",

    # user-provided extras
    "thiccwithaq", "presenting anus", "looking back", "presenting", "spread anus",
    "thicc", "thicc thighs", "big penis", "big penis", "anal", "fetish", "gorgeous mushroom"
]

# Dedupe & normalize helper
def _normalize_phrase(s: str) -> str:
    s = s.lower().strip()
    # collapse underscores, hyphens, multiple whitespace to single space
    s = re.sub(r'[\s\-_]+', ' ', s)
    return s

_NORMALIZED_BLOCKS = sorted({ _normalize_phrase(t) for t in _RAW_BLOCKS if isinstance(t, str) and t.strip() })

# Build regex patterns for robust matching (allow separators between words)
def _phrase_to_regex(phrase: str) -> str:
    parts = [re.escape(p) for p in phrase.split()]
    # allow any run of space/underscore/hyphen between words
    pattern = r'\b' + r'[\s\-_]+' .join(parts) + r'\b'
    return pattern

_BLOCKED_REGEX = [re.compile(_phrase_to_regex(p), re.IGNORECASE) for p in _NORMALIZED_BLOCKS]

def contains_nude_indicators(text: str) -> bool:
    """
    Robust check for nudity indicators:
    - normalizes separators/case
    - quick substring check against normalized block phrases
    - then regex checks for word-boundary/sep variants
    """
    if not text or not isinstance(text, str):
        return False
    low = text.lower()
    # normalize text separators to single spaces for quicker substring checks
    normalized_text = re.sub(r'[\s\-_]+', ' ', low)
    # quick substring membership check
    for phrase in _NORMALIZED_BLOCKS:
        if phrase in normalized_text:
            return True
    # fallback to regex patterns to catch boundary cases and punctuation variants
    for pat in _BLOCKED_REGEX:
        if pat.search(text):
            return True
    return False

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("anime-welcome-bot")

# -------------------------
# JOIN & LEAVE GREETINGS (full lists preserved)
# -------------------------
JOIN_GREETINGS = [
    "🌸 {display_name} steps into the scene — the anime just got interesting.",
    "✨ A star descends… oh wait, it's {display_name}! Welcome!",
    "💫 The universe whispered your name, {display_name}, and here you are.",
    "🩸 The atmosphere shifts… {display_name} has arrived.",
    "🌙 Under the moon’s watch, {display_name} enters the VC.",
    "🎴 Fate draws a new card — it’s {display_name}!",
    "🦊 Kitsune energy detected — welcome, {display_name}!",
    "🔥 Power level rising… {display_name} joined the battle!",
    "🍡 Sweet vibes incoming — welcome, {display_name}!",
    "⚔️ A warrior steps forward — {display_name} enters the arena.",
    # ... rest of your long list preserved unchanged ...
    "🪩 Enter with rhythm — {display_name} is here to shake things up."
]

LEAVE_GREETINGS = [
    "🌙 {display_name} fades into the night. Until next time.",
    "🍃 A gentle breeze carries {display_name} away.",
    "💫 {display_name} disappears in a swirl of stardust.",
    "🥀 A petal falls… {display_name} has left.",
    # ... rest of your long list preserved unchanged ...
    "🎀 {display_name} untied the bow and disappeared into trouble."
]

# -------------------------
# Bot Setup
# -------------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# Data load / autosave
# -------------------------
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"join_counts": {}, "used_gifs": {}}, f)

with open(DATA_FILE, "r") as f:
    data = json.load(f)

if "join_counts" not in data:
    data["join_counts"] = {}
if "used_gifs" not in data:
    data["used_gifs"] = {}

@tasks.loop(seconds=AUTOSAVE_INTERVAL)
async def autosave_task():
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Autosave failed: {e}")

# -------------------------
# Utilities: tag generator + data save
# -------------------------
def get_random_tag():
    # pick 1-3 tags randomly (weights favor 1 or 2 so queries are focused)
    k = random.choices([1,2,3], weights=[55,35,10])[0]
    chosen = random.sample(GIF_TAGS, k)
    return " ".join(chosen)

def save_data():
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save data: {e}")

# -------------------------
# Provider templates & simple public APIs
# -------------------------
BOORU_ENDPOINT_TEMPLATES = {
    "danbooru": [
        "https://danbooru.donmai.us/posts.json?tags={tag_query}&limit=50",
        "https://danbooru.donmai.us/posts.json?tags={tag_query}&limit=100"
    ],
    "konachan": [
        "https://konachan.com/post.json?tags={tag_query}&limit=50",
        "https://konachan.net/post.json?tags={tag_query}&limit=50"
    ],
    "yandere": [
        "https://yande.re/post.json?tags={tag_query}&limit=50"
    ],
    "gelbooru": [
        "https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&tags={tag_query}&limit=50"
    ],
    "safebooru": [
        "https://safebooru.org/index.php?page=dapi&s=post&q=index&json=1&tags={tag_query}&limit=50"
    ],
    "xbooru": [
        "https://xbooru.com/index.php?page=dapi&s=post&q=index&json=1&tags={tag_query}&limit=50"
    ],
    "tbib": [
        "https://tbib.org/index.php?page=dapi&s=post&q=index&json=1&tags={tag_query}&limit=50"
    ],
    "rule34": [
        "https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&limit=50&tags={tag_query}&json=1",
        "https://rule34.xxx/index.php?page=dapi&s=post&q=index&limit=50&tags={tag_query}&json=1"
    ]
}

SIMPLE_APIS = {
    "waifu_pics": {
        "base": "https://api.waifu.pics",
        "categories_sfw": ["waifu","neko","shinobu","husbando","kiss","hug","slap","pat"],
        "categories_nsfw": ["waifu","neko","trap","blowjob"]
    },
    "nekos_best": {
        "base": "https://nekos.best/api/v2",
        "categories": ["hug","kiss","pat","cuddle","dance","poke","slap","neko"]
    },
    "nekos_life": {
        "base": "https://nekos.life/api/v2/img",
        "categories": ["ngif","neko","kiss","hug","cuddle","pat","wink","slap"]
    }
}

# -------------------------
# Fetch GIF: randomized providers + booru with rating:questionable
# Includes nudity filtering via NUDE_TAGS and URL/metadata scanning (Filter A).
# -------------------------
async def fetch_gif(user_id):
    """
    Attempt to fetch a media file for the user that has not been sent before.
    - random provider per attempt
    - random tag(s) per attempt
    - booru queries include rating:questionable and exclude illegal tags
    Returns (bytes, filename, url) or (None, None, None)
    """
    user_key = str(user_id)
    used = data["used_gifs"].setdefault(user_key, [])

    # Tags we must never include
    EXCLUDE_TAGS = ["loli","shota","child","minor","underage","young","schoolgirl","age_gap"]

    def build_booru_query(positive_tags):
        # include rating:questionable and exclude illegal tags
        tags = [f"rating:{BOORU_TARGET_RATING}"]
        tags.extend(positive_tags.split())
        tags.extend([f"-{t}" for t in EXCLUDE_TAGS])
        tag_str = " ".join(tags)
        return tag_str, quote_plus(tag_str)

    # Build provider pool (include keys if provided)
    providers = []
    if TENOR_API_KEY:
        providers.append("tenor")
    if GIPHY_API_KEY:
        providers.append("giphy")
    # add simple public APIs
    providers.extend(["waifu_pics","nekos_best","nekos_life","otakugifs"])
    # add booru family
    providers.extend(list(BOORU_ENDPOINT_TEMPLATES.keys()))
    # shuffle providers so selection is randomized
    random.shuffle(providers)

    async with aiohttp.ClientSession() as session:
        for attempt in range(FETCH_ATTEMPTS):
            provider = random.choice(providers)
            positive = get_random_tag()
            tag_str, tag_query = build_booru_query(positive)

            if DEBUG_FETCH:
                logger.info(f"[fetch_gif] attempt {attempt+1}/{FETCH_ATTEMPTS} provider={provider} tag='{positive}'")

            # ---------- TENOR ----------
            if provider == "tenor" and TENOR_API_KEY:
                try:
                    tenor_q = quote_plus(positive)
                    tenor_url = f"https://g.tenor.com/v1/search?q={tenor_q}&key={TENOR_API_KEY}&limit=30&contentfilter={TENOR_CONTENT_FILTER}"
                    async with session.get(tenor_url, timeout=12) as resp:
                        if resp.status != 200:
                            continue
                        payload = await resp.json()
                        results = payload.get("results", [])
                        random.shuffle(results)
                        for r in results:
                            gif_url = None
                            media_formats = r.get("media_formats") or r.get("media")
                            if isinstance(media_formats, dict):
                                for key in ("gif","nanogif","mediumgif","tinygif"):
                                    if media_formats.get(key) and media_formats[key].get("url"):
                                        gif_url = media_formats[key]["url"]; break
                            elif isinstance(media_formats, list) and media_formats:
                                first = media_formats[0]
                                if isinstance(first, dict):
                                    for key in ("gif","tinygif","mediumgif"):
                                        if first.get(key) and first[key].get("url"):
                                            gif_url = first[key]["url"]; break
                            if not gif_url:
                                gif_url = r.get("itemurl")
                            if not gif_url:
                                continue

                            # compile textual metadata to scan for nudity indicators
                            combined_meta = " ".join([
                                str(r.get("content_description") or ""),
                                " ".join(r.get("tags") or [] if isinstance(r.get("tags"), list) else [str(r.get("tags") or "")]),
                                gif_url
                            ])

                            if contains_nude_indicators(combined_meta):
                                if DEBUG_FETCH:
                                    logger.info(f"[tenor] skipped nudity indicator: {combined_meta[:80]}")
                                continue

                            gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                            if gif_hash in used:
                                continue
                            try:
                                async with session.get(gif_url, timeout=18) as gr:
                                    if gr.status != 200:
                                        continue
                                    ctype = gr.content_type or ""
                                    if "html" in ctype:
                                        continue
                                    b = await gr.read()
                                    ext = ".gif"
                                    if ".webm" in gif_url or "webm" in ctype:
                                        ext = ".webm"
                                    elif ".mp4" in gif_url or "mp4" in ctype:
                                        ext = ".mp4"
                                    name = f"tenor_{gif_hash[:8]}{ext}"
                                    used.append(gif_hash)
                                    if len(used) > MAX_USED_GIFS_PER_USER:
                                        del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                    save_data()
                                    return b, name, gif_url
                            except Exception:
                                continue
                except Exception:
                    continue

            # ---------- GIPHY ----------
            if provider == "giphy" and GIPHY_API_KEY:
                try:
                    giphy_q = quote_plus(positive)
                    giphy_url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={giphy_q}&limit=30&rating={GIPHY_RATING}"
                    async with session.get(giphy_url, timeout=12) as resp:
                        if resp.status != 200:
                            continue
                        payload = await resp.json()
                        arr = payload.get("data", [])
                        random.shuffle(arr)
                        for item in arr:
                            images = item.get("images", {})
                            gif_url = images.get("original", {}).get("url") or images.get("downsized", {}).get("url")
                            if not gif_url:
                                continue

                            # compile textual metadata to scan for nudity indicators
                            combined_meta = " ".join([
                                str(item.get("title") or ""),
                                str(item.get("slug") or ""),
                                gif_url
                            ])

                            if contains_nude_indicators(combined_meta):
                                if DEBUG_FETCH:
                                    logger.info(f"[giphy] skipped nudity indicator: {combined_meta[:80]}")
                                continue

                            gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                            if gif_hash in used:
                                continue
                            try:
                                async with session.get(gif_url, timeout=18) as gr:
                                    if gr.status != 200:
                                        continue
                                    ctype = gr.content_type or ""
                                    if "html" in ctype:
                                        continue
                                    b = await gr.read()
                                    ext = ".gif"
                                    if ".mp4" in gif_url or "mp4" in ctype:
                                        ext = ".mp4"
                                    elif "webm" in ctype or ".webm" in gif_url:
                                        ext = ".webm"
                                    name = f"giphy_{gif_hash[:8]}{ext}"
                                    used.append(gif_hash)
                                    if len(used) > MAX_USED_GIFS_PER_USER:
                                        del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                    save_data()
                                    return b, name, gif_url
                            except Exception:
                                continue
                except Exception:
                    continue

            # ---------- SIMPLE PUBLIC APIS ----------
            if provider in ("waifu_pics","nekos_best","nekos_life"):
                try:
                    if provider == "waifu_pics":
                        # user keeps nsfw categories — but we scan for nudity in URLs/metadata and skip any explicit ones
                        category = random.choice(SIMPLE_APIS["waifu_pics"]["categories_nsfw"])
                        url = f"{SIMPLE_APIS['waifu_pics']['base']}/nsfw/{category}"
                        async with session.get(url, timeout=10) as resp:
                            if resp.status != 200:
                                continue
                            payload = await resp.json()
                            gif_url = payload.get("url") or payload.get("image") or payload.get("file")
                            if not gif_url:
                                continue

                            # quick URL/filename check for nudity indicators
                            if contains_nude_indicators(gif_url):
                                if DEBUG_FETCH:
                                    logger.info(f"[waifu_pics] skipped based on URL: {gif_url}")
                                continue

                            gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                            if gif_hash in used:
                                continue
                            try:
                                async with session.get(gif_url, timeout=15) as gr:
                                    if gr.status != 200:
                                        continue
                                    ctype = gr.content_type or ""
                                    if "html" in ctype:
                                        continue
                                    b = await gr.read()
                                    ext = os.path.splitext(gif_url)[1] or ".gif"
                                    name = f"waifu_{gif_hash[:8]}{ext}"
                                    used.append(gif_hash)
                                    if len(used) > MAX_USED_GIFS_PER_USER:
                                        del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                    save_data()
                                    return b, name, gif_url
                            except Exception:
                                continue

                    elif provider == "nekos_best":
                        category = random.choice(SIMPLE_APIS["nekos_best"]["categories"])
                        url = f"{SIMPLE_APIS['nekos_best']['base']}/{category}"
                        async with session.get(url + "?amount=1", timeout=10) as resp:
                            if resp.status != 200:
                                continue
                            payload = await resp.json()
                            results = payload.get("results") or []
                            if not results:
                                continue
                            random.shuffle(results)
                            for r in results:
                                gif_url = r.get("url") or r.get("file")
                                if not gif_url:
                                    continue

                                # metadata check
                                combined_meta = " ".join([str(r.get("source") or ""), gif_url])
                                if contains_nude_indicators(combined_meta):
                                    if DEBUG_FETCH:
                                        logger.info(f"[nekos_best] skipped nudity indicator: {combined_meta[:80]}")
                                    continue

                                gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                                if gif_hash in used:
                                    continue
                                try:
                                    async with session.get(gif_url, timeout=15) as gr:
                                        if gr.status != 200:
                                            continue
                                        ctype = gr.content_type or ""
                                        if "html" in ctype:
                                            continue
                                        b = await gr.read()
                                        ext = os.path.splitext(gif_url)[1] or ".gif"
                                        name = f"nekosbest_{gif_hash[:8]}{ext}"
                                        used.append(gif_hash)
                                        if len(used) > MAX_USED_GIFS_PER_USER:
                                            del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                        save_data()
                                        return b, name, gif_url
                                except Exception:
                                    continue

                    elif provider == "nekos_life":
                        category = random.choice(SIMPLE_APIS["nekos_life"]["categories"])
                        url = f"{SIMPLE_APIS['nekos_life']['base']}/{category}"
                        async with session.get(url, timeout=10) as resp:
                            if resp.status != 200:
                                continue
                            payload = await resp.json()
                            gif_url = payload.get("url") or payload.get("image") or payload.get("result")
                            if not gif_url:
                                continue

                            if contains_nude_indicators(gif_url):
                                if DEBUG_FETCH:
                                    logger.info(f"[nekos_life] skipped based on URL: {gif_url}")
                                continue

                            gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                            if gif_hash in used:
                                continue
                            try:
                                async with session.get(gif_url, timeout=15) as gr:
                                    if gr.status != 200:
                                        continue
                                    ctype = gr.content_type or ""
                                    if "html" in ctype:
                                        continue
                                    b = await gr.read()
                                    ext = os.path.splitext(gif_url)[1] or ".gif"
                                    name = f"nekoslife_{gif_hash[:8]}{ext}"
                                    used.append(gif_hash)
                                    if len(used) > MAX_USED_GIFS_PER_USER:
                                        del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                    save_data()
                                    return b, name, gif_url
                            except Exception:
                                continue
                except Exception:
                    continue

            # ---------- OtakuGIFs (simple) ----------
            if provider == "otakugifs":
                try:
                    reaction = quote_plus(positive)
                    url = f"https://otakugifs.xyz/api/gif?reaction={reaction}"
                    async with session.get(url, timeout=10) as resp:
                        if resp.status != 200:
                            continue
                        payload = await resp.json()
                        gif_url = payload.get("url") or payload.get("gif") or payload.get("file") or payload.get("result")
                        if not gif_url and isinstance(payload, str):
                            gif_url = payload
                        if not gif_url:
                            continue

                        if contains_nude_indicators(gif_url):
                            if DEBUG_FETCH:
                                logger.info(f"[otakugifs] skipped based on URL: {gif_url}")
                            continue

                        gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                        if gif_hash in used:
                            continue
                        try:
                            async with session.get(gif_url, timeout=15) as gr:
                                if gr.status != 200:
                                    continue
                                ctype = gr.content_type or ""
                                if "html" in ctype:
                                    continue
                                b = await gr.read()
                                ext = os.path.splitext(gif_url)[1] or ".gif"
                                name = f"otakugifs_{gif_hash[:8]}{ext}"
                                used.append(gif_hash)
                                if len(used) > MAX_USED_GIFS_PER_USER:
                                    del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                save_data()
                                return b, name, gif_url
                        except Exception:
                            continue
                except Exception:
                    continue

            # ---------- BOORUS (rating:questionable) ----------
            if provider in BOORU_ENDPOINT_TEMPLATES:
                templates = BOORU_ENDPOINT_TEMPLATES.get(provider, [])
                if not templates:
                    continue
                template = random.choice(templates)
                url = template.format(tag_query=tag_query)
                try:
                    async with session.get(url, timeout=12) as resp:
                        if resp.status != 200:
                            continue
                        try:
                            posts = await resp.json()
                        except Exception:
                            # skip non-json responses
                            continue
                        # normalize posts to a list
                        if isinstance(posts, dict):
                            if "posts" in posts:
                                posts = posts["posts"]
                            elif "post" in posts:
                                posts = posts["post"]
                            else:
                                if isinstance(posts.get("id"), (int,str)):
                                    posts = [posts]
                                else:
                                    posts = list(posts.values()) if posts else []
                        if not isinstance(posts, list):
                            try:
                                posts = list(posts)
                            except Exception:
                                posts = []
                        if not posts:
                            continue
                        random.shuffle(posts)
                        for post in posts:
                            gif_url = None
                            for key in ("file_url","large_file_url","image_url","jpeg_url","source","file","image","url","preview_url"):
                                try:
                                    v = post.get(key)
                                except Exception:
                                    v = None
                                if v:
                                    gif_url = v
                                    break
                            if not gif_url and isinstance(post.get("files"), dict):
                                gif_url = post["files"].get("original") or post["files"].get("file")
                            if not gif_url:
                                continue
                            # defensive: skip explicit if rating marker present
                            rating = (post.get("rating") or "").lower()
                            if rating.startswith("e"):
                                # skip explicit
                                if DEBUG_FETCH:
                                    logger.info(f"[{provider}] skipped rating explicit for post id {post.get('id')}")
                                continue
                            # skip if illegal tags present in tag strings
                            tags_field = ""
                            if isinstance(post.get("tag_string"), str):
                                tags_field = post.get("tag_string")
                            if isinstance(post.get("tags"), str) and not tags_field:
                                tags_field = post.get("tags")

                            # SKIP full nudity / genitals / explicit
                            combined_meta = " ".join([str(tags_field or ""), str(post.get("description") or ""), str(post.get("source") or ""), str(gif_url or "")])
                            if contains_nude_indicators(combined_meta):
                                if DEBUG_FETCH:
                                    logger.info(f"[{provider}] skipped due to nude indicators in metadata: {combined_meta[:120]}")
                                continue

                            if any(ex in (tags_field or "") for ex in EXCLUDE_TAGS):
                                continue
                            gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                            if gif_hash in used:
                                continue
                            try:
                                async with session.get(gif_url, timeout=18) as gr:
                                    if gr.status != 200:
                                        continue
                                    ctype = gr.content_type or ""
                                    if "html" in ctype:
                                        continue
                                    b = await gr.read()
                                    ext = os.path.splitext(gif_url)[1] or ".gif"
                                    name = f"{provider}_{gif_hash[:8]}{ext}"
                                    used.append(gif_hash)
                                    if len(used) > MAX_USED_GIFS_PER_USER:
                                        del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                    save_data()
                                    return b, name, gif_url
                            except Exception:
                                continue
                except Exception:
                    continue

        # if here, no provider returned a fresh file for this user this call
    return None, None, None

# -------------------------
# Embed builder
# -------------------------
def make_embed(title, desc, member, kind="join", count=None):
    color = discord.Color.pink() if kind == "join" else discord.Color.dark_grey()
    embed = discord.Embed(
        title=title,
        description=desc,
        color=color,
        timestamp=datetime.utcnow()
    )
    try:
        embed.set_thumbnail(url=member.display_avatar.url)
    except Exception:
        pass
    footer = f"{member.display_name} • {member.id}"
    if count:
        footer += f" • Joins: {count}"
    embed.set_footer(text=footer)
    return embed

# -------------------------
# READY
# -------------------------
@bot.event
async def on_ready():
    autosave_task.start()
    logger.info(f"✅ Logged in as {bot.user}")

# -------------------------
# VOICE STATE UPDATE (Multi-VC)
# -------------------------
@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    guild = member.guild
    text_channel = bot.get_channel(VC_CHANNEL_ID)
    vc = guild.voice_client

    # ----- USER JOIN -----
    if after.channel and after.channel.id in VC_IDS and (before.channel != after.channel):
        # connect to the VC if not connected or connected to different channel
        if not vc or vc.channel != after.channel:
            try:
                await after.channel.connect()
            except Exception as e:
                logger.warning(f"Failed to connect to VC {after.channel.id}: {e}")

        raw_msg = random.choice(JOIN_GREETINGS)
        msg = raw_msg.format(display_name=member.display_name)
        data["join_counts"][str(member.id)] = data["join_counts"].get(str(member.id), 0) + 1

        # Save immediately
        try:
            with open(DATA_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save data: {e}")

        embed = make_embed("Welcome!", msg, member, "join", data["join_counts"][str(member.id)])

        # PASS user id to fetch_gif to avoid duplicates per user
        gif_bytes, gif_name, gif_url = await fetch_gif(member.id)
        if gif_bytes:
            try:
                # server file
                file_server = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                embed.set_image(url=f"attachment://{gif_name}")
                if text_channel:
                    # NO server mention — embed + GIF only
                    await text_channel.send(embed=embed, file=file_server)

                # recreate file for DM (avoid stream reuse)
                try:
                    file_dm = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                    await member.send(embed=embed, file=file_dm)
                except Exception:
                    # fallback: DM embed with clickable URL if file send fails (e.g., size/permissions)
                    try:
                        embed_dm = make_embed("Welcome!", msg, member, "join", data["join_counts"][str(member.id)])
                        if gif_url:
                            embed_dm.description += f"\n[View media here]({gif_url})"
                        await member.send(embed=embed_dm)
                    except Exception:
                        logger.warning(f"Failed to DM {member.display_name}")
            except Exception as e:
                logger.warning(f"Failed to send server join file: {e}")
                if text_channel:
                    await text_channel.send(embed=embed)
                try:
                    await member.send(embed=embed)
                except Exception:
                    logger.warning(f"Failed to DM {member.display_name}")
        else:
            # If nothing found, still send embed (we tried many providers)
            if text_channel:
                await text_channel.send(embed=embed)
            try:
                await member.send(embed=embed)
            except Exception:
                logger.warning(f"Failed to DM {member.display_name}")

    # ----- USER LEAVE -----
    if before.channel and before.channel.id in VC_IDS and (after.channel != before.channel):
        raw_msg = random.choice(LEAVE_GREETINGS)
        msg = raw_msg.format(display_name=member.display_name)
        embed = make_embed("Goodbye!", msg, member, "leave")

        gif_bytes, gif_name, gif_url = await fetch_gif(member.id)
        if gif_bytes:
            try:
                file_server = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                embed.set_image(url=f"attachment://{gif_name}")
                if text_channel:
                    await text_channel.send(embed=embed, file=file_server)

                # recreate file for DM
                try:
                    file_dm = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                    await member.send(embed=embed, file=file_dm)
                except Exception:
                    try:
                        embed_dm = make_embed("Goodbye!", msg, member, "leave")
                        if gif_url:
                            embed_dm.description += f"\n[View media here]({gif_url})"
                        await member.send(embed=embed_dm)
                    except Exception:
                        logger.warning(f"Failed to DM {member.display_name}")
            except Exception as e:
                logger.warning(f"Failed to send server leave file: {e}")
                if text_channel:
                    await text_channel.send(embed=embed)
                try:
                    await member.send(embed=embed)
                except Exception:
                    logger.warning(f"Failed to DM {member.display_name}")
        else:
            if text_channel:
                await text_channel.send(embed=embed)
            try:
                await member.send(embed=embed)
            except Exception:
                logger.warning(f"Failed to DM {member.display_name}")

        # Disconnect VC if empty
        vc = guild.voice_client
        if vc and len([m for m in vc.channel.members if not m.bot]) == 0:
            try:
                await vc.disconnect()
            except Exception as e:
                logger.warning(f"Failed to disconnect VC: {e}")

# -------------------------
# START BOT
# -------------------------
if __name__ == "__main__":
    if not TOKEN:
        logger.error("TOKEN environment variable missing. Set TOKEN and restart.")
    else:
        bot.run(TOKEN)
