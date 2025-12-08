# bot.py
import os
import io
import json
import time
import asyncio
import logging
import random
from datetime import datetime

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

# Image sizes
CARD_WIDTH = 900
CARD_HEIGHT = 300
AVATAR_SIZE = 220

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("anime-welcome-bot")

# -------------------------
# Default messages (loaded into data.json if not present)
# -------------------------
DEFAULT_JOIN_GREETINGS = [
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

DEFAULT_LEAVE_GREETINGS = [
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
# Structure:
# {
#   "join_greetings": [...],
#   "leave_greetings": [...],
#   "join_counts": { "<member_id>": int },
#   "last_greet": { "<member_id>": unix_ts }
# }
# -------------------------
data_lock = asyncio.Lock()
data = {
    "join_greetings": DEFAULT_JOIN_GREETINGS.copy(),
    "leave_greetings": DEFAULT_LEAVE_GREETINGS.copy(),
    "join_counts": {},
    "last_greet": {}
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
                # merge with defaults to avoid missing keys
                data["join_greetings"] = loaded.get("join_greetings", DEFAULT_JOIN_GREETINGS.copy())
                data["leave_greetings"] = loaded.get("leave_greetings", DEFAULT_LEAVE_GREETINGS.copy())
                data["join_counts"] = {k: int(v) for k, v in loaded.get("join_counts", {}).items()}
                data["last_greet"] = {k: float(v) for k, v in loaded.get("last_greet", {}).items()}
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
# Image generation (Pillow)
# -------------------------
async def fetch_avatar_bytes(url: str) -> bytes:
    """
    Fetch avatar bytes via aiohttp. Returns raw bytes or None on failure.
    """
    if not url:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
                else:
                    logger.warning(f"Failed to fetch avatar: HTTP {resp.status}")
                    return None
    except Exception:
        logger.exception("Error fetching avatar bytes")
        return None

def circle_crop(im: Image.Image, size: int) -> Image.Image:
    im = im.resize((size, size)).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    im.putalpha(mask)
    return im

def make_welcome_card(member_name: str, avatar_bytes: bytes, kind: str = "join") -> bytes:
    """
    Create an image card (PNG bytes) with avatar and anime-ish border.
    kind: 'join' or 'leave'
    """
    # create background
    bg_color = (255, 240, 245) if kind == "join" else (235, 243, 255)
    img = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), bg_color)

    draw = ImageDraw.Draw(img)

    # Soft rounded rectangle background stripe
    stripe_color = (255, 228, 235) if kind == "join" else (220, 235, 255)
    stripe_h = CARD_HEIGHT - 40
    draw.rounded_rectangle((20, 20, CARD_WIDTH-20, stripe_h), radius=20, fill=stripe_color)

    # Avatar
    avatar = None
    if avatar_bytes:
        try:
            with Image.open(io.BytesIO(avatar_bytes)) as av:
                avatar = circle_crop(av, AVATAR_SIZE)
        except Exception:
            avatar = None

    if avatar is None:
        # fallback: plain circle with initials
        avatar = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (255, 255, 255, 0))
        ad = ImageDraw.Draw(avatar)
        ad.ellipse((0,0,AVATAR_SIZE,AVATAR_SIZE), fill=(255,255,255))
        # initials
        initials = "".join([p[0] for p in member_name.split()[:2]]).upper()
        try:
            font = ImageFont.truetype("arial.ttf", 72)
        except Exception:
            font = ImageFont.load_default()
        w, h = ad.textsize(initials, font=font)
        ad.text(((AVATAR_SIZE-w)//2, (AVATAR_SIZE-h)//2), initials, fill=(60,60,60), font=font)

    # avatar border (anime-ish ring)
    ring = Image.new("RGBA", (AVATAR_SIZE+12, AVATAR_SIZE+12), (0,0,0,0))
    rd = ImageDraw.Draw(ring)
    outer = (0,0,AVATAR_SIZE+12,AVATAR_SIZE+12)
    rd.ellipse(outer, fill=None, outline=(255, 100, 180), width=8)

    # paste avatar + ring onto card
    av_x = 40
    av_y = (CARD_HEIGHT - AVATAR_SIZE) // 2
    img.paste(ring, (av_x-6, av_y-6), ring)
    img.paste(avatar, (av_x, av_y), avatar)

    # Text
    try:
        font_title = ImageFont.truetype("arial.ttf", 36)
        font_sub = ImageFont.truetype("arial.ttf", 20)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    # Title + subtitle arrangement
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

    # small decoration: sakura petals / stars (simple circles)
    for i in range(6):
        rx = random.randint(title_x, CARD_WIDTH-40)
        ry = random.randint(30, CARD_HEIGHT-30)
        rcol = (255, 180, 220) if kind == "join" else (180, 210, 255)
        draw.ellipse((rx, ry, rx+6, ry+6), fill=rcol)

    # final slight blur for softness
    result = img.filter(ImageFilter.SMOOTH)

    # save to bytes
    out = io.BytesIO()
    result.save(out, format="PNG")
    out.seek(0)
    return out.read()

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
# Admin commands
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

    # Acquire voice & text channel objects
    guild = member.guild
    target_voice = guild.get_channel(VC_ID)  # voice channel object
    text_channel = bot.get_channel(VC_CHANNEL_ID)  # may be None

    # If the configured voice channel isn't in this guild, ignore
    if target_voice is None or target_voice.guild.id != guild.id:
        return

    # Current voice client for the guild (if bot connected)
    vc_client = guild.voice_client

    # CASE: user joined the target voice channel
    if before.channel is None and after.channel == target_voice:
        # Connect bot if not connected
        if not vc_client or not vc_client.is_connected():
            try:
                await target_voice.connect()
                logger.info(f"Connected to VC {target_voice.name} because {member.display_name} joined.")
            except Exception:
                logger.exception("Failed to connect to voice channel")

        # prepare greeting text
        greeting_template = random.choice(data.get("join_greetings", DEFAULT_JOIN_GREETINGS))
        greeting_text = greeting_template.format(display_name=member.display_name, random_ch=random.randint(1,99))

        # increment join count & update last greet
        join_count = increment_join_count(member.id)
        update_last_greet(member.id)

        # prepare embed + image
        embed = make_embed("Welcome!", greeting_text, member, kind="join", join_count=join_count)

        # fetch avatar & create image
        avatar_url = getattr(member.display_avatar, "url", None)
        avatar_bytes = None
        try:
            avatar_bytes = await fetch_avatar_bytes(avatar_url)
        except Exception:
            avatar_bytes = None

        try:
            card_bytes = make_welcome_card(member.display_name, avatar_bytes, kind="join")
            file = discord.File(io.BytesIO(card_bytes), filename="welcome.png")
            embed.set_image(url="attachment://welcome.png")
        except Exception:
            file = None
            logger.exception("Failed to create welcome card image")

        # DM user (with embed + image)
        try:
            if file:
                await member.send(embed=embed, file=file)
            else:
                await member.send(embed=embed)
        except Exception:
            logger.info(f"Couldn't DM {member.display_name} (closed DMs?)")

        # Send to text channel if available
        if text_channel:
            try:
                if file:
                    # need to recreate file object because discord.File is consumed
                    await text_channel.send(embed=embed, file=discord.File(io.BytesIO(card_bytes), filename="welcome.png"))
                else:
                    await text_channel.send(embed=embed)
            except Exception:
                logger.exception("Failed to send join embed to text channel")

        # persist data
        await save_data_async()

    # CASE: user left the target voice channel
    if before.channel == target_voice and (after.channel is None or after.channel != target_voice):
        farewell_template = random.choice(data.get("leave_greetings", DEFAULT_LEAVE_GREETINGS))
        farewell_text = farewell_template.format(display_name=member.display_name, random_ch=random.randint(1,99))
        join_count = int(data.get("join_counts", {}).get(str(member.id), 0))
        embed = make_embed("Goodbye!", farewell_text, member, kind="leave", join_count=join_count)

        # try to create image
        avatar_url = getattr(member.display_avatar, "url", None)
        avatar_bytes = None
        try:
            avatar_bytes = await fetch_avatar_bytes(avatar_url)
        except Exception:
            avatar_bytes = None

        try:
            card_bytes = make_welcome_card(member.display_name, avatar_bytes, kind="leave")
            file = discord.File(io.BytesIO(card_bytes), filename="goodbye.png")
            embed.set_image(url="attachment://goodbye.png")
        except Exception:
            file = None
            logger.exception("Failed to create goodbye card image")

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
                    await text_channel.send(embed=embed, file=discord.File(io.BytesIO(card_bytes), filename="goodbye.png"))
                else:
                    await text_channel.send(embed=embed)
            except Exception:
                logger.exception("Failed to send leave embed to text channel")

        # if bot is connected and nobody (except bots) remains in the voice channel, disconnect
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
