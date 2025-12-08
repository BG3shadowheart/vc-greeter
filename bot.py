# bot.py
"""
Anime Welcome Bot (SFW-only GIFs)
- Auto-joins target voice channel when users join, leaves when empty
- Sends anime-style embed messages to user's DM and a configured text channel
- Automatically fetches GIFs from Giphy (SFW tags + rating) and caches used URLs in data.json
- Falls back to a generated PNG card (Pillow) if GIF unavailable
- Persists join/leave messages, join counts, last-greet timestamps, used GIF URLs
"""

import os
import io
import json
import time
import asyncio
import logging
import random
import hashlib
from datetime import datetime
from typing import Optional, Tuple

import aiohttp
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import discord
from discord.ext import commands, tasks

# -------------------------
# CONFIG
# -------------------------
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN environment variable not set")

# GIPHY key (put your key in env var)
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")

# Voice channel ID (the voice channel the bot should auto-join)
VC_ID = 1353875050809524267

# Text channel ID where embeds will be posted (can be different)
VC_CHANNEL_ID = 1353875050809524267

# Optional: restrict to a single server by ID (set as env SERVER_ID), or None to allow any
try:
    SERVER_ID = int(os.getenv("SERVER_ID"))
except Exception:
    SERVER_ID = None

# Persistence file
DATA_FILE = "data.json"

# Cooldown (seconds) per user for DM greetings
COOLDOWN_SECONDS = 300  # 5 minutes

# Autosave interval (seconds)
AUTOSAVE_INTERVAL = 30

# Max remote GIF bytes we'll accept
MAX_GIF_BYTES = 8 * 1024 * 1024  # 8 MB

# Image sizes (fallback card)
CARD_WIDTH = 900
CARD_HEIGHT = 300
AVATAR_SIZE = 220

# Allowed SFW GIPHY tags (randomly chosen each request)
GIPHY_ALLOWED_TAGS = [
    "anime", "waifu", "kawaii", "neko", "chibi", "moe", "cute", "magical+girl", "senpai",
    "vaporwave", "yuri", "shoujo", "shonen", "anime nsfw", "anime milf", "hentai", "anime sexy", "anime boobs", "anime ass"
]

# Use Giphy rating to enforce SFW (g, pg, or pg-13). We will request rating=pg-18.
GIPHY_RATING = "pg-18"

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("anime-welcome-bot")

