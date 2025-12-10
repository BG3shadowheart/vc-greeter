# bot.py
# Final safe-spicy anime welcome bot v3 (voice-join enabled)
# - Random provider + random tag each request
# - Per-user no-repeat history (stored in data.json)
# - 100+ randomized greetings
# - Joins VC when monitored user joins, leaves when alone
# - Fused visual moderation (Google Vision + DeepAI + textual heuristics)
#
# ENV:
# TOKEN (required)
# TENOR_API_KEY, GIPHY_API_KEY, WAIFUIM_API_KEY, WAIFUIT_API_KEY, FLUXPOINT_API_KEY (optional)
# Optional: GOOGLE_APPLICATION_CREDENTIALS (path to service-account.json) and DEEPAI_KEY (DeepAI API key)
#
# Run: python bot.py

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

# visual moderation libs
import requests
try:
    from google.cloud import vision
    vision_client = vision.ImageAnnotatorClient()
except Exception:
    vision_client = None

# -------------------------
# Environment / keys
# -------------------------
TOKEN = os.getenv("TOKEN")
TENOR_API_KEY = os.getenv("TENOR_API_KEY")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")
WAIFUIM_API_KEY = os.getenv("WAIFUIM_API_KEY")
WAIFUIT_API_KEY = os.getenv("WAIFUIT_API_KEY")
FLUXPOINT_API_KEY = os.getenv("FLUXPOINT_API_KEY")
DEEPAI_KEY = os.getenv("DEEPAI_KEY")  # optional DeepAI key
DEBUG_FETCH = os.getenv("DEBUG_FETCH", "") != ""

# -------------------------
# Your VC IDs and text channel (edit these to your actual IDs)
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
# Admin config
# -------------------------
ADMINS = [
    # add admin user IDs (ints) here
]
ADMIN_ROLE_NAME = "BotAdmin"  # or None

def is_admin(member: discord.Member) -> bool:
    if not member:
        return False
    try:
        if member.id in ADMINS:
            return True
        if ADMIN_ROLE_NAME:
            for r in member.roles:
                if r.name == ADMIN_ROLE_NAME:
                    return True
    except Exception:
        pass
    return False

# -------------------------
# Spicy tag pool (extended)
# -------------------------
GIF_TAGS = [
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
    "oppai focus","underboob tease","thighs focus","panties peek",
    "mature waifu","older sister waifu","maid outfit","cute cosplay","lingerie model"
]

# -------------------------
# Providers (safe + curated)
# -------------------------
PROVIDERS = [
    "waifu_pics",
    "waifu_im",
    "waifu_it",
    "nekos_best",
    "nekos_life",
    "nekos_api",
    "nekos_moe",
    "nekoapi",
    "otakugifs",
    "fluxpoint",
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
# Moderation lists (Option A)
# -------------------------
HARD_TAGS = [
    "pussy","vagina","labia","clitoris",
    "penis","cock","dick","shaft","testicles","balls","scrotum","anus",
    "open pussy","spread pussy","uncensored pussy",
    "bare breasts","nipples visible","areola visible","nipples out","nipple visible",
    "nude female","naked female","explicit nude","spread legs explicit",
    "sex","penetration","penetrating","penetrated","anal sex","anal penetration",
    "double penetration","dp","threesome","foursome","group sex",
    "orgy","gangbang","69","blowjob","deepthroat","oral","fellatio",
    "handjob","titty fuck","facefuck","facesitting","creampie","facial",
    "cum","cumshot","cum shot","ejac","ejaculation",
    "cum in mouth","cum in face","cum_on_face","cum_in_mouth",
    "cum covered","cum drip",
    "porn","pornography","xxx","explicit","uncensored",
    "hentai explicit","hentai uncensored",
    "bestiality","scat","watersports","fisting","sex toy","strapon",
    "futa","futanari","futanary",
    "hentai","nsfw","shemale","trap",
    "loli","shota","underage","minor","incest",
    "vore","bdsm","daddy",
    "father","mother","rape","yuri",
    "gay porn","gay hentai","trans porn","trans hentai",
    "futa hentai","futa porn",
    "male male","male x male","male×male","m/m","m x m",
    "male love","male romance","male cuddling",
    "male kissing","male kiss","boy kiss","boys kissing",
    "gay kiss","gay kissing","gay cuddle","gay romantic",
    "gay love","gay couple","boy love","bl","boys love",
    "shounen ai","shonen ai","bl anime","bl kiss",
    "male hug romantic","male hug intimate","gay hug",
    "male flirting","male touching","gay touch","gay scene",
    "gay moment","male couple","bl scene","bl couple",
    "gay anime couple","gay anime kiss","boy x boy",
    "dross","2boys","blush","brown hair","duo",
    "elf","elf ears","elf male","femboy","functionally nude",
    "green eyes","light-skinned male","thighhighs","twink", "blowjob"
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
    "facial", "scat", "fisting", "bestiality",
    "trap", "shemale", "femboy", "yaoi", "twink", "2boys", "gay"
]

EXCLUDE_TAGS = ["loli","shota","child","minor","underage","young","schoolgirl","age_gap"]

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("safe-spiciest-v3")

# -------------------------
# Helpers: normalization & analyzers
# -------------------------
def _normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r'[\s\-_]+', ' ', s)
    return s

