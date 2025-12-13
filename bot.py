# bot_spiciest_final_spicy_only.py
# Single-file Discord bot — spicy (suggestive) GIFs, avoids explicit nudity.
# Requirements: aiohttp, discord.py (rewrite), Python 3.10+
# Env vars required: TOKEN, TENOR_API_KEY (opt), GIPHY_API_KEY (opt), WAIFUIM_API_KEY (opt), WAIFUIT_API_KEY (opt)
# Recommended: set DEBUG_FETCH="true" in Railway to see provider logs, then disable when happy.

import os
import io
import json
import random
import hashlib
import logging
import re
from datetime import datetime
from urllib.parse import quote_plus
import aiohttp
import discord
from discord.ext import commands, tasks

# ------------- CONFIG -------------
TOKEN = os.getenv("TOKEN")
TENOR_API_KEY = os.getenv("TENOR_API_KEY")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")
WAIFUIM_API_KEY = os.getenv("WAIFUIM_API_KEY")
WAIFUIT_API_KEY = os.getenv("WAIFUIT_API_KEY")  # Waifu.it token (Authorization: <TOKEN>)

_DEBUG_RAW = os.getenv("DEBUG_FETCH", "")
DEBUG_FETCH = str(_DEBUG_RAW).strip().lower() in ("1", "true", "yes", "on")

VC_IDS = [
    1353875050809524267,
    21409170559337762980,
    1353875404217253909,
    1353882705246556220
]
VC_CHANNEL_ID = 1371916812903780573

DATA_FILE = "data.json"
AUTOSAVE_INTERVAL = 30
MAX_USED_GIFS_PER_USER = 1000
FETCH_ATTEMPTS = 30
REQUEST_TIMEOUT = 12

# ------------- TAG SOURCES (seed) -------------
_seed_gif_tags = [
    "busty","big breasts","oppai","huge breasts","big boobs",
    "milf","mommy","mature","thick","thicc","thick thighs","thighs","thighfocus",
    "jiggle","bounce","booty","ass","big ass","curvy","round booty","thicc booty",
    "lingerie","underwear","panties","pantyhose","stockings","garter",
    "bikini","swimsuit","beach","cleavage","sideboob","underboob","ecchi",
    "fanservice","teasing","seductive","sexy","flirty","anime waifu","waifu",
    "cosplay","maid","school uniform","cheerleader","anime lingerie","oppai focus",
    "playful","blush","wink","kiss","cuddle","hug","dance","shimmy"
]

# ------------- BLOCK / FILTER TAGS -------------
HARD_TAGS = [
    "pussy","vagina","labia","clitoris","penis","cock","dick","shaft","testicles","balls","scrotum","anus",
    "uncensored","nude","naked","topless","bottomless","nipples","nipples out","nipples visible",
    "penetration","sex","porn","xxx","creampie","cum","cumshot","fisting","scat","bestiality",
    "underage","minor","loli","shota","child","young","agegap","age_gap","rape"
]
SOFT_TAGS = ["stockings","teasing","sexy","lewd","suggestive","cleavage","bikini","lingerie","thighs","booty","oppai","panties","cosplay","maid","swimsuit","underwear"]
FILENAME_BLOCK_KEYWORDS = ["orgy","creampie","facial","scat","fisting","bestiality"]
EXCLUDE_TAGS = ["loli","shota","child","minor","underage","young","schoolgirl","age_gap"]

# ------------- Logging -------------
logging.basicConfig(level=logging.DEBUG if DEBUG_FETCH else logging.INFO)
logger = logging.getLogger("spiciest-bot")

# ------------- Utilities (text normalization / nudity checks) -------------
def _normalize_text(s: str) -> str:
    return "" if not s else re.sub(r'[\s\-_]+', ' ', s.lower())

def analyze_nudity_indicators(text: str):
    """Return (hard_found:bool, soft_count:int)"""
    if not text or not isinstance(text, str):
        return False, 0
    normalized = _normalize_text(text)
    for h in HARD_TAGS:
        if h in normalized:
            return True, 0
    soft_count = 0
    for s in SOFT_TAGS:
        if s in normalized:
            soft_count += 1
    return False, soft_count

def contains_nude_indicators(text: str) -> bool:
    hard, soft_count = analyze_nudity_indicators(text)
    # Hard lens banned; if many soft tags (>=3) treat as risky and block
    return hard or (soft_count >= 3)

def filename_has_block_keyword(url: str) -> bool:
    if not url:
        return False
    low = url.lower()
    return any(kw in low for kw in FILENAME_BLOCK_KEYWORDS)

