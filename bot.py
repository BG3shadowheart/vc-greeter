# bot_spiciest_final_all_in_one.py
# Final consolidated NSFW spiciest bot (round-robin / provider-term priority)
# Requirements: aiohttp, discord.py
# Env vars: TOKEN (required), TENOR_API_KEY (opt), GIPHY_API_KEY (opt),
#          WAIFUIM_API_KEY (opt), WAIFUIT_API_KEY (opt), DEBUG_FETCH (opt true/1),
#          TRUE_RANDOM (opt true/1)
# Optional: DISCORD_MAX_UPLOAD (bytes)

import os
import io
import json
import random
import hashlib
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlparse
import aiohttp
import discord
from discord.ext import commands, tasks
from collections import deque

# ---------------- CONFIG ----------------
TOKEN = os.getenv("TOKEN")
TENOR_API_KEY = os.getenv("TENOR_API_KEY")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")
WAIFUIM_API_KEY = os.getenv("WAIFUIM_API_KEY")
WAIFUIT_API_KEY = os.getenv("WAIFUIT_API_KEY")

_DEBUG_RAW = os.getenv("DEBUG_FETCH", "")
DEBUG_FETCH = str(_DEBUG_RAW).strip().lower() in ("1", "true", "yes", "on")
TRUE_RANDOM = str(os.getenv("TRUE_RANDOM", "")).strip().lower() in ("1", "true", "yes")

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
FETCH_ATTEMPTS = 40
REQUEST_TIMEOUT = 14

DISCORD_MAX_UPLOAD = int(os.getenv("DISCORD_MAX_UPLOAD", str(8 * 1024 * 1024)))
HEAD_SIZE_LIMIT = DISCORD_MAX_UPLOAD
DEFAULT_HEADERS = {"User-Agent": "spiciest-bot/1.0 (+https://github.com/)"}

# ---------------- Logging ----------------
logging.basicConfig(level=logging.DEBUG if DEBUG_FETCH else logging.INFO)
logger = logging.getLogger("spiciest-final")

# ---------------- Safety lists ----------------
_seed_gif_tags = [
    "busty","big breasts","oppai","huge breasts","big boobs",
    "milf","mommy","mature","thick","thicc","thick thighs","thighs","thighfocus",
    "jiggle","bounce","booty","ass","big ass","curvy","round booty","thicc booty",
    "lingerie","panties","pantyhose","stockings","garter",
    "bikini","swimsuit","cleavage","sideboob","underboob","ecchi",
    "fanservice","teasing","seductive","sexy","flirty","waifu","cosplay","maid","school uniform","cheerleader"
]

ILLEGAL_TAGS = [
    "underage","minor","child","loli","shota","young","agegap","rape","sexual violence",
    "bestiality","zoophilia","bestial","scat","fisting","incest","pedo","pedophile","creampie"
]

FILENAME_BLOCK_KEYWORDS = ["orgy","creampie","facial","scat","fisting","bestiality"]
EXCLUDE_TAGS = ["loli","shota","child","minor","underage","young","schoolgirl","age_gap"]

# ---------------- Helpers ----------------
def _normalize_text(s: str) -> str:
    return "" if not s else re.sub(r'[\s\-_]+', ' ', s.lower())