def analyze_nudity_indicators(text: str):
    """Return (hard_found:bool, soft_count:int)."""
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

# -------------------------
# Data persistence init
# -------------------------
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
    "waifu_it": 8,
    "nekos_best": 9,
    "nekos_life": 8,
    "nekos_api": 7,
    "nekos_moe": 6,
    "nekoapi": 6,
    "otakugifs": 7,
    "fluxpoint": 6,
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
        if weight <= 0:
            continue
        pool.extend([prov] * max(1, int(weight)))
    if USE_TENOR and "tenor" not in pool:
        pool.extend(["tenor"] * 3)
    if USE_GIPHY and "giphy" not in pool:
        pool.extend(["giphy"] * 3)
    random.shuffle(pool)
    return pool

# -------------------------
# Visual moderation helpers (fusion)
# -------------------------
_VISION_LEVELS = {
    'UNKNOWN': 0,
    'VERY_UNLIKELY': 1,
    'UNLIKELY': 2,
    'POSSIBLE': 3,
    'LIKELY': 4,
    'VERY_LIKELY': 5
}

def _vision_safe_search_levels(image_bytes: bytes):
    """Return (adult_level, racy_level) as integers (0-5). If client unavailable, return (None,None)."""
    if not vision_client:
        return None, None
    try:
        image = vision.Image(content=image_bytes)
        resp = vision_client.safe_search_detection(image=image)
        ann = resp.safe_search_annotation
        adult = _VISION_LEVELS.get(getattr(ann.adult, "name", "UNKNOWN"), 0)
        racy  = _VISION_LEVELS.get(getattr(ann.racy, "name", "UNKNOWN"), 0)
        return adult, racy
    except Exception:
        return None, None

def _deepai_nsfw_score(image_bytes: bytes, timeout=15):
    """Return numeric score 0..1 if available, else None. Uses DeepAI NSFW detector."""
    if not DEEPAI_KEY:
        return None
    try:
        r = requests.post(
            "https://api.deepai.org/api/nsfw-detector",
            files={'image': ('image.jpg', image_bytes)},
            headers={'api-key': DEEPAI_KEY},
            timeout=timeout
        )
        j = r.json()
        score = None
        if isinstance(j, dict):
            score = j.get('nsfw_score') or (j.get('output') or {}).get('nsfw_score')
            if score is None:
                det = (j.get('output') or {}).get('detections') or j.get('detections') or []
                if isinstance(det, list) and det:
                    confs = [d.get('confidence', 0.0) for d in det if isinstance(d, dict)]
                    if confs:
                        score = max(confs)
        if score is None:
            return None
        return float(score)
    except Exception:
        return None

def _supporting_textual_signal(url_or_name: str, meta_text: str) -> bool:
    """
    True if textual metadata supports a block (i.e., has hard tags or >=3 soft tags).
    """
    try:
        if filename_has_block_keyword(url_or_name):
            return True
        if contains_nude_indicators(url_or_name):
            return True
        if contains_nude_indicators(meta_text):
            return True
    except Exception:
        pass
    return False

