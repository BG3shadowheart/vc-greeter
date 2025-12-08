# bot_fixed.py — Safe & resilient Anime Welcome Bot (NSFW channel expected)
# Changes made: robust JSON load/save, resilient Giphy fetch with fallbacks,
# safer VC join/leave detection (covers moves between voice channels),
# avoid sending NSFW media over DMs, guard against missing channels/permissions,
# improved logging and exception handling.

import os
import io
import json
import asyncio
import random
import hashlib
import logging
from datetime import datetime
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands, tasks

# -------------------------
# CONFIG
# -------------------------
TOKEN = os.getenv("TOKEN")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")

# Replace with real IDs (integers). Verify in Discord dev mode.
VC_ID = 1353875050809524267
VC_CHANNEL_ID = 1446752109151260792   # TEXT channel for greetings (should be NSFW as you said)

DATA_FILE = Path("data.json")
AUTOSAVE_INTERVAL = 30  # seconds

# ✅ NSFW ENABLED TAGS (you said the channel is already NSFW)
GIPHY_ALLOWED_TAGS = [
    "anime sexy", "anime waifu", "hentai", "anime ecchi",
    "anime boobs", "anime ass", "anime milf", "anime girl"
]
GIPHY_RATING = "r"

# -------------------------
# LOGGING
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("anime-bot")

# -------------------------
# GREETINGS
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

# Minimal fallback image bytes (transparent 1x1 GIF) to avoid sending invalid attachments.
# This is used only if Giphy fails; you can replace with a real local file if desired.
FALLBACK_GIF_BYTES = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
FALLBACK_GIF_NAME = "fallback.gif"

# -------------------------
# BOT SETUP
# -------------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# in-memory data
data = {"join_counts": {}}

# -------------------------
# AUTO SAVE
# -------------------------
@tasks.loop(seconds=AUTOSAVE_INTERVAL)
async def autosave_task():
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with DATA_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.debug("Autosaved data.json")
    except Exception:
        logger.exception("Failed to autosave data file")

# -------------------------
# RESILIENT GIPHY FETCH
# -------------------------
async def fetch_giphy(session: aiohttp.ClientSession):
    """Return (bytes, filename, is_nsfw) or (None, None, False) on failure.
    We keep the function safe: never raise to caller; always return a sensible value.
    """
    if not GIPHY_API_KEY:
        logger.warning("GIPHY_API_KEY not set — using fallback gif")
        return FALLBACK_GIF_BYTES, FALLBACK_GIF_NAME, True

    tag = random.choice(GIPHY_ALLOWED_TAGS)
    url = f"https://api.giphy.com/v1/gifs/random?api_key={GIPHY_API_KEY}&tag={tag}&rating={GIPHY_RATING}"

    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status != 200:
                logger.warning("Giphy API returned status %s", resp.status)
                return FALLBACK_GIF_BYTES, FALLBACK_GIF_NAME, True

            obj = await resp.json()

            # Defensive navigation of response
            gif_data = obj.get("data") or {}
            images = gif_data.get("images") or {}
            original = images.get("original") or {}
            gif_url = original.get("url")

            if not gif_url:
                logger.warning("Giphy response had no image url, falling back")
                return FALLBACK_GIF_BYTES, FALLBACK_GIF_NAME, True

            # fetch actual gif bytes
            async with session.get(gif_url, timeout=15) as r:
                if r.status != 200:
                    logger.warning("Failed to fetch GIF bytes, status %s", r.status)
                    return FALLBACK_GIF_BYTES, FALLBACK_GIF_NAME, True
                gif_bytes = await r.read()

            # create a stable filename
            name = f"gif_{hashlib.sha1(gif_url.encode()).hexdigest()[:8]}.gif"

            # We treat GIPHY_RATING == 'r' as nsfw flag True
            is_nsfw = (GIPHY_RATING.lower() == "r")
            return gif_bytes, name, is_nsfw

    except asyncio.TimeoutError:
        logger.exception("Timeout while contacting Giphy")
    except Exception:
        logger.exception("Unexpected error while fetching from Giphy")

    return FALLBACK_GIF_BYTES, FALLBACK_GIF_NAME, True

# -------------------------
# EMBED CREATOR
# -------------------------
def make_embed(title: str, desc: str, member: discord.Member, kind: str = "join", count: int = None):
    color = discord.Color.pink() if kind == "join" else discord.Color.dark_grey()

    embed = discord.Embed(
        title=title,
        description=desc,
        color=color,
        timestamp=datetime.utcnow()
    )

    try:
        embed.set_thumbnail(url=str(member.display_avatar.url))
    except Exception:
        # in weird cases the avatar url may not be accessible
        logger.debug("Could not set thumbnail for member %s", member.id)

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
    # load data file safely
    if DATA_FILE.exists():
        try:
            with DATA_FILE.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data.update(loaded)
            logger.info("Loaded data.json")
        except json.JSONDecodeError:
            logger.exception("data.json is corrupted or invalid JSON — starting fresh")
        except Exception:
            logger.exception("Unexpected error loading data.json — starting fresh")

    # start autosave if not already running
    if not autosave_task.is_running():
        autosave_task.start()

    logger.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

