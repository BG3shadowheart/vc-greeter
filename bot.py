# SFW bot.py
import os
import io
import json
import random
import hashlib
import logging
import re
import asyncio
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus, urlparse

import aiohttp
import discord
from discord.ext import commands, tasks
from collections import deque

try:
    from PIL import Image, ImageSequence
except Exception:
    Image = None

# ====== Config / ENV KEYS ======
TOKEN = os.getenv("TOKEN", "")
WAIFUIM_API_KEY = os.getenv("WAIFUIM_API_KEY", "")
DANBOORU_USER = os.getenv("DANBOORU_USER", "")
DANBOORU_API_KEY = os.getenv("DANBOORU_API_KEY", "")
GELBOORU_API_KEY = os.getenv("GELBOORU_API_KEY", "")
GELBOORU_USER = os.getenv("GELBOORU_USER", "")

_DEBUG_RAW = os.getenv("DEBUG_FETCH", "")
DEBUG_FETCH = str(_DEBUG_RAW).strip().lower() in ("1", "true", "yes", "on")
TRUE_RANDOM = str(os.getenv("TRUE_RANDOM", "")).strip().lower() in ("1", "true", "yes")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "14"))
DISCORD_MAX_UPLOAD = int(os.getenv("DISCORD_MAX_UPLOAD", str(8 * 1024 * 1024)))
HEAD_SIZE_LIMIT = DISCORD_MAX_UPLOAD
DATA_FILE = os.getenv("DATA_FILE", "data_sfw.json")
AUTOSAVE_INTERVAL = int(os.getenv("AUTOSAVE_INTERVAL", "30"))
FETCH_ATTEMPTS = int(os.getenv("FETCH_ATTEMPTS", "40"))
MAX_USED_GIFS_PER_USER = int(os.getenv("MAX_USED_GIFS_PER_USER", "1000"))

VC_IDS = [
    1353875050809524267,
    1379350260010455051,
    1353882705246556220
]
VC_CHANNEL_ID = int(os.getenv("VC_CHANNEL_ID", "1371916812903780573"))

logging.basicConfig(level=logging.DEBUG if DEBUG_FETCH else logging.INFO)
logger = logging.getLogger("spiciest-sfw")

# ====== Helpers & Filters ======
_token_split_re = re.compile(r"[^a-z0-9]+")

ILLEGAL_TAGS = [
    "underage", "minor", "child", "loli", "shota", "young", "agegap",
    "bestiality", "zoophilia", "bestial",
    "scat", "fisting", "incest", "pedo", "pedophile"
]

BLOCKED_TAGS = [
    "futanari", "futa", "dickgirl", "shemale", "transgender", "newhalf",
    "yaoi", "gay", "male", "femboy", "trap", "otoko_no_ko", "crossdressing",
    "penis", "bara", "3d", "real", "photo", "cosplay", "irl",
    "nude", "naked", "nipples", "pussy", "vagina", "sex", "cum", "anal", "oral",
    "hentai", "xxx", "explicit", "masturbation", "penetration"
]

FILENAME_BLOCK_KEYWORDS = ["nude", "naked", "hentai", "sex", "cum", "pussy"]

EXCLUDE_TAGS = [
    "loli", "shota", "child", "minor", "underage", "young", "schoolgirl", "age_gap",
    "futa", "futanari", "shemale", "dickgirl", "femboy", "trap",
    "gay", "yaoi", "male", "man", "boy", "penis"
]

def _normalize_text(s: str) -> str:
    return "" if not s else re.sub(r'[\s\-_]+', ' ', s.lower())

def _tag_is_disallowed(t: str) -> bool:
    if not t:
        return True
    t = t.lower()
    if any(b in t for b in ILLEGAL_TAGS):
        return True
    if any(ex in t for ex in EXCLUDE_TAGS):
        return True
    if any(bl in t for bl in BLOCKED_TAGS):
        return True
    return False

def contains_illegal_indicators(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    normalized = _normalize_text(text)
    for bad in ILLEGAL_TAGS:
        if bad in normalized:
            return True
    for blocked in BLOCKED_TAGS:
        if blocked in normalized:
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

def add_tag_to_gif_tags(tag: str, GIF_TAGS, data_save):
    if not tag or not isinstance(tag, str):
        return False
    t = tag.strip().lower()
    if len(t) < 3 or t in GIF_TAGS or _tag_is_disallowed(t):
        return False
    GIF_TAGS.append(t)
    data_save["gif_tags"] = _dedupe_preserve_order(data_save.get("gif_tags", []) + [t])
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data_save, f, indent=2)
    except Exception:
        pass
    logger.debug(f"learned tag: {t}")
    return True