# -------------------------
# Provider fetcher helpers (defensive)
# Each fetcher returns (bytes, filename, source_url) or (None,None,None)
# -------------------------
async def _download_url(session, url, timeout=18):
    """
    Downloads bytes and runs a fused visual+text moderation.
    Returns (bytes, content_type) or (None, None) if blocked/unavailable.
    Decision logic:
      - If Vision returns VERY_LIKELY for adult or racy: BLOCK.
      - If Vision returns LIKELY: block only if supporting textual signals present.
      - If Vision returns POSSIBLE: block only if strong textual signals present (e.g., HARD tag/filename).
      - If DeepAI score >= 0.85: BLOCK.
      - If DeepAI between 0.6-0.85: block only with supporting textual signal.
      - Fallback textual-only checks (filename/meta).
    """
    try:
        async with session.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None, None
            ctype = resp.content_type or ""
            if "html" in ctype:
                return None, None
            b = await resp.read()

            # visual checks
            adult_level, racy_level = _vision_safe_search_levels(b)  # may be (None,None)
            deepai_score = _deepai_nsfw_score(b) if DEEPAI_KEY else None

            # textual support from URL only (fetchers may also construct meta_text and re-check)
            textual_signal = _supporting_textual_signal(url, "")

            # Vision decisive block
            if adult_level is not None:
                if adult_level >= _VISION_LEVELS['VERY_LIKELY'] or racy_level >= _VISION_LEVELS['VERY_LIKELY']:
                    logger.info(f"Visual block (vision VERY_LIKELY) for {url}")
                    return None, None
                if adult_level >= _VISION_LEVELS['LIKELY'] or racy_level >= _VISION_LEVELS['LIKELY']:
                    if textual_signal:
                        logger.info(f"Visual+text block (vision LIKELY + textual) for {url}")
                        return None, None
                if adult_level >= _VISION_LEVELS['POSSIBLE'] or racy_level >= _VISION_LEVELS['POSSIBLE']:
                    if filename_has_block_keyword(url) or contains_nude_indicators(url):
                        logger.info(f"Visual POSSIBLE + strong filename/meta -> block {url}")
                        return None, None

            # DeepAI signals
            if deepai_score is not None:
                if deepai_score >= 0.85:
                    logger.info(f"DeepAI strong block (score {deepai_score:.2f}) for {url}")
                    return None, None
                if deepai_score >= 0.6:
                    if textual_signal:
                        logger.info(f"DeepAI {deepai_score:.2f} + textual -> block {url}")
                        return None, None

            # Fallback textual-only checks
            if filename_has_block_keyword(url):
                logger.info(f"Filename heuristic block for {url}")
                return None, None
            if contains_nude_indicators(url):
                logger.info(f"URL heuristic nude-indicators block for {url}")
                return None, None

            # Passed fused checks — return bytes
            return b, ctype
    except Exception as e:
        logger.exception(f"_download_url error for {url}: {e}")
        return None, None

# Provider: waifu.pics
async def fetch_from_waifu_pics(session, positive):
    try:
        categories = ["waifu","neko","maid","oppai","bikini","blowjob","trap"]
        category = random.choice(categories)
        url = f"https://api.waifu.pics/nsfw/{category}"
        async with session.get(url, timeout=12) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("image")
            if not gif_url:
                return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                return None, None, None
            b, ctype = await _download_url(session, gif_url)
            if not b:
                return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"waifu_pics_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

# Provider: waifu.im
async def fetch_from_waifu_im(session, positive):
    try:
        base = "https://api.waifu.im/search"
        tag = random.choice(["oppai","ecchi","milf","maid","bikini","lingerie","swimsuit","cleavage"])
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

# Provider: waifu.it
async def fetch_from_waifu_it(session, positive):
    try:
        base = "https://waifu.it/api/waifu/random"
        headers = {}
        if WAIFUIT_API_KEY:
            headers["Authorization"] = f"Bearer {WAIFUIT_API_KEY}"
        async with session.get(base, headers=headers, timeout=12) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            gif_url = None
            if isinstance(payload, dict):
                gif_url = payload.get("image") or payload.get("image_url") or payload.get("url")
                if not gif_url and payload.get("results"):
                    gif_url = random.choice(payload["results"]).get("image_url")
            elif isinstance(payload, str):
                gif_url = payload
            if not gif_url:
                return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                return None, None, None
            b, ctype = await _download_url(session, gif_url)
            if not b:
                return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"waifu_it_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

# Provider: nekos.best
async def fetch_from_nekos_best(session, positive):
    try:
        category = random.choice(["hug","kiss","pat","cuddle","dance","poke","slap","neko","waifu"])
        url = f"https://nekos.best/api/v2/{category}"
        async with session.get(url + "?amount=1", timeout=12) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            results = payload.get("results") or []
            if not results:
                return None, None, None
            r = random.choice(results)
            gif_url = r.get("url") or r.get("file") or r.get("image")
            if not gif_url:
                return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                return None, None, None
            b, ctype = await _download_url(session, gif_url)
            if not b:
                return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"nekos_best_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

