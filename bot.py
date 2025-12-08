# bot.py — Optimized Anime Welcome Bot (NSFW | Custom Messages | No GIF Duplication Limit)

import os, io, json, asyncio, random, hashlib, logging
from datetime import datetime
import aiohttp
import discord
from discord.ext import commands, tasks

# -------------------------
# CONFIG
# -------------------------
TOKEN = os.getenv("TOKEN")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")

VC_ID = 1353875050809524267
VC_CHANNEL_ID = 1446752109151260792   # ✅ GREETING CHANNEL

DATA_FILE = "data.json"
AUTOSAVE_INTERVAL = 30

# ✅ STRICT HENTAI / ANIME-ART ONLY
GIPHY_ALLOWED_TAGS = [
    "anime sexy",
    "anime waifu",
    "hentai",
    "anime ecchi",
    "anime boobs",
    "anime ass",
    "anime milf",
    "anime girl",
    "hentai anime",
    "anime girl ecchi",
    "genshin impact anime",
    "gaming anime girl",
    "anime fighting scene",
    "anime battle",

    # ✅ More hentai / anime-art related tags added
    "hentai anime art",
    "anime hentai",
    "anime ecchi hentai",
    "nsfw anime art",
    "hentai waifu",
    "hentai anime girl",
    "anime hentai gif",
    "2d hentai animation",
    "anime nsfw gif",
    "ecchi anime girl",
    "anime fanservice",
    "anime lewd",
    "anime ero",
    "waifu ecchi",
    "hentai 2d animation",
    "anime blush ecchi",
    "anime seductive",
    "anime suggestive",
    "ecchi fighting anime",
    "lewd anime girl",
    "anime swimsuit ecchi"
]
GIPHY_RATING = "r"

# -------------------------
# LOGGING
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("anime-bot")

# -------------------------
# ✅ JOIN GREETINGS (100+)
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
# BOT SETUP
# -------------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

data = {
    "join_counts": {}
}

# -------------------------
# AUTO SAVE
# -------------------------
@tasks.loop(seconds=AUTOSAVE_INTERVAL)
async def autosave_task():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# -------------------------
# NSFW HENTAI GIF FETCH
# -------------------------
async def fetch_giphy():
    tag = random.choice(GIPHY_ALLOWED_TAGS)
    url = f"https://api.giphy.com/v1/gifs/random?api_key={GIPHY_API_KEY}&tag={tag}&rating={GIPHY_RATING}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            obj = await resp.json()
            gif_url = obj["data"]["images"]["original"]["url"]

            async with session.get(gif_url) as r:
                gif_bytes = await r.read()
                name = f"gif_{hashlib.sha1(gif_url.encode()).hexdigest()[:6]}.gif"
                return gif_bytes, name

# -------------------------
# EMBED
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
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data.update(json.load(f))

    autosave_task.start()
    print(f"✅ Logged in as {bot.user}")

# -------------------------
# VOICE EVENTS
# -------------------------
@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    guild = member.guild
    target_vc = guild.get_channel(VC_ID)
    text_channel = bot.get_channel(VC_CHANNEL_ID)
    vc = guild.voice_client

    # ✅ USER JOIN
    if before.channel is None and after.channel == target_vc:
        if not vc:
            await target_vc.connect()

        raw_msg = random.choice(JOIN_GREETINGS)
        msg = raw_msg.format(display_name=member.display_name)

        data["join_counts"][str(member.id)] = data["join_counts"].get(str(member.id), 0) + 1

        embed = make_embed("Welcome!", msg, member, "join", data["join_counts"][str(member.id)])

        gif_bytes, gif_name = await fetch_giphy()
        file = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
        embed.set_image(url=f"attachment://{gif_name}")

        if text_channel:
            await text_channel.send(content=member.mention, embed=embed, file=file)

        try:
            await member.send(embed=embed, file=file)
        except:
            pass

    # ✅ USER LEAVE
    if before.channel == target_vc and after.channel != target_vc:
        raw_msg = random.choice(LEAVE_GREETINGS)
        msg = raw_msg.format(display_name=member.display_name)

        embed = make_embed("Goodbye!", msg, member, "leave")

        gif_bytes, gif_name = await fetch_giphy()
        file = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
        embed.set_image(url=f"attachment://{gif_name}")

        if text_channel:
            await text_channel.send(content=member.mention, embed=embed, file=file)

        try:
            await member.send(embed=embed, file=file)
        except:
            pass

        if vc and len([m for m in vc.channel.members if not m.bot]) == 0:
            await vc.disconnect()

# -------------------------
# START BOT
# -------------------------
bot.run(TOKEN)
