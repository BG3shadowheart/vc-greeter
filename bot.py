# bot_revised.py
# Revised: boosted safe providers + hard/soft nudity filter (Option A)
# Usage:
#   export TOKEN="your_discord_bot_token"
#   export TENOR_API_KEY="..."   # optional
#   export GIPHY_API_KEY="..."   # optional
# Then run: python bot_revised.py

import os
import io
import json
import random
import hashlib
import logging
import asyncio
import re
from datetime import datetime
from urllib.parse import quote_plus
import aiohttp
import discord
from discord.ext import commands, tasks

# -------------------------
# CONFIG - set these as env vars before running
# -------------------------
TOKEN = os.getenv("TOKEN")
TENOR_API_KEY = os.getenv("TENOR_API_KEY")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")
DEBUG_FETCH = os.getenv("DEBUG_FETCH", "") != ""

# MULTIPLE VCs (kept same as your uploaded file)
VC_IDS = [
    1353875050809524267,
    21409170559337762980,
    1353875404217253909,
    1353882705246556220
]

# TEXT CHANNEL TO POST EMBEDS (kept same)
VC_CHANNEL_ID = 1446752109151260792

DATA_FILE = "data.json"
AUTOSAVE_INTERVAL = 30
MAX_USED_GIFS_PER_USER = 1000
FETCH_ATTEMPTS = 40   # attempts to find a gif

# -------------------------
# GIF TAGS (kept large & spicy as you had)
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
    "anime kiss","anime couple kiss","anime romantic","romantic anime",
    "anime hug","cute anime hug","anime love","anime couple hug",
    "sexy anime girl","horny anime","horny waifu","sexy milf anime",
    "anime milf horny","romantic hentai","ecchi kiss","ecchi hug",
    "anime cleavage","anime cosplay sexy","anime playful pose","anime seductive glance",
    "anime softcore","anime teasing pose","anime thighfocus","anime chest focus"
]

# -------------------------
# RATING / FILTER SETTINGS
# -------------------------
BOORU_TARGET_RATING = "questionable"
GIPHY_RATING = "pg-13"
TENOR_CONTENT_FILTER = "medium"

# -------------------------
# PROVIDER CATEGORIES
# -------------------------
# These are treated as "safe-sexy" providers: we BOOST them and DO NOT run the nudity scan.
# They produce suggestive/sexy GIFs but are not generally explicit porn.
SAFE_NO_SCAN_PROVIDERS = {"waifu_pics", "nekos_best", "nekos_life", "otakugifs"}

# Booru family (contains explicit content sometimes) - will be scanned
BOORU_ENDPOINT_TEMPLATES = {
    "danbooru": [
        "https://danbooru.donmai.us/posts.json?tags={tag_query}&limit=50",
        "https://danbooru.donmai.us/posts.json?tags={tag_query}&limit=100"
    ],
    "konachan": [
        "https://konachan.com/post.json?tags={tag_query}&limit=50",
        "https://konachan.net/post.json?tags={tag_query}&limit=50"
    ],
    "yandere": [
        "https://yande.re/post.json?tags={tag_query}&limit=50"
    ],
    "gelbooru": [
        "https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&tags={tag_query}&limit=50"
    ],
    "safebooru": [
        "https://safebooru.org/index.php?page=dapi&s=post&q=index&json=1&tags={tag_query}&limit=50"
    ],
    "xbooru": [
        "https://xbooru.com/index.php?page=dapi&s=post&q=index&json=1&tags={tag_query}&limit=50"
    ],
    "tbib": [
        "https://tbib.org/index.php?page=dapi&s=post&q=index&json=1&tags={tag_query}&limit=50"
    ],
    "rule34": [
        "https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&limit=50&tags={tag_query}&json=1",
        "https://rule34.xxx/index.php?page=dapi&s=post&q=index&limit=50&tags={tag_query}&json=1"
    ]
}

SIMPLE_APIS = {
    "waifu_pics": {
        "base": "https://api.waifu.pics",
        "categories_sfw": ["waifu","neko","shinobu","husbando","kiss","hug","slap","pat"],
        "categories_nsfw": ["waifu","neko","trap","blowjob"]
    },
    "nekos_best": {
        "base": "https://nekos.best/api/v2",
        "categories": ["hug","kiss","pat","cuddle","dance","poke","slap","neko"]
    },
    "nekos_life": {
        "base": "https://nekos.life/api/v2/img",
        "categories": ["ngif","neko","kiss","hug","cuddle","pat","wink","slap"]
    }
}