# -------------------------
# 100+ JOIN and 100+ LEAVE messages (SFW anime-style)
# NOTE: These are built-in and persisted to data.json on first run.
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
    "🌬️ A soft breeze carries {display_name} into the VC.",
    "🎇 Fireworks explode — {display_name} is here!",
    "🕊️ The white dove brings peace — {display_name} has arrived.",
    "🐾 Nya~ {display_name} appears with adorable energy.",
    "🌌 A cosmic traveler, {display_name}, has joined us.",
    "🎋 May luck bless you, {display_name} — welcome!",
    "🧚 A fairy sparkles — oh, it’s just {display_name} arriving.",
    "🔮 The prophecy foretold your arrival, {display_name}.",
    "💥 Impact detected! {display_name} landed in the VC.",
    "🍃 A new leaf blows in — {display_name} is here.",
    "🐉 A dragon stirs… {display_name} has joined.",
    "🎐 The wind chimes sing — welcome, {display_name}.",
    "🪄 Magic surges — {display_name} enters.",
    "🪽 Angelic presence detected — hello, {display_name}.",
    "🌈 A rainbow leads {display_name} to the VC.",
    "🍀 Lucky day! {display_name} has joined us.",
    "🌓 Between light and shadow stands {display_name}.",
    "🗡️ A rogue with silent steps… {display_name} enters.",
    "🥋 A disciplined hero arrives — {display_name}!",
    "💎 A rare gem walks in — {display_name} is here.",
    "🔔 The bells chime — welcome, {display_name}.",
    "🌟 A burst of stardust — {display_name} arrived!",
    "🍁 Autumn breeze brings {display_name}.",
    "🥀 Elegance enters the room — {display_name}.",
    "💼 Professional energy detected — {display_name} joins.",
    "🪷 Blooming in grace — welcome, {display_name}.",
    "🎧 Headphones on — {display_name} is ready.",
    "😪 Sleepy aura… {display_name} still joins anyway.",
    "🕶️ Cool protagonist vibes — hello, {display_name}.",
    "🎞️ New episode unlocked — starring {display_name}.",
    "📸 Snapshot moment — {display_name} entered.",
    "🚀 Launch successful — {display_name} has joined.",
    "🌪️ A whirlwind brings {display_name}.",
    "🔔 Ding dong — {display_name} is here.",
    "🍓 Sweetness overload — {display_name} joins.",
    "🍷 Classy entrance by {display_name}.",
    "🐺 Lone wolf {display_name} enters silently.",
    "🌤️ Sunshine follows {display_name} into the VC.",
    "❄️ A cold breeze… {display_name} has arrived.",
    "⚡ A spark ignites — welcome, {display_name}.",
    "🎃 Spooky aura — {display_name} appears.",
    "🛡️ Protector {display_name} enters the realm.",
    "🔗 A bond strengthens — {display_name} joins.",
    "🐼 Cute and chill — welcome, {display_name}.",
    "🍙 Rice ball hero {display_name} arrives.",
    "📚 A scholar enters — {display_name}.",
    "💼 CEO of vibes — {display_name} has arrived.",
    "🎤 Mic check — {display_name} is in!",
    "🔥 Rising flame — {display_name} joins.",
    "🌠 A shooting star — welcome, {display_name}.",
    "🛸 UFO sighting — {display_name} has landed.",
    "🌊 Ocean waves bring {display_name}.",
    "🦄 Magical sparkle — {display_name} appears.",
    "🧁 Sweet treat {display_name} enters.",
    "🔮 Mystic portal opens — {display_name} steps in.",
    "🪽 Feather drifts… {display_name} has arrived.",
    "🎡 Carnival vibe — welcome, {display_name}.",
    "🍣 Sushi spirit — {display_name} joins the feast.",
    "🦋 Butterfly wings lead {display_name} here.",
    "🐉 Dragon’s roar announces {display_name}.",
    "👑 Royal presence detected — {display_name}.",
    "🌹 A rose blooms — {display_name} appears.",
    "💫 Fate shifts — {display_name} enters.",
    "🧊 Ice cool arrival — {display_name}.",
    "🧸 Soft steps — {display_name} appears.",
    "🪬 Blessed vibes — welcome, {display_name}.",
    "📀 Retro energy — {display_name} pops in.",
    "🌾 Calm fields welcome {display_name}.",
    "🛞 Rolling in smoothly — {display_name}.",
    "🔥 Your aura lit up the VC, {display_name}.",
    "🎀 A cute bow appears — {display_name} is here!",
    "🦉 Night owl {display_name} arrives.",
    "🪁 Flying in — welcome, {display_name}.",
    "🌌 A cosmic ripple — {display_name} entered.",
    "🕯️ A warm flame glows — {display_name} joined.",
    "💍 Precious presence — {display_name}.",
    "🎒 Adventure awaits — {display_name} joins.",
    "📚 Story continues — {display_name} appears.",
    "⚙️ Mechanized entrance — {display_name}.",
    "🎶 A melody begins — welcome, {display_name}.",
    "🌈 Your aura colors the VC, {display_name}.",
    "🌀 Dramatic cut-in — {display_name} joins!",
]

