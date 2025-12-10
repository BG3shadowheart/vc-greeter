# bot_spiciest_final_v3_with_vcjoin_fixed.py
# Final safe-spicy anime welcome bot v3 (voice-join enabled) - REMOVED Fluxpoint and Waifu.it
# CHANGES: Providers now *try* to use your full GIF_TAGS value first for every fetcher. If the provider
# doesn't support arbitrary tags or the attempt fails, the fetcher falls back to its original category list.
# This preserves provider-specific categories while allowing your entire custom tag list to be used.

import os
import io
import json
import random
import hashlib
import logging
import re
import asyncio
from datetime import datetime
from urllib.parse import quote_plus, urlparse
import aiohttp
import discord
from discord.ext import commands, tasks

# -------------------------
# Environment / keys
# -------------------------
TOKEN = os.getenv("TOKEN")
TENOR_API_KEY = os.getenv("TENOR_API_KEY")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")
WAIFUIM_API_KEY = os.getenv("WAIFUIM_API_KEY")
DEBUG_FETCH = os.getenv("DEBUG_FETCH", "") != ""

# -------------------------
# Your VC IDs and text channel (copied / preserved)
# -------------------------
VC_IDS = [
    1353875050809524267,
    21409170559337762980,
    1353875404217253909,
    1353882705246556220
]
VC_CHANNEL_ID = 1446752109151260792

# -------------------------
# Files & limits
# -------------------------
DATA_FILE = "data.json"             # holds join_counts, used_gifs, provider_weights, sent_history
AUTOSAVE_INTERVAL = 30
MAX_USED_GIFS_PER_USER = 1000       # memory cap per user
FETCH_ATTEMPTS = 60                 # attempts per fetch cycle

# -------------------------
# Spicy tag pool (extended) - MASTER TAGS. The master randomizer uses these tags.
# You asked for this custom list to be used across every provider; the fetchers now attempt
# to use whichever tag is chosen from this list first.
# -------------------------
GIF_TAGS = [
    # core spicy
    "busty","big breasts","oppai","busty anime","huge breasts","big boobs",
    "milf","mommy","mature","mature anime","older waifu","mommy waifu",
    "thick","thicc","thick thighs","thighs","thighfocus","anime thick thighs",
    "jiggle","bounce","booty","ass","big ass","curvy","round booty","thicc booty",
    "lingerie","underwear","panties","pantyhose","stockings","hosiery","garter",
    "bikini","swimsuit","beach bikini","beach waifu",
    "cleavage","low cut","crop top","underboob","sideboob","underboob focus",
    "ecchi","fanservice","teasing","seductive","sexy","flirty","suggestive",
    "anime waifu","waifu","anime girl","cute waifu","hot waifu","anime babe",
    "cosplay","uniform","maid","school uniform","cheerleader",
    "anime lingerie","anime bikini","anime cleavage","anime oppai","oppai focus",
    "seductive pose","playful","blush","wink","kiss","cuddle","hug",
    "anime tease","anime flirt","soft erotic","suggestive pose","playful tease",
    "side profile cleavage","hip sway","shimmy","dance tease",
    "bouncy","nip slip","peekaboo","portrait cleavage",
    # extras to diversify queries
    "oppai focus","underboob tease","thighs focus","panties peek",
    "mature waifu","older sister waifu","maid outfit","cute cosplay","lingerie model"
]

# -------------------------
# Providers (safe + curated)
# -------------------------
PROVIDERS = [
    "waifu_pics",
    "waifu_im",
    "nekos_best",
    "nekos_life",
    "nekos_api",
    "nekos_moe",
    "nekoapi",
    "otakugifs",
    "nekosapi_v1",
    "waifuapi_alt",
    "latapi",
    "animegirls_online",
    "tenor",
    "giphy"
]

USE_TENOR = bool(TENOR_API_KEY)
USE_GIPHY = bool(GIPHY_API_KEY)