def _dedupe_preserve_order(lst):
    seen = set()
    out = []
    for x in lst:
        if not isinstance(x, str):
            continue
        nx = x.strip().lower()
        if not nx or nx in seen:
            continue
        seen.add(nx)
        out.append(nx)
    return out

def _tag_is_disallowed(t: str) -> bool:
    if not t:
        return True
    t = t.lower()
    if any(ex in t for ex in EXCLUDE_TAGS):
        return True
    # Don't ban soft tags — we want those — but block obvious hard tags
    for h in HARD_TAGS:
        if h in t:
            return True
    return False

# ------------- Data file init -------------
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({
            "join_counts": {},
            "used_gifs": {},
            "provider_weights": {},
            "sent_history": {},
            "gif_tags": []
        }, f, indent=2)

with open(DATA_FILE, "r") as f:
    data = json.load(f)

data.setdefault("join_counts", {})
data.setdefault("used_gifs", {})
data.setdefault("provider_weights", {})
data.setdefault("sent_history", {})
data.setdefault("gif_tags", [])

persisted = _dedupe_preserve_order(data.get("gif_tags", []))
seed = _dedupe_preserve_order(_seed_gif_tags)
combined = seed + [t for t in persisted if t not in seed]
GIF_TAGS = [t for t in _dedupe_preserve_order(combined) if not _tag_is_disallowed(t)]
if not GIF_TAGS:
    GIF_TAGS = ["waifu"]

# default provider weights — you can tune these via DATA_FILE provider_weights
default_weights = {
    "waifu_pics": 3,
    "waifu_im": 3,
    "waifu_it": 2,
    "nekos_best": 2,
    "nekos_life": 1,
    "nekos_moe": 1,
    "otakugifs": 1,
    "tenor": 3,
    "giphy": 3,
    "animegirls_online": 0
}
for k, v in default_weights.items():
    data["provider_weights"].setdefault(k, v)

@tasks.loop(seconds=AUTOSAVE_INTERVAL)
async def autosave_task():
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Autosave failed: {e}")

def save_data():
    try:
        data["gif_tags"] = GIF_TAGS
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save data: {e}")

def add_tag_to_gif_tags(tag: str):
    if not tag or not isinstance(tag, str): return False
    t = tag.strip().lower()
    if len(t) < 3 or t in GIF_TAGS or _tag_is_disallowed(t): return False
    GIF_TAGS.append(t)
    data["gif_tags"] = _dedupe_preserve_order(data.get("gif_tags", []) + [t])
    save_data()
    logger.debug(f"learned safe tag: {t}")
    return True

_token_split_re = re.compile(r"[^a-z0-9]+")
def extract_and_add_tags_from_meta(meta_text: str):
    if not meta_text: return
    text = _normalize_text(meta_text)
    tokens = _token_split_re.split(text)
    for tok in tokens:
        tok = tok.strip()
        if not tok or tok.isdigit() or len(tok) < 3: continue
        add_tag_to_gif_tags(tok)

async def _download_url(session, url, timeout=REQUEST_TIMEOUT):
    try:
        async with session.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                logger.debug(f"_download_url {url} -> status {resp.status}")
                return None, None
            ctype = resp.content_type or ""
            if "html" in ctype:
                logger.debug(f"_download_url skipping html content for {url}")
                return None, None
            b = await resp.read()
            return b, ctype
    except Exception as e:
        logger.debug(f"_download_url exception {e} for {url}")
        return None, None

# ------------- SPICE MAPPING (tag analysis -> provider queries) -------------
# The idea: convert user tags into provider-safe queries that prefer 'spicy but not nude'.
SPICY_TERMS = set([
    "busty","big breasts","oppai","big boobs","cleavage","underboob","sideboob",
    "lingerie","panties","bikini","swimsuit","thighs","thighfocus","stockings",
    "curvy","booty","ass","big ass","jiggle","bounce","cosplay","maid","school uniform",
    "cheerleader","seductive","flirty"
])

def classify_tag_strength(tag: str):
    """Return 'hard' if contains hard keywords to block, 'soft' if suggestive, 'neutral' otherwise."""
    if not tag: return "neutral"
    t = _normalize_text(tag)
    for h in HARD_TAGS:
        if h in t:
            return "hard"
    soft_count = 0
    for s in SOFT_TAGS:
        if s in t:
            soft_count += 1
    if any(s in t for s in SPICY_TERMS) or soft_count > 0:
        return "soft"
    return "neutral"

