# bot.py — Optimized Anime Welcome Bot (NSFW | Tenor + Giphy | Multi-VC | No Server Mention)
# FULL SCRIPT — copy & paste as-is
# Added: owner-only react-based GIF rejection (owner can ❌ a GIF to never use it again for that server)
# Updated: wait before adding reactions so owner has time to react

import os
import io
import json
import random
import hashlib
import logging
import asyncio
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands, tasks

# -------------------------
# CONFIG
# -------------------------
TOKEN = os.getenv("TOKEN")
TENOR_API_KEY = os.getenv("TENOR_API_KEY")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")

# MULTIPLE VCs (same server)
VC_IDS = [
    1353875050809524267,
    21409170559337762980,
    1353882705246556220
]

# GREETING TEXT CHANNEL
VC_CHANNEL_ID = 1446752109151260792   # GREETING CHANNEL

DATA_FILE = "data.json"
AUTOSAVE_INTERVAL = 30

# ✅ STRICT HENTAI / ANIME-ART RELATED TAGS
GIF_TAGS = [
    "anime sexy","anime waifu","hentai","anime ecchi","anime boobs",
    "anime ass","anime milf","anime girl","hentai anime","anime girl ecchi",
    "genshin impact waifu","game waifu","anime hot girl","anime milf",
    "hentai anime girl","funny hentai","anime ecchi hentai","nsfw anime",
    "hentai waifu","hentai anime girl","anime hentai gif","hentai animation",
    "anime nsfw gif","ecchi anime girl","anime fanservice","anime lewd","anime ero",
    "waifu ecchi","hentai fanmade","anime blush ecchi","anime seductive",
    "anime suggestive","ecchi fighting anime","lewd anime girl","anime swimsuit ecchi"
]

GIPHY_RATING = "r"

# -------------------------
# LOGGING
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("anime-bot")

# -------------------------
# JOIN & LEAVE GREETINGS (full lists)
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
    "⚙️ Mechanized entrance — {display_name} enters.",
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
# BOT SETUP
# -------------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True
intents.reactions = True  # required to listen to reactions

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# DATA LOADING / AUTOSAVE
# -------------------------
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"join_counts": {}, "rejected_gifs": {}, "message_gif_map": {}}, f)

with open(DATA_FILE, "r") as f:
    data = json.load(f)

# ensure keys exist
data.setdefault("join_counts", {})
data.setdefault("rejected_gifs", {})       # guild_id (str) -> [gif_url, ...]
data.setdefault("message_gif_map", {})     # guild_id (str) -> {message_id (str): gif_url}

def save_data():
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save data: {e}")

@tasks.loop(seconds=AUTOSAVE_INTERVAL)
async def autosave_task():
    save_data()

# -------------------------
# FETCH GIF (TENOR FIRST, FALLBACK GIPHY) with rejection avoidance
# -------------------------
async def fetch_gif(guild_id=None, max_attempts=6):
    """
    Returns (gif_bytes, gif_name, gif_url) or (None, None, None).
    If guild_id provided, will avoid gif_urls in data['rejected_gifs'][guild_id].
    """
    rejected = set()
    if guild_id is not None:
        rejected = set(data.get("rejected_gifs", {}).get(str(guild_id), []))

    for attempt in range(max_attempts):
        tag = random.choice(GIF_TAGS)

        # Try Tenor
        if TENOR_API_KEY:
            try:
                tenor_url = f"https://g.tenor.com/v1/random?q={tag}&key={TENOR_API_KEY}&limit=1&contentfilter=off"
                async with aiohttp.ClientSession() as session:
                    async with session.get(tenor_url, timeout=10) as resp:
                        if resp.status == 200:
                            data_resp = await resp.json()
                            # tenor v1 format
                            if data_resp.get("results"):
                                res = data_resp["results"][0]
                                gif_url = None
                                # try different possible paths
                                if res.get("media") and isinstance(res["media"], list) and res["media"][0].get("gif"):
                                    gif_url = res["media"][0]["gif"].get("url")
                                if not gif_url and res.get("media_formats") and res["media_formats"].get("gif"):
                                    gif_url = res["media_formats"]["gif"].get("url")
                                if not gif_url and res.get("media") and res["media"][0].get("nanogif"):
                                    gif_url = res["media"][0]["nanogif"].get("url")
                                if gif_url and gif_url not in rejected:
                                    async with session.get(gif_url, timeout=10) as gr:
                                        if gr.status == 200:
                                            gif_bytes = await gr.read()
                                            name = f"tenor_{hashlib.sha1(gif_url.encode()).hexdigest()[:6]}.gif"
                                            return gif_bytes, name, gif_url
                                # if rejected, continue loop and try again
            except Exception as e:
                logger.debug(f"Tenor attempt failed: {e}")

        # Fallback to Giphy
        if GIPHY_API_KEY:
            try:
                giphy_url = f"https://api.giphy.com/v1/gifs/random?api_key={GIPHY_API_KEY}&tag={tag}&rating={GIPHY_RATING}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(giphy_url, timeout=10) as resp:
                        if resp.status == 200:
                            obj = await resp.json()
                            gif_url = obj.get("data", {}).get("images", {}).get("original", {}).get("url")
                            if gif_url and gif_url not in rejected:
                                async with session.get(gif_url, timeout=10) as gr:
                                    if gr.status == 200:
                                        gif_bytes = await gr.read()
                                        name = f"giphy_{hashlib.sha1(gif_url.encode()).hexdigest()[:6]}.gif"
                                        return gif_bytes, name, gif_url
            except Exception as e:
                logger.debug(f"Giphy attempt failed: {e}")

        # if we reach here, try next attempt (different tag)
    # final fallback
    return None, None, None