# -------------------------
# Moderation lists (unchanged)
# -------------------------
HARD_TAGS = [
    "pussy","vagina","labia","clitoris",
    "penis","cock","dick","shaft","testicles","balls","scrotum","anus",
    "open pussy","spread pussy","uncensored pussy",
    "bare breasts","nipples visible","areola visible","nipples out","nipple visible",
    "nude female","naked female","explicit nude","spread legs explicit",
    "sex","penetration","penetrating","penetrated","anal sex","double penetration","dp",
    "threesome","foursome","group sex","orgy","69",
    "blowjob","deepthroat","oral","fellatio","handjob","titty fuck",
    "facefuck","facesitting","creampie","facial",
    "cum","cumshot","cum shot","ejac","ejaculation",
    "cum in mouth","cum in face","cum_on_face","cum_in_mouth","cum covered","cum drip",
    "porn","pornography","xxx","explicit","uncensored","hentai explicit","hentai uncensored",
    "bestiality","scat","watersports","fisting","sex toy","strapon",
    "gay","homosexual","gay male","gay male porn","gay porn","gaysex","gay-sex",
    "man","men","male","males","boy","boys","young man","young man",
    "shemale","shemales","shemale porn","trap","traps","femboy","femboys","femboy porn",
    "trans","transgender","transsexual","mtf","ftm","crossdresser","cross-dresser",
    "male nudity","male breasts","dickgirl","dick-girl","futa","futanari",
    "sissy","sissy porn","beard","male nipples"
]

SOFT_TAGS = [
    "nude","naked","topless","bottomless",
    "nipples","areola","lingerie","lingerie girl",
    "erotic","ecchi","sensual","lewd","teasing",
    "big boobs","boobs","oppai","busty","huge breasts","busty anime",
    "ass","booty","thick","thighs","thighfocus","jiggle","bounce",
    "milf","mommy","mature","seductive","sexy","fanservice",
    "cleavage","swimsuit","bikini","underwear","cosplay","panties","stockings",
    "underboob","sideboob","nip slip"
]

FILENAME_BLOCK_KEYWORDS = [
    "cum", "pussy", "nude", "naked", "penis", "cock", "vagina",
    "explicit", "uncensored", "xxx", "hentai", "orgy", "creampie",
    "facial", "scat", "fisting", "bestiality"
]

EXCLUDE_TAGS = ["loli","shota","child","minor","underage","young","schoolgirl","age_gap"]

# -------------------------
# Logging, helpers and persistence (unchanged except for small docs)
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("safe-spiciest-v3")

def _normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r'[\s\-_]+', ' ', s)
    return s

def analyze_nudity_indicators(text: str):
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
    if hard:
        return True
    if soft_count >= 3:
        return True
    return False

def filename_has_block_keyword(url: str) -> bool:
    if not url:
        return False
    low = url.lower()
    for kw in FILENAME_BLOCK_KEYWORDS:
        if kw in low:
            return True
    return False

def domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({
            "join_counts": {},
            "used_gifs": {},
            "provider_weights": {},
            "sent_history": {}
        }, f)

with open(DATA_FILE, "r") as f:
    data = json.load(f)

data.setdefault("join_counts", {})
data.setdefault("used_gifs", {})
data.setdefault("provider_weights", {})
data.setdefault("sent_history", {})