def map_tag_for_provider(provider: str, tag: str) -> str:
    """
    Convert arbitrary tag to provider-appropriate category or search term.
    Aim: spicy-but-not-nude (lingerie, bikini, cleavage, oppai, thigh, boots...)
    """
    t = (tag or "").lower().strip()
    if provider in ("tenor", "giphy"):
        # search keywords: add "anime" and focus on spicy keywords
        # prefer explicit spicy terms if present, else fallback to tag
        for s in SPICY_TERMS:
            if s in t:
                return f"{s} anime"
        # if tag is neutral, return "anime waifu"
        return f"{t or 'waifu'} anime"
    if provider == "waifu_pics":
        # waifu.pics has many SFW categories; to keep 'spicy but not nude' choose SFW categories that convey cute/sexy
        # If tag matches a known SFW category use it, else fallback to 'waifu'
        valid_sfw = {"waifu","neko","cuddle","hug","kiss","blush","dance","wink","pat","smug","bonk","awoo","nom","bite"}
        for s in SPICY_TERMS:
            if s in t:
                # Some spicy => prefer 'waifu' (SFW) but will add term to block checks later
                return "waifu"
        # if any direct SFW matches:
        if t in valid_sfw:
            return t
        return "waifu"
    if provider == "waifu_it":
        # Waifu.it categories vary; we'll fallback to named categories or 'waifu'
        for s in ("waifu","neko","kitsune","bikini","lingerie","sexy","cosplay"):
            if s in t:
                return s
        return "waifu"
    if provider.startswith("nekos"):
        # nekos.best/nekos.life support 'waifu','neko','avatar','hug','kiss','smug','cuddle'
        for s in ("waifu","neko","hug","kiss","cuddle","smug","pat"):
            if s in t:
                return s
        # if spicy words present, map to 'waifu'
        if any(s in t for s in SPICY_TERMS):
            return "waifu"
        return t or "waifu"
    if provider == "otakugifs":
        # Otakugifs uses 'reaction' param: kiss, hug, slap, dance, wink, cuddle...
        for s in ("kiss","hug","slap","punch","dance","wink","cuddle"):
            if s in t:
                return s
        return "waifu"
    if provider == "animegirls_online":
        return t or "waifu"
    # fallback
    return t or "waifu"

# ------------- FETCHERS (per-provider) -------------
# Each fetcher returns (bytes, filename, source_url) or (None,None,None)

async def fetch_from_waifu_pics(session, positive):
    try:
        category = map_tag_for_provider("waifu_pics", positive)
        # Use SFW endpoint to avoid explicit nudity — the mapper still biases spicy terms
        url = f"https://api.waifu.pics/sfw/{quote_plus(category)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                logger.debug(f"waifu_pics {category} -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("image")
            if not gif_url:
                return None, None, None
            # quick filters
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                return None, None, None
            extract_and_add_tags_from_meta(json.dumps(payload))
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"waifu_pics_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception as e:
        logger.debug(f"fetch_from_waifu_pics error: {e}")
        return None, None, None

