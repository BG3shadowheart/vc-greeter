# bot.py — Optimized Anime Welcome Bot (NSFW | Tenor + Giphy | Multi-VC | No Server Mention)
# FULL SCRIPT — copy & paste as-is

import os
import io
import json
import random
import hashlib
import logging
import asyncio
from datetime import datetime
from urllib.parse import quote_plus

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
MAX_USED_GIFS_PER_USER = 500  # keep history bounded to avoid unbounded data growth

# -------------------------
# GIF TAGS (combined: your requested + optimized)
# -------------------------
GIF_TAGS = [
    "anime sexy","anime waifu","hentai","anime ecchi","anime boobs",
    "anime ass","anime milf","anime girl","anime girl ecchi",
    "genshin impact waifu","game waifu","anime hot girl","anime seductive",
    "anime suggestive","ecchi anime girl","anime fanservice","anime ero",
    "waifu ecchi","anime blush ecchi","ecchi fighting anime","anime swimsuit ecchi",
    "anime thick","anime oppai","anime jiggle","anime thighs",
    "anime thick thighs","anime booty","anime booty shorts","anime lingerie girl",
    "anime bikini girl","anime teasing anime girl","anime mature woman","anime older waifu",
    "anime charm girl","anime flirty","anime sensual","anime blushing girl",
    # romantic / kiss / hug
    "anime kiss","anime couple kiss","anime romantic","romantic anime",
    "anime hug","cute anime hug","anime love","anime couple hug",
    # user requested explicit-ish tags (you asked)
    "sexy anime girl","horny anime","horny waifu","sexy milf anime",
    "anime milf horny","romantic hentai","ecchi kiss","ecchi hug"
]

# keep as you asked
GIPHY_RATING = "pg-13"
TENOR_CONTENT_FILTER = "medium"

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

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# DATA LOADING / AUTOSAVE
# -------------------------
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"join_counts": {}, "used_gifs": {}}, f)

with open(DATA_FILE, "r") as f:
    data = json.load(f)

# ensure the structure exists
if "join_counts" not in data:
    data["join_counts"] = {}
if "used_gifs" not in data:
    data["used_gifs"] = {}

@tasks.loop(seconds=AUTOSAVE_INTERVAL)
async def autosave_task():
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Autosave failed: {e}")

# -------------------------
# RANDOMIZED TAG GENERATOR (mixes 1-3 tags)
# -------------------------
def get_random_tag():
    # choose 1 to 3 tags and join them — ensures variety and mixed queries
    k = random.choices([1, 2, 3], weights=[60, 30, 10])[0]
    chosen = random.sample(GIF_TAGS, k)
    # join with spaces to form a natural search query
    return " ".join(chosen)

# -------------------------
# SAVE DATA UTIL
# -------------------------
def save_data():
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save data: {e}")