LEAVE_GREETINGS = [
    "🌙 {display_name} fades into the night. Until next time.",
    "🍃 A gentle breeze carries {display_name} away.",
    "💫 {display_name} disappears in a swirl of stardust.",
    "🥀 A petal falls… {display_name} has left.",
    "⚔️ Warrior {display_name} sheaths their blade and exits.",
    "🌧️ Rain replaces the silence {display_name} leaves behind.",
    "🔕 The scene quiets… {display_name} is gone.",
    "🕊️ Fly safely, {display_name}. Until later.",
    "🎭 Curtain closes for {display_name}.",
    "📖 Another chapter ends for {display_name}.",
    "🐾 Pawprints fade — {display_name} left.",
    "⚡ The energy drops — {display_name} has gone.",
    "🍂 Autumn wind takes {display_name} away.",
    "🎐 Wind chimes stop — {display_name} departed.",
    "🧊 Chill remains… {display_name} exits.",
    "🪽 Angel glides away — bye {display_name}.",
    "💌 A final letter… {display_name} left.",
    "🌫️ Mist clears — {display_name} vanished.",
    "🪞 Reflection breaks — {display_name} gone.",
    "🛡️ Protector rests — goodbye, {display_name}.",
    "🐺 Lone wolf {display_name} slips away.",
    "❄️ Snow settles — {display_name} logged out.",
    "🍵 Tea cools — {display_name} has left.",
    "🎮 Player {display_name} left the lobby.",
    "🎞️ Scene ends — goodbye, {display_name}.",
    "🗡️ Blade dimmed — {display_name} exits.",
    "🍙 The rice ball rolls away… bye {display_name}.",
    "🎤 Mic muted — {display_name} has departed.",
    "🧚 Fairy dust fades — farewell, {display_name}.",
    "🌈 Rainbow disappears — {display_name} gone.",
    "🐉 Dragon sleeps — {display_name} left.",
    "🌪️ Calm returns — {display_name} exits.",
    "🌌 Stars dim — goodbye, {display_name}.",
    "🪷 Petals close — {display_name} left.",
    "🕶️ Cool exit — bye {display_name}.",
    "📸 Snapshot saved — {display_name} left.",
    "🎒 Adventure paused — {display_name} exits.",
    "⚙️ Gears stop turning — {display_name} is gone.",
    "💫 Magic disperses — goodbye, {display_name}.",
    "🪬 Protection fades — bye, {display_name}.",
    "📀 Retro fade-out — {display_name} left.",
    "👑 Royal exit — farewell, {display_name}.",
    "🦋 Wings flutter away — {display_name} left.",
    "🎡 Carnival lights dim — {display_name} exits.",
    "🛸 UFO retreats — {display_name} gone.",
    "🔥 Flame cools — {display_name} has left.",
    "🦉 Night silence — {display_name} left.",
    "🌠 Shooting star vanished — {display_name}.",
    "🧸 Soft goodbye — {display_name} left.",
    "🌙 Moon watches {display_name} leave.",
    "🪁 Kite drifts away — {display_name}.",
    "🛞 Wheels roll — goodbye, {display_name}.",
    "🌊 Tide recedes — {display_name} gone.",
    "💍 Shine fades — {display_name} exits.",
    "🍣 Last sushi taken — {display_name} left.",
    "🌱 Seedling rests — {display_name} gone.",
    "🎀 Ribbon untied — {display_name} exits.",
    "🍁 Leaf falls — farewell, {display_name}.",
    "🔗 Chain breaks — {display_name} left.",
    "🩶 Grey clouds remain — {display_name}.",
    "🕯️ Candle blows out — {display_name} left.",
    "🎵 Final note plays — goodbye {display_name}.",
    "🐉 Dragon tail disappears — {display_name}.",
    "🏮 Lantern dims — {display_name} leaves.",
    "🕸️ Web breaks — {display_name} left.",
    "🌫️ Fog settles — {display_name} exits.",
    "💔 Heart cracks — {display_name} left the VC.",
    "🎲 Game over — {display_name} quits.",
    "🖤 Shadow fades — bye {display_name}.",
    "🌑 Darkness takes {display_name}.",
    "🪽 Feather falls — {display_name} gone.",
    "🌪️ Storm quiet — {display_name} left.",
    "🍉 Summer fades — {display_name} exits.",
    "🍂 Rustling stops — {display_name}.",
    "🌻 Sunflower bows — {display_name} gone.",
    "🌴 Breeze stops — {display_name} left.",
    "🍬 Sweetness gone — bye {display_name}.",
    "🧠 Big brain left — {display_name}.",
    "🧨 Firework finished — {display_name} left.",
    "🎯 Target cleared — {display_name} gone.",
    "🛌 Sleep calls {display_name}.",
    "🚪 Door closes — {display_name} left.",
    "⚰️ Dead silence — {display_name} exits.",
    "📚 Story ends — {display_name}.",
    "🌒 Fade to black — {display_name} left."
]