async def fetch_from_waifu_im(session, positive):
    try:
        base = "https://api.waifu.im/search"
        # prefer non-nude results but allow 'suggestive' via tag selection — server controls is_nsfw param
        params = {"included_tags": positive, "is_nsfw": "false", "limit": 5}
        headers = {}
        if WAIFUIM_API_KEY:
            headers["Authorization"] = f"Bearer {WAIFUIM_API_KEY}"
        async with session.get(base, params=params, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                logger.debug(f"waifu.im search -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            images = payload.get("images") or payload.get("data") or []
            if not images:
                return None, None, None
            img = random.choice(images)
            gif_url = img.get("url") or img.get("image") or img.get("src")
            if not gif_url:
                return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(str(img)):
                return None, None, None
            extract_and_add_tags_from_meta(str(img.get("tags", "")))
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"waifu_im_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception as e:
        logger.debug(f"fetch_from_waifu_im error: {e}")
        return None, None, None

async def fetch_from_waifu_it(session, positive):
    try:
        if not WAIFUIT_API_KEY:
            logger.debug("waifu.it skipped: API key missing")
            return None, None, None
        category = map_tag_for_provider("waifu_it", positive)
        # Use v4 (stable)
        endpoint = f"https://waifu.it/api/v4/{quote_plus(category)}"
        headers = {"Authorization": WAIFUIT_API_KEY}
        async with session.get(endpoint, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                logger.debug(f"waifu.it {endpoint} -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            # payload shapes vary — try common keys
            gif_url = payload.get("url") or payload.get("image") or (payload.get("data") and payload["data"].get("url"))
            if not gif_url:
                logger.debug("waifu.it response missing url")
                return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                return None, None, None
            extract_and_add_tags_from_meta(json.dumps(payload))
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"waifu_it_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception as e:
        logger.debug(f"fetch_from_waifu_it error: {e}")
        return None, None, None

async def fetch_from_nekos_best(session, positive):
    try:
        cat = map_tag_for_provider("nekos_best", positive)
        url = f"https://nekos.best/api/v2/{quote_plus(cat)}?amount=1"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                logger.debug(f"nekos.best {cat} -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            results = payload.get("results") or []
            if not results: return None, None, None
            r = results[0]
            gif_url = r.get("url") or r.get("file") or r.get("image")
            if not gif_url: return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(str(r)):
                return None, None, None
            extract_and_add_tags_from_meta(json.dumps(r))
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"nekos_best_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception as e:
        logger.debug(f"fetch_from_nekos_best error: {e}")
        return None, None, None

async def fetch_from_nekos_life(session, positive):
    try:
        cat = map_tag_for_provider("nekos_life", positive)
        url = f"https://nekos.life/api/v2/img/{quote_plus(cat)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                logger.debug(f"nekos.life {cat} -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("image") or payload.get("result")
            if not gif_url: return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(str(payload)):
                return None, None, None
            extract_and_add_tags_from_meta(json.dumps(payload))
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"nekos_life_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception as e:
        logger.debug(f"fetch_from_nekos_life error: {e}")
        return None, None, None

async def fetch_from_nekos_moe(session, positive):
    try:
        tag = quote_plus(positive)
        url = f"https://nekos.moe/api/v3/gif/random?tag={tag}"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                logger.debug(f"nekos.moe -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            images = payload.get("images") or payload.get("data") or []
            if not images: return None, None, None
            item = random.choice(images)
            gif_url = item.get("file") or item.get("url") or item.get("original") or item.get("image")
            if not gif_url and item.get("id"):
                gif_url = f"https://nekos.moe/image/{item['id']}.gif"
            if not gif_url:
                return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(str(item)):
                return None, None, None
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"nekos_moe_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception as e:
        logger.debug(f"fetch_from_nekos_moe error: {e}")
        return None, None, None

async def fetch_from_otakugifs(session, positive):
    try:
        valid_reactions = ["kiss","hug","slap","punch","wink","dance","cuddle"]
        reaction = "waifu"
        for v in valid_reactions:
            if v in positive:
                reaction = v
                break
        url = f"https://otakugifs.xyz/api/gif?reaction={quote_plus(reaction)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                logger.debug(f"otakugifs -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("gif") or payload.get("file")
            if not gif_url: return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(str(payload)):
                return None, None, None
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"otakugifs_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception as e:
        logger.debug(f"fetch_from_otakugifs error: {e}")
        return None, None, None

async def fetch_from_animegirls_online(session, positive):
    try:
        url = f"https://animegirls.online/api/random?tag={quote_plus(positive)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                logger.debug(f"animegirls_online -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("image")
            if not gif_url: return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(str(payload)):
                return None, None, None
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"animegirls_online_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception as e:
        logger.debug(f"fetch_from_animegirls_online error: {e}")
        return None, None, None

async def fetch_from_tenor(session, positive):
    if not TENOR_API_KEY:
        return None, None, None
    try:
        q = map_tag_for_provider("tenor", positive)
        tenor_url = f"https://g.tenor.com/v1/search?q={quote_plus(q)}&key={TENOR_API_KEY}&limit=25&contentfilter=low"
        async with session.get(tenor_url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                logger.debug(f"tenor search -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            results = payload.get("results", []) or []
            random.shuffle(results)
            for r in results:
                media = r.get("media") or r.get("media_formats")
                gif_url = None
                if isinstance(media, list) and media:
                    m = media[0]
                    if isinstance(m, dict):
                        gif_url = (m.get("gif") or m.get("mediumgif") or {}).get("url")
                elif isinstance(media, dict):
                    for k in ("gif","mediumgif","nanogif","tinygif"):
                        entry = media.get(k)
                        if isinstance(entry, dict) and entry.get("url"):
                            gif_url = entry["url"]; break
                gif_url = gif_url or r.get("itemurl") or r.get("url")
                if not gif_url: continue
                if filename_has_block_keyword(gif_url) or contains_nude_indicators(str(r)):
                    continue
                b, ctype = await _download_url(session, gif_url)
                if not b: continue
                name = f"tenor_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}.gif"
                return b, name, gif_url
    except Exception as e:
        logger.debug(f"fetch_from_tenor error: {e}")
        return None, None, None

async def fetch_from_giphy(session, positive):
    if not GIPHY_API_KEY:
        return None, None, None
    try:
        q = map_tag_for_provider("giphy", positive)
        giphy_url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={quote_plus(q)}&limit=25&rating=pg-13"
        async with session.get(giphy_url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                logger.debug(f"giphy search -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            arr = payload.get("data", []) or []
            random.shuffle(arr)
            for item in arr:
                gif_url = item.get("images", {}).get("original", {}).get("url")
                if not gif_url: continue
                if filename_has_block_keyword(gif_url) or contains_nude_indicators(str(item)):
                    continue
                b, ctype = await _download_url(session, gif_url)
                if not b: continue
                name = f"giphy_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}.gif"
                return b, name, gif_url
    except Exception as e:
        logger.debug(f"fetch_from_giphy error: {e}")
        return None, None, None

# ------------- Provider registry & pool builder -------------
PROVIDER_FETCHERS = {
    "waifu_pics": fetch_from_waifu_pics,
    "waifu_im": fetch_from_waifu_im,
    "waifu_it": fetch_from_waifu_it,
    "nekos_best": fetch_from_nekos_best,
    "nekos_life": fetch_from_nekos_life,
    "nekos_moe": fetch_from_nekos_moe,
    "otakugifs": fetch_from_otakugifs,
    "animegirls_online": fetch_from_animegirls_online,
    "tenor": fetch_from_tenor,
    "giphy": fetch_from_giphy
}

def build_provider_pool():
    pool = []
    for prov, weight in data["provider_weights"].items():
        if prov not in PROVIDER_FETCHERS:
            continue
        if weight <= 0:
            continue
        pool.extend([prov] * max(1, int(weight)))
    # drop those that require missing keys
    if not TENOR_API_KEY:
        pool = [p for p in pool if p != "tenor"]
    if not GIPHY_API_KEY:
        pool = [p for p in pool if p != "giphy"]
    if not WAIFUIT_API_KEY:
        pool = [p for p in pool if p != "waifu_it"]
    random.shuffle(pool)
    # fallback: if empty, include any provider that doesn't require missing keys
    if not pool:
        pool = [p for p in PROVIDER_FETCHERS.keys() if not (
            (p == "tenor" and not TENOR_API_KEY) or
            (p == "giphy" and not GIPHY_API_KEY) or
            (p == "waifu_it" and not WAIFUIT_API_KEY)
        )]
    return pool

# ------------- Core fetch loop -------------
async def fetch_gif(user_id):
    user_key = str(user_id)
    sent = data["sent_history"].setdefault(user_key, [])
    providers = build_provider_pool()
    async with aiohttp.ClientSession() as session:
        for attempt in range(FETCH_ATTEMPTS):
            if not providers:
                providers = build_provider_pool()
            provider = random.choice(providers)
            positive = random.choice(GIF_TAGS)
            if DEBUG_FETCH:
                logger.debug(f"[fetch_gif] attempt {attempt+1}/{FETCH_ATTEMPTS} provider={provider} tag='{positive}'")
            fetcher = PROVIDER_FETCHERS.get(provider)
            if not fetcher:
                continue
            try:
                result = await fetcher(session, positive)
            except Exception as e:
                logger.debug(f"fetcher {provider} raised: {e}")
                result = (None, None, None)
            if not result or not result[0]:
                continue
            b, name, gif_url = result
            if not gif_url:
                continue
            # final filters
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                continue
            gif_hash = hashlib.sha1((gif_url or name or "").encode()).hexdigest()
            if gif_hash in sent:
                continue
            sent.append(gif_hash)
            if len(sent) > MAX_USED_GIFS_PER_USER:
                del sent[:len(sent) - MAX_USED_GIFS_PER_USER]
            save_data()
            return b, name, gif_url
    return None, None, None

# ------------- Discord messaging -------------
# You can keep your previous JOIN_GREETINGS / LEAVE_GREETINGS arrays — reuse them
JOIN_GREETINGS = [
    "🌸 {display_name} sashays into the scene — waifu energy rising!",
    "✨ {display_name} arrived and the room got a whole lot warmer.",
    "🔥 {display_name} joined — clutch your hearts (and waifus).",
    "💫 {display_name} appears — the waifu meter spikes.",
    "🍑 {display_name} walked in — cheeks feeling watched.",
    "😏 {display_name} entered — someone brought snacks and thighs.",
    "🎀 {display_name} steps in — cute, spicy, and a little extra.",
    "🩷 {display_name} joined — cleavage alert in 3...2...1.",
    "🌙 {display_name} arrives — moonlight + waifu vibes.",
    "🦊 {display_name} has joined — foxiness overload.",
    "💃 {display_name} joined — shake it, waifu style.",
    "🎴 {display_name} appears — draw that lucky card, baby.",
    "🍡 {display_name} came — sweet, tempting, and blushing.",
    "🌶️ {display_name} arrived — a little spice never hurt.",
    "🪩 {display_name} joined — ready to party and flirt.",
    "👑 {display_name} enters — royalty of the flirty league.",
    "🌺 {display_name} joined — flowers + flirts incoming.",
    "🍑 Thicc vibes as {display_name} arrives.",
    "✨ Stars twinkle — {display_name} is here to slay.",
    "🥂 {display_name} has entered — cheers to the waifu life.",
    "🫠 {display_name} joined — melting hearts left and right.",
    "🎯 {display_name} arrived — hit the target of spiciness.",
    "🧋 {display_name} stepped in — sweet bubble tea energy.",
    "🏮 {display_name} joins — festival of flirty faces.",
    "🫦 {display_name} entered — pouty lips and big eyes.",
    "🎐 {display_name} arrives — wind chimes and winks.",
    "🌟 {display_name} joined — glitter and glances.",
    "🛸 {display_name} beamed down — alien waifu confirmed.",
    "🌈 {display_name} arrives — color me smitten.",
    "🍒 {display_name} showed up — cherry cheeks and smiles.",
    "🪄 {display_name} joined — magic of a thousand blushes.",
    "🧸 {display_name} enters — soft hugs and soft waifus.",
    "💌 {display_name} arrived — a love letter in motion.",
    "🔮 {display_name} joined — destiny's spicy twist.",
    "🕊️ {display_name} appears — gentle flirts incoming.",
    "📸 {display_name} walks in — strike a pose, darling.",
    "🥳 {display_name} joined — confetti, smiles, and thigh-highs.",
    "🧿 {display_name} arrived — protective charm, seductive grin.",
    "🏖️ {display_name} joins — beach bikini and sun-kissed waifu.",
    "🚀 {display_name} enters — lift off to flirt space.",
    "🎶 {display_name} joined — soundtrack: heartbeat & blush.",
    "🍯 {display_name} walks in — sticky-sweet charm detected.",
    "🧁 {display_name} joined — sugar-coated shenanigans.",
    "💎 {display_name} arrives — gem-bright and cheeky.",
    "🩰 {display_name} joined — tutu twirls and coy winks.",
    "🦄 {display_name} enters — magical waifu shimmer.",
    "🌊 {display_name} arrives — waves of flirtation.",
    "🍓 {display_name} joined — strawberry-sweet smiles.",
    "🎈 {display_name} appears — balloon pop of attention.",
    "🌿 {display_name} entered — herb-scented flirty breeze.",
    "🧩 {display_name} joined — puzzlingly cute moves.",
    "🧬 {display_name} arrived — genetically optimized charm.",
    "🌓 {display_name} joins — half-moon, full tease.",
    "📚 {display_name} enters — scholarly seduction.",
    "🏵️ {display_name} arrived — floral blush and mischief.",
    "🛁 {display_name} joined — steam, suds, and soft glances.",
    "🧨 {display_name} appears — explosive cuteness.",
    "🦋 {display_name} joined — fluttering lashes and coy smiles.",
    "🥀 {display_name} enters — rosy petals and low-key spice.",
    "🍫 {display_name} arrived — chocolatey charm unlocked.",
    "🍷 {display_name} joined — sip, smile, sway.",
    "🪙 {display_name} appears — a coin-flip of choices: flirt or tease?",
    "🧭 {display_name} arrived — compass points to cute.",
    "🪴 {display_name} joined — potted waifu energy.",
    "🗝️ {display_name} enters — key to your heart (maybe!).",
    "🛍️ {display_name} arrived — shopping bags full of sass.",
    "🧶 {display_name} joins — knitted charm and warm hugs.",
    "🧥 {display_name} entered — coat-swathe and smolder.",
    "🩸 {display_name} joined — whisper of dramatic flair.",
    "🪞 {display_name} appears — reflection looks better today.",
    "🖤 {display_name} arrived — mysterious and alluring.",
    "💐 {display_name} joined — a bouquet of winks.",
    "🍀 {display_name} enters — lucky charm energy.",
    "🛹 {display_name} arrived — skater flip and flirt.",
    "🛼 {display_name} joins — roller-disco tease.",
    "🕶️ {display_name} entered — sunglasses, smiles, sass.",
    "📯 {display_name} arrived — the trumpets of attention!",
    "🔔 {display_name} joined — ding-ding! look here!",
    "🎤 {display_name} enters — sing, sway, seduce.",
    "⛩️ {display_name} joined — torii gate to waifu heaven.",
    "🏮 {display_name} appears — lantern-lit flirtation.",
    "🧚 {display_name} joined — fairy winks and mischief.",
    "🌸 {display_name} steps in — blossom & blush combo.",
    "😽 {display_name} joined — cat-like charm engaged.",
    "🥂 {display_name} arrived — cheers to cheeky times.",
    "🩰 {display_name} steps in — ballet blush style.",
    "🧋 {display_name} walked in — boba and flirty vibes.",
    "🪄 {display_name} arrived — spellbound cuteness."
]

LEAVE_GREETINGS = [
    "🌙 {display_name} drifts away — the moon hushes a little.",
    "🍃 {display_name} fades out — petals fall where they once stood.",
    "💫 {display_name} slips away — stardust in their wake.",
    "🥀 {display_name} leaves — a blush left behind.",
    "🫶 {display_name} departed — hands empty, hearts full.",
    "🪄 {display_name} vanished — the magic took them home.",
    "🍯 {display_name} left — sticky-sweet memories remain.",
    "🧸 {display_name} walked off — soft hugs lost a bearer.",
    "🫠 {display_name} logged off — meltdown of cuteness over.",
    "🎴 {display_name} leaves — fortune says 'see you soon'.",
    "🎈 {display_name} floated away — pop! gone.",
    "🚀 {display_name} took off — orbiting elsewhere now.",
    "🏖️ {display_name} left — headed to sunny shores.",
    "🍓 {display_name} walked off — strawberry smiles left behind.",
    "🎀 {display_name} departs — ribbon untied, wink kept.",
    "🪩 {display_name} left — disco lights dim a bit.",
    "🌺 {display_name} leaves — trail of petals.",
    "🦊 {display_name} slinked away — fox-like mystery continues.",
    "🕊️ {display_name} flew off — gentle and graceful.",
    "📸 {display_name} left — last snapshot captured the grin.",
    "🧁 {display_name} dipped out — frosting still warm.",
    "🔮 {display_name} vanished — fate will meet again.",
    "🪞 {display_name} walked away — mirror shows a smile.",
    "🍷 {display_name} left — glass half-empty of flirtation.",
    "🧭 {display_name} left — compass points elsewhere.",
    "🧶 {display_name} departed — yarn untangles softly.",
    "🩰 {display_name} leaves — tutus and goodbyes.",
    "🛁 {display_name} left — steam cleared the room.",
    "🦄 {display_name} galloped off — mythical and missed.",
    "📚 {display_name} left — story paused mid-page.",
    "🍫 {display_name} faded — cocoa-sweet exit.",
    "🫦 {display_name} stepped away — pout still in the air.",
    "🌊 {display_name} drifted off — tide took them.",
    "🎶 {display_name} left — song fades but hum remains.",
    "🧿 {display_name} departed — charm still glowing.",
    "🏮 {display_name} left — lanterns dim.",
    "🪴 {display_name} stepped away — potted bliss remains.",
    "🗝️ {display_name} left — key placed down gently.",
    "⛩️ {display_name} left the shrine — prayers kept.",
    "🧚 {display_name} fluttered away — fairy dust lingers.",
    "🖤 {display_name} left — mysterious silence follows.",
    "🌿 {display_name} departed — green hush in the air.",
    "🛍️ {display_name} left — bags full of mischief.",
    "📯 {display_name} rode off — trumpet call dwindles.",
    "🪙 {display_name} vanished — luck rolls onward.",
    "🪄 {display_name} left — spell undone.",
    "😽 {display_name} slipped away — catlike grace retained.",
    "🎯 {display_name} left — target missed this time.",
    "🥂 {display_name} left — toast to next time.",
    "🧥 {display_name} left — coat taken, glances kept.",
    "🛹 {display_name} skated off — kickflip and goodbye.",
    "🛼 {display_name} rolled away — rollerbeats fade.",
    "🕶️ {display_name} left — shades down and gone.",
    "🔔 {display_name} departed — bell tolls faintly.",
    "📸 {display_name} left — last frame a smirk.",
    "🪙 {display_name} left — coin flicked into the void.",
    "🧩 {display_name} walked off — puzzle missing a piece.",
    "🪞 {display_name} left — reflection smiles alone.",
    "🌸 {display_name} drifted away — petals to the wind.",
    "💌 {display_name} left — letter sealed and mailed.",
    "🏵️ {display_name} departed — floral farewell.",
    "🧿 {display_name} left — charm still hums softly.",
    "🧋 {display_name} left — last bubble popped.",
    "🍒 {display_name} left — cherries still on the plate.",
    "🍡 {display_name} walked away — dango leftover.",
    "🧨 {display_name} vanished — sparkles died down.",
    "🛏️ {display_name} left — nap time continues elsewhere.",
    "🪶 {display_name} left — feather trails behind.",
    "🛸 {display_name} left — alien waifu gone."
]
while len(LEAVE_GREETINGS) < 60:
    LEAVE_GREETINGS.append(random.choice(LEAVE_GREETINGS))

def make_embed(title, desc, member, kind="join", count=None):
    color = discord.Color.purple() if kind == "join" else discord.Color.dark_gray()
    embed = discord.Embed(title=title, description=desc, color=color, timestamp=datetime.utcnow())
    try:
        embed.set_thumbnail(url=member.display_avatar.url)
    except Exception:
        pass
    footer = f"{member.display_name} • {member.id}"
    if count:
        footer += f" • Joins: {count}"
    embed.set_footer(text=footer)
    return embed

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    autosave_task.start()
    logger.info(f"✅ Logged in as {bot.user} (id={bot.user.id})")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    text_channel = bot.get_channel(VC_CHANNEL_ID)

    # Auto-join / move
    if after.channel and (after.channel.id in VC_IDS) and (before.channel != after.channel):
        try:
            vc = discord.utils.get(bot.voice_clients, guild=member.guild)
            if vc:
                if vc.channel.id != after.channel.id:
                    await vc.move_to(after.channel)
            else:
                await after.channel.connect()
        except Exception as e:
            logger.warning(f"VC join logic error: {e}")

    # JOIN message
    if after.channel and (after.channel.id in VC_IDS) and (before.channel != after.channel):
        raw = random.choice(JOIN_GREETINGS)
        msg = raw.format(display_name=member.display_name)
        data["join_counts"][str(member.id)] = data["join_counts"].get(str(member.id), 0) + 1
        embed = make_embed("Welcome!", msg, member, "join", data["join_counts"][str(member.id)])
        gif_bytes, gif_name, gif_url = await fetch_gif(member.id)
        if gif_bytes:
            try:
                file_server = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                embed.set_image(url=f"attachment://{gif_name}")
                if text_channel:
                    await text_channel.send(embed=embed, file=file_server)
                try:
                    file_dm = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                    await member.send(embed=embed, file=file_dm)
                except Exception:
                    # fallback: DM embed with link only
                    try:
                        embed_dm = make_embed("Welcome!", msg, member, "join", data["join_counts"][str(member.id)])
                        if gif_url:
                            embed_dm.description += f"\n[View media here]({gif_url})"
                        await member.send(embed=embed_dm)
                    except Exception:
                        logger.debug(f"Failed to DM {member.display_name}")
            except Exception as e:
                logger.error(f"Failed to send join image: {e}")
                if text_channel:
                    await text_channel.send(embed=embed)
        else:
            if text_channel:
                await text_channel.send(embed=embed)

    # LEAVE message
    if before.channel and (before.channel.id in VC_IDS) and (after.channel != before.channel):
        raw = random.choice(LEAVE_GREETINGS)
        msg = raw.format(display_name=member.display_name)
        embed = make_embed("Goodbye!", msg, member, "leave")
        gif_bytes, gif_name, gif_url = await fetch_gif(member.id)
        if gif_bytes:
            try:
                file_server = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                embed.set_image(url=f"attachment://{gif_name}")
                if text_channel:
                    await text_channel.send(embed=embed, file=file_server)
                try:
                    file_dm = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                    await member.send(embed=embed, file=file_dm)
                except Exception:
                    pass
            except Exception:
                if text_channel:
                    await text_channel.send(embed=embed)
        else:
            if text_channel:
                await text_channel.send(embed=embed)

        # disconnect if empty
        try:
            vc = discord.utils.get(bot.voice_clients, guild=member.guild)
            if vc and len([m for m in vc.channel.members if not m.bot]) == 0:
                await vc.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    if not TOKEN:
        logger.error("TOKEN environment missing. Set TOKEN and restart.")
    else:
        bot.run(TOKEN)
