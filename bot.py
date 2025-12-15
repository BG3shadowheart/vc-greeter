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

TOKEN = os.getenv("TOKEN", "")
WAIFUIM_API_KEY = os.getenv("WAIFUIM_API_KEY", "")
DANBOORU_USER = os.getenv("DANBOORU_USER", "")
DANBOORU_API_KEY = os.getenv("DANBOORU_API_KEY", "")

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
    int(os.getenv("VC_ID_1", "1409170559337762980")),
]
VC_CHANNEL_ID = int(os.getenv("VC_CHANNEL_ID", "1371916812903780573"))

logging.basicConfig(level=logging.DEBUG if DEBUG_FETCH else logging.INFO)
logger = logging.getLogger("spiciest-sfw")

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
    "thighs", "thick_thighs", "thicc", "legs", "stockings", "thighhighs", "garter_belt",
    "cleavage", "big_breasts", "huge_breasts", "oppai", "breast_focus", "boobs",
    "underboob", "sideboob", "cleavage_cutout", "breast_squeeze",
    "ass", "butt", "big_ass", "ass_focus", "tight_clothes",
    "skirt_lift", "shirt_lift", "clothes_lift", "upskirt", "panty_shot",
    "see_through", "transparent", "wet", "wet_clothes", "sweaty",
    "revealing_clothes", "micro_bikini", "string_bikini", "slingshot_swimsuit",
    "leotard", "bodysuit", "gym_uniform", "sports_bra", "sportswear",
    "maid", "bunny_girl", "playboy_bunny", "bunny_ears", "animal_ears",
    "catgirl", "cat_ears", "tail", "kemonomimi", "fox_girl", "fox_ears",
    "seductive", "seductive_smile", "bedroom_eyes", "flirty", "teasing",
    "blushing", "embarrassed", "shy", "surprised", "aroused_face",
    "pose", "seductive_pose", "sitting", "lying", "on_back", "on_stomach",
    "bent_over", "all_fours", "arched_back", "stretching",
    "spread_legs", "legs_apart", "m_legs", "open_legs", "legs_up",
    "towel", "bath_towel", "bathing", "shower", "wet_hair", "after_bath",
    "bedroom", "bed", "pillow", "lying_on_bed", "on_bed",
    "beach", "poolside", "pool", "summer", "tan", "tanned", "dark_skin",
    "midriff", "navel", "stomach", "abs", "toned", "athletic",
    "armpits", "armpit_focus", "arms_up", "arms_behind_head",
    "curvy", "voluptuous", "hourglass_figure", "wide_hips",
    "short_shorts", "hot_pants", "daisy_dukes", "denim_shorts",
    "miniskirt", "micro_skirt", "pleated_skirt", "pencil_skirt",
    "fishnet", "fishnet_stockings", "fishnet_thighhighs", "garter_straps",
    "lace", "lace_trim", "lace_panties", "lace_bra", "frills",
    "ribbon", "bow", "hair_ribbon", "neck_ribbon",
    "choker", "collar", "necklace", "jewelry", "earrings",
    "glasses", "megane", "sunglasses", "eyewear",
    "high_heels", "heels", "stiletto", "boots", "thigh_boots",
    "gloves", "elbow_gloves", "fingerless_gloves",
    "blonde", "brunette", "redhead", "pink_hair", "purple_hair", "blue_hair",
    "long_hair", "short_hair", "twintails", "ponytail", "pigtails",
    "idol", "singer", "performer", "stage", "concert",
    "cheerleader", "cheerleading", "pom_poms",
    "nurse", "teacher", "secretary", "office_lady", "business_suit",
    "school_uniform", "sailor_uniform", "serafuku",
    "yoga", "yoga_pants", "exercise", "workout", "gym",
    "sleeping", "sleepy", "yawning", "waking_up", "stretching",
    "eating", "drinking", "popsicle", "ice_cream", "lollipop",
    "looking_at_viewer", "looking_back", "from_behind", "from_below", "from_above",
    "wink", "smiling", "grin", "happy", "playful",
    "multiple_girls", "2girls", "3girls", "yuri", "girl_on_girl", "lesbian",
    "angel", "demon", "succubus", "demon_girl", "horns", "wings", "halo",
    "elf", "elf_ears", "pointy_ears", "dark_elf",
    "monster_girl", "slime_girl", "lamia", "harpy",
    "mermaid", "underwater", "water", "bubbles"
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