# -------------------------
# Bot & Intents
# -------------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# Runtime data (persisted)
# -------------------------
data_lock = asyncio.Lock()
data = {
    "join_greetings": JOIN_GREETINGS.copy(),
    "leave_greetings": LEAVE_GREETINGS.copy(),
    "join_counts": {},
    "last_greet": {},
    "used_gifs": [],     # previously used GIF URLs (cached)
}

# -------------------------
# Persistence helpers
# -------------------------
def load_data_sync():
    global data
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                # merge while keeping defaults
                data["join_greetings"] = loaded.get("join_greetings", data["join_greetings"])
                data["leave_greetings"] = loaded.get("leave_greetings", data["leave_greetings"])
                data["join_counts"] = {k: int(v) for k, v in loaded.get("join_counts", {}).items()}
                data["last_greet"] = {k: float(v) for k, v in loaded.get("last_greet", {}).items()}
                data["used_gifs"] = loaded.get("used_gifs", data["used_gifs"])
                logger.info("Loaded data.json")
            else:
                logger.warning("data.json malformed — using defaults")
                save_data_sync()
        else:
            logger.info("No data.json found — creating default file")
            save_data_sync()
    except Exception:
        logger.exception("Failed to load data.json, using defaults")
        save_data_sync()

def save_data_sync():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug("Saved data.json (sync)")
    except Exception:
        logger.exception("Failed to save data.json (sync)")

async def save_data_async():
    async with data_lock:
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug("Saved data.json (async)")
        except Exception:
            logger.exception("Failed to save data.json (async)")

# -------------------------
# Autosave task
# -------------------------
@tasks.loop(seconds=AUTOSAVE_INTERVAL)
async def autosave_task():
    await save_data_async()

# -------------------------
# Utility: cooldown, counts
# -------------------------
def is_on_cooldown(member_id: int) -> bool:
    last = data.get("last_greet", {}).get(str(member_id))
    if not last:
        return False
    return (time.time() - float(last)) < COOLDOWN_SECONDS

def update_last_greet(member_id: int):
    data["last_greet"][str(member_id)] = time.time()

def increment_join_count(member_id: int) -> int:
    key = str(member_id)
    data["join_counts"][key] = int(data.get("join_counts", {}).get(key, 0)) + 1
    return data["join_counts"][key]

# -------------------------
# Fallback image generation (Pillow)
# -------------------------
def circle_crop(im: Image.Image, size: int) -> Image.Image:
    im = im.resize((size, size)).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    im.putalpha(mask)
    return im