# -------------------------
# Hard & Soft tag lists (Option A)
# Hard = immediate block (1 match)
# Soft = block only if 3+ matches
# -------------------------
HARD_TAGS = [
    "pussy","vagina","labia","clitoris",
    "penis","cock","dick","shaft","testicles","balls",
    "anus",
    "sex","penetration","penetrating","penetrated",
    "blowjob","deepthroat","oral","fellatio","handjob",
    "cum","cumshot","ejac","orgasm","masturbation",
    "titty fuck","facefuck","facesitting",
    "anal sex","doggystyle","cowgirl","69","threesome","foursome",
    "group sex","orgy","gangbang","double penetration","dp",
    "creampie","facial",
    "explicit","xxx","nsfw_high","hentai explicit",
    "uncensored","porn","pornography","sex toy","strapon",
    "bestiality","scat","watersports","fisting",
    # remove sexual orientation words that are harmless; keep anatomy/acts
]

SOFT_TAGS = [
    "nude","naked","topless","bottomless",
    "nipples","areola","lingerie",
    "erotic","ecchi","sensual","lewd","teasing",
    "big boobs","boobs","oppai","busty","huge breasts",
    "ass","booty","thick thighs","thick","jiggle",
    "milf","mommy","seductive","sexy","fanservice",
    "cleavage","swimsuit","bikini","underwear","cosplay"
]

# normalize helper
def _normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r'[\s\-_]+', ' ', s)
    return s

def analyze_nudity_indicators(text: str):
    """
    Returns (hard_found:bool, soft_count:int)
    - hard_found True means immediate block
    - soft_count is number of soft tag matches
    """
    if not text or not isinstance(text, str):
        return False, 0
    normalized = _normalize_text(text)

    # HARD check
    for h in HARD_TAGS:
        if h in normalized:
            return True, 0

    # SOFT count
    soft_count = 0
    for s in SOFT_TAGS:
        if s in normalized:
            soft_count += 1

    return False, soft_count

def contains_nude_indicators(text: str) -> bool:
    """
    Implement Option A:
    - If any HARD tag found -> block
    - If soft_count >= 3 -> block
    - Otherwise allow
    """
    hard, soft_count = analyze_nudity_indicators(text)
    if hard:
        return True
    if soft_count >= 3:
        return True
    return False

# -------------------------
# Exclude list for illegal/underage tags (always exclude from booru queries)
# -------------------------
EXCLUDE_TAGS = ["loli","shota","child","minor","underage","young","schoolgirl","age_gap"]

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("anime-welcome-bot")