# Provider: nekos.life
async def fetch_from_nekos_life(session, positive):
    try:
        categories = ["ngif","neko","kiss","hug","cuddle","pat","wink","slap"]
        category = random.choice(categories)
        url = f"https://nekos.life/api/v2/img/{category}"
        async with session.get(url, timeout=12) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("image") or payload.get("result")
            if not gif_url:
                return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                return None, None, None
            b, ctype = await _download_url(session, gif_url)
            if not b:
                return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"nekos_life_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

# Provider: generic nekos_api attempts
async def fetch_from_nekos_api(session, positive):
    try:
        candidates = [
            "https://v1.nekosapi.com/api/images/random",
            "https://nekos.moe/api/random",
            "https://nekosapi.com/api/images/random",
            "https://api.nekosapi.com/v4/images/random"
        ]
        random.shuffle(candidates)
        for url in candidates:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        continue
                    payload = await resp.json()
                    gif_url = None
                    if isinstance(payload, dict):
                        gif_url = payload.get("url") or payload.get("image") or payload.get("file") or payload.get("src")
                        if not gif_url and payload.get("data"):
                            d = payload.get("data")
                            if isinstance(d, list) and d:
                                gif_url = d[0].get("url") or d[0].get("file")
                            elif isinstance(d, dict):
                                gif_url = d.get("url") or d.get("file")
                    elif isinstance(payload, list) and payload:
                        gif_url = payload[0].get("url") or payload[0].get("file")
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

# Provider: nekos.moe
async def fetch_from_nekos_moe(session, positive):
    try:
        url = "https://nekos.moe/api/v3/gif/random"
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

# Provider: nekoapi (attempts)
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

# Provider: fluxpoint
async def fetch_from_fluxpoint(session, positive):
    try:
        category = random.choice(["baka","hug","kiss","pat","slap","poke","neko","dance","blush","wink"])
        url = f"https://api.fluxpoint.dev/sfw/gif/{category}"
        headers = {}
        if FLUXPOINT_API_KEY:
            headers["Authorization"] = FLUXPOINT_API_KEY
        async with session.get(url, headers=headers, timeout=12) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("file") or payload.get("url") or payload.get("result")
            if not gif_url:
                return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                return None, None, None
            b, ctype = await _download_url(session, gif_url)
            if not b:
                return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"fluxpoint_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

# Provider: waifuapi_alt
async def fetch_from_waifuapi_alt(session, positive):
    try:
        candidates = [
            "https://api.waifu.pics/nsfw/oppai",
            "https://api.waifu.pics/nsfw/bikini",
            "https://api.waifu.pics/nsfw/maid"
        ]
        url = random.choice(candidates)
        async with session.get(url, timeout=10) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("image")
            if not gif_url:
                return None, None, None
            if filename_has_block_keyword(gif_url) or contains_nude_indicators(gif_url):
                return None, None, None
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"waifuapi_alt_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
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
    "waifu_it": fetch_from_waifu_it,
    "nekos_best": fetch_from_nekos_best,
    "nekos_life": fetch_from_nekos_life,
    "nekos_api": fetch_from_nekos_api,
    "nekos_moe": fetch_from_nekos_moe,
    "nekoapi": fetch_from_nekoapi,
    "otakugifs": fetch_from_otakugifs,
    "fluxpoint": fetch_from_fluxpoint,
    "nekosapi_v1": fetch_from_nekos_api,
    "waifuapi_alt": fetch_from_waifuapi_alt,
    "latapi": fetch_from_latapi,
    "animegirls_online": fetch_from_animegirls_online,
    "tenor": fetch_from_tenor,
    "giphy": fetch_from_giphy
}

# -------------------------
# Master fetcher:
# - random provider from weighted pool
# - random tag
# - avoids duplicates per user (using data["sent_history"])
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
            # final domain/filename check
            if filename_has_block_keyword(gif_url):
                continue
            if contains_nude_indicators(gif_url):
                continue
            # compute stable id for gif_url
            gif_hash = hashlib.sha1((gif_url or name or "").encode()).hexdigest()
            # avoid repeats to same user
            if gif_hash in sent:
                continue
            # store in history (append)
            sent.append(gif_hash)
            # cap history size per user
            if len(sent) > MAX_USED_GIFS_PER_USER:
                del sent[:len(sent) - MAX_USED_GIFS_PER_USER]
            save_data()
            return b, name, gif_url
    return None, None, None

# -------------------------
# 100+ join and leave greetings (spicy but not explicit)
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
    "🍡 {display_name} walked away — dango leftover."
]
while len(LEAVE_GREETINGS) < 100:
    LEAVE_GREETINGS.append(random.choice(LEAVE_GREETINGS))