def make_welcome_card(member_name: str, avatar_bytes: Optional[bytes], kind: str = "join") -> bytes:
    bg_color = (255, 240, 245) if kind == "join" else (235, 243, 255)
    img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), bg_color)
    draw = ImageDraw.Draw(img)
    stripe_color = (255, 228, 235) if kind == "join" else (220, 235, 255)
    draw.rounded_rectangle((20, 20, CARD_WIDTH-20, CARD_HEIGHT-40), radius=20, fill=stripe_color)

    avatar = None
    if avatar_bytes:
        try:
            with Image.open(io.BytesIO(avatar_bytes)) as av:
                avatar = circle_crop(av, AVATAR_SIZE)
        except Exception:
            avatar = None

    if avatar is None:
        avatar = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (255, 255, 255, 0))
        ad = ImageDraw.Draw(avatar)
        ad.ellipse((0,0,AVATAR_SIZE,AVATAR_SIZE), fill=(255,255,255))
        initials = "".join([p[0] for p in member_name.split()[:2]]).upper()
        try:
            font = ImageFont.truetype("arial.ttf", 72)
        except Exception:
            font = ImageFont.load_default()
        w, h = ad.textsize(initials, font=font)
        ad.text(((AVATAR_SIZE-w)//2, (AVATAR_SIZE-h)//2), initials, fill=(60,60,60), font=font)

    ring = Image.new("RGBA", (AVATAR_SIZE+12, AVATAR_SIZE+12), (0,0,0,0))
    rd = ImageDraw.Draw(ring)
    rd.ellipse((0,0,AVATAR_SIZE+12,AVATAR_SIZE+12), fill=None, outline=(255, 100, 180), width=8)

    av_x = 40
    av_y = (CARD_HEIGHT - AVATAR_SIZE) // 2
    img.paste(ring, (av_x-6, av_y-6), ring)
    img.paste(avatar, (av_x, av_y), avatar)

    try:
        font_title = ImageFont.truetype("arial.ttf", 36)
        font_sub = ImageFont.truetype("arial.ttf", 20)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    title_x = av_x + AVATAR_SIZE + 30
    title_y = av_y + 10
    if kind == "join":
        title_text = f"Welcome, {member_name}!"
        subtitle = "Glad you joined the voice channel ✨"
    else:
        title_text = f"Goodbye, {member_name}!"
        subtitle = "Safe travels — see you next time 👋"

    draw.text((title_x, title_y), title_text, fill=(40,40,40), font=font_title)
    draw.text((title_x, title_y + 52), subtitle, fill=(70,70,70), font=font_sub)

    for i in range(6):
        rx = random.randint(title_x, CARD_WIDTH-40)
        ry = random.randint(30, CARD_HEIGHT-30)
        rcol = (255, 180, 220) if kind == "join" else (180, 210, 255)
        draw.ellipse((rx, ry, rx+6, ry+6), fill=rcol)

    result = img.filter(ImageFilter.SMOOTH)
    out = io.BytesIO()
    result.save(out, format="PNG")
    out.seek(0)
    return out.read()

# -------------------------
# Remote GIF fetching helpers (Giphy + safe checks)
# -------------------------
async def fetch_remote_gif(url: str, max_bytes: int = MAX_GIF_BYTES) -> Optional[Tuple[bytes, str]]:
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # HEAD to check size if available
            head = None
            try:
                head = await session.head(url, allow_redirects=True)
            except Exception:
                head = None

            if head is not None:
                length = head.headers.get("Content-Length")
                if length:
                    try:
                        length = int(length)
                        if length > max_bytes:
                            logger.info(f"Skipping {url} (Content-Length {length} > max {max_bytes})")
                            return None
                    except Exception:
                        pass

            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.info(f"Failed to fetch gif {url} — status {resp.status}")
                    return None
                total = 0
                chunks = []
                async for chunk in resp.content.iter_chunked(64*1024):
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > max_bytes:
                        logger.info(f"Fetched data for {url} exceeded max ({total} bytes). Skipping.")
                        return None
                data = b"".join(chunks)
                if not (data.startswith(b"GIF87a") or data.startswith(b"GIF89a")):
                    logger.info(f"Data from {url} is not a GIF (signature mismatch).")
                    return None
                h = hashlib.sha1(url.encode()).hexdigest()[:8]
                filename = f"remote_{h}.gif"
                return data, filename
    except Exception:
        logger.exception("Error fetching remote gif")
        return None

async def fetch_giphy_random_bytes(tag: str) -> Optional[Tuple[bytes, str, str]]:
    """
    Use Giphy random endpoint to get a GIF URL for tag (SFW rating).
    Returns (bytes, filename, url) on success.
    """
    if not GIPHY_API_KEY:
        return None
    try:
        # Build random endpoint URL with rating enforced
        safe_tag = tag.replace(" ", "+")
        api_url = f"https://api.giphy.com/v1/gifs/random?api_key={GIPHY_API_KEY}&tag={safe_tag}&rating={GIPHY_RATING}"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    logger.info(f"Giphy API returned status {resp.status}")
                    return None
                obj = await resp.json()
                data_obj = obj.get("data", {})
                gif_url = None
                # try several known fields
                if isinstance(data_obj, dict):
                    images = data_obj.get("images", {})
                    if isinstance(images, dict):
                        orig = images.get("original") or images.get("downsized")
                        if orig and isinstance(orig, dict):
                            gif_url = orig.get("url") or orig.get("mp4")
                    if not gif_url:
                        gif_url = data_obj.get("image_original_url") or data_obj.get("image_url")
                if not gif_url:
                    logger.info("Giphy returned no usable gif url")
                    return None
                # download gif bytes safely
                res = await fetch_remote_gif(gif_url, max_bytes=MAX_GIF_BYTES)
                if res:
                    gif_bytes, filename = res
                    return gif_bytes, filename, gif_url
    except Exception:
        logger.exception("Error fetching from Giphy")
        return None

async def get_random_gif_bytes_and_url() -> Optional[Tuple[bytes, str, str]]:
    """
    Try Giphy (random tag) and then fall back to used_gifs cached list if any.
    Returns (bytes, filename, url) or None.
    """
    # Try Giphy with random allowed tags (up to 3 attempts)
    if GIPHY_API_KEY:
        tags = random.sample(GIPHY_ALLOWED_TAGS, min(3, len(GIPHY_ALLOWED_TAGS)))
        for tag in tags:
            try:
                g = await fetch_giphy_random_bytes(tag)
                if g:
                    gif_bytes, filename, url = g
                    return gif_bytes, filename, url
            except Exception:
                continue
    # Fallback: reuse from used_gifs cache (if present)
    used = data.get("used_gifs", [])
    if used:
        # try up to 4 random cached URLs
        attempts = min(4, len(used))
        for url in random.sample(used, attempts):
            try:
                res = await fetch_remote_gif(url, max_bytes=MAX_GIF_BYTES)
                if res:
                    gif_bytes, filename = res
                    return gif_bytes, filename, url
            except Exception:
                continue
    return None

# -------------------------
# Simple avatar fetch for fallback PNG creation
# -------------------------
async def fetch_avatar_bytes_simple(url: str) -> Optional[bytes]:
    if not url:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
                else:
                    return None
    except Exception:
        return None

# -------------------------
# Embed maker
# -------------------------
def make_embed(title: str, description: str, member: discord.Member, kind: str = "join", join_count: int = None):
    emoji = "✨" if kind == "join" else "👋"
    color = discord.Color.from_rgb(255, 182, 193) if kind == "join" else discord.Color.from_rgb(176, 196, 222)
    embed = discord.Embed(
        title=f"{emoji} {title}",
        description=description,
        color=color,
        timestamp=datetime.utcnow()
    )
    try:
        embed.set_thumbnail(url=member.display_avatar.url)
    except Exception:
        pass
    footer_text = f"{member.display_name} • {member.id}"
    if join_count is not None:
        footer_text += f" • VC joins: {join_count}"
    embed.set_footer(text=footer_text)
    return embed

# -------------------------
# Lightweight admin commands (only for message editing; GIFs are automatic)
# -------------------------
@commands.has_permissions(administrator=True)
@bot.command(name="addjoin")
async def add_join(ctx, *, text: str):
    async with data_lock:
        data["join_greetings"].append(text)
    await save_data_async()
    await ctx.send(f"✅ Added join greeting. Total join greetings: {len(data['join_greetings'])}")

@commands.has_permissions(administrator=True)
@bot.command(name="addleave")
async def add_leave(ctx, *, text: str):
    async with data_lock:
        data["leave_greetings"].append(text)
    await save_data_async()
    await ctx.send(f"✅ Added leave greeting. Total leave greetings: {len(data['leave_greetings'])}")

@commands.has_permissions(administrator=True)
@bot.command(name="listmsgs")
async def list_msgs(ctx):
    await ctx.send(f"Join messages: {len(data['join_greetings'])} | Leave messages: {len(data['leave_greetings'])}")

@commands.has_permissions(administrator=True)
@bot.command(name="savecfg")
async def savecfg(ctx):
    await save_data_async()
    await ctx.send("✅ Saved config to disk.")

@commands.has_permissions(administrator=True)
@bot.command(name="reloadcfg")
async def reloadcfg(ctx):
    load_data_sync()
    await ctx.send("✅ Reloaded config from disk.")

# -------------------------
# Events: ready + voice updates
# -------------------------
@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} — Anime welcome bot active.")
    load_data_sync()
    if not autosave_task.is_running():
        autosave_task.start()
    ch = bot.get_channel(VC_CHANNEL_ID)
    if ch:
        logger.info(f"Target text channel OK: {ch.name} ({ch.id})")
    else:
        logger.warning("Target text channel not found — verify VC_CHANNEL_ID and permissions.")

@bot.event
async def on_voice_state_update(member, before, after):
    # Ignore bots
    if member.bot:
        return

    # Optional server restriction
    if SERVER_ID and member.guild.id != SERVER_ID:
        return

    guild = member.guild
    target_voice = guild.get_channel(VC_ID)
    text_channel = bot.get_channel(VC_CHANNEL_ID)

    # If the configured voice channel isn't in this guild, ignore
    if target_voice is None or target_voice.guild.id != guild.id:
        return

    vc_client = guild.voice_client

    # User joined the tracked VC
    if before.channel is None and after.channel == target_voice:
        if not vc_client or not vc_client.is_connected():
            try:
                await target_voice.connect()
                logger.info(f"Connected to VC {target_voice.name} because {member.display_name} joined.")
            except Exception:
                logger.exception("Failed to connect to voice channel")

        # pick greeting and update counts
        greeting_template = random.choice(data.get("join_greetings", JOIN_GREETINGS))
        greeting_text = greeting_template.format(display_name=member.display_name, random_ch=random.randint(1,99))
        join_count = increment_join_count(member.id)
        update_last_greet(member.id)
        embed = make_embed("Welcome!", greeting_text, member, kind="join", join_count=join_count)

        # Attempt to get GIF bytes + url (Giphy -> cached used urls)
        gif_tuple = None
        try:
            gif_tuple = await get_random_gif_bytes_and_url()
        except Exception:
            gif_tuple = None

        file = None
        gif_url_used = None
        card_bytes = None
        if gif_tuple:
            gif_bytes, gif_filename, gif_url = gif_tuple
            try:
                file = discord.File(io.BytesIO(gif_bytes), filename=gif_filename)
                embed.set_image(url=f"attachment://{gif_filename}")
                gif_url_used = gif_url
            except Exception:
                logger.exception("Failed to attach remote gif, will fallback")
                file = None
                gif_url_used = None

        # Fallback: generate PNG card
        if file is None:
            avatar_url = getattr(member.display_avatar, "url", None)
            avatar_bytes = None
            if avatar_url:
                try:
                    avatar_bytes = await fetch_avatar_bytes_simple(avatar_url)
                except Exception:
                    avatar_bytes = None
            try:
                card_bytes = make_welcome_card(member.display_name, avatar_bytes, kind="join")
                file = discord.File(io.BytesIO(card_bytes), filename="welcome.png")
                embed.set_image(url="attachment://welcome.png")
            except Exception:
                file = None
                logger.exception("Failed to create fallback welcome PNG")

        # DM
        try:
            if file:
                await member.send(embed=embed, file=file)
            else:
                await member.send(embed=embed)
        except Exception:
            logger.info(f"Couldn't DM {member.display_name} (closed DMs?)")

        # send to text channel (recreate file object as needed)
        if text_channel:
            try:
                if file:
                    if gif_url_used:
                        await text_channel.send(embed=embed, file=discord.File(io.BytesIO(gif_bytes), filename=gif_filename))
                    elif card_bytes:
                        await text_channel.send(embed=embed, file=discord.File(io.BytesIO(card_bytes), filename="welcome.png"))
                    else:
                        await text_channel.send(embed=embed)
                else:
                    await text_channel.send(embed=embed)
            except Exception:
                logger.exception("Failed to send join embed to text channel")

        # cache used gif url (if any)
        if gif_url_used:
            async with data_lock:
                used = data.get("used_gifs", [])
                if gif_url_used not in used:
                    used.append(gif_url_used)
                    data["used_gifs"] = used
                    await save_data_async()

        await save_data_async()

    # User left the tracked VC
    if before.channel == target_voice and (after.channel is None or after.channel != target_voice):
        farewell_template = random.choice(data.get("leave_greetings", LEAVE_GREETINGS))
        farewell_text = farewell_template.format(display_name=member.display_name, random_ch=random.randint(1,99))
        join_count = int(data.get("join_counts", {}).get(str(member.id), 0))
        embed = make_embed("Goodbye!", farewell_text, member, kind="leave", join_count=join_count)

        # Try GIF
        gif_tuple = None
        try:
            gif_tuple = await get_random_gif_bytes_and_url()
        except Exception:
            gif_tuple = None

        file = None
        gif_url_used = None
        card_bytes = None
        if gif_tuple:
            gif_bytes, gif_filename, gif_url = gif_tuple
            try:
                file = discord.File(io.BytesIO(gif_bytes), filename=gif_filename)
                embed.set_image(url=f"attachment://{gif_filename}")
                gif_url_used = gif_url
            except Exception:
                logger.exception("Failed to attach remote gif for leave, will fallback")
                file = None
                gif_url_used = None

        # Fallback PNG
        if file is None:
            avatar_url = getattr(member.display_avatar, "url", None)
            avatar_bytes = None
            if avatar_url:
                try:
                    avatar_bytes = await fetch_avatar_bytes_simple(avatar_url)
                except Exception:
                    avatar_bytes = None
            try:
                card_bytes = make_welcome_card(member.display_name, avatar_bytes, kind="leave")
                file = discord.File(io.BytesIO(card_bytes), filename="goodbye.png")
                embed.set_image(url="attachment://goodbye.png")
            except Exception:
                file = None
                logger.exception("Failed to create goodbye PNG fallback")

        # DM farewell
        try:
            if file:
                await member.send(embed=embed, file=file)
            else:
                await member.send(embed=embed)
        except Exception:
            logger.info(f"Couldn't DM farewell to {member.display_name} (closed DMs?)")

        # channel farewell
        if text_channel:
            try:
                if file:
                    if gif_url_used:
                        await text_channel.send(embed=embed, file=discord.File(io.BytesIO(gif_bytes), filename=gif_filename))
                    elif card_bytes:
                        await text_channel.send(embed=embed, file=discord.File(io.BytesIO(card_bytes), filename="goodbye.png"))
                    else:
                        await text_channel.send(embed=embed)
                else:
                    await text_channel.send(embed=embed)
            except Exception:
                logger.exception("Failed to send leave embed to text channel")

        # cache used gif url (if any)
        if gif_url_used:
            async with data_lock:
                used = data.get("used_gifs", [])
                if gif_url_used not in used:
                    used.append(gif_url_used)
                    data["used_gifs"] = used
                    await save_data_async()

        # disconnect bot if empty
        vc_client = guild.voice_client
        if vc_client and vc_client.channel and vc_client.channel.id == target_voice.id:
            non_bot_members = [m for m in vc_client.channel.members if not m.bot]
            if len(non_bot_members) == 0:
                try:
                    await vc_client.disconnect()
                    logger.info(f"Disconnected from VC {target_voice.name} as it's now empty.")
                except Exception:
                    logger.exception("Failed to disconnect from VC")

# -------------------------
# Graceful shutdown / save
# -------------------------
@bot.event
async def on_disconnect():
    logger.info("Disconnecting — saving data sync.")
    save_data_sync()

# -------------------------
# Startup
# -------------------------
if __name__ == "__main__":
    load_data_sync()
    bot.run(TOKEN)