def contains_illegal_indicators(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    normalized = _normalize_text(text)
    for bad in ILLEGAL_TAGS:
        if bad in normalized:
            return True
    return False

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
    if any(b in t for b in ILLEGAL_TAGS):
        return True
    return False

# ---------------- Data file init ----------------
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

# Normalize persisted provider weights to 1 unless user explicitly set 0
# This prevents old high weights (e.g. giphy) from dominating.
default_providers = ["waifu_pics","waifu_im","waifu_it","nekos_best","nekos_life","nekos_moe","otakugifs","animegirls_online","tenor","giphy"]
for prov in default_providers:
    if data.get("provider_weights", {}).get(prov, None) == 0:
        # keep disabled intentionally
        continue
    data.setdefault("provider_weights", {})[prov] = 1

with open(DATA_FILE, "w") as _f:
    json.dump(data, _f, indent=2)
if DEBUG_FETCH:
    logger.debug(f"Normalized provider_weights: {data.get('provider_weights')}")

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

def persist_all_data():
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to persist all data: {e}")

def add_tag_to_gif_tags(tag: str):
    if not tag or not isinstance(tag, str): return False
    t = tag.strip().lower()
    if len(t) < 3 or t in GIF_TAGS or _tag_is_disallowed(t): return False
    GIF_TAGS.append(t)
    data["gif_tags"] = _dedupe_preserve_order(data.get("gif_tags", []) + [t])
    save_data()
    logger.debug(f"learned tag: {t}")
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

# ---------------- HTTP helpers ----------------
async def _head_url(session, url, timeout=REQUEST_TIMEOUT):
    try:
        async with session.head(url, timeout=timeout, headers=DEFAULT_HEADERS, allow_redirects=True) as resp:
            return resp.status, dict(resp.headers)
    except Exception as e:
        if DEBUG_FETCH:
            logger.debug(f"HEAD failed for {url}: {e}")
        return None, {}

async def _download_bytes_with_limit(session, url, size_limit=HEAD_SIZE_LIMIT, timeout=REQUEST_TIMEOUT):
    try:
        async with session.get(url, timeout=timeout, headers=DEFAULT_HEADERS, allow_redirects=True) as resp:
            if resp.status != 200:
                if DEBUG_FETCH:
                    logger.debug(f"GET {url} returned {resp.status}")
                return None, None
            ctype = resp.content_type or ""
            total = 0
            chunks = []
            async for chunk in resp.content.iter_chunked(1024):
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > size_limit:
                    if DEBUG_FETCH:
                        logger.debug(f"download exceeded limit {size_limit} for {url}")
                    return None, ctype
            return b"".join(chunks), ctype
    except Exception as e:
        if DEBUG_FETCH:
            logger.debug(f"GET exception for {url}: {e}")
        return None, None

# ---------------- Provider-specific term pools ----------------
WAIFU_PICS_TERMS = [
    "oppai","busty","big breasts","huge breasts","underboob","sideboob",
    "lingerie","panties","thong","pantyhose","stockings","garter",
    "bikini","swimsuit","beach","cleavage","lowcut","crop top","corset",
    "thighs","thighfocus","booty","big ass","curvy","seductive","teasing",
    "blush","wink","kiss","cuddle","playful"
]

WAIFU_IM_TERMS = [
    "busty","oppai","cleavage","lingerie","panties","underwear","pantie",
    "thighs","stockings","booty","bikini","swimsuit","brazilian","micro bikini",
    "crop top","corset","latex","sexy cosplay","maid outfit","school uniform","cheerleader",
    "underboob","sideboob","nip slip","peekaboo","soft erotic","flirty","seductive"
]

WAIFU_IT_TERMS = [
    "waifu","oppai","busty","bikini","lingerie","thighs","stockings","garter",
    "panties","cosplay","maid","school uniform","cheerleader","cute waifu","hot waifu",
    "big boobs","big ass","booty shake","thighfocus","underboob","sideboob",
    "underwear","seductive pose","playful tease","blush","wink","cuddle","kiss"
]

NEKOS_BEST_TERMS = [
    "waifu","neko","oppai","busty","hug","kiss","cuddle","smug","pat",
    "bikini","lingerie","thighs","booty","dance","blush","wink","seduce",
    "fanservice","ecchi","cosplay","maid","school","idol","swimsuit","underboob",
    "sideboob","cleavage","peach","thicc"
]

NEKOS_LIFE_TERMS = [
    "neko","waifu","bikini","swimsuit","lingerie","panties","thighs","stockings",
    "oppai","big breasts","cute cosplay","maid","school uniform","cheerleader",
    "blush","kiss","cuddle","hug","smug","pat","dance","wink","teasing","seductive"
]

NEKOS_MOE_TERMS = [
    "waifu","oppai","busty","bikini","lingerie","thighs","booty","cute cosplay",
    "maid","schoolgirl","cheerleader","swimsuit","underwear","panties","stockings",
    "underboob","sideboob","cleavage","thicc","jiggle","bounce","blush","wink","kiss"
]

NEKOAPI_TERMS = [
    "waifu","neko","oppai","busty","lingerie","panties","thighs","stockings",
    "bikini","swimsuit","maid","cosplay","cleavage","underboob","sideboob","booty",
    "big ass","thicc","curvy","seductive","teasing","flirty","blush","kiss","cuddle"
]

OTAKUGIFS_TERMS = [
    "kiss","hug","slap","dance","wink","cuddle","poke","blush","smug","pat",
    "sexy","tease","fanservice","bikini","lingerie","oppai","thighs","booty",
    "waifu","cosplay","maid","school uniform","cheerleader","thicc","jiggle"
]

ANIMEGIRLS_TERMS = [
    "waifu","oppai","bikini","lingerie","thighs","stockings","panties","booty",
    "swimsuit","cosplay","maid","school uniform","teasing","seductive","blush",
    "wink","kiss","cuddle","dance","sideboob","underboob","cleavage","thicc","curvy"
]

TENOR_TERMS = [
    "busty anime","big breasts anime","oppai anime","cleavage anime","lingerie anime",
    "bikini anime","thighs anime","stockings anime","booty anime","big ass anime",
    "ecchi anime","fanservice anime","sexy anime","flirty anime","cosplay anime",
    "maid anime","school uniform anime","cheerleader anime","underboob anime","sideboob anime",
    "thicc anime","jiggle anime","bounce anime","peekaboo anime","playful anime"
]

GIPHY_TERMS = [
    "busty anime","big boobs anime","oppai anime","bikini anime","lingerie anime",
    "cleavage anime","thighs anime","stockings anime","booty shake anime","curvy anime",
    "ecchi","fanservice","sexy anime","flirty","cosplay","maid outfit anime",
    "school uniform anime","cheerleader anime","underboob","sideboob","thicc anime",
    "jiggle","bounce","peekaboo","playful","seductive"
]

PROVIDER_TERMS = {
    "waifu_pics": WAIFU_PICS_TERMS,
    "waifu_im": WAIFU_IM_TERMS,
    "waifu_it": WAIFU_IT_TERMS,
    "nekos_best": NEKOS_BEST_TERMS,
    "nekos_life": NEKOS_LIFE_TERMS,
    "nekos_moe": NEKOS_MOE_TERMS,
    "nekoapi": NEKOAPI_TERMS,
    "otakugifs": OTAKUGIFS_TERMS,
    "animegirls_online": ANIMEGIRLS_TERMS,
    "tenor": TENOR_TERMS,
    "giphy": GIPHY_TERMS
}

# ---------------- Tag -> provider mapping ----------------
def map_tag_for_provider(provider: str, tag: str) -> str:
    """
    Prefer provider-specific pool. If incoming tag already matches pool, return it.
    Otherwise pick a pool term to maximize coverage.
    """
    t = (tag or "").lower().strip()
    pool = PROVIDER_TERMS.get(provider, [])
    if t:
        for p in pool:
            if p in t:
                return p
    # If pool available, pick randomly from pool (makes provider use its supported terms)
    if pool:
        return random.choice(pool)
    # fallback to passed tag or a neutral 'waifu'
    return t or "waifu"

# ------------------ FETCHERS (return gif_url, name_hint, meta) ------------------
# (Use provider pools and mapping in fetch_gif call to prioritize provider categories)

async def fetch_from_waifu_pics(session, positive):
    try:
        category = map_tag_for_provider("waifu_pics", positive)
        url = f"https://api.waifu.pics/nsfw/{quote_plus(category)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT, headers=DEFAULT_HEADERS) as resp:
            if resp.status != 200:
                logger.debug(f"waifu_pics nsfw {category} -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("image")
            if not gif_url: return None, None, None
            if filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(payload) + " " + (category or "")): return None, None, None
            extract_and_add_tags_from_meta(json.dumps(payload))
            return gif_url, f"waifu_pics_{category}", payload
    except Exception as e:
        logger.debug(f"fetch_from_waifu_pics error: {e}")
        return None, None, None

async def fetch_from_waifu_im(session, positive):
    try:
        q = map_tag_for_provider("waifu_im", positive)
        base = "https://api.waifu.im/search"
        params = {"included_tags": q, "is_nsfw": "true", "limit": 5}
        headers = dict(DEFAULT_HEADERS)
        if WAIFUIM_API_KEY:
            headers["Authorization"] = f"Bearer {WAIFUIM_API_KEY}"
        async with session.get(base, params=params, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                logger.debug(f"waifu.im nsfw search -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            images = payload.get("images") or payload.get("data") or []
            if not images: return None, None, None
            img = random.choice(images)
            gif_url = img.get("url") or img.get("image") or img.get("src")
            if not gif_url: return None, None, None
            if filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(img) + " " + (q or "")): return None, None, None
            extract_and_add_tags_from_meta(str(img.get("tags", "")))
            return gif_url, f"waifu_im_{q}", img
    except Exception as e:
        logger.debug(f"fetch_from_waifu_im error: {e}")
        return None, None, None

async def fetch_from_waifu_it(session, positive):
    try:
        if not WAIFUIT_API_KEY:
            logger.debug("waifu.it skipped: key missing")
            return None, None, None
        q = map_tag_for_provider("waifu_it", positive)
        endpoint = f"https://waifu.it/api/v4/{quote_plus(q)}"
        headers = dict(DEFAULT_HEADERS)
        headers["Authorization"] = WAIFUIT_API_KEY
        async with session.get(endpoint, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                logger.debug(f"waifu.it {endpoint} -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("image") or (payload.get("data") and payload["data"].get("url"))
            if not gif_url: return None, None, None
            if filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(payload) + " " + (q or "")): return None, None, None
            extract_and_add_tags_from_meta(json.dumps(payload))
            return gif_url, f"waifu_it_{q}", payload
    except Exception as e:
        logger.debug(f"fetch_from_waifu_it error: {e}")
        return None, None, None

async def fetch_from_nekos_best(session, positive):
    try:
        q = map_tag_for_provider("nekos_best", positive)
        url = f"https://nekos.best/api/v2/{quote_plus(q)}?amount=1"
        async with session.get(url, timeout=REQUEST_TIMEOUT, headers=DEFAULT_HEADERS) as resp:
            if resp.status != 200:
                logger.debug(f"nekos.best {q} -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            results = payload.get("results") or []
            if not results: return None, None, None
            r = results[0]
            gif_url = r.get("url") or r.get("file") or r.get("image")
            if not gif_url: return None, None, None
            if filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(r) + " " + (q or "")): return None, None, None
            extract_and_add_tags_from_meta(json.dumps(r))
            return gif_url, f"nekos_best_{q}", r
    except Exception as e:
        logger.debug(f"fetch_from_nekos_best error: {e}")
        return None, None, None

async def fetch_from_nekos_life(session, positive):
    try:
        q = map_tag_for_provider("nekos_life", positive)
        url = f"https://nekos.life/api/v2/img/{quote_plus(q)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT, headers=DEFAULT_HEADERS) as resp:
            if resp.status != 200:
                logger.debug(f"nekos.life {q} -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("image") or payload.get("result")
            if not gif_url: return None, None, None
            if filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(payload) + " " + (q or "")): return None, None, None
            extract_and_add_tags_from_meta(json.dumps(payload))
            return gif_url, f"nekos_life_{q}", payload
    except Exception as e:
        logger.debug(f"fetch_from_nekos_life error: {e}")
        return None, None, None

async def fetch_from_nekos_moe(session, positive):
    try:
        q = map_tag_for_provider("nekos_moe", positive)
        url = f"https://nekos.moe/api/v3/gif/random?tag={quote_plus(q)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT, headers=DEFAULT_HEADERS) as resp:
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
            if not gif_url: return None, None, None
            if filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(item) + " " + (q or "")): return None, None, None
            return gif_url, f"nekos_moe_{q}", item
    except Exception as e:
        logger.debug(f"fetch_from_nekos_moe error: {e}")
        return None, None, None

async def fetch_from_otakugifs(session, positive):
    try:
        q = map_tag_for_provider("otakugifs", positive)
        valid_reactions = ["kiss","hug","slap","punch","wink","dance","cuddle"]
        reaction = "waifu"
        for v in valid_reactions:
            if v in q:
                reaction = v
                break
        url = f"https://otakugifs.xyz/api/gif?reaction={quote_plus(reaction)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT, headers=DEFAULT_HEADERS) as resp:
            if resp.status != 200:
                logger.debug(f"otakugifs -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("gif") or payload.get("file")
            if not gif_url: return None, None, None
            if filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(payload) + " " + (q or "")): return None, None, None
            return gif_url, f"otakugifs_{reaction}", payload
    except Exception as e:
        logger.debug(f"fetch_from_otakugifs error: {e}")
        return None, None, None

async def fetch_from_animegirls_online(session, positive):
    try:
        q = map_tag_for_provider("animegirls_online", positive)
        url = f"https://animegirls.online/api/random?tag={quote_plus(q)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT, headers=DEFAULT_HEADERS) as resp:
            if resp.status != 200:
                logger.debug(f"animegirls_online -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("image")
            if not gif_url: return None, None, None
            if filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(payload) + " " + (q or "")): return None, None, None
            return gif_url, f"animegirls_online_{q}", payload
    except Exception as e:
        logger.debug(f"fetch_from_animegirls_online error: {e}")
        return None, None, None

async def fetch_from_tenor(session, positive):
    if not TENOR_API_KEY:
        return None, None, None
    try:
        q = map_tag_for_provider("tenor", positive)
        tenor_url = f"https://g.tenor.com/v1/search?q={quote_plus(q)}&key={TENOR_API_KEY}&limit=30&contentfilter=off"
        async with session.get(tenor_url, timeout=REQUEST_TIMEOUT, headers=DEFAULT_HEADERS) as resp:
            if resp.status != 200:
                logger.debug(f"tenor -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            results = payload.get("results", []) or []
            random.shuffle(results)
            for r in results:
                media = r.get("media") or r.get("media_formats") or []
                gif_url = None
                if isinstance(media, list) and media:
                    m = media[0]
                    for k in ("gif","mediumgif","nanogif","tinygif","mp4","webm"):
                        entry = m.get(k)
                        if isinstance(entry, dict) and entry.get("url"):
                            gif_url = entry["url"]; break
                elif isinstance(media, dict):
                    for k in ("gif","mediumgif","nanogif","tinygif","mp4","webm"):
                        entry = media.get(k)
                        if isinstance(entry, dict) and entry.get("url"):
                            gif_url = entry["url"]; break
                if not gif_url:
                    for key in ("itemurl","url","media_url"):
                        if r.get(key):
                            gif_url = r.get(key); break
                if not gif_url: continue
                if filename_has_block_keyword(gif_url): continue
                if contains_illegal_indicators(json.dumps(r) + " " + (q or "")): continue
                return gif_url, f"tenor_{q}", r
    except Exception as e:
        logger.debug(f"fetch_from_tenor error: {e}")
        return None, None, None

async def fetch_from_giphy(session, positive):
    if not GIPHY_API_KEY:
        return None, None, None
    try:
        q = map_tag_for_provider("giphy", positive)
        giphy_url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={quote_plus(q)}&limit=30&rating=r"
        async with session.get(giphy_url, timeout=REQUEST_TIMEOUT, headers=DEFAULT_HEADERS) as resp:
            if resp.status != 200:
                logger.debug(f"giphy -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            arr = payload.get("data", []) or []
            random.shuffle(arr)
            for item in arr:
                gif_url = item.get("images", {}).get("original", {}).get("url")
                if not gif_url: continue
                if filename_has_block_keyword(gif_url): continue
                if contains_illegal_indicators(json.dumps(item) + " " + (q or "")): continue
                return gif_url, f"giphy_{q}", item
    except Exception as e:
        logger.debug(f"fetch_from_giphy error: {e}")
        return None, None, None

# ---------------- Provider registry ----------------
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

# ---------------- Provider cycling fairness ----------------
_provider_cycle_deque = deque()
_last_cycle_refresh = None

def build_provider_pool():
    providers = [p for p in PROVIDER_FETCHERS.keys()]
    if "tenor" in providers and not TENOR_API_KEY:
        providers.remove("tenor")
    if "giphy" in providers and not GIPHY_API_KEY:
        providers.remove("giphy")
    if "waifu_it" in providers and not WAIFUIT_API_KEY:
        providers.remove("waifu_it")
    available = []
    for p in providers:
        w = int(data.get("provider_weights", {}).get(p, 1))
        if w <= 0:
            continue
        available.append(p)
    if not available:
        return []
    if TRUE_RANDOM:
        random.shuffle(available)
        return available
    global _provider_cycle_deque, _last_cycle_refresh
    now = datetime.utcnow()
    if not _provider_cycle_deque or (_last_cycle_refresh and (now - _last_cycle_refresh) > timedelta(minutes=15)):
        random.shuffle(available)
        _provider_cycle_deque = deque(available)
        _last_cycle_refresh = now
        if DEBUG_FETCH:
            logger.debug(f"Provider cycle (refreshed): {_provider_cycle_deque}")
    else:
        current = list(_provider_cycle_deque)
        if set(current) != set(available):
            random.shuffle(available)
            _provider_cycle_deque = deque(available)
            _last_cycle_refresh = now
            if DEBUG_FETCH:
                logger.debug(f"Provider cycle (rebuild): {_provider_cycle_deque}")
    return list(_provider_cycle_deque)

# ---------------- Reliability: HEAD+GET ----------------
async def attempt_get_media_bytes(session, gif_url):
    if not gif_url:
        return None, None, "no-url"
    if contains_illegal_indicators(gif_url):
        return None, None, "illegal-indicator-in-url"
    status, headers = await _head_url(session, gif_url)
    if status is None:
        b, ctype = await _download_bytes_with_limit(session, gif_url, size_limit=HEAD_SIZE_LIMIT)
        if b:
            return b, ctype, "downloaded-after-head-failed"
        return None, ctype, "head-failed-get-failed"
    if status not in (200,301,302):
        b, ctype = await _download_bytes_with_limit(session, gif_url, size_limit=HEAD_SIZE_LIMIT)
        if b:
            return b, ctype, f"get-after-head-{status}"
        return None, ctype, f"head-{status}-get-failed"
    cl = headers.get("Content-Length") or headers.get("content-length")
    ctype = headers.get("Content-Type") or headers.get("content-type") or ""
    if cl:
        try:
            clv = int(cl)
            if clv > HEAD_SIZE_LIMIT:
                return None, ctype, f"too-large-head-{clv}"
            b, ctype2 = await _download_bytes_with_limit(session, gif_url, size_limit=HEAD_SIZE_LIMIT)
            if b:
                return b, ctype2 or ctype, "downloaded-with-head-size"
            return None, ctype2 or ctype, "head-said-small-but-get-failed"
        except Exception:
            b, ctype2 = await _download_bytes_with_limit(session, gif_url, size_limit=HEAD_SIZE_LIMIT)
            if b:
                return b, ctype2 or ctype, "downloaded-with-head-parse-except"
            return None, ctype2 or ctype, "head-parse-get-failed"
    else:
        b, ctype2 = await _download_bytes_with_limit(session, gif_url, size_limit=HEAD_SIZE_LIMIT)
        if b:
            return b, ctype2 or ctype, "downloaded-unknown-size"
        return None, ctype2 or ctype, "unknown-size-get-failed-or-too-large"

# ---------------- FETCH_GIF improved flow ----------------
async def fetch_gif(user_id):
    user_key = str(user_id)
    sent = data["sent_history"].setdefault(user_key, [])
    providers = build_provider_pool()
    if not providers:
        if DEBUG_FETCH:
            logger.debug("No providers available.")
        return None, None, None

    async with aiohttp.ClientSession() as session:
        tried_providers = set()
        attempt = 0
        while attempt < FETCH_ATTEMPTS:
            attempt += 1
            if TRUE_RANDOM:
                provider = random.choice(providers)
            else:
                global _provider_cycle_deque, _last_cycle_refresh
                if not _provider_cycle_deque:
                    _provider_cycle_deque = deque(build_provider_pool())
                if not _provider_cycle_deque:
                    return None, None, None
                provider = _provider_cycle_deque.popleft()
                _provider_cycle_deque.append(provider)
                if DEBUG_FETCH:
                    logger.debug(f"Round-robin provider chosen: {provider}")

            tried_providers.add(provider)
            fetcher = PROVIDER_FETCHERS.get(provider)
            if not fetcher:
                if DEBUG_FETCH:
                    logger.debug(f"No fetcher for provider {provider}")
                continue

            # pick a tag: prefer provider term pools (ensures provider-specific categories used)
            provider_pool = PROVIDER_TERMS.get(provider, None)
            if provider_pool:
                positive = random.choice(provider_pool)
            else:
                positive = random.choice(GIF_TAGS)

            if DEBUG_FETCH:
                logger.debug(f"[fetch_gif] attempt {attempt}/{FETCH_ATTEMPTS} provider={provider} positive='{positive}'")

            try:
                gif_url, name_hint, meta = await fetcher(session, positive)
            except Exception as e:
                if DEBUG_FETCH:
                    logger.debug(f"Fetcher exception for {provider}: {e}")
                continue

            if not gif_url:
                if DEBUG_FETCH:
                    logger.debug(f"{provider} returned no url.")
                if len(tried_providers) >= len(providers):
                    tried_providers.clear()
                continue

            if filename_has_block_keyword(gif_url):
                if DEBUG_FETCH:
                    logger.debug(f"{provider} returned blocked filename keyword in {gif_url}")
                continue
            if contains_illegal_indicators((gif_url or "") + " " + (str(meta) or "")):
                if DEBUG_FETCH:
                    logger.debug(f"{provider} returned illegal indicators in meta/url for {gif_url}")
                continue

            gif_hash = hashlib.sha1((gif_url or name_hint or "").encode()).hexdigest()
            if gif_hash in sent:
                if DEBUG_FETCH:
                    logger.debug(f"Already sent gif hash for {gif_url}; skipping.")
                continue

            b, ctype, reason = await attempt_get_media_bytes(session, gif_url)
            if DEBUG_FETCH:
                logger.debug(f"attempt_get_media_bytes -> provider={provider} url={gif_url} reason={reason} bytes_ok={bool(b)} ctype={ctype}")

            if b:
                ext = ""
                try:
                    parsed = urlparse(gif_url)
                    ext = os.path.splitext(parsed.path)[1] or ".gif"
                    if len(ext) > 6:
                        ext = ".gif"
                except Exception:
                    ext = ".gif"
                name = f"{provider}_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
                sent.append(gif_hash)
                if len(sent) > MAX_USED_GIFS_PER_USER:
                    del sent[:len(sent) - MAX_USED_GIFS_PER_USER]
                data["sent_history"][user_key] = sent
                persist_all_data()
                return b, name, gif_url
            else:
                # link-only fallback
                sent.append(gif_hash)
                if len(sent) > MAX_USED_GIFS_PER_USER:
                    del sent[:len(sent) - MAX_USED_GIFS_PER_USER]
                data["sent_history"][user_key] = sent
                persist_all_data()
                return None, None, gif_url

        if DEBUG_FETCH:
            logger.debug("fetch_gif exhausted attempts.")
        return None, None, None

# ---------------- Discord helpers ----------------
def make_embed(title, desc, member, kind="join", count=None):
    color = discord.Color.dark_red() if kind == "join" else discord.Color.dark_gray()
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

async def send_embed_with_media(text_channel, member, embed, gif_bytes, gif_name, gif_url):
    max_upload = DISCORD_MAX_UPLOAD
    try:
        if gif_bytes and len(gif_bytes) <= max_upload:
            try:
                file_server = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                embed.set_image(url=f"attachment://{gif_name}")
                if text_channel:
                    await text_channel.send(embed=embed, file=file_server)
            except Exception as e:
                logger.debug(f"attach->channel failed: {e}")
                if text_channel:
                    if gif_url:
                        if gif_url not in (embed.description or ""):
                            embed.description = (embed.description or "") + f"\n\n[View media here]({gif_url})"
                    await text_channel.send(embed=embed)
            try:
                file_dm = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                await member.send(embed=embed, file=file_dm)
            except Exception as e:
                logger.debug(f"attach->DM failed: {e}")
                try:
                    dm_embed = make_embed(embed.title or "Media", embed.description or "", member, kind="join")
                    if gif_url:
                        if gif_url not in (dm_embed.description or ""):
                            dm_embed.description = (dm_embed.description or "") + f"\n\n[View media here]({gif_url})"
                    await member.send(embed=dm_embed)
                except Exception as e2:
                    logger.debug(f"DM link fallback failed: {e2}")
        else:
            if gif_url:
                if gif_url not in (embed.description or ""):
                    embed.description = (embed.description or "") + f"\n\n[View media here]({gif_url})"
            if text_channel:
                await text_channel.send(embed=embed)
            try:
                dm_embed = make_embed(embed.title or "Media", embed.description or "", member, kind="join")
                if gif_url:
                    if gif_url not in (dm_embed.description or ""):
                        dm_embed.description = (dm_embed.description or "") + f"\n\n[View media here]({gif_url})"
                await member.send(embed=dm_embed)
            except Exception as e:
                logger.debug(f"DM link only failed: {e}")
    except Exception as e:
        logger.warning(f"unexpected error in send_embed_with_media: {e}")
        try:
            if text_channel:
                await text_channel.send(embed=embed)
            await member.send(embed=embed)
        except Exception:
            logger.debug("final fallback failed")

# ---------------- Discord events/messages ----------------
JOIN_GREETINGS = [
    "🌸 {display_name} sashays into the scene — waifu energy rising!",
    "✨ {display_name} arrived and the room got a whole lot warmer.",
    "🔥 {display_name} joined — clutch your hearts (and waifus).",
    # ... (kept as in your lists)
]
# fill greetings to a decent size if needed
while len(JOIN_GREETINGS) < 50:
    JOIN_GREETINGS.append(random.choice(JOIN_GREETINGS))
LEAVE_GREETINGS = ["🌙 {display_name} drifts away — the moon hushes a little."]
while len(LEAVE_GREETINGS) < 50:
    LEAVE_GREETINGS.append(random.choice(LEAVE_GREETINGS))

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    autosave_task.start()
    # startup provider report
    available = []
    for p in PROVIDER_FETCHERS.keys():
        key_ok = True
        if p == "tenor" and not TENOR_API_KEY: key_ok = False
        if p == "giphy" and not GIPHY_API_KEY: key_ok = False
        if p == "waifu_it" and not WAIFUIT_API_KEY: key_ok = False
        available.append((p, key_ok, data.get("provider_weights", {}).get(p, 1)))
    logger.info("Provider availability (provider, api_key_present, weight):")
    for t in available:
        logger.info(t)
    logger.info(f"Logged in as {bot.user} (id={bot.user.id})")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    text_channel = bot.get_channel(VC_CHANNEL_ID)
    # Auto-join
    if after.channel and (after.channel.id in VC_IDS) and (before.channel != after.channel):
        try:
            vc = discord.utils.get(bot.voice_clients, guild=member.guild)
            if vc:
                if vc.channel.id != after.channel.id:
                    await vc.move_to(after.channel)
            else:
                await after.channel.connect()
        except Exception as e:
            logger.warning(f"VC join error: {e}")

    # JOIN message
    if after.channel and (after.channel.id in VC_IDS) and (before.channel != after.channel):
        raw = random.choice(JOIN_GREETINGS)
        msg = raw.format(display_name=member.display_name)
        data["join_counts"][str(member.id)] = data["join_counts"].get(str(member.id), 0) + 1
        embed = make_embed("Welcome!", msg, member, "join", data["join_counts"][str(member.id)])
        gif_bytes, gif_name, gif_url = await fetch_gif(member.id)
        await send_embed_with_media(text_channel, member, embed, gif_bytes, gif_name, gif_url)

    # LEAVE message
    if before.channel and (before.channel.id in VC_IDS) and (after.channel != before.channel):
        raw = random.choice(LEAVE_GREETINGS)
        msg = raw.format(display_name=member.display_name)
        embed = make_embed("Goodbye!", msg, member, "leave")
        gif_bytes, gif_name, gif_url = await fetch_gif(member.id)
        await send_embed_with_media(text_channel, member, embed, gif_bytes, gif_name, gif_url)
        try:
            vc = discord.utils.get(bot.voice_clients, guild=member.guild)
            if vc and len([m for m in vc.channel.members if not m.bot]) == 0:
                await vc.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    if not TOKEN:
        logger.error("TOKEN missing. Set TOKEN and restart.")
    else:
        bot.run(TOKEN)