# -------------------------
# FETCH GIF (TENOR FIRST, FALLBACK GIPHY + NO-KEY BOORUS) - AVOID SENDING SAME GIF TO SAME USER
# -------------------------
async def fetch_gif(user_id):
    """
    Attempts to fetch a GIF not previously sent to `user_id`.
    Search order is randomized per call across providers:
      Tenor, Giphy, Danbooru, Konachan, Yande.re, Gelbooru, Rule34, OtakuGIFs
    All booru queries use rating:questionable and explicitly exclude illegal tags.
    Returns (gif_bytes, filename, gif_url) or (None, None, None).
    """
    user_key = str(user_id)
    used = data["used_gifs"].setdefault(user_key, [])

    # Extra booru-safe exclusion tags (never request these)
    EXCLUDE_TAGS = ["loli", "shota", "child", "minor", "underage", "young", "schoolgirl", "age_gap"]

    # helper to build booru tag string and url-encode it
    def build_booru_query(positive_tags):
        tags = ["rating:questionable"]
        # positive_tags is space-separated words; append them
        tags.extend(positive_tags.split())
        # add requires-exclude tags prefixed with '-'
        tags.extend([f"-{t}" for t in EXCLUDE_TAGS])
        tag_str = " ".join(tags)
        return tag_str, quote_plus(tag_str)

    # providers list (include Tenor/Giphy only if keys present)
    providers = []
    if TENOR_API_KEY:
        providers.append("tenor")
    if GIPHY_API_KEY:
        providers.append("giphy")
    # always include no-key boorus
    providers.extend(["danbooru", "konachan", "yandere", "gelbooru", "rule34", "otakugifs"])
    # shuffle provider order to ensure randomness per call
    random.shuffle(providers)

    async with aiohttp.ClientSession() as session:
        # We'll attempt each provider in the shuffled order; for each provider, use 1-2 randomized queries
        for provider in providers:
            # pick 1-2 different tags to try for this provider to avoid repeats
            tries_for_provider = 2
            for t_try in range(tries_for_provider):
                positive = get_random_tag()
                tag_str, tag_query = build_booru_query(positive)

                # ---------- TENOR (API key) -----------
                if provider == "tenor" and TENOR_API_KEY:
                    try:
                        tenor_q = quote_plus(positive)
                        tenor_url = f"https://g.tenor.com/v1/search?q={tenor_q}&key={TENOR_API_KEY}&limit=20&contentfilter=off"
                        async with session.get(tenor_url, timeout=10) as resp:
                            if resp.status == 200:
                                payload = await resp.json()
                                results = payload.get("results", [])
                                random.shuffle(results)
                                for result in results:
                                    gif_url = None
                                    media_formats = result.get("media_formats") or result.get("media")
                                    if isinstance(media_formats, dict):
                                        gif_entry = media_formats.get("gif")
                                        if gif_entry and gif_entry.get("url"):
                                            gif_url = gif_entry.get("url")
                                        # fallback to other gif-like fields
                                        for key in ("nanogif", "mediumgif", "tinygif"):
                                            if not gif_url and media_formats.get(key) and media_formats[key].get("url"):
                                                gif_url = media_formats[key].get("url")
                                    elif isinstance(media_formats, list) and len(media_formats) > 0:
                                        first = media_formats[0]
                                        if isinstance(first, dict):
                                            gif_entry = first.get("gif") or first.get("tinygif")
                                            if gif_entry and gif_entry.get("url"):
                                                gif_url = gif_entry.get("url")
                                    if not gif_url and result.get("itemurl"):
                                        gif_url = result.get("itemurl")

                                    if not gif_url:
                                        continue

                                    gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                                    if gif_hash in used:
                                        continue

                                    # attempt download
                                    try:
                                        async with session.get(gif_url, timeout=15) as gr:
                                            if gr.status == 200:
                                                b = await gr.read()
                                                ext = ".gif"
                                                ctype = gr.content_type or ""
                                                if ".webm" in gif_url or "webm" in ctype:
                                                    ext = ".webm"
                                                elif ".mp4" in gif_url or "mp4" in ctype:
                                                    ext = ".mp4"
                                                name = f"tenor_{gif_hash[:6]}{ext}"
                                                used.append(gif_hash)
                                                if len(used) > MAX_USED_GIFS_PER_USER:
                                                    del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                                save_data()
                                                return b, name, gif_url
                                    except Exception as e:
                                        logger.debug(f"Tenor download error: {e}")
                    except Exception as e:
                        logger.debug(f"Tenor search error: {e}")

                # ---------- GIPHY (API key) -----------
                if provider == "giphy" and GIPHY_API_KEY:
                    try:
                        giphy_q = quote_plus(positive)
                        giphy_url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={giphy_q}&limit=20&rating={GIPHY_RATING}"
                        async with session.get(giphy_url, timeout=10) as resp:
                            if resp.status == 200:
                                payload = await resp.json()
                                arr = payload.get("data", [])
                                random.shuffle(arr)
                                for item in arr:
                                    images = item.get("images", {})
                                    gif_url = None
                                    if images and images.get("original") and images["original"].get("url"):
                                        gif_url = images["original"].get("url")
                                    if not gif_url:
                                        continue
                                    gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                                    if gif_hash in used:
                                        continue
                                    try:
                                        async with session.get(gif_url, timeout=15) as gr:
                                            if gr.status == 200:
                                                b = await gr.read()
                                                ext = ".gif"
                                                ctype = gr.content_type or ""
                                                if ".mp4" in gif_url or "mp4" in ctype:
                                                    ext = ".mp4"
                                                elif "webm" in ctype or ".webm" in gif_url:
                                                    ext = ".webm"
                                                name = f"giphy_{gif_hash[:6]}{ext}"
                                                used.append(gif_hash)
                                                if len(used) > MAX_USED_GIFS_PER_USER:
                                                    del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                                save_data()
                                                return b, name, gif_url
                                    except Exception as e:
                                        logger.debug(f"Giphy download error: {e}")
                    except Exception as e:
                        logger.debug(f"Giphy search error: {e}")

                # ---------- BOORU FALLBACKS (no key required) -----------
                if provider in ("danbooru", "konachan", "yandere", "gelbooru", "rule34", "otakugifs"):
                    booru_endpoints_map = {
                        "danbooru": f"https://danbooru.donmai.us/posts.json?tags={tag_query}&limit=50",
                        "konachan": f"https://konachan.com/post.json?tags={tag_query}&limit=50",
                        "yandere": f"https://yande.re/post.json?tags={tag_query}&limit=50",
                        "gelbooru": f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&tags={tag_query}&limit=50",
                        "rule34": f"https://rule34.xxx/index.php?page=dapi&s=post&q=index&json=1&tags={tag_query}&limit=50",
                        "otakugifs": f"https://otakugifs.xyz/api/gif?reaction={quote_plus(positive)}"
                    }
                    url = booru_endpoints_map.get(provider)
                    if not url:
                        continue
                    try:
                        async with session.get(url, timeout=12) as resp:
                            if resp.status != 200:
                                continue
                            posts = await resp.json()
                            # normalize: some endpoints return dict with 'posts' key
                            if isinstance(posts, dict) and "posts" in posts:
                                posts = posts["posts"]
                            if not posts:
                                continue
                            random.shuffle(posts)
                            for post in posts:
                                # Many boorus provide 'file_url' or 'large_file_url' or 'image' etc.
                                gif_url = None
                                for fkey in ("file_url", "large_file_url", "image_url", "jpeg_url", "source", "file", "image", "url", "preview_url"):
                                    v = post.get(fkey)
                                    if v:
                                        gif_url = v
                                        break
                                if not gif_url:
                                    continue

                                # Defensive: ensure rating is not explicit
                                rating = post.get("rating") or post.get("rating")
                                if isinstance(rating, str):
                                    if rating.lower().startswith("e"):  # explicit -> skip
                                        continue
                                # Skip items whose tag strings explicitly include 'rating:explicit' or explicit marker
                                tags_field = ""
                                if isinstance(post.get("tag_string"), str):
                                    tags_field = post.get("tag_string")
                                if isinstance(post.get("tags"), str) and not tags_field:
                                    tags_field = post.get("tags")
                                if "rating:explicit" in (tags_field or ""):
                                    continue
                                # Ensure blacklist not in tags
                                if any(ex in (tags_field or "") for ex in EXCLUDE_TAGS):
                                    continue

                                # avoid duplicates
                                gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                                if gif_hash in used:
                                    continue

                                # try download
                                try:
                                    async with session.get(gif_url, timeout=15) as gr:
                                        if gr.status == 200:
                                            b = await gr.read()
                                            ctype = gr.content_type or ""
                                            ext = ".gif"
                                            if ".webm" in gif_url or "webm" in ctype:
                                                ext = ".webm"
                                            elif ".mp4" in gif_url or "mp4" in ctype:
                                                ext = ".mp4"
                                            elif ".png" in gif_url or "png" in ctype:
                                                ext = ".png"
                                            elif ".jpg" in gif_url or "jpeg" in gif_url or "jpeg" in ctype:
                                                ext = ".jpg"
                                            name = f"{provider.lower()}_{gif_hash[:6]}{ext}"
                                            used.append(gif_hash)
                                            if len(used) > MAX_USED_GIFS_PER_USER:
                                                del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                            save_data()
                                            return b, name, gif_url
                                except Exception as e:
                                    logger.debug(f"{provider} media download error: {e}")
                    except Exception as e:
                        logger.debug(f"{provider} query error: {e}")

        # if here, no provider produced a fresh gif for this user this call
    # nothing found
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
    try:
        embed.set_thumbnail(url=member.display_avatar.url)
    except Exception:
        pass
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
        try:
            with open(DATA_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save data: {e}")

        embed = make_embed("Welcome!", msg, member, "join", data["join_counts"][str(member.id)])

        # PASS user id to fetch_gif to avoid duplicates per user
        gif_bytes, gif_name, gif_url = await fetch_gif(member.id)
        if gif_bytes:
            try:
                # server file
                file_server = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                embed.set_image(url=f"attachment://{gif_name}")
                if text_channel:
                    # NO server mention — embed + GIF only
                    await text_channel.send(embed=embed, file=file_server)

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

    # ----- USER LEAVE -----
    if before.channel and before.channel.id in VC_IDS and (after.channel != before.channel):
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