# -------------------------
# JOIN & LEAVE GREETINGS (copied / preserved)
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
    # extended flirty
    "🔥 {display_name} glides in like a slow-burning spoiler — and suddenly everyone's night has a plot twist.",
    "😉 Well, hello trouble — {display_name} decided to show up.",
    "😏 Someone call the spotlight — {display_name} just entered the scene.",
    "💋 Oh? {display_name} is here. Someone's feeling dangerous.",
    "😈 Alert: {display_name} entered. Expect mischief and charm.",
    "🍸 {display_name} arrived — drinks, drama, and delightful chaos.",
    "🌶️ Spice level rising… {display_name} just joined.",
    "🖤 {display_name} strolled in like they owe the world an apology.",
    "💫 The plot thickens now that {display_name} has appeared.",
    "🎲 Risky move: {display_name} showed up and we're all losing our cool.",
    "🕶️ Bold entrance by {display_name}. Attitude: 100.",
    "🎯 Target acquired — {display_name} is on the scene.",
    "🌙 Midnight mischief incoming because {display_name} is here.",
    "✨ If charisma were a crime, {display_name} would be serving life.",
    "🍷 Classy and a little dangerous — {display_name} has arrived.",
    "🖤 {display_name} just lowered the tone of the room in the best way.",
    "🎭 Drama upgrade: starring {display_name} in tonight's chaos.",
    "🔥 Someone turn on the fan — {display_name} brought the heat.",
    "💼 {display_name} walked in and instantly made everything complicated.",
    "🎧 Soundtrack change — {display_name} just dropped the bass.",
    "🪄 Magic? No — just {display_name} doing their thing.",
    "🍒 Sweet with a hint of trouble — hello {display_name}.",
    "⚡ Quick warning: {display_name} energizes bad ideas.",
    "🦊 Sly and irresistible — {display_name} joins the party.",
    "🌹 Roses are cliché, but {display_name} is not — welcome.",
    "📸 Pose for the chaos — {display_name} has arrived.",
    "🚀 {display_name} entered and launched everyone's expectations.",
    "💥 Subtlety left the building when {display_name} walked in.",
    "🪩 Glitter and wrong decisions — thanks for coming, {display_name}.",
    "🩶 Dark charm alert: {display_name} stepped in.",
    "💃 Someone set the music — {display_name} is ready to stir things up.",
    "🔮 I can't predict the future, but {display_name} usually means late-night plans.",
    "🍯 Sweet talker spotted — {display_name} has joined.",
    "🪤 You walked into temptation — hi {display_name}.",
    "🎟️ VIP access granted — {display_name} showed up fashionably late.",
    "🗝️ Keys to chaos delivered by {display_name}.",
    "🦋 Flirtation levels rising — {display_name} is in the room.",
    "💡 Bright idea: follow {display_name} at your own risk.",
    "📚 There goes the plot twist — {display_name} arrived.",
    "🌊 Tides turned — {display_name} just made waves.",
    "🧊 Cold look, hot entrance — {display_name} is here.",
    "🕯️ Candlelit mischief begins now that {display_name} joined.",
    "🎰 All bets on {display_name} — and the odds are deliciously skewed.",
    "🍓 {display_name} rolled in and suddenly dessert is mandatory.",
    "📯 Sound the horn — {display_name} is in the building.",
    "🧭 Lost? No — just following {display_name}'s magnetic pull.",
    "🌪️ Chaos tasteful enough to be art — thanks {display_name}.",
    "🛋️ Softer than a threat: welcome {display_name}.",
    "🧨 Short fuse, big effect — {display_name} is here.",
    "🎈 Innocent smile, guilty intentions — hi {display_name}.",
    "💼 Corporate mischief courtesy of {display_name}.",
    "🪞Mirror check: yep, {display_name} still looks like trouble.",
    "🍬 Sweet façade, sticky consequences — welcome, {display_name}.",
    "🏮 Lanterns flicker — {display_name} lights up the night.",
    "🎤 Mic dropped — {display_name} doesn't need to say a thing.",
    "🪩 Your entrance made the playlist skip — thank you {display_name}.",
    "🦄 Rare and slightly scandalous — {display_name} appears.",
    "🕶️ Cool glare detected. {display_name} just arrived.",
    "🍾 Pop the cork — {display_name} deserves the celebration.",
    "🛡️ Charming enough to disarm — {display_name} walks in.",
    "💃 The room got rhythm when {display_name} took a step.",
    "🧩 Missing piece found: {display_name} completes the puzzle.",
    "🌈 Colorful trouble has arrived — hey {display_name}.",
    "🪙 Heads up: {display_name} flips expectations and pockets secrets.",
    "🖋️ Signature entrance — {display_name} signs in with flair.",
    "🎯 You came, you saw, you slayed — welcome {display_name}.",
    "🍷 Velvet tone and sharp edges — that's {display_name}.",
    "🔞 Mature vibes only — {display_name} enters the room.",
    "🕯️ Soft light, sharper intentions — hello {display_name}.",
    "🏷️ Tagged: irresistible. {display_name} checks in.",
    "🎩 Classy with attitude — {display_name} tips the hat.",
    "🫦 Lips sealed, eyes loud — {display_name} is here.",
    "📅 Tonight's agenda: {display_name} causes a scene.",
    "🛋️ Stay seated — {display_name} prefers to steal the show.",
    "🧨 Quiet before the fun — {display_name} just arrived.",
    "🔗 Chains optional, charm mandatory — welcome {display_name}.",
    "🌀 Dizzying presence detected — {display_name} joins.",
    "💼 Work hard, tease harder — {display_name} is in the VC.",
    "🌒 Shadows lengthen when {display_name} shows up.",
    "🥀 Pretty and a little poisonous — hi {display_name}.",
    "📯 Announce the mischief — {display_name} has entered.",
    "🔥 Slow burn starter: {display_name} has arrived.",
    "🦩 Graceful and dangerous — welcome, {display_name}.",
    "💬 Conversation killer: {display_name} just logged on.",
    "🎀 Cute on purpose, trouble by accident — thanks for coming {display_name}.",
    "🪬 Lucky strike — {display_name} brings the kind of luck you whisper about.",
    "🌶️ Too hot to handle, too fun to deny — {display_name} joined.",
    "🧸 Soft voice, sharp looks — say hello to {display_name}.",
    "🎲 Double or nothing — {display_name} is ready to play.",
    "🗝️ Unlocking curiosity: {display_name} has arrived.",
    "🥂 Raise a glass — {display_name} showed up and the night's improved.",
    "🕹️ Someone hit the turbo — {display_name} entered the lobby.",
    "🪓 Cute smile, dangerous plans — welcome {display_name}.",
    "📸 Snap. Scene. {display_name} just made the highlight reel.",
    "🔮 Fate called and said: meet {display_name}.",
    "🪩 Enter with rhythm — {display_name} is here to shake things up."
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
    "🌒 Fade to black — {display_name} left.",
    # extended flirty leave lines
    "💋 {display_name} slipped away — and the room exhaled with regret.",
    "😈 Gone already? {display_name} leaves a better mess than most create.",
    "🖤 {display_name} left the stage — manners optional, memories guaranteed.",
    "🍃 {display_name} faded like smoke; seductive and impossible to hold.",
    "🔐 Door closed. {display_name} stole the moment and the key.",
    "🎭 Curtain call for {display_name} — encore not included.",
    "🥀 {display_name} left; perfection and trouble went with them.",
    "🍷 {display_name} departed — someone pour a little regret.",
    "🕯️ The lights dim when {display_name} steps away.",
    "⚡ {display_name} left a spark and a small disaster.",
    "🍬 Sweet exit, bitter aftertaste — bye {display_name}.",
    "🪩 The party lost its playlist when {display_name} left.",
    "🕶️ {display_name} ghosted with style — classy and cold.",
    "🔮 {display_name} vanished like a prediction you loved anyway.",
    "💼 {display_name} logged off and took the drama with them.",
    "🌙 Night swooped in after {display_name} left the room.",
    "🎯 {display_name} left — aim: flawless. Impact: unforgettable.",
    "🦊 Sly departure from {display_name}; the mystery deepens.",
    "🍓 {display_name} drifted away leaving sticky memories.",
    "🛋️ {display_name} retired to the shadows — the couch remembers.",
    "🧨 Exit with a bang — {display_name} didn't leave quietly.",
    "🦋 {display_name} flew off; everyone still smells the chaos.",
    "🎲 {display_name} left the table and the stakes rose higher.",
    "🍾 {display_name} popped out — classy exit, dramatic effect.",
    "🗝️ {display_name} closed the door on trouble and goodbyes.",
    "🩶 The room lost its edge when {display_name} left.",
    "📯 Announce: {display_name} has departed — rumors welcomed.",
    "🌹 {display_name}'s exit felt like a rose dropped in slow motion.",
    "🧭 {display_name} walked away and left a trail we all want to follow.",
    "🪞 Reflection left the mirror — {display_name} is gone.",
    "🪤 The trapdoor opened; {display_name} vanished with a wink.",
    "🔞 Mature exit: {display_name} left the scene while raising eyebrows.",
    "🕯️ {display_name} departed — the candle still flickers from their touch.",
    "🥂 Cheers to {display_name} — left us smiling and slightly guilty.",
    "📸 {display_name} left the frame; the photo's still hot.",
    "🧩 {display_name} removed themselves and somehow completed the puzzle.",
    "🌪️ A quiet storm left with {display_name}.",
    "🎩 {display_name} tipped their hat and walked away like a plot twist.",
    "🍷 The bottle's emptier now that {display_name} is gone.",
    "🦉 Night feels smarter when {display_name} takes off.",
    "🌊 {display_name} drifted out; the tide kept the memory.",
    "🪬 Luck shifted when {display_name} left the room.",
    "🛡️ Protector gone — {display_name} exits with dangerous grace.",
    "🔗 {display_name} unlinked themselves and left us all a little looser.",
    "📚 The chapter ended when {display_name} left; we read it twice.",
    "🧠 Clever exit — {display_name} left us thinking about bad decisions.",
    "🎭 Stage empty; {display_name} took the spotlight with them.",
    "🍒 Leaving like a sin dressed as dessert — bye {display_name}.",
    "🪁 {display_name} drifted away, playful and untouchable.",
    "🗡️ Sharp goodbye — {display_name} left with teeth and style.",
    "🎶 The last note faded when {display_name} stepped away.",
    "🪙 {display_name} vanished with a trick up their sleeve.",
    "🦄 {display_name} left; the rare air still hums.",
    "🕊️ {display_name} flew off and left a few hearts unsettled.",
    "✨ Exit stage left: {display_name} made it dramatic as always.",
    "🍂 {display_name} fell away like a leaf—beautiful and brief.",
    "🧸 {display_name} walked out smiling; the room feels oddly betrayed.",
    "💥 {display_name} left like fireworks — loud and unforgettable.",
    "🍭 {display_name} left a sweet mess on the floor.",
    "🕯️ Flicker gone: {display_name} departed and the glow lingered.",
    "🔔 {display_name} rang out and then vanished into the night.",
    "🦩 Stylish exit by {display_name} — elegant with a sting.",
    "📀 The record scratched when {display_name} took their leave.",
    "🪓 A clean cut goodbye — {display_name} left the scene.",
    "🌈 {display_name} left a streak of color and trouble.",
    "🏮 Lanterns dimmed as {display_name} disappeared down the lane.",
    "🎤 Microphone dropped; {display_name} departed without an encore.",
    "🥀 {display_name} left; the bouquet still smells like risk.",
    "🪞 Mirror emptied — {display_name} is nowhere to be found.",
    "🪩 The last dancer left: {display_name}. The floor misses them.",
    "🕶️ {display_name} slipped away wearing an attitude and sunglasses.",
    "🧭 Direction lost when {display_name} turned away and walked off.",
    "🎯 Closing target: {display_name} left, aim impeccable.",
    "📅 Calendar note: {display_name} left and the night shifted tone.",
    "🧪 {display_name} conducted an experiment and then quietly exited.",
    "🔮 {display_name} left like a prophecy fulfilled—mysterious and satisfying.",
    "🪬 The charm left with {display_name}; good luck tries to follow.",
    "🔞 {display_name} left—no kids allowed in the memory lane.",
    "🍷 {display_name} left and the glass still tastes like their name.",
    "🪣 Clean exit: {display_name} wiped the slate and left an impression.",
    "🎲 {display_name} rolled away and the dice keep whispering.",
    "🗝️ {display_name} took the secret and left us grinning.",
    "📸 Photo fades when {display_name} leaves, but the smile remains.",
    "🧨 {display_name} walked off—residue of excitement remains.",
    "🥂 {display_name} toasted the room with their exit.",
    "🦊 Cunning goodbye—{display_name} left and the foxes cheered.",
    "🔗 Links broken; {display_name} left the chain of events unfinished.",
    "🛞 Wheels stop — {display_name} is gone but the ride lingers.",
    "🕯️ The flame dipped as {display_name} stepped into the dark.",
    "🧩 {display_name} left and the pieces still fit a little wrong after.",
    "🎀 {display_name} untied the bow and disappeared into trouble."
]