def extract_and_add_tags_from_meta(meta_text: str, GIF_TAGS, data_save):
    if not meta_text:
        return
    text = _normalize_text(meta_text)
    tokens = _token_split_re.split(text)
    for tok in tokens:
        tok = tok.strip()
        if not tok or tok.isdigit() or len(tok) < 3:
            continue
        add_tag_to_gif_tags(tok, GIF_TAGS, data_save)

# ====== Persistent data (load/create) ======
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"provider_weights": {}, "sent_history": {}, "gif_tags": [], "vc_state": {}}, f, indent=2)

with open(DATA_FILE, "r") as f:
    data = json.load(f)

data.setdefault("provider_weights", {})
data.setdefault("sent_history", {})
data.setdefault("gif_tags", [])
data.setdefault("vc_state", {})

_seed_gif_tags = [
    "waifu", "neko", "kawaii", "cute", "smile", "blush", "ecchi", "suggestive",
    "bikini", "swimsuit", "lingerie", "underwear", "panties", "bra",
    "thighs", "thick_thighs", "thicc", "legs", "stockings", "thighhighs",
    "cleavage", "big_breasts", "oppai", "breast_focus", "boobs",
    "underboob", "sideboob", "cleavage_cutout", "breast_squeeze",
    "ass", "butt", "big_ass", "ass_focus", "tight_clothes",
    "maid", "bunny_girl", "catgirl", "kemonomimi", "fox_girl", "tail",
    "blonde", "brunette", "pink_hair", "long_hair", "short_hair",
    "twintails", "ponytail", "pigtails", "smiling", "wink"
]

persisted = _dedupe_preserve_order(data.get("gif_tags", []))
seed = _dedupe_preserve_order(_seed_gif_tags)
combined = seed + [t for t in persisted if t not in seed]
GIF_TAGS = [t for t in _dedupe_preserve_order(combined) if not _tag_is_disallowed(t)]
if not GIF_TAGS:
    GIF_TAGS = ["waifu", "ecchi"]

def save_data():
    try:
        data["gif_tags"] = GIF_TAGS
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"save failed: {e}")

@tasks.loop(seconds=AUTOSAVE_INTERVAL)
async def autosave_task():
    try:
        save_data()
    except Exception as e:
        logger.warning(f"Autosave failed: {e}")