# -------------------------
# EMBED BUILDER
# -------------------------
def make_embed(title, desc, member, kind="join", count=None):
    color = discord.Color.pink() if kind == "join" else discord.Color.dark_grey()
    embed = discord.Embed(
        title=title,
        description=desc,
        color=color,
        timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
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
# REACTION HANDLER (OWNER ONLY)
# -------------------------
@bot.event
async def on_reaction_add(reaction, user):
    """
    Owner can react with ✅ to approve (no-op) or ❌ to reject (never use again).
    Only reactions in VC_CHANNEL_ID on bot messages are considered.
    """
    try:
        message = reaction.message
        if message.author != bot.user:
            return
        if message.channel.id != VC_CHANNEL_ID:
            return

        guild = message.guild
        if not guild:
            return

        owner_id = guild.owner_id
        # only owner reactions matter
        if user.id != owner_id:
            # remove reactions from non-owners to keep it clear
            try:
                await message.remove_reaction(reaction.emoji, user)
            except Exception:
                pass
            return

        emoji = str(reaction.emoji)
        guild_key = str(guild.id)
        msg_key = str(message.id)
        # find gif_url associated with this message (if any)
        message_map = data.get("message_gif_map", {}).get(guild_key, {})
        gif_url = message_map.get(msg_key)

        if not gif_url:
            # nothing to do
            return

        if emoji == "❌" or emoji == "✖️":
            # add to rejected for this guild
            rejected = data.setdefault("rejected_gifs", {}).setdefault(guild_key, [])
            if gif_url not in rejected:
                rejected.append(gif_url)
                save_data()
            # optionally edit message footer to indicate rejected (non-intrusive)
            try:
                new_embed = message.embeds[0]
                # append small note to description
                desc = new_embed.description or ""
                if "\n\n**Owner:** Rejected" not in desc:
                    new_desc = desc + "\n\n**Owner:** Rejected (will not be used again)"
                    # create a copy and edit
                    edited = discord.Embed.from_dict(new_embed.to_dict())
                    edited.description = new_desc
                    await message.edit(embed=edited)
            except Exception:
                pass

            # remove mapping for this message (we won't use it again)
            try:
                data["message_gif_map"].get(guild_key, {}).pop(msg_key, None)
                save_data()
            except Exception:
                pass

        elif emoji == "✅" or emoji == "✔️":
            # approve = do nothing but mark that owner approved this message (optional)
            try:
                new_embed = message.embeds[0]
                desc = new_embed.description or ""
                if "\n\n**Owner:** Approved" not in desc:
                    new_desc = desc + "\n\n**Owner:** Approved"
                    edited = discord.Embed.from_dict(new_embed.to_dict())
                    edited.description = new_desc
                    await message.edit(embed=edited)
            except Exception:
                pass

            # clear mapping for cleanliness
            try:
                data["message_gif_map"].get(guild_key, {}).pop(msg_key, None)
                save_data()
            except Exception:
                pass

    except Exception as e:
        logger.debug(f"on_reaction_add error: {e}")

# -------------------------
# VOICE STATE UPDATE (MULTI VC)
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
        save_data()

        embed = make_embed("Welcome!", msg, member, "join", data["join_counts"][str(member.id)])

        gif_bytes, gif_name, gif_url = await fetch_gif(guild.id)
        if gif_bytes:
            try:
                # server file
                file_server = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                embed.set_image(url=f"attachment://{gif_name}")
                if text_channel:
                    sent = await text_channel.send(embed=embed, file=file_server)
                else:
                    sent = None

                # store message->gif_url mapping so owner can react later
                try:
                    if sent and gif_url:
                        gid = str(guild.id)
                        data.setdefault("message_gif_map", {}).setdefault(gid, {})[str(sent.id)] = gif_url
                        save_data()
                    # add reactions for owner to choose (only useful if gif present)
                    if sent:
                        # WAIT a moment to ensure Discord has processed the message before reacting
                        await asyncio.sleep(1)
                        for emoji in ("✅", "❌"):
                            try:
                                await sent.add_reaction(emoji)
                            except Exception as e:
                                logger.debug(f"Failed to add reaction {emoji} to message {sent.id}: {e}")
                except Exception:
                    pass

                # recreate file for DM (avoid stream reuse)
                try:
                    file_dm = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                    await member.send(embed=embed, file=file_dm)
                except Exception:
                    # fallback: DM embed with clickable URL if file send fails (e.g., size/permissions)
                    try:
                        embed_dm = make_embed("Welcome!", msg, member, "join", data["join_counts"][str(member.id)])
                        if gif_url:
                            embed_dm.description += f"\n[View GIF here]({gif_url})"
                        await member.send(embed=embed_dm)
                    except Exception:
                        logger.warning(f"Failed to DM {member.display_name}")
            except Exception as e:
                logger.warning(f"Failed to send server join file: {e}")
                if text_channel:
                    try:
                        sent = await text_channel.send(embed=embed)
                    except Exception:
                        sent = None
                try:
                    await member.send(embed=embed)
                except Exception:
                    logger.warning(f"Failed to DM {member.display_name}")
        else:
            if text_channel:
                try:
                    sent = await text_channel.send(embed=embed)
                except Exception:
                    sent = None
            try:
                await member.send(embed=embed)
            except Exception:
                logger.warning(f"Failed to DM {member.display_name}")

    # ----- USER LEAVE -----
    if before.channel and before.channel.id in VC_IDS and (after.channel != before.channel):
        raw_msg = random.choice(LEAVE_GREETINGS)
        msg = raw_msg.format(display_name=member.display_name)
        embed = make_embed("Goodbye!", msg, member, "leave")

        gif_bytes, gif_name, gif_url = await fetch_gif(guild.id)
        if gif_bytes:
            try:
                file_server = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                embed.set_image(url=f"attachment://{gif_name}")
                if text_channel:
                    sent = await text_channel.send(embed=embed, file=file_server)
                else:
                    sent = None

                # store mapping for owner reaction
                try:
                    if sent and gif_url:
                        gid = str(guild.id)
                        data.setdefault("message_gif_map", {}).setdefault(gid, {})[str(sent.id)] = gif_url
                        save_data()
                    if sent:
                        # WAIT a moment to ensure Discord has processed the message before reacting
                        await asyncio.sleep(1)
                        for emoji in ("✅", "❌"):
                            try:
                                await sent.add_reaction(emoji)
                            except Exception as e:
                                logger.debug(f"Failed to add reaction {emoji} to message {sent.id}: {e}")
                except Exception:
                    pass

                # recreate file for DM
                try:
                    file_dm = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                    await member.send(embed=embed, file=file_dm)
                except Exception:
                    try:
                        embed_dm = make_embed("Goodbye!", msg, member, "leave")
                        if gif_url:
                            embed_dm.description += f"\n[View GIF here]({gif_url})"
                        await member.send(embed=embed_dm)
                    except Exception:
                        logger.warning(f"Failed to DM {member.display_name}")
            except Exception as e:
                logger.warning(f"Failed to send server leave file: {e}")
                if text_channel:
                    try:
                        await text_channel.send(embed=embed)
                    except Exception:
                        pass
                try:
                    await member.send(embed=embed)
                except Exception:
                    logger.warning(f"Failed to DM {member.display_name}")
        else:
            if text_channel:
                try:
                    await text_channel.send(embed=embed)
                except Exception:
                    pass
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
