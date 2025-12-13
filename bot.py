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

logging.basicConfig(level=logging.DEBUG if DEBUG_FETCH else logging.INFO)
logger = logging.getLogger("spiciest-final-fixed")

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

default_providers = [
    "waifu_pics","waifu_im","waifu_it","nekos_best","nekos_life",
    "nekos_moe","otakugifs","animegirls_online","tenor","giphy","nekoapi"
]
for prov in default_providers:
    if data.get("provider_weights", {}).get(prov, None) == 0:
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

WAIFU_PICS_TERMS = ["neko", "waifu", "trap", "blowjob"]

WAIFU_IM_TERMS = [
    "waifu", "maid", "ero", "ecchi", "hentai", "milf", "ass", "oral", "paizuri",
    "oppai", "underboob", "cleavage"
]

WAIFU_IT_TERMS = ["waifu", "husbando"]

NEKOS_BEST_TERMS = [
    "husbando", "kitsune", "neko", "waifu",
    "kiss", "hug", "cuddle", "pat", "wink", "smug", "dance"
]

NEKOS_LIFE_TERMS = [
    "neko", "ngif", "lewd", "feet", "holo", "pat", "kiss", "hug"
]

NEKOS_MOE_TERMS = [
    "bikini", "swimsuit", "breasts", "panties", "blush", "waifu", "thighs", "stockings"
]

NEKOAPI_TERMS = [
    "waifu", "neko", "oppai", "bikini", "thighs", "panties", "stockings"
]

OTAKUGIFS_TERMS = ["kiss", "hug", "slap", "punch", "wink", "dance", "cuddle", "poke"]

ANIMEGIRLS_TERMS = ["waifu", "bikini", "cosplay", "maid", "school uniform", "swimsuit", "cute"]

TENOR_TERMS = [
    "busty anime", "big breasts anime", "oppai anime", "cleavage anime", "lingerie anime",
    "bikini anime", "thighs anime", "stockings anime", "booty anime", "ecchi anime",
    "fanservice anime", "sexy anime"
]