# ====== Provider mapping and tag mapping ======
PROVIDER_TERMS = {
    "waifu_pics": ["waifu", "neko"],
    "waifu_im": ["ecchi", "ero", "oppai", "selfies", "uniform", "maid"],
    "nekos_best": ["neko", "waifu", "kitsune", "husbando"],
    "danbooru": ["ecchi", "bikini", "swimsuit", "cleavage", "thighs", "ass", "breasts", "panties", "lingerie"],
    "gelbooru": ["ecchi", "bikini", "swimsuit", "panties", "thighs", "cleavage", "upskirt"],
    "nekosia": ["catgirl", "foxgirl", "wolfgirl"],
    "anyanime": ["gif", "png"]
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

# ====== Network helper to download with size limit ======
async def _download_bytes_with_limit(session, url, size_limit=HEAD_SIZE_LIMIT, timeout=REQUEST_TIMEOUT):
    try:
        async with session.get(url, timeout=timeout, allow_redirects=True) as resp:
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

# ====== Provider fetch implementations (SFW providers only) ======
async def fetch_from_waifu_pics(session, positive):
    try:
        category = map_tag_for_provider("waifu_pics", positive)
        url = f"https://api.waifu.pics/sfw/{quote_plus(category)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                if DEBUG_FETCH:
                    logger.debug(f"waifu_pics sfw {category} -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("image")
            if not gif_url or filename_has_block_keyword(gif_url):
                return None, None, None
            if contains_illegal_indicators(json.dumps(payload) + " " + (category or "")):
                return None, None, None
            extract_and_add_tags_from_meta(json.dumps(payload), GIF_TAGS, data)
            return gif_url, f"waifu_pics_{category}", payload
    except Exception:
        return None, None, None

async def fetch_from_waifu_im(session, positive):
    try:
        q = map_tag_for_provider("waifu_im", positive)
        base = "https://api.waifu.im/search"
        params = {"included_tags": q, "is_nsfw": "false", "limit": 8}
        headers = {}
        if WAIFUIM_API_KEY:
            headers["Authorization"] = f"Bearer {WAIFUIM_API_KEY}"
        async with session.get(base, params=params, headers=headers or None, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            images = payload.get("images", [])
            if not images:
                return None, None, None
            img = random.choice(images)
            gif_url = img.get("url")
            if not gif_url or filename_has_block_keyword(gif_url):
                return None, None, None
            if contains_illegal_indicators(json.dumps(img) + " " + (q or "")):
                return None, None, None
            extract_and_add_tags_from_meta(str(img.get("tags", "")), GIF_TAGS, data)
            return gif_url, f"waifu_im_{q}", img
    except Exception:
        return None, None, None

async def fetch_from_nekos_best(session, positive):
    try:
        q = map_tag_for_provider("nekos_best", positive)
        url = f"https://nekos.best/api/v2/{quote_plus(q)}?amount=1"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                if DEBUG_FETCH:
                    logger.debug(f"nekos.best {q} -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            results = payload.get("results", [])
            if not results:
                return None, None, None
            r = results[0]
            gif_url = r.get("url")
            if not gif_url or filename_has_block_keyword(gif_url):
                return None, None, None
            if contains_illegal_indicators(json.dumps(r) + " " + (q or "")):
                return None, None, None
            extract_and_add_tags_from_meta(json.dumps(r), GIF_TAGS, data)
            return gif_url, f"nekos_best_{q}", r
    except Exception:
        return None, None, None

async def fetch_from_danbooru(session, positive):
    try:
        blocked_str = " ".join([f"-{b}" for b in BLOCKED_TAGS])
        tags = f"{positive} rating:questionable {blocked_str} 1girl -rating:explicit".strip()
        base = "https://danbooru.donmai.us/posts.json"
        params = {"tags": tags, "limit": 20, "random": "true"}
        headers = {}
        if DANBOORU_USER and DANBOORU_API_KEY:
            import base64
            credentials = base64.b64encode(f"{DANBOORU_USER}:{DANBOORU_API_KEY}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        async with session.get(base, params=params, headers=headers or None, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                return None, None, None
            posts = await resp.json()
            if not posts:
                return None, None, None
            post = random.choice(posts)
            gif_url = post.get("file_url") or post.get("large_file_url")
            if not gif_url or filename_has_block_keyword(gif_url):
                return None, None, None
            if contains_illegal_indicators(json.dumps(post)):
                return None, None, None
            extract_and_add_tags_from_meta(str(post.get("tag_string", "")), GIF_TAGS, data)
            return gif_url, f"danbooru_{positive}", post
    except Exception:
        return None, None, None

async def fetch_from_gelbooru(session, positive):
    try:
        blocked_str = " ".join([f"-{b}" for b in BLOCKED_TAGS])
        tags = f"{positive} rating:questionable {blocked_str} 1girl -rating:explicit".strip()
        base = "https://gelbooru.com/index.php"
        params = {
            "page": "dapi",
            "s": "post",
            "q": "index",
            "json": "1",
            "tags": tags,
            "limit": 20
        }
        if GELBOORU_API_KEY and GELBOORU_USER:
            params["api_key"] = GELBOORU_API_KEY
            params["user_id"] = GELBOORU_USER
        async with session.get(base, params=params, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            posts = payload.get("post", [])
            if not posts:
                return None, None, None
            post = random.choice(posts)
            gif_url = post.get("file_url")
            if not gif_url or filename_has_block_keyword(gif_url):
                return None, None, None
            if contains_illegal_indicators(json.dumps(post)):
                return None, None, None
            extract_and_add_tags_from_meta(post.get("tags", ""), GIF_TAGS, data)
            return gif_url, f"gelbooru_{positive}", post
    except Exception:
        return None, None, None

# New SFW public providers
async def fetch_from_nekosia(session, positive):
    try:
        category = map_tag_for_provider("nekosia", positive)
        url = f"https://api.nekosia.cat/api/v1/images/{category}?count=1"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            image_info = payload.get("image", {}).get("original", {})
            gif_url = image_info.get("url")
            if not gif_url:
                return None, None, None
            tags = payload.get("tags", [])
            extract_and_add_tags_from_meta(" ".join(tags), GIF_TAGS, data)
            return gif_url, f"nekosia_{category}", payload
    except Exception:
        return None, None, None

async def fetch_from_anyanime(session, positive):
    try:
        type_choice = map_tag_for_provider("anyanime", positive)
        url = f"https://any-anime-api.vercel.app/v1/anime/{type_choice}/1"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            images = payload.get("images", [])
            if not images:
                return None, None, None
            gif_url = random.choice(images)
            if not gif_url:
                return None, None, None
            return gif_url, f"anyanime_{type_choice}", payload
    except Exception:
        return None, None, None

# ====== Providers list (SFW) ======
PROVIDERS = [
    ("waifu_im", fetch_from_waifu_im, 30),
    ("danbooru", fetch_from_danbooru, 25),
    ("nekosia", fetch_from_nekosia, 20),
    ("gelbooru", fetch_from_gelbooru, 20),
    ("anyanime", fetch_from_anyanime, 15),
    ("nekos_best", fetch_from_nekos_best, 15),
    ("waifu_pics", fetch_from_waifu_pics, 10),
]

def _hash_url(url):
    return hashlib.md5(url.encode()).hexdigest()

def _choose_random_provider():
    if TRUE_RANDOM:
        return random.choice(PROVIDERS)
    else:
        weights = [w for _, _, w in PROVIDERS]
        return random.choices(PROVIDERS, weights=weights, k=1)[0]

# ====== Main fetch/selection logic ======
async def _fetch_one_gif(session, user_id=None, used_hashes=None):
    if used_hashes is None:
        used_hashes = set()

    tag = random.choice(GIF_TAGS)
    name, fetch_func, weight = _choose_random_provider()

    try:
        url, source, meta = await fetch_func(session, tag)
        if url:
            h = _hash_url(url)
            if h not in used_hashes:
                return url, source, meta, h
    except Exception as e:
        if DEBUG_FETCH:
            logger.debug(f"{name} fail: {e}")

    return None, None, None, None

async def fetch_random_gif(session, user_id=None):
    user_id_str = str(user_id) if user_id else "global"
    user_history = data["sent_history"].setdefault(user_id_str, [])
    used_hashes = set(user_history)

    for attempt in range(FETCH_ATTEMPTS):
        url, source, meta, url_hash = await _fetch_one_gif(session, user_id, used_hashes)
        if url:
            user_history.append(url_hash)
            if len(user_history) > MAX_USED_GIFS_PER_USER:
                user_history.pop(0)
            data["sent_history"][user_id_str] = user_history
            logger.info(f"Attempt {attempt+1}: Fetched from {source}")
            return url, source, meta

    logger.warning(f"Failed to fetch after {FETCH_ATTEMPTS} attempts")
    return None, None, None

# ====== Utility: compress images if too large ======
async def compress_image(image_bytes, target_size=DISCORD_MAX_UPLOAD):
    if not Image:
        return image_bytes
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.format == "GIF":
            return image_bytes
        output = io.BytesIO()
        quality = 95
        while quality > 10:
            output.seek(0)
            output.truncate()
            img.save(output, format=img.format or "JPEG", quality=quality, optimize=True)
            if output.tell() <= target_size:
                return output.getvalue()
            quality -= 10
        return output.getvalue()
    except Exception as e:
        logger.error(f"Compression failed: {e}")
        return image_bytes

# ====== Embeds + send greeting helper ======
JOIN_GREETINGS = [
    "🌸 {display_name} sashays into the scene — waifu energy rising!",
    "✨ {display_name} arrived and the room got a whole lot warmer.",
    "🔥 {display_name} joined — clutch your hearts (and waifus).",
    "💫 {display_name} appears — the waifu meter spikes.",
    "🍑 {display_name} walked in — cheeks feeling watched.",
    "😏 {display_name} entered — someone brought snacks and thighs.",
]

LEAVE_GREETINGS = [
    "🌙 {display_name} drifts away — the moon hushes a little.",
    "🍃 {display_name} fades out — petals fall where they once stood.",
    "💫 {display_name} slips away — stardust in their wake.",
]

async def send_greeting_with_image_embed(channel, session, greeting_text, image_url, member, send_to_dm=None):
    try:
        image_bytes, content_type = await _download_bytes_with_limit(session, image_url)
        if not image_bytes or len(image_bytes) > DISCORD_MAX_UPLOAD:
            if image_bytes and len(image_bytes) > DISCORD_MAX_UPLOAD:
                image_bytes = await compress_image(image_bytes)
            if not image_bytes or len(image_bytes) > DISCORD_MAX_UPLOAD:
                await channel.send(greeting_text)
                return

        ext = ".jpg"
        if "gif" in image_url.lower() or (content_type and "gif" in content_type):
            ext = ".gif"
        elif "png" in image_url.lower() or (content_type and "png" in content_type):
            ext = ".png"
        elif "webp" in image_url.lower() or (content_type and "webp" in content_type):
            ext = ".webp"

        filename = f"sfw{ext}"
        file = discord.File(io.BytesIO(image_bytes), filename=filename)

        embed = discord.Embed(
            description=greeting_text,
            color=discord.Color.from_rgb(255, 182, 193)
        )
        embed.set_author(name=member.display_name, icon_url=getattr(member.display_avatar, "url", None))
        embed.set_image(url=f"attachment://{filename}")
        embed.set_footer(text="SFW Bot")

        await channel.send(embed=embed, file=file)

        if send_to_dm:
            try:
                dm_file = discord.File(io.BytesIO(image_bytes), filename=filename)
                dm_embed = discord.Embed(
                    description=greeting_text,
                    color=discord.Color.from_rgb(255, 182, 193)
                )
                dm_embed.set_author(name=member.display_name, icon_url=getattr(member.display_avatar, "url", None))
                dm_embed.set_image(url=f"attachment://{filename}")
                dm_embed.set_footer(text="SFW Bot")
                await send_to_dm.send(embed=dm_embed, file=dm_file)
            except Exception as e:
                logger.warning(f"Could not DM: {e}")

    except Exception as e:
        logger.error(f"Failed to send greeting embed: {e}")
        try:
            await channel.send(greeting_text)
        except Exception:
            pass

# ====== Voice-channel logic & helper functions ======
def get_all_vcs_with_users(guild):
    out = []
    for vc_id in VC_IDS:
        vc = guild.get_channel(vc_id)
        if vc and isinstance(vc, discord.VoiceChannel):
            users = [m for m in vc.members if not m.bot]
            if users:
                out.append((vc, users))
    return out

def check_all_vcs_empty(guild):
    for vc_id in VC_IDS:
        vc = guild.get_channel(vc_id)
        if vc and isinstance(vc, discord.VoiceChannel):
            users = [m for m in vc.members if not m.bot]
            if len(users) > 0:
                return False
    return True

async def update_bot_vc_position(guild, target_channel=None):
    voice_client = guild.voice_client

    if target_channel and target_channel.id in VC_IDS:
        users_in_target = [m for m in target_channel.members if not m.bot]
        if users_in_target:
            if voice_client and voice_client.is_connected():
                if voice_client.channel.id != target_channel.id:
                    try:
                        await voice_client.move_to(target_channel)
                        logger.info(f"Bot moved to VC: {target_channel.name}")
                    except Exception as e:
                        logger.error(f"Failed to move to VC: {e}")
            else:
                try:
                    await target_channel.connect()
                    logger.info(f"Bot joined VC: {target_channel.name}")
                except Exception as e:
                    logger.error(f"Failed to join VC: {e}")
            return target_channel

    vcs_with_users = get_all_vcs_with_users(guild)

    if not vcs_with_users:
        if voice_client and voice_client.is_connected():
            try:
                await voice_client.disconnect()
                logger.info("Bot disconnected - all monitored VCs are empty")
            except Exception as e:
                logger.error(f"Failed to disconnect: {e}")
        return None

    target_vc = vcs_with_users[0][0]

    if voice_client and voice_client.is_connected():
        if voice_client.channel.id == target_vc.id:
            return target_vc
        try:
            await voice_client.move_to(target_vc)
            logger.info(f"Bot moved to VC: {target_vc.name}")
            return target_vc
        except Exception as e:
            logger.error(f"Failed to move to VC: {e}")
            return None
    else:
        try:
            await target_vc.connect()
            logger.info(f"Bot joined VC: {target_vc.name}")
            return target_vc
        except Exception as e:
            logger.error(f"Failed to join VC: {e}")
            return None

# ====== Bot setup and events ======
intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user}")
    autosave_task.start()
    check_vc.start()
    for guild in bot.guilds:
        await update_bot_vc_position(guild)

async def join_voice_channel():
    await bot.wait_until_ready()
    for vc_id in VC_IDS:
        vc = bot.get_channel(vc_id)
        if vc and isinstance(vc, discord.VoiceChannel):
            try:
                if vc.guild.voice_client is None:
                    await vc.connect()
                    logger.info(f"Bot joined voice channel: {vc.name}")
                else:
                    logger.info(f"Bot already in voice channel: {vc.name}")
            except Exception as e:
                logger.error(f"Failed to join VC: {e}")

@tasks.loop(seconds=300)
async def check_vc_connection():
    for vc_id in VC_IDS:
        vc = bot.get_channel(vc_id)
        if vc and isinstance(vc, discord.VoiceChannel):
            if vc.guild.voice_client is None or not vc.guild.voice_client.is_connected():
                try:
                    await vc.connect()
                    logger.info(f"Reconnected to VC: {vc.name}")
                except Exception as e:
                    logger.error(f"Failed to reconnect to VC: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    guild = member.guild
    before_vc = before.channel
    after_vc = after.channel

    before_in_monitored = before_vc and before_vc.id in VC_IDS
    after_in_monitored = after_vc and after_vc.id in VC_IDS

    if after_in_monitored and (not before_in_monitored or before_vc != after_vc):
        channel = bot.get_channel(VC_CHANNEL_ID)
        if channel:
            try:
                greeting = random.choice(JOIN_GREETINGS).format(display_name=member.display_name)
                async with aiohttp.ClientSession() as session:
                    gif_url, source, meta = await fetch_random_gif(session, member.id)
                    if gif_url:
                        await send_greeting_with_image_embed(channel, session, greeting, gif_url, member, send_to_dm=member)
                    else:
                        await channel.send(greeting)
            except Exception as e:
                logger.error(f"Failed to send join greeting: {e}")

        await asyncio.sleep(0.3)
        await update_bot_vc_position(guild, target_channel=after_vc)
        return

    if before_in_monitored and (not after_in_monitored or before_vc != after_vc):
        channel = bot.get_channel(VC_CHANNEL_ID)
        if channel:
            try:
                leave_msg = random.choice(LEAVE_GREETINGS).format(display_name=member.display_name)
                async with aiohttp.ClientSession() as session:
                    gif_url, source, meta = await fetch_random_gif(session, member.id)
                    if gif_url:
                        await send_greeting_with_image_embed(channel, session, leave_msg, gif_url, member, send_to_dm=member)
                    else:
                        await channel.send(leave_msg)
            except Exception as e:
                logger.error(f"Failed to send leave greeting: {e}")

        await asyncio.sleep(0.3)
        await update_bot_vc_position(guild)

@tasks.loop(seconds=30)
async def check_vc():
    for guild in bot.guilds:
        await update_bot_vc_position(guild)

# ====== Commands ======
@bot.command()
async def sfw(ctx):
    async with aiohttp.ClientSession() as session:
        gif_url, source, meta = await fetch_random_gif(session, ctx.author.id)
        if gif_url:
            try:
                image_bytes, content_type = await _download_bytes_with_limit(session, gif_url)
                if image_bytes:
                    if len(image_bytes) > DISCORD_MAX_UPLOAD:
                        image_bytes = await compress_image(image_bytes)
                    if image_bytes and len(image_bytes) <= DISCORD_MAX_UPLOAD:
                        ext = ".jpg"
                        if "gif" in gif_url.lower() or (content_type and "gif" in content_type):
                            ext = ".gif"
                        elif "png" in gif_url.lower() or (content_type and "png" in content_type):
                            ext = ".png"
                        filename = f"sfw{ext}"
                        file = discord.File(io.BytesIO(image_bytes), filename=filename)
                        await ctx.send(file=file)
                        return
            except Exception:
                pass
        await ctx.send("Failed to fetch SFW content. Try again.")

# ====== Run ======
if not TOKEN:
    logger.error("No TOKEN env var set. Exiting.")
else:
    bot.run(TOKEN)