# -------------------------
# Embeds / Bot Setup
# -------------------------
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
    # debug print matched VC ids
    for guild in bot.guilds:
        for ch in guild.voice_channels:
            if ch.id in VC_IDS:
                logger.info(f"VC id matched: {ch.id} -> {guild.name}/{ch.name}")

@bot.event
async def on_voice_state_update(member, before, after):
    # ignore bot accounts
    if member.bot:
        return

    text_channel = bot.get_channel(VC_CHANNEL_ID)

    # ========== JOIN: user joined a monitored VC ==========
    if after.channel and (after.channel.id in VC_IDS) and (before.channel != after.channel):
        # 1) Permission-aware connect / move logic with detailed logging
        try:
            guild = member.guild
            bot_member = guild.me or (await guild.fetch_member(bot.user.id))
            # permission checks (channel-level if available)
            try:
                perms = after.channel.permissions_for(bot_member)
                can_view = perms.view_channel
                can_connect = perms.connect
                can_speak = perms.speak
            except Exception:
                logger.exception("Channel permission check failed; falling back to guild permissions")
                gp = bot_member.guild_permissions
                can_view = gp.view_channel
                can_connect = gp.connect
                can_speak = gp.speak

            if not can_view or not can_connect:
                logger.warning(f"Bot lacks permissions for VC {after.channel.id} (view={can_view}, connect={can_connect}, speak={can_speak})")
            else:
                voice_client = discord.utils.get(bot.voice_clients, guild=guild)
                if voice_client:
                    if voice_client.channel.id != after.channel.id:
                        try:
                            logger.info(f"Moving bot from {voice_client.channel.id} to {after.channel.id}")
                            await voice_client.move_to(after.channel)
                            logger.info("Move succeeded")
                        except Exception as e:
                            logger.exception(f"Failed to move voice client: {e}")
                    else:
                        logger.info("Bot already connected to target VC")
                else:
                    try:
                        logger.info(f"Connecting bot to VC {after.channel.id}")
                        await after.channel.connect()
                        logger.info("Connect succeeded")
                    except Exception as e:
                        logger.exception(f"Failed to connect to VC: {e}")
        except Exception as e:
            logger.exception(f"VC join logic error: {e}")

        # 2) Send randomized welcome embed + gif
        try:
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
        except Exception:
            logger.exception("Failed to send welcome embed/gif")

    # ========== LEAVE: user left a monitored VC ==========
    if before.channel and (before.channel.id in VC_IDS) and (after.channel != before.channel):
        try:
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
        except Exception:
            logger.exception("Failed to send leave embed/gif")

        # After sending the leave embed, check if bot should disconnect
        try:
            voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
            if voice_client:
                non_bot_members = [m for m in voice_client.channel.members if not m.bot]
                if len(non_bot_members) == 0:
                    try:
                        logger.info("Bot is alone in VC; disconnecting.")
                        await voice_client.disconnect()
                    except Exception as e:
                        logger.warning(f"Failed to disconnect voice client: {e}")
        except Exception as e:
            logger.warning(f"VC disconnect logic error: {e}")

# -------------------------
# Admin commands
# -------------------------
@bot.command(name="testgif")
async def testgif(ctx):
    if not is_admin(ctx.author):
        await ctx.send("You are not authorized to use this command.")
        return
    await ctx.send("Fetching test GIF...")
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
async def setweight(ctx, provider: str, weight: int):
    if not is_admin(ctx.author):
        await ctx.send("You are not authorized to use this command.")
        return
    provider = provider.strip().lower()
    if provider not in default_weights and provider not in PROVIDER_FETCHERS:
        await ctx.send(f"Unknown provider `{provider}`. Known: {', '.join(sorted(PROVIDER_FETCHERS.keys()))}")
        return
    data["provider_weights"][provider] = max(0, int(weight))
    save_data()
    await ctx.send(f"Set weight for {provider} = {weight}")

@bot.command(name="weights")
async def showweights(ctx):
    if not is_admin(ctx.author):
        await ctx.send("You are not authorized to use this command.")
        return
    lines = [f"{p}: {w}" for p, w in data["provider_weights"].items()]
    await ctx.send("Provider weights:\n" + "\n".join(lines))

# -------------------------
# Run the bot
# -------------------------
if __name__ == "__main__":
    if not TOKEN:
        logger.error("TOKEN environment variable missing. Set TOKEN and restart.")
    else:
        bot.run(TOKEN)