GIPHY_TERMS = [
    "busty anime", "big boobs anime", "oppai anime", "bikini anime", "lingerie anime",
    "cleavage anime", "thighs anime", "booty shake anime", "ecchi", "fanservice"
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

def map_tag_for_provider(provider: str, tag: str) -> str:
    t = (tag or "").lower().strip()
    pool = PROVIDER_TERMS.get(provider, [])
    if t:
        for p in pool:
            if p in t:
                return p
    if pool:
        return random.choice(pool)
    return t or "waifu"

async def fetch_from_waifu_pics(session, positive):
    try:
        category = map_tag_for_provider("waifu_pics", positive)
        url = f"https://api.waifu.pics/nsfw/{quote_plus(category)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT, headers=DEFAULT_HEADERS) as resp:
            if resp.status != 200:
                if DEBUG_FETCH:
                    logger.debug(f"waifu_pics nsfw {category} -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("image")
            if not gif_url:
                return None, None, None
            if filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(payload) + " " + (category or "")): return None, None, None
            extract_and_add_tags_from_meta(json.dumps(payload))
            return gif_url, f"waifu_pics_{category}", payload
    except Exception as e:
        if DEBUG_FETCH:
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
                if DEBUG_FETCH:
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
        if DEBUG_FETCH:
            logger.debug(f"fetch_from_waifu_im error: {e}")
        return None, None, None

async def fetch_from_waifu_it(session, positive):
    try:
        if not WAIFUIT_API_KEY:
            if DEBUG_FETCH:
                logger.debug("waifu.it skipped: key missing")
            return None, None, None
        q = map_tag_for_provider("waifu_it", positive)
        endpoint = f"https://waifu.it/api/v4/{quote_plus(q)}"
        headers = dict(DEFAULT_HEADERS)
        headers["Authorization"] = WAIFUIT_API_KEY
        async with session.get(endpoint, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                if DEBUG_FETCH:
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
        if DEBUG_FETCH:
            logger.debug(f"fetch_from_waifu_it error: {e}")
        return None, None, None

async def fetch_from_nekos_best(session, positive):
    try:
        q = map_tag_for_provider("nekos_best", positive)
        url = f"https://nekos.best/api/v2/{quote_plus(q)}?amount=1"
        async with session.get(url, timeout=REQUEST_TIMEOUT, headers=DEFAULT_HEADERS) as resp:
            if resp.status != 200:
                if DEBUG_FETCH:
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
        if DEBUG_FETCH:
            logger.debug(f"fetch_from_nekos_best error: {e}")
        return None, None, None

async def fetch_from_nekos_life(session, positive):
    try:
        q = map_tag_for_provider("nekos_life", positive)
        url = f"https://nekos.life/api/v2/img/{quote_plus(q)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT, headers=DEFAULT_HEADERS) as resp:
            if resp.status != 200:
                if DEBUG_FETCH:
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
        if DEBUG_FETCH:
            logger.debug(f"fetch_from_nekos_life error: {e}")
        return None, None, None

async def fetch_from_nekos_moe(session, positive):
    try:
        q = map_tag_for_provider("nekos_moe", positive)
        url = f"https://nekos.moe/api/v3/gif/random?tag={quote_plus(q)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT, headers=DEFAULT_HEADERS) as resp:
            if resp.status != 200:
                if DEBUG_FETCH:
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
        if DEBUG_FETCH:
            logger.debug(f"fetch_from_nekos_moe error: {e}")
        return None, None, None

async def fetch_from_otakugifs(session, positive):
    try:
        q = map_tag_for_provider("otakugifs", positive)
        valid_reactions = ["kiss","hug","slap","punch","wink","dance","cuddle","poke"]
        reaction = "waifu"
        for v in valid_reactions:
            if v in q:
                reaction = v
                break
        url = f"https://otakugifs.xyz/api/gif?reaction={quote_plus(reaction)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT, headers=DEFAULT_HEADERS) as resp:
            if resp.status != 200:
                if DEBUG_FETCH:
                    logger.debug(f"otakugifs -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("gif") or payload.get("file")
            if not gif_url: return None, None, None
            if filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(payload) + " " + (q or "")): return None, None, None
            return gif_url, f"otakugifs_{reaction}", payload
    except Exception as e:
        if DEBUG_FETCH:
            logger.debug(f"fetch_from_otakugifs error: {e}")
        return None, None, None

async def fetch_from_animegirls_online(session, positive):
    try:
        q = map_tag_for_provider("animegirls_online", positive)
        url = f"https://animegirls.online/api/random?tag={quote_plus(q)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT, headers=DEFAULT_HEADERS) as resp:
            if resp.status != 200:
                if DEBUG_FETCH:
                    logger.debug(f"animegirls_online -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("image")
            if not gif_url: return None, None, None
            if filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(payload) + " " + (q or "")): return None, None, None
            return gif_url, f"animegirls_online_{q}", payload
    except Exception as e:
        if DEBUG_FETCH:
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
                if DEBUG_FETCH:
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
        if DEBUG_FETCH:
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
                if DEBUG_FETCH:
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
        if DEBUG_FETCH:
            logger.debug(f"fetch_from_giphy error: {e}")
        return None, None, None

PROVIDER_FETCHERS = {
    "waifu_pics": fetch_from_waifu_pics,
    "waifu_im": fetch_from_waifu_im,
    "waifu_it": fetch_from_waifu_it,
    "nekos_best": fetch_from_nekos_best,
    "nekos_life": fetch_from_nekos_life,
    "nekos_moe": fetch_from_nekos_moe,
    "nekoapi": fetch_from_nekos_moe,
    "otakugifs": fetch_from_otakugifs,
    "animegirls_online": fetch_from_animegirls_online,
    "tenor": fetch_from_tenor,
    "giphy": fetch_from_giphy
}

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
                sent.append(gif_hash)
                if len(sent) > MAX_USED_GIFS_PER_USER:
                    del sent[:len(sent) - MAX_USED_GIFS_PER_USER]
                data["sent_history"][user_key] = sent
                persist_all_data()
                return None, None, gif_url

        if DEBUG_FETCH:
            logger.debug("fetch_gif exhausted attempts.")
        return None, None, None

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
                await member.send(dm_embed)
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
while len(JOIN_GREETINGS) < 100:
    JOIN_GREETINGS.append(random.choice(JOIN_GREETINGS))

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
LEAVE_GREETINGS = ["🌙 {display_name} drifts away — the moon hushes a little."]
while len(LEAVE_GREETINGS) < 100:
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

    if after.channel and (after.channel.id in VC_IDS) and (before.channel != after.channel):
        raw = random.choice(JOIN_GREETINGS)
        msg = raw.format(display_name=member.display_name)
        data["join_counts"][str(member.id)] = data["join_counts"].get(str(member.id), 0) + 1
        embed = make_embed("Welcome!", msg, member, "join", data["join_counts"][str(member.id)])
        gif_bytes, gif_name, gif_url = await fetch_gif(member.id)
        await send_embed_with_media(text_channel, member, embed, gif_bytes, gif_name, gif_url)

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