PROVIDER_TERMS = {
    "waifu_pics": ["waifu", "neko"],
    "waifu_im": ["ecchi", "ero", "oppai", "selfies", "uniform", "maid"],
    "nekos_best": ["neko", "waifu", "kitsune", "husbando"],
    "danbooru": ["ecchi", "bikini", "swimsuit", "cleavage", "thighs", "ass", "breasts", "panties", "lingerie"],
    "gelbooru": ["ecchi", "bikini", "swimsuit", "panties", "thighs", "cleavage", "upskirt"],
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

async def _download_bytes_with_limit(session, url, size_limit=HEAD_SIZE_LIMIT, timeout=REQUEST_TIMEOUT):
    try:
        async with session.get(url, timeout=timeout, allow_redirects=True) as resp:
            if resp.status != 200:
                if DEBUG_FETCH: logger.debug(f"GET {url} returned {resp.status}")
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
                    if DEBUG_FETCH: logger.debug(f"download exceeded limit {size_limit} for {url}")
                    return None, ctype
            return b"".join(chunks), ctype
    except Exception as e:
        if DEBUG_FETCH: logger.debug(f"GET exception for {url}: {e}")
        return None, None

async def fetch_from_waifu_pics(session, positive):
    try:
        category = map_tag_for_provider("waifu_pics", positive)
        url = f"https://api.waifu.pics/sfw/{quote_plus(category)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                if DEBUG_FETCH: logger.debug(f"waifu_pics sfw {category} -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url") or payload.get("image")
            if not gif_url or filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(payload) + " " + (category or "")): return None, None, None
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
            if not images: return None, None, None
            img = random.choice(images)
            gif_url = img.get("url")
            if not gif_url or filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(img) + " " + (q or "")): return None, None, None
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
                if DEBUG_FETCH: logger.debug(f"nekos.best {q} -> {resp.status}")
                return None, None, None
            payload = await resp.json()
            results = payload.get("results", [])
            if not results: return None, None, None
            r = results[0]
            gif_url = r.get("url")
            if not gif_url or filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(r) + " " + (q or "")): return None, None, None
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
            if not posts: return None, None, None
            post = random.choice(posts)
            gif_url = post.get("file_url") or post.get("large_file_url")
            if not gif_url or filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(post)): return None, None, None
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
        async with session.get(base, params=params, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                return None, None, None
            payload = await resp.json()
            posts = payload.get("post", [])
            if not posts: return None, None, None
            post = random.choice(posts)
            gif_url = post.get("file_url")
            if not gif_url or filename_has_block_keyword(gif_url): return None, None, None
            if contains_illegal_indicators(json.dumps(post)): return None, None, None
            extract_and_add_tags_from_meta(post.get("tags", ""), GIF_TAGS, data)
            return gif_url, f"gelbooru_{positive}", post
    except Exception:
        return None, None, None

PROVIDERS = [
    ("waifu_im", fetch_from_waifu_im, 30),
    ("danbooru", fetch_from_danbooru, 25),
    ("gelbooru", fetch_from_gelbooru, 20),
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

async def send_greeting_with_image_embed(channel, session, greeting_text, image_url, member):
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
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.set_image(url=f"attachment://{filename}")
        embed.set_footer(text="SFW Ecchi Bot")
        
        await channel.send(embed=embed, file=file)
        logger.info(f"Sent greeting embed with image: {filename}")
    except Exception as e:
        logger.error(f"Failed to send greeting embed: {e}")
        await channel.send(greeting_text)

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

@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id:
        return
    
    if before.channel is None and after.channel is not None:
        if after.channel.id in VC_IDS:
            guild = after.channel.guild
            if guild.voice_client is None:
                try:
                    await after.channel.connect()
                    logger.info(f"Bot joined VC: {after.channel.name}")
                except Exception as e:
                    logger.error(f"Failed to join VC: {e}")
            
            channel = bot.get_channel(VC_CHANNEL_ID)
            if channel:
                try:
                    greeting = random.choice(JOIN_GREETINGS).format(display_name=member.display_name)
                    
                    async with aiohttp.ClientSession() as session:
                        gif_url, source, meta = await fetch_random_gif(session, member.id)
                        if gif_url:
                            await send_greeting_with_image_embed(channel, session, greeting, gif_url, member)
                            logger.info(f"Sent join greeting embed from {source}")
                        else:
                            await channel.send(greeting)
                except Exception as e:
                    logger.error(f"Failed to send join greeting: {e}")
    
    elif before.channel is not None and after.channel is None:
        if before.channel.id in VC_IDS:
            channel = bot.get_channel(VC_CHANNEL_ID)
            if channel:
                try:
                    leave_msg = random.choice(LEAVE_GREETINGS).format(display_name=member.display_name)
                    
                    async with aiohttp.ClientSession() as session:
                        gif_url, source, meta = await fetch_random_gif(session, member.id)
                        if gif_url:
                            await send_greeting_with_image_embed(channel, session, leave_msg, gif_url, member)
                            logger.info(f"Sent leave greeting embed from {source}")
                        else:
                            await channel.send(leave_msg)
                except Exception as e:
                    logger.error(f"Failed to send leave greeting: {e}")
            
            remaining = [m for m in before.channel.members if not m.bot]
            if len(remaining) == 0:
                guild = before.channel.guild
                if guild.voice_client:
                    try:
                        await guild.voice_client.disconnect()
                        logger.info(f"Bot left VC: {before.channel.name} (no users)")
                    except Exception as e:
                        logger.error(f"Failed to leave VC: {e}")

@tasks.loop(seconds=120)
async def check_vc():
    for vc_id in VC_IDS:
        vc = bot.get_channel(vc_id)
        if not vc or not isinstance(vc, discord.VoiceChannel):
            continue
        
        remaining = [m for m in vc.members if not m.bot]
        if len(remaining) == 0:
            if vc.guild.voice_client:
                try:
                    await vc.guild.voice_client.disconnect()
                    logger.info(f"Bot left empty VC: {vc.name}")
                except Exception:
                    pass

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
            except:
                await ctx.send("Failed to fetch SFW content. Try again.")
        else:
            await ctx.send("Failed to fetch SFW content. Try again.")

bot.run(TOKEN)