# -------------------------
# VOICE STATE HANDLER
# -------------------------
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    # ignore bot users
    if member.bot:
        return

    guild = member.guild

    # defensive: attempt to resolve channels
    target_vc = guild.get_channel(VC_ID)
    text_channel = bot.get_channel(VC_CHANNEL_ID)

    # If the configured channels are missing, log & return
    if target_vc is None:
        logger.warning("Configured voice channel (VC_ID=%s) not found in guild %s", VC_ID, guild.id)
        return

    if text_channel is None:
        logger.warning("Configured text channel (VC_CHANNEL_ID=%s) not found", VC_CHANNEL_ID)
        # we continue — we still update join counts and attempt DMs

    # Normalize before/after channels (None if not present)
    before_chan = before.channel if before else None
    after_chan = after.channel if after else None

    # Detect entering the target VC (covers joining from outside and moving from other VCs)
    joined_target = (before_chan != target_vc) and (after_chan == target_vc)
    left_target = (before_chan == target_vc) and (after_chan != target_vc)

    # Use a single aiohttp session per operation for efficiency/timeout handling
    async with aiohttp.ClientSession() as session:
        # -------------------------
        # USER JOIN
        # -------------------------
        if joined_target:
            # attempt to connect the bot to VC if not already connected
            try:
                vc_client = guild.voice_client
                if not vc_client or vc_client.channel.id != target_vc.id:
                    try:
                        await target_vc.connect()
                        logger.info("Connected to voice channel %s", target_vc.id)
                    except Exception:
                        logger.exception("Failed to connect to voice channel — continuing without voice")

                raw_msg = random.choice(JOIN_GREETINGS)
                msg = raw_msg.format(display_name=member.display_name)

                # increment join counter
                data["join_counts"][str(member.id)] = data["join_counts"].get(str(member.id), 0) + 1
                count = data["join_counts"][str(member.id)]

                embed = make_embed("Welcome!", msg, member, "join", count)

                # fetch gif safely
                gif_bytes, gif_name, is_nsfw = await fetch_giphy(session)

                # Build file only if bytes present
                file = None
                if gif_bytes:
                    file = discord.File(io.BytesIO(gif_bytes), filename=gif_name)

                # Send to text channel if available
                if text_channel:
                    try:
                        if file:
                            # send embed with attachment
                            await text_channel.send(embed=embed, file=file)
                        else:
                            await text_channel.send(embed=embed)
                    except Exception:
                        logger.exception("Failed to send welcome embed to text channel")

                # Avoid sending NSFW GIFs in DMs — only send a safe text/embed without media
                try:
                    if member.dm_channel is None:
                        try:
                            await member.create_dm()
                        except Exception:
                            logger.debug("Could not create DM for member %s", member.id)

                    # If the fetched GIF is flagged NSFW, do NOT attach it to DM
                    if file and not is_nsfw:
                        try:
                            await member.send(embed=embed, file=file)
                        except Exception:
                            logger.debug("Couldn't send DM with image; skipping")
                    else:
                        # send DM without attachment (safer)
                        try:
                            await member.send(embed=embed)
                        except Exception:
                            logger.debug("Couldn't send DM without image; skipping")
                except Exception:
                    logger.exception("Unexpected error while attempting member DM")

        # -------------------------
        # USER LEAVE
        # -------------------------
        if left_target:
            raw_msg = random.choice(LEAVE_GREETINGS)
            msg = raw_msg.format(display_name=member.display_name)

            embed = make_embed("Goodbye!", msg, member, "leave")

            gif_bytes, gif_name, is_nsfw = await fetch_giphy(session)
            file = None
            if gif_bytes:
                file = discord.File(io.BytesIO(gif_bytes), filename=gif_name)

            if text_channel:
                try:
                    if file:
                        await text_channel.send(embed=embed, file=file)
                    else:
                        await text_channel.send(embed=embed)
                except Exception:
                    logger.exception("Failed to send leave embed to text channel")

            # DM without NSFW media
            try:
                if member.dm_channel is None:
                    try:
                        await member.create_dm()
                    except Exception:
                        logger.debug("Could not create DM for member %s", member.id)

                if file and not is_nsfw:
                    try:
                        await member.send(embed=embed, file=file)
                    except Exception:
                        logger.debug("Couldn't send DM with image; skipping")
                else:
                    try:
                        await member.send(embed=embed)
                    except Exception:
                        logger.debug("Couldn't send DM without image; skipping")
            except Exception:
                logger.exception("Unexpected error while attempting DM on leave")

            # Auto-disconnect the bot from VC when empty
            try:
                vc_client = guild.voice_client
                if vc_client and vc_client.channel.id == target_vc.id:
                    non_bot_members = [m for m in vc_client.channel.members if not m.bot]
                    if len(non_bot_members) == 0:
                        try:
                            await vc_client.disconnect()
                            logger.info("Disconnected from voice channel %s (empty)", target_vc.id)
                        except Exception:
                            logger.exception("Failed to disconnect from voice channel")
            except Exception:
                logger.exception("Error checking/disconnecting voice client")

# -------------------------
# SIMPLE ADMIN COMMANDS (optional)
# -------------------------
@bot.command(name="reload_greetings")
@commands.has_permissions(administrator=True)
async def _reload_greetings(ctx):
    """Example admin command placeholder — you could reload lists from disk if needed."""
    await ctx.send("Greetings reload placeholder — lists are embedded in the bot file.")

# -------------------------
# START BOT
# -------------------------
if __name__ == "__main__":
    if not TOKEN:
        logger.error("TOKEN not set — aborting")
    else:
        try:
            bot.run(TOKEN)
        except Exception:
            logger.exception("Bot terminated unexpectedly")