# default provider weights
default_weights = {
    "waifu_pics": 12,
    "waifu_im": 10,
    "nekos_best": 9,
    "nekos_life": 8,
    "nekos_api": 7,
    "nekos_moe": 6,
    "nekoapi": 6,
    "otakugifs": 7,
    "nekosapi_v1": 5,
    "waifuapi_alt": 5,
    "latapi": 5,
    "animegirls_online": 4,
    "tenor": 4,
    "giphy": 4
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
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save data: {e}")

def build_provider_pool():
    pool = []
    for prov, weight in data["provider_weights"].items():
        if prov not in PROVIDER_FETCHERS:
            continue
        if weight <= 0:
            continue
        pool.extend([prov] * max(1, int(weight)))
    if USE_TENOR and "tenor" not in pool:
        pool.extend(["tenor"] * 3)
    if USE_GIPHY and "giphy" not in pool:
        pool.extend(["giphy"] * 3)
    random.shuffle(pool)
    return pool

async def _download_url(session, url, timeout=18):
    try:
        async with session.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None, None
            ctype = resp.content_type or ""
            if "html" in ctype:
                return None, None
            b = await resp.read()
            return b, ctype
    except Exception:
        return None, None

# -------------------------
# Provider fetchers
# - For providers that previously only used a small local category list,
#   we now *try* using the chosen `positive` tag first (from GIF_TAGS).
# - If that attempt fails (non-200, missing image, or fails safety checks),
#   we fall back to the original provider-specific category selection.
# -------------------------

# Provider: waifu.pics
async def fetch_from_waifu_pics(session, positive):
    try:
        categories = ["waifu","neko","maid","oppai","bikini","blowjob","trap"]
        # First try positive as a category (many of your GIF_TAGS map to waifu.pics categories)
        tried_urls = []
        attempt_order = [positive] + [c for c in categories if c != positive]
        for category in attempt_order:
            url = f"https://api.waifu.pics/nsfw/{quote_plus(category)}"
            tried_urls.append(url)
            try:
                async with session.get(url, timeout=12) as resp:
                    if resp.status != 200:
                        continue
                    payload = await resp.json()
                    gif_url = payload.get("url") or payload.get("image")
                    if not gif_url:
                        continue
                    if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                        continue
                    b, ctype = await _download_url(session, gif_url)
                    if not b:
                        continue
                    ext = os.path.splitext(gif_url)[1] or ".gif"
                    name = f"waifu_pics_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
                    return b, name, gif_url
            except Exception:
                continue
        return None, None, None
    except Exception:
        return None, None, None

# Provider: waifu.im
async def fetch_from_waifu_im(session, positive):
    try:
        base = "https://api.waifu.im/search"
        tag = positive
        params = {"included_tags": tag, "is_nsfw": "true"}
        headers = {}
        if WAIFUIM_API_KEY:
            headers["Authorization"] = f"Bearer {WAIFUIM_API_KEY}"
        async with session.get(base, params=params, headers=headers, timeout=12) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            images = payload.get("images") or payload.get("data") or []
            if not images:
                return None, None, None
            img = random.choice(images)
            gif_url = img.get("url") or img.get("image") or img.get("src")
            if not gif_url:
                return None, None, None
            if filename_has_block_keyword(gif_url):
                return None, None, None
            meta_text = " ".join(filter(None, [img.get("tags", ""), img.get("source", ""), str(img.get("is_nsfw", ""))]))
            if contains_nude_indicators(meta_text) or contains_nude_indicators(gif_url):
                return None, None, None
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"waifu_im_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

# Provider: nekos.best
async def fetch_from_nekos_best(session, positive):
    try:
        categories = ["hug","kiss","pat","cuddle","dance","poke","slap","neko","waifu","ngif"]
        # Try using positive directly as endpoint, then fallback to known categories
        attempt_order = [positive] + [c for c in categories if c != positive]
        for cat in attempt_order:
            url = f"https://nekos.best/api/v2/{quote_plus(cat)}"
            try:
                async with session.get(url + "?amount=1", timeout=12) as resp:
                    if resp.status != 200:
                        continue
                    payload = await resp.json()
                    results = payload.get("results") or []
                    if not results:
                        continue
                    r = random.choice(results)
                    gif_url = r.get("url") or r.get("file") or r.get("image")
                    if not gif_url:
                        continue
                    if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                        continue
                    b, ctype = await _download_url(session, gif_url)
                    if not b: continue
                    ext = os.path.splitext(gif_url)[1] or ".gif"
                    name = f"nekos_best_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
                    return b, name, gif_url
            except Exception:
                continue
        return None, None, None
    except Exception:
        return None, None, None

# Provider: nekos.life
async def fetch_from_nekos_life(session, positive):
    try:
        categories = ["ngif","neko","kiss","hug","cuddle","pat","wink","slap"]
        attempt_order = [positive] + [c for c in categories if c != positive]
        for category in attempt_order:
            url = f"https://nekos.life/api/v2/img/{quote_plus(category)}"
            try:
                async with session.get(url, timeout=12) as resp:
                    if resp.status != 200:
                        continue
                    payload = await resp.json()
                    gif_url = payload.get("url") or payload.get("image") or payload.get("result")
                    if not gif_url:
                        continue
                    if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                        continue
                    b, ctype = await _download_url(session, gif_url)
                    if not b:
                        continue
                    ext = os.path.splitext(gif_url)[1] or ".gif"
                    name = f"nekos_life_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
                    return b, name, gif_url
            except Exception:
                continue
        return None, None, None
    except Exception:
        return None, None, None

# Provider: nekos_api / nekosapi sites (generic attempts)
async def fetch_from_nekos_api(session, positive):
    try:
        candidates = [
            f"https://v1.nekosapi.com/api/images/random?type={quote_plus(positive)}",
            f"https://nekos.moe/api/random?tag={quote_plus(positive)}",
            "https://nekosapi.com/api/images/random",
            f"https://api.nekosapi.com/v4/images/random?type={quote_plus(positive)}"
        ]
        random.shuffle(candidates)
        for url in candidates:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        continue
                    payload = await resp.json()
                    if isinstance(payload, dict):
                        gif_url = payload.get("url") or payload.get("image") or payload.get("file") or payload.get("src")
                        if not gif_url and payload.get("data"):
                            d = payload.get("data")
                            if isinstance(d, list) and d:
                                gif_url = d[0].get("url") or d[0].get("file")
                            elif isinstance(d, dict):
                                gif_url = d.get("url") or d.get("file")
                        if not gif_url:
                            continue
                    elif isinstance(payload, list) and payload:
                        gif_url = payload[0].get("url") or payload[0].get("file")
                    else:
                        continue
                    if not gif_url:
                        continue
                    if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                        continue
                    b, ctype = await _download_url(session, gif_url)
                    if not b:
                        continue
                    ext = os.path.splitext(gif_url)[1] or ".jpg"
                    name = f"nekos_api_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
                    return b, name, gif_url
            except Exception:
                continue
    except Exception:
        return None, None, None
    return None, None, None

# Provider: nekos_moe
async def fetch_from_nekos_moe(session, positive):
    try:
        url = f"https://nekos.moe/api/v3/gif/random?tag={quote_plus(positive)}"
        async with session.get(url, timeout=12) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            gifs = payload.get("images") or payload.get("data") or []
            if isinstance(gifs, dict):
                gifs = [gifs]
            if not gifs:
                return None, None, None
            item = random.choice(gifs)
            gif_url = item.get("file") or item.get("url") or item.get("original") or item.get("image")
            if not gif_url:
                return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                return None, None, None
            b, ctype = await _download_url(session, gif_url)
            if not b:
                return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"nekos_moe_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

# Provider: nekoapi
async def fetch_from_nekoapi(session, positive):
    try:
        candidates = [
            f"https://nekoapi.app/api/v1/gif/{quote_plus(positive)}",
            f"https://nekosapi.xyz/api/{quote_plus(positive)}",
            f"https://api.neko-love.xyz/v1/gif/{quote_plus(positive)}"
        ]
        random.shuffle(candidates)
        for url in candidates:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        continue
                    payload = await resp.json()
                    gif_url = payload.get("url") or payload.get("file") or payload.get("image") or payload.get("result")
                    if not gif_url:
                        continue
                    if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                        continue
                    b, ctype = await _download_url(session, gif_url)
                    if not b:
                        continue
                    ext = os.path.splitext(gif_url)[1] or ".gif"
                    name = f"nekoapi_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
                    return b, name, gif_url
            except Exception:
                continue
    except Exception:
        return None, None, None

# Provider: otakugifs
async def fetch_from_otakugifs(session, positive):
    try:
        reaction = quote_plus(positive)
        url = f"https://otakugifs.xyz/api/gif?reaction={reaction}"
        async with session.get(url, timeout=12) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("gif") or payload.get("file") or payload.get("result")
            if not gif_url and isinstance(payload, str):
                gif_url = payload
            if not gif_url:
                return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                return None, None, None
            b, ctype = await _download_url(session, gif_url)
            if not b:
                return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"otakugifs_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

# Provider: generic alt waifu api (waifuapi_alt)
async def fetch_from_waifuapi_alt(session, positive):
    try:
        candidates = [
            f"https://api.waifu.pics/nsfw/{quote_plus(positive)}",
            "https://api.waifu.pics/nsfw/oppai",
            "https://api.waifu.pics/nsfw/bikini",
            "https://api.waifu.pics/nsfw/maid"
        ]
        random.shuffle(candidates)
        for url in candidates:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        continue
                    payload = await resp.json()
                    gif_url = payload.get("url") or payload.get("image")
                    if not gif_url:
                        continue
                    if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                        continue
                    b, ctype = await _download_url(session, gif_url)
                    if not b:
                        continue
                    ext = os.path.splitext(gif_url)[1] or ".gif"
                    name = f"waifuapi_alt_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
                    return b, name, gif_url
            except Exception:
                continue
    except Exception:
        return None, None, None

# Provider: latapi
async def fetch_from_latapi(session, positive):
    try:
        candidates = [
            f"https://latapi.pics/api/v1/random?tags={quote_plus(positive)}",
            f"https://latapi.xyz/api/random?tag={quote_plus(positive)}"
        ]
        random.shuffle(candidates)
        for url in candidates:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        continue
                    payload = await resp.json()
                    gif_url = payload.get("url") or payload.get("image") or payload.get("file")
                    if not gif_url:
                        continue
                    if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                        continue
                    b, ctype = await _download_url(session, gif_url)
                    if not b: continue
                    ext = os.path.splitext(gif_url)[1] or ".gif"
                    name = f"latapi_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
                    return b, name, gif_url
            except Exception:
                continue
    except Exception:
        return None, None, None

# Provider: animegirls_online
async def fetch_from_animegirls_online(session, positive):
    try:
        candidates = [
            f"https://animegirls.online/api/random?tag={quote_plus(positive)}",
            "https://animegirls.online/api/random"
        ]
        random.shuffle(candidates)
        for url in candidates:
            try:
                async with session.get(url, timeout=12) as resp:
                    if resp.status != 200:
                        continue
                    payload = await resp.json()
                    gif_url = payload.get("url") or payload.get("image") or payload.get("file")
                    if not gif_url:
                        continue
                    if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                        continue
                    b, ctype = await _download_url(session, gif_url)
                    if not b:
                        continue
                    ext = os.path.splitext(gif_url)[1] or ".gif"
                    name = f"animegirls_online_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
                    return b, name, gif_url
            except Exception:
                continue
    except Exception:
        return None, None, None

# Provider: Tenor
async def fetch_from_tenor(session, positive):
    if not TENOR_API_KEY:
        return None, None, None
    try:
        tenor_q = quote_plus(positive)
        tenor_url = f"https://g.tenor.com/v1/search?q={tenor_q}&key={TENOR_API_KEY}&limit=30&contentfilter=medium"
        async with session.get(tenor_url, timeout=12) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            results = payload.get("results", [])
            random.shuffle(results)
            for r in results:
                gif_url = None
                media_formats = r.get("media_formats") or r.get("media")
                if isinstance(media_formats, dict):
                    for key in ("gif","nanogif","mediumgif","tinygif"):
                        entry = media_formats.get(key)
                        if entry and isinstance(entry, dict) and entry.get("url"):
                            gif_url = entry["url"]; break
                elif isinstance(media_formats, list) and media_formats:
                    first = media_formats[0]
                    for key in ("gif","tinygif","mediumgif"):
                        if isinstance(first, dict) and first.get(key) and isinstance(first[key], dict) and first[key].get("url"):
                            gif_url = first[key]["url"]; break
                if not gif_url:
                    gif_url = r.get("itemurl") or r.get("url")
                if not gif_url: continue
                if filename_has_block_keyword(gif_url): continue
                combined_meta = " ".join([
                    str(r.get("content_description") or ""),
                    " ".join(r.get("tags") or [] if isinstance(r.get("tags"), list) else [str(r.get("tags") or "")]),
                    gif_url
                ])
                hard, soft_count = analyze_nudity_indicators(combined_meta)
                if hard or soft_count >= 3: continue
                b, ctype = await _download_url(session, gif_url)
                if not b: continue
                ext = ".gif"
                if ".webm" in gif_url or "webm" in (ctype or ""): ext = ".webm"
                elif ".mp4" in gif_url or "mp4" in (ctype or ""): ext = ".mp4"
                name = f"tenor_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
                return b, name, gif_url
    except Exception:
        return None, None, None

# Provider: Giphy
async def fetch_from_giphy(session, positive):
    if not GIPHY_API_KEY:
        return None, None, None
    try:
        giphy_q = quote_plus(positive)
        giphy_url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={giphy_q}&limit=30&rating=pg-13"
        async with session.get(giphy_url, timeout=12) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            arr = payload.get("data", [])
            random.shuffle(arr)
            for item in arr:
                images = item.get("images", {})
                gif_url = images.get("original", {}).get("url") or images.get("downsized", {}).get("url")
                if not gif_url:
                    continue
                if filename_has_block_keyword(gif_url):
                    continue
                combined_meta = " ".join([str(item.get("title") or ""), str(item.get("slug") or ""), gif_url])
                hard, soft_count = analyze_nudity_indicators(combined_meta)
                if hard or soft_count >= 3:
                    continue
                b, ctype = await _download_url(session, gif_url)
                if not b:
                    continue
                ext = ".gif"
                if ".mp4" in gif_url or "mp4" in (ctype or ""):
                    ext = ".mp4"
                elif ".webm" in (ctype or "") or ".webm" in gif_url:
                    ext = ".webm"
                name = f"giphy_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
                return b, name, gif_url
    except Exception:
        return None, None, None

# Map provider name -> function
PROVIDER_FETCHERS = {
    "waifu_pics": fetch_from_waifu_pics,
    "waifu_im": fetch_from_waifu_im,
    "nekos_best": fetch_from_nekos_best,
    "nekos_life": fetch_from_nekos_life,
    "nekos_api": fetch_from_nekos_api,
    "nekos_moe": fetch_from_nekos_moe,
    "nekoapi": fetch_from_nekoapi,
    "otakugifs": fetch_from_otakugifs,
    "waifuapi_alt": fetch_from_waifuapi_alt,
    "latapi": fetch_from_latapi,
    "animegirls_online": fetch_from_animegirls_online,
    "tenor": fetch_from_tenor,
    "giphy": fetch_from_giphy
}

# -------------------------
# Master fetcher (unchanged semantics):
# - pick a random provider from weighted pool
# - pick a random tag from GIF_TAGS each attempt
# - attempt provider fetch; providers will try the chosen tag first
# - avoid repeats per-user
# -------------------------
async def fetch_gif(user_id):
    user_key = str(user_id)
    sent = data["sent_history"].setdefault(user_key, [])
    providers = build_provider_pool()
    async with aiohttp.ClientSession() as session:
        for attempt in range(FETCH_ATTEMPTS):
            provider = random.choice(providers) if providers else random.choice(list(PROVIDER_FETCHERS.keys()))
            positive = random.choice(GIF_TAGS)
            if DEBUG_FETCH:
                logger.info(f"[fetch_gif] attempt {attempt+1}/{FETCH_ATTEMPTS} provider={provider} tag='{positive}'")
            fetcher = PROVIDER_FETCHERS.get(provider)
            if not fetcher:
                continue
            try:
                result = await fetcher(session, positive)
            except Exception:
                result = (None, None, None)
            if not result or not result[0]:
                continue
            b, name, gif_url = result
            if not gif_url:
                continue
            if filename_has_block_keyword(gif_url):
                continue
            if contains_nude_indicators(gif_url):
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

# -------------------------
# Join/leave greetings, embeds, and bot runtime (unchanged)
# -------------------------
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
    JOIN_GREETINGS.append(random.choice(JOIN_GREETINGS).replace(" joined"," arrived"))

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
while len(LEAVE_GREETINGS) < 100:
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

    # Voice join (connect/move)
    if after.channel and (after.channel.id in VC_IDS) and (before.channel != after.channel):
        try:
            voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
            if voice_client:
                if voice_client.channel.id != after.channel.id:
                    try:
                        await voice_client.move_to(after.channel)
                    except Exception as e:
                        logger.warning(f"Failed to move voice client: {e}")
            else:
                try:
                    await after.channel.connect()
                except Exception as e:
                    logger.warning(f"Failed to connect to channel: {e}")
        except Exception as e:
            logger.warning(f"VC join logic error: {e}")

    # JOIN greeting
    if after.channel and (after.channel.id in VC_IDS) and (before.channel != after.channel):
        raw_msg = random.choice(JOIN_GREETINGS)
        msg = raw_msg.format(display_name=member.display_name)
        data["join_counts"][str(member.id)] = data["join_counts"].get(str(member.id), 0) + 1
        try:
            with open(DATA_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
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
                    try:
                        embed_dm = make_embed("Welcome!", msg, member, "join", data["join_counts"][str(member.id)])
                        if gif_url:
                            embed_dm.description += f"\n[View media here]({gif_url})"
                        await member.send(embed=embed_dm)
                    except Exception:
                        logger.warning(f"Failed to DM {member.display_name}")
            except Exception as e:
                logger.warning(f"Failed to send join file: {e}")
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

    # LEAVE greeting
    if before.channel and (before.channel.id in VC_IDS) and (after.channel != before.channel):
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
                logger.warning(f"Failed to send leave file: {e}")
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

        try:
            voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
            if voice_client:
                non_bot_members = [m for m in voice_client.channel.members if not m.bot]
                if len(non_bot_members) == 0:
                    try:
                        await voice_client.disconnect()
                    except Exception as e:
                        logger.warning(f"Failed to disconnect voice client: {e}")
        except Exception as e:
            logger.warning(f"VC disconnect logic error: {e}")

# Owner/admin commands
@bot.command(name="testgif")
@commands.is_owner()
async def testgif(ctx):
    await ctx.defer()
    gif_bytes, gif_name, gif_url = await fetch_gif(ctx.author.id)
    if gif_bytes:
        try:
            file = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
            embed = make_embed("Test GIF", "Safe-spicy test GIF (safe providers).", ctx.author, "join")
            embed.set_image(url=f"attachment://{gif_name}")
            await ctx.send(embed=embed, file=file)
            return
        except Exception as e:
            logger.warning(f"testgif send failed: {e}")
    await ctx.send("Couldn't fetch a test GIF right now. Try again later.")

@bot.command(name="setweight")
@commands.is_owner()
async def setweight(ctx, provider: str, weight: int):
    provider = provider.strip().lower()
    if provider not in default_weights and provider not in PROVIDER_FETCHERS:
        await ctx.send(f"Unknown provider `{provider}`. Known: {', '.join(sorted(PROVIDER_FETCHERS.keys()))}")
        return
    data["provider_weights"][provider] = max(0, int(weight))
    save_data()
    await ctx.send(f"Set weight for {provider} = {weight}")

@bot.command(name="weights")
@commands.is_owner()
async def showweights(ctx):
    lines = [f"{p}: {w}" for p, w in data["provider_weights"].items()]
    await ctx.send("Provider weights:\n" + "\n".join(lines))

if __name__ == "__main__":
    if not TOKEN:
        logger.error("TOKEN environment variable missing. Set TOKEN and restart.")
    else:
        bot.run(TOKEN)