# -------------------------
# Bot Setup
# -------------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# Data load / autosave
# -------------------------
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"join_counts": {}, "used_gifs": {}}, f)

with open(DATA_FILE, "r") as f:
    data = json.load(f)

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

def save_data():
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save data: {e}")

# -------------------------
# Helper: choose provider pool with boosting
# Balanced approach: favor safe providers but allow boorus & tenor/giphy
# -------------------------
def build_provider_pool():
    pool = []
    # Boost safe providers (higher weight)
    pool.extend(["waifu_pics"] * 8)
    pool.extend(["nekos_best"] * 6)
    pool.extend(["nekos_life"] * 6)
    pool.extend(["otakugifs"] * 5)

    # tenor/giphy moderate
    if TENOR_API_KEY:
        pool.extend(["tenor"] * 4)
    if GIPHY_API_KEY:
        pool.extend(["giphy"] * 4)

    # boorus (less weight but present)
    pool.extend(list(BOORU_ENDPOINT_TEMPLATES.keys()))  # each once
    return pool

# -------------------------
# GIF fetch function (tries many providers + applies scanning rules)
# -------------------------
async def fetch_gif(user_id):
    user_key = str(user_id)
    used = data["used_gifs"].setdefault(user_key, [])

    def build_booru_query(positive_tags):
        tags = [f"rating:{BOORU_TARGET_RATING}"]
        tags.extend(positive_tags.split())
        tags.extend([f"-{t}" for t in EXCLUDE_TAGS])
        tag_str = " ".join(tags)
        return tag_str, quote_plus(tag_str)

    providers = build_provider_pool()
    random.shuffle(providers)

    async with aiohttp.ClientSession() as session:
        for attempt in range(FETCH_ATTEMPTS):
            provider = random.choice(providers)
            positive = random.choice(GIF_TAGS)  # pick single spicy tag (focused)
            tag_str, tag_query = build_booru_query(positive)

            if DEBUG_FETCH:
                logger.info(f"[fetch_gif] attempt {attempt+1}/{FETCH_ATTEMPTS} provider={provider} tag='{positive}'")

            # ---------- TENOR ----------
            if provider == "tenor" and TENOR_API_KEY:
                try:
                    tenor_q = quote_plus(positive)
                    tenor_url = f"https://g.tenor.com/v1/search?q={tenor_q}&key={TENOR_API_KEY}&limit=30&contentfilter={TENOR_CONTENT_FILTER}"
                    async with session.get(tenor_url, timeout=12) as resp:
                        if resp.status != 200:
                            continue
                        payload = await resp.json()
                        results = payload.get("results", [])
                        random.shuffle(results)
                        for r in results:
                            gif_url = None
                            media_formats = r.get("media_formats") or r.get("media")
                            if isinstance(media_formats, dict):
                                for key in ("gif","nanogif","mediumgif","tinygif"):
                                    if media_formats.get(key) and media_formats[key].get("url"):
                                        gif_url = media_formats[key]["url"]; break
                            elif isinstance(media_formats, list) and media_formats:
                                first = media_formats[0]
                                if isinstance(first, dict):
                                    for key in ("gif","tinygif","mediumgif"):
                                        if first.get(key) and first[key].get("url"):
                                            gif_url = first[key]["url"]; break
                            if not gif_url:
                                gif_url = r.get("itemurl")
                            if not gif_url:
                                continue

                            # combine textual metadata
                            combined_meta = " ".join([
                                str(r.get("content_description") or ""),
                                " ".join(r.get("tags") or [] if isinstance(r.get("tags"), list) else [str(r.get("tags") or "")]),
                                gif_url
                            ])

                            # Tenor: moderate scan using hard/soft rules
                            hard, soft_count = analyze_nudity_indicators(combined_meta)
                            if hard or soft_count >= 3:
                                if DEBUG_FETCH:
                                    logger.info(f"[tenor] skipped nudity indicator: hard={hard} soft_count={soft_count}")
                                continue

                            gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                            if gif_hash in used:
                                continue
                            try:
                                async with session.get(gif_url, timeout=18) as gr:
                                    if gr.status != 200:
                                        continue
                                    ctype = gr.content_type or ""
                                    if "html" in ctype:
                                        continue
                                    b = await gr.read()
                                    ext = ".gif"
                                    if ".webm" in gif_url or "webm" in ctype:
                                        ext = ".webm"
                                    elif ".mp4" in gif_url or "mp4" in ctype:
                                        ext = ".mp4"
                                    name = f"tenor_{gif_hash[:8]}{ext}"
                                    used.append(gif_hash)
                                    if len(used) > MAX_USED_GIFS_PER_USER:
                                        del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                    save_data()
                                    return b, name, gif_url
                            except Exception:
                                continue
                except Exception:
                    continue

            # ---------- GIPHY ----------
            if provider == "giphy" and GIPHY_API_KEY:
                try:
                    giphy_q = quote_plus(positive)
                    giphy_url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={giphy_q}&limit=30&rating={GIPHY_RATING}"
                    async with session.get(giphy_url, timeout=12) as resp:
                        if resp.status != 200:
                            continue
                        payload = await resp.json()
                        arr = payload.get("data", [])
                        random.shuffle(arr)
                        for item in arr:
                            images = item.get("images", {})
                            gif_url = images.get("original", {}).get("url") or images.get("downsized", {}).get("url")
                            if not gif_url:
                                continue

                            combined_meta = " ".join([str(item.get("title") or ""), str(item.get("slug") or ""), gif_url])
                            hard, soft_count = analyze_nudity_indicators(combined_meta)
                            if hard or soft_count >= 3:
                                if DEBUG_FETCH:
                                    logger.info(f"[giphy] skipped nudity indicator: hard={hard} soft_count={soft_count}")
                                continue

                            gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                            if gif_hash in used:
                                continue
                            try:
                                async with session.get(gif_url, timeout=18) as gr:
                                    if gr.status != 200:
                                        continue
                                    ctype = gr.content_type or ""
                                    if "html" in ctype:
                                        continue
                                    b = await gr.read()
                                    ext = ".gif"
                                    if ".mp4" in gif_url or "mp4" in ctype:
                                        ext = ".mp4"
                                    elif "webm" in ctype or ".webm" in gif_url:
                                        ext = ".webm"
                                    name = f"giphy_{gif_hash[:8]}{ext}"
                                    used.append(gif_hash)
                                    if len(used) > MAX_USED_GIFS_PER_USER:
                                        del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                    save_data()
                                    return b, name, gif_url
                            except Exception:
                                continue
                except Exception:
                    continue

            # ---------- SAFE-NO-SCAN PROVIDERS (boosted) ----------
            if provider in SAFE_NO_SCAN_PROVIDERS:
                try:
                    if provider == "waifu_pics":
                        category = random.choice(SIMPLE_APIS["waifu_pics"]["categories_nsfw"])
                        url = f"{SIMPLE_APIS['waifu_pics']['base']}/nsfw/{category}"
                        async with session.get(url, timeout=10) as resp:
                            if resp.status != 200:
                                continue
                            payload = await resp.json()
                            gif_url = payload.get("url") or payload.get("image") or payload.get("file")
                            if not gif_url:
                                continue

                            # NO scanning here (safe provider). Still avoid duplicates.
                            gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                            if gif_hash in used:
                                continue
                            try:
                                async with session.get(gif_url, timeout=15) as gr:
                                    if gr.status != 200:
                                        continue
                                    ctype = gr.content_type or ""
                                    if "html" in ctype:
                                        continue
                                    b = await gr.read()
                                    ext = os.path.splitext(gif_url)[1] or ".gif"
                                    name = f"waifu_{gif_hash[:8]}{ext}"
                                    used.append(gif_hash)
                                    if len(used) > MAX_USED_GIFS_PER_USER:
                                        del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                    save_data()
                                    return b, name, gif_url
                            except Exception:
                                continue

                    elif provider == "nekos_best":
                        category = random.choice(SIMPLE_APIS["nekos_best"]["categories"])
                        url = f"{SIMPLE_APIS['nekos_best']['base']}/{category}"
                        async with session.get(url + "?amount=1", timeout=10) as resp:
                            if resp.status != 200:
                                continue
                            payload = await resp.json()
                            results = payload.get("results") or []
                            if not results:
                                continue
                            random.shuffle(results)
                            for r in results:
                                gif_url = r.get("url") or r.get("file")
                                if not gif_url:
                                    continue
                                gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                                if gif_hash in used:
                                    continue
                                try:
                                    async with session.get(gif_url, timeout=15) as gr:
                                        if gr.status != 200:
                                            continue
                                        ctype = gr.content_type or ""
                                        if "html" in ctype:
                                            continue
                                        b = await gr.read()
                                        ext = os.path.splitext(gif_url)[1] or ".gif"
                                        name = f"nekosbest_{gif_hash[:8]}{ext}"
                                        used.append(gif_hash)
                                        if len(used) > MAX_USED_GIFS_PER_USER:
                                            del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                        save_data()
                                        return b, name, gif_url
                                except Exception:
                                    continue

                    elif provider == "nekos_life":
                        category = random.choice(SIMPLE_APIS["nekos_life"]["categories"])
                        url = f"{SIMPLE_APIS['nekos_life']['base']}/{category}"
                        async with session.get(url, timeout=10) as resp:
                            if resp.status != 200:
                                continue
                            payload = await resp.json()
                            gif_url = payload.get("url") or payload.get("image") or payload.get("result")
                            if not gif_url:
                                continue
                            gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                            if gif_hash in used:
                                continue
                            try:
                                async with session.get(gif_url, timeout=15) as gr:
                                    if gr.status != 200:
                                        continue
                                    ctype = gr.content_type or ""
                                    if "html" in ctype:
                                        continue
                                    b = await gr.read()
                                    ext = os.path.splitext(gif_url)[1] or ".gif"
                                    name = f"nekoslife_{gif_hash[:8]}{ext}"
                                    used.append(gif_hash)
                                    if len(used) > MAX_USED_GIFS_PER_USER:
                                        del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                    save_data()
                                    return b, name, gif_url
                            except Exception:
                                continue

                    elif provider == "otakugifs":
                        reaction = quote_plus(positive)
                        url = f"https://otakugifs.xyz/api/gif?reaction={reaction}"
                        async with session.get(url, timeout=10) as resp:
                            if resp.status != 200:
                                continue
                            payload = await resp.json()
                            gif_url = payload.get("url") or payload.get("gif") or payload.get("file") or payload.get("result")
                            if not gif_url and isinstance(payload, str):
                                gif_url = payload
                            if not gif_url:
                                continue
                            gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                            if gif_hash in used:
                                continue
                            try:
                                async with session.get(gif_url, timeout=15) as gr:
                                    if gr.status != 200:
                                        continue
                                    ctype = gr.content_type or ""
                                    if "html" in ctype:
                                        continue
                                    b = await gr.read()
                                    ext = os.path.splitext(gif_url)[1] or ".gif"
                                    name = f"otakugifs_{gif_hash[:8]}{ext}"
                                    used.append(gif_hash)
                                    if len(used) > MAX_USED_GIFS_PER_USER:
                                        del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                    save_data()
                                    return b, name, gif_url
                            except Exception:
                                continue
                except Exception:
                    continue

            # ---------- BOORUS family (scan required) ----------
            if provider in BOORU_ENDPOINT_TEMPLATES:
                templates = BOORU_ENDPOINT_TEMPLATES.get(provider, [])
                if not templates:
                    continue
                template = random.choice(templates)
                url = template.format(tag_query=tag_query)
                try:
                    async with session.get(url, timeout=12) as resp:
                        if resp.status != 200:
                            continue
                        try:
                            posts = await resp.json()
                        except Exception:
                            continue
                        if isinstance(posts, dict):
                            if "posts" in posts:
                                posts = posts["posts"]
                            elif "post" in posts:
                                posts = posts["post"]
                            else:
                                if isinstance(posts.get("id"), (int,str)):
                                    posts = [posts]
                                else:
                                    posts = list(posts.values()) if posts else []
                        if not isinstance(posts, list):
                            try:
                                posts = list(posts)
                            except Exception:
                                posts = []
                        if not posts:
                            continue
                        random.shuffle(posts)
                        for post in posts:
                            gif_url = None
                            for key in ("file_url","large_file_url","image_url","jpeg_url","source","file","image","url","preview_url"):
                                try:
                                    v = post.get(key)
                                except Exception:
                                    v = None
                                if v:
                                    gif_url = v
                                    break
                            if not gif_url and isinstance(post.get("files"), dict):
                                gif_url = post["files"].get("original") or post["files"].get("file")
                            if not gif_url:
                                continue
                            # defensive: skip explicit if rating marker present
                            rating = (post.get("rating") or "").lower()
                            if rating.startswith("e"):
                                if DEBUG_FETCH:
                                    logger.info(f"[{provider}] skipped rating explicit for post id {post.get('id')}")
                                continue

                            tags_field = ""
                            if isinstance(post.get("tag_string"), str):
                                tags_field = post.get("tag_string")
                            if isinstance(post.get("tags"), str) and not tags_field:
                                tags_field = post.get("tags")

                            combined_meta = " ".join([str(tags_field or ""), str(post.get("description") or ""), str(post.get("source") or ""), str(gif_url or "")])

                            # run Option A scan: HARD immediate, SOFT count
                            hard, soft_count = analyze_nudity_indicators(combined_meta)
                            if hard or soft_count >= 3:
                                if DEBUG_FETCH:
                                    logger.info(f"[{provider}] skipped due to nudity: hard={hard} soft_count={soft_count}")
                                continue

                            # skip if illegal tags present
                            if any(ex in (tags_field or "") for ex in EXCLUDE_TAGS):
                                continue

                            gif_hash = hashlib.sha1(gif_url.encode()).hexdigest()
                            if gif_hash in used:
                                continue
                            try:
                                async with session.get(gif_url, timeout=18) as gr:
                                    if gr.status != 200:
                                        continue
                                    ctype = gr.content_type or ""
                                    if "html" in ctype:
                                        continue
                                    b = await gr.read()
                                    ext = os.path.splitext(gif_url)[1] or ".gif"
                                    name = f"{provider}_{gif_hash[:8]}{ext}"
                                    used.append(gif_hash)
                                    if len(used) > MAX_USED_GIFS_PER_USER:
                                        del used[:len(used) - MAX_USED_GIFS_PER_USER]
                                    save_data()
                                    return b, name, gif_url
                            except Exception:
                                continue
                except Exception:
                    continue

        # no valid gif found in attempts
    return None, None, None

# -------------------------
# Embed builder
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
# VOICE STATE UPDATE (Multi-VC)
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
                            embed_dm.description += f"\n[View media here]({gif_url})"
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
            # If nothing found, still send embed (we tried many providers)
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
                            embed_dm.description += f"\n[View media here]({gif_url})"
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
