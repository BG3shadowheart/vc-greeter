# bot_spiciest_final_fixed.py
import os
import io
import json
import random
import hashlib
import logging
import re
from datetime import datetime
from urllib.parse import quote_plus
import aiohttp
import discord
from discord.ext import commands, tasks

# --- CONFIGURATION ---
TOKEN = os.getenv("TOKEN")
TENOR_API_KEY = os.getenv("TENOR_API_KEY")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")
WAIFUIM_API_KEY = os.getenv("WAIFUIM_API_KEY")
WAIFUIT_API_KEY = os.getenv("WAIFUIT_API_KEY")

DEBUG_FETCH = os.getenv("DEBUG_FETCH", "true") != "" # Default to true for debugging

VC_IDS = [
    1353875050809524267,
    21409170559337762980,
    1353875404217253909,
    1353882705246556220
]
VC_CHANNEL_ID = 1371916812903780573

DATA_FILE = "data.json"
AUTOSAVE_INTERVAL = 30
MAX_USED_GIFS_PER_USER = 1000
FETCH_ATTEMPTS = 15  # Reduced attempts because logic is smarter now
REQUEST_TIMEOUT = 10

# --- TAGS & LISTS ---

_seed_gif_tags = [
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
    "mature waifu","older sister waifu","maid outfit","cute cosplay","lingerie model",
    "lingerie girl","sensual","lewd","seductive","sexy","fanservice","pantie"
]

HARD_TAGS = [
    "pussy","vagina","labia","clitoris","penis","cock","dick","shaft","testicles","balls","scrotum","anus",
    "open pussy","spread pussy","uncensored pussy","bare breasts","nude","naked","topless","bottomless",
    "nipples","nipple","areola","areolas","areola visible","nipples visible","nipples out","nipple visible",
    "nude female","naked female","explicit nude","spread legs explicit",
    "sex","penetration","penetrating","penetrated","anal sex","double penetration","dp",
    "threesome","foursome","group sex","orgy","69","blowjob","deepthroat","oral","fellatio","handjob",
    "titty fuck","facefuck","facesitting","creampie","facial","cum","cumshot","cum shot","ejac","ejaculation",
    "cum in mouth","cum in face","cum_on_face","cum_in_mouth","cum covered","cum drip",
    "porn","pornography","xxx","explicit","uncensored","hentai explicit","hentai uncensored",
    "bestiality","scat","watersports","fisting","sex toy","strapon",
    "gay","homosexual","gay male","gay porn","gaysex","man","men","male","males",
    "boy","boys","young man","shemale","shemales","trap","traps","femboy","femboys",
    "trans","transgender","transsexual","mtf","ftm","crossdresser","male nudity","male breasts",
    "futa","futanari","sissy","dickgirl"
]

SOFT_TAGS = ["stockings","teasing","sexy","lewd","soft erotic","suggestive","suggestive pose"]
FILENAME_BLOCK_KEYWORDS = ["orgy","creampie","facial","scat","fisting","bestiality"]
EXCLUDE_TAGS = ["loli","shota","child","minor","underage","young","schoolgirl","age_gap"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("safe-spiciest-v4")

# --- HELPERS ---

def _normalize_text(s: str) -> str:
    return "" if not s else re.sub(r'[\s\-_]+', ' ', s.lower())

def analyze_nudity_indicators(text: str):
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
    return hard or (soft_count >= 3)

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

def _tag_is_disallowed(t: str) -> bool:
    if not t:
        return True
    t = t.lower()
    if any(ex in t for ex in EXCLUDE_TAGS):
        return True
    return False

# --- DATA MANAGEMENT ---

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({
            "join_counts": {},
            "used_gifs": {},
            "provider_weights": {},
            "sent_history": {},
            "gif_tags": []
        }, f, indent=2)

with open(DATA_FILE, "r") as f:
    data = json.load(f)

data.setdefault("join_counts", {})
data.setdefault("used_gifs", {})
data.setdefault("provider_weights", {})
data.setdefault("sent_history", {})
data.setdefault("gif_tags", [])

persisted = _dedupe_preserve_order(data.get("gif_tags", []))
seed = _dedupe_preserve_order(_seed_gif_tags)
combined = seed + [t for t in persisted if t not in seed]
GIF_TAGS = [t for t in _dedupe_preserve_order(combined) if not _tag_is_disallowed(t)]
if not GIF_TAGS:
    GIF_TAGS = ["waifu"]

# Default weights (Fluxpoint removed)
default_weights = {
    "waifu_pics": 2, "waifu_im": 3, "waifu_it": 2, "nekos_best": 2, 
    "nekos_life": 1, "nekos_moe": 1, "otakugifs": 1, 
    "tenor": 2, "giphy": 2, "animegirls_online": 1
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
        data["gif_tags"] = GIF_TAGS
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save data: {e}")

def add_tag_to_gif_tags(tag: str):
    if not tag or not isinstance(tag, str): return False
    t = tag.strip().lower()
    if len(t) < 3 or t in GIF_TAGS or _tag_is_disallowed(t): return False
    GIF_TAGS.append(t)
    data["gif_tags"] = _dedupe_preserve_order(data.get("gif_tags", []) + [t])
    save_data()
    return True

_token_split_re = re.compile(r"[^a-z0-9]+")
def extract_and_add_tags_from_meta(meta_text: str):
    if not meta_text: return
    text = _normalize_text(meta_text)
    tokens = _token_split_re.split(text)
    for tok in tokens:
        tok = tok.strip()
        if not tok or tok.isdigit() or len(tok) < 3: continue
        add_tag_to_gif_tags(tok)

async def _download_url(session, url, timeout=REQUEST_TIMEOUT):
    try:
        async with session.get(url, timeout=timeout) as resp:
            if resp.status != 200: return None, None
            ctype = resp.content_type or ""
            if "html" in ctype: return None, None
            b = await resp.read()
            return b, ctype
    except Exception:
        return None, None

# --- CRITICAL FIX: SMART CATEGORY MAPPING ---
# This converts random tags (e.g., "big boobs") into valid API categories (e.g., "waifu")
def get_valid_category(provider, tag):
    tag = tag.lower()
    
    # NEKOS.BEST (Strict categories)
    if provider == "nekos_best":
        if "cat" in tag or "neko" in tag: return "neko"
        if "fox" in tag or "kitsune" in tag: return "kitsune"
        if "hug" in tag: return "hug"
        if "kiss" in tag: return "kiss"
        return "waifu" # Safe default

    # WAIFU.PICS (Strict categories)
    if provider == "waifu_pics":
        # SFW Categories that match common tags
        valid_sfw = ["waifu", "neko", "shinobu", "megumin", "bully", "cuddle", "cry", "hug", "awoo", "kiss", "lick", "pat", "smug", "bonk", "yeet", "blush", "smile", "wave", "highfive", "handhold", "nom", "bite", "glomp", "slap", "kill", "kick", "happy", "wink", "poke", "dance", "cringe"]
        if tag in valid_sfw: return tag
        
        # Mapping logic
        if "cat" in tag or "neko" in tag: return "neko"
        if "cry" in tag or "sad" in tag: return "cry"
        if "kiss" in tag: return "kiss"
        if "hug" in tag: return "hug"
        return "waifu" # Safe default

    # WAIFU.IT (Strict)
    if provider == "waifu_it":
        if "waifu" in tag: return "waifu"
        if "neko" in tag: return "neko"
        if "kitsune" in tag: return "kitsune"
        if "lofi" in tag: return "lofi"
        if "creepy" in tag: return "creepy"
        return "waifu" # Default

    # NEKOS.LIFE (Strict)
    if provider == "nekos_life":
        if "cat" in tag or "neko" in tag: return "neko"
        if "fox" in tag: return "fox_girl"
        if "avatar" in tag: return "avatar"
        return "waifu"

    # Default: Return tag as-is for search engines like Giphy/Tenor/Waifu.im
    return tag

# --- FETCHERS ---

async def fetch_from_waifu_pics(session, positive):
    try:
        # Use the mapper to get a valid category
        category = get_valid_category("waifu_pics", positive)
        # We default to SFW to avoid 404s and strict hard-tag filtering, 
        # but 'waifu' category is usually cute/spicy enough.
        url = f"https://api.waifu.pics/sfw/{category}"
        
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200: return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url")
            
            if not gif_url or filename_has_block_keyword(gif_url): return None, None, None
            if contains_nude_indicators(gif_url): return None, None, None
            
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"waifu_pics_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

async def fetch_from_waifu_im(session, positive):
    try:
        # Waifu.im SUPPORTS tags, so we use 'positive' directly.
        base = "https://api.waifu.im/search"
        # We ask for NSFW, but we rely on your HARD_TAGS to filter out actual porn.
        # This gets the "spicy" stuff (ecchi) without going too far.
        params = {"included_tags": positive, "is_nsfw": "false"} 
        # NOTE: Changed is_nsfw to false because your HARD_TAGS are very strict. 
        # If you want slightly spicy, waifu.im SFW is still good. 
        # If you want ecchi, change to "null" or "true" but expect more blocks.
        
        headers = {}
        if WAIFUIM_API_KEY:
            headers["Authorization"] = f"Bearer {WAIFUIM_API_KEY}"
            
        async with session.get(base, params=params, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200: return None, None, None
            payload = await resp.json()
            images = payload.get("images", [])
            if not images: return None, None, None
            
            img = random.choice(images)
            gif_url = img.get("url")
            
            if not gif_url or filename_has_block_keyword(gif_url): return None, None, None
            meta = str(img.get("tags", ""))
            if contains_nude_indicators(meta): return None, None, None
            
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"waifu_im_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

async def fetch_from_waifu_it(session, positive):
    try:
        if not WAIFUIT_API_KEY: return None, None, None
        category = get_valid_category("waifu_it", positive)
        endpoint = f"https://waifu.it/api/v4/{category}"
        
        headers = {"Authorization": WAIFUIT_API_KEY}
        
        async with session.get(endpoint, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200: return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url")
            
            if not gif_url or filename_has_block_keyword(gif_url): return None, None, None
            if contains_nude_indicators(gif_url): return None, None, None
            
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"waifu_it_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

async def fetch_from_nekos_best(session, positive):
    try:
        category = get_valid_category("nekos_best", positive)
        url = f"https://nekos.best/api/v2/{category}?amount=1"
        
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200: return None, None, None
            payload = await resp.json()
            results = payload.get("results", [])
            if not results: return None, None, None
            
            r = results[0]
            gif_url = r.get("url")
            
            if not gif_url or filename_has_block_keyword(gif_url): return None, None, None
            if contains_nude_indicators(gif_url): return None, None, None
            
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"nekos_best_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

async def fetch_from_nekos_life(session, positive):
    try:
        category = get_valid_category("nekos_life", positive)
        url = f"https://nekos.life/api/v2/img/{category}"
        
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200: return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url")
            
            if not gif_url or filename_has_block_keyword(gif_url): return None, None, None
            if contains_nude_indicators(gif_url): return None, None, None
            
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"nekos_life_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

async def fetch_from_nekos_moe(session, positive):
    try:
        # nekos.moe supports search tags
        tag = quote_plus(positive)
        url = f"https://nekos.moe/api/v3/gif/random?tag={tag}"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200: return None, None, None
            payload = await resp.json()
            images = payload.get("images", [])
            if not images: return None, None, None
            
            item = random.choice(images)
            # constructing url for nekos.moe
            if item.get("id"):
                gif_url = f"https://nekos.moe/image/{item['id']}.gif"
            else:
                return None, None, None

            if contains_nude_indicators(gif_url): return None, None, None
            
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            name = f"nekos_moe_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}.gif"
            return b, name, gif_url
    except Exception:
        return None, None, None

async def fetch_from_otakugifs(session, positive):
    try:
        # Otakugifs expects reactions like "kiss", "slap", or general text
        # We try to map to reactions if possible, otherwise send raw
        reaction = positive 
        valid_reactions = ["kiss", "hug", "slap", "punch", "wink", "dance", "cuddle"]
        found = False
        for v in valid_reactions:
            if v in positive:
                reaction = v
                found = True
                break
        if not found:
            # If not a reaction, asking for "waifu" implies general anime gif
            reaction = "waifu"

        url = f"https://otakugifs.xyz/api/gif?reaction={reaction}"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200: return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url")
            
            if not gif_url or filename_has_block_keyword(gif_url): return None, None, None
            
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"otakugifs_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

async def fetch_from_animegirls_online(session, positive):
    try:
        # Supports searching
        url = f"https://animegirls.online/api/random?tag={quote_plus(positive)}"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200: return None, None, None
            payload = await resp.json()
            gif_url = payload.get("url")
            
            if not gif_url or filename_has_block_keyword(gif_url): return None, None, None
            if contains_nude_indicators(gif_url): return None, None, None
            
            b, ctype = await _download_url(session, gif_url)
            if not b: return None, None, None
            ext = os.path.splitext(gif_url)[1] or ".gif"
            name = f"animegirls_online_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}{ext}"
            return b, name, gif_url
    except Exception:
        return None, None, None

async def fetch_from_tenor(session, positive):
    if not TENOR_API_KEY: return None, None, None
    try:
        tenor_q = quote_plus(positive + " anime")
        tenor_url = f"https://g.tenor.com/v1/search?q={tenor_q}&key={TENOR_API_KEY}&limit=20&contentfilter=low"
        async with session.get(tenor_url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200: return None, None, None
            payload = await resp.json()
            results = payload.get("results", [])
            random.shuffle(results)
            
            for r in results:
                media = r.get("media", [])
                if not media: continue
                gif_url = media[0].get("gif", {}).get("url")
                
                if not gif_url or filename_has_block_keyword(gif_url): continue
                if contains_nude_indicators(gif_url): continue
                
                b, ctype = await _download_url(session, gif_url)
                if not b: continue
                name = f"tenor_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}.gif"
                return b, name, gif_url
    except Exception:
        return None, None, None

async def fetch_from_giphy(session, positive):
    if not GIPHY_API_KEY: return None, None, None
    try:
        giphy_q = quote_plus(positive + " anime")
        # rating=pg-13 allows for some spice but filters hard nudity
        giphy_url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={giphy_q}&limit=20&rating=pg-13"
        async with session.get(giphy_url, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200: return None, None, None
            payload = await resp.json()
            arr = payload.get("data", [])
            random.shuffle(arr)
            
            for item in arr:
                gif_url = item.get("images", {}).get("original", {}).get("url")
                if not gif_url or filename_has_block_keyword(gif_url): continue
                
                b, ctype = await _download_url(session, gif_url)
                if not b: continue
                name = f"giphy_{hashlib.sha1(gif_url.encode()).hexdigest()[:10]}.gif"
                return b, name, gif_url
    except Exception:
        return None, None, None

PROVIDER_FETCHERS = {
    "waifu_pics": fetch_from_waifu_pics,
    "waifu_im": fetch_from_waifu_im,
    "waifu_it": fetch_from_waifu_it,
    "nekos_best": fetch_from_nekos_best,
    "nekos_life": fetch_from_nekos_life,
    "nekos_moe": fetch_from_nekos_moe,
    "otakugifs": fetch_from_otakugifs,
    "animegirls_online": fetch_from_animegirls_online,
    "tenor": fetch_from_tenor,
    "giphy": fetch_from_giphy
}

def build_provider_pool():
    pool = []
    # Add providers based on weights
    for prov, weight in data["provider_weights"].items():
        if prov in PROVIDER_FETCHERS and weight > 0:
            pool.extend([prov] * weight)
            
    # Ensure keys are present for key-based providers
    if not TENOR_API_KEY: 
        pool = [p for p in pool if p != "tenor"]
    if not GIPHY_API_KEY:
        pool = [p for p in pool if p != "giphy"]
    if not WAIFUIT_API_KEY:
        pool = [p for p in pool if p != "waifu_it"]

    random.shuffle(pool)
    return pool if pool else list(PROVIDER_FETCHERS.keys())

async def fetch_gif(user_id):
    user_key = str(user_id)
    sent = data["sent_history"].setdefault(user_key, [])
    providers = build_provider_pool()
    
    async with aiohttp.ClientSession() as session:
        for attempt in range(FETCH_ATTEMPTS):
            if not providers: providers = build_provider_pool()
            provider = random.choice(providers)
            positive = random.choice(GIF_TAGS)
            
            if DEBUG_FETCH:
                logger.info(f"[fetch_gif] attempt {attempt+1} | provider: {provider} | tag: {positive}")
            
            fetcher = PROVIDER_FETCHERS.get(provider)
            if not fetcher: continue
            
            try:
                result = await fetcher(session, positive)
            except Exception as e:
                logger.error(f"Error in {provider}: {e}")
                result = (None, None, None)
                
            if not result or not result[0]:
                continue
                
            b, name, gif_url = result
            if not gif_url: continue
            
            gif_hash = hashlib.sha1((gif_url).encode()).hexdigest()
            if gif_hash in sent:
                continue
                
            sent.append(gif_hash)
            if len(sent) > MAX_USED_GIFS_PER_USER:
                del sent[:len(sent) - MAX_USED_GIFS_PER_USER]
            save_data()
            return b, name, gif_url
            
    return None, None, None

# --- MESSAGES & DISCORD EVENTS ---

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

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot: return
    text_channel = bot.get_channel(VC_CHANNEL_ID)

    # Auto-join logic
    if after.channel and (after.channel.id in VC_IDS) and (before.channel != after.channel):
        try:
            vc = discord.utils.get(bot.voice_clients, guild=member.guild)
            if vc:
                if vc.channel.id != after.channel.id:
                    await vc.move_to(after.channel)
            else:
                await after.channel.connect()
        except Exception as e:
            logger.warning(f"VC logic error: {e}")

    # JOIN Message
    if after.channel and (after.channel.id in VC_IDS) and (before.channel != after.channel):
        raw_msg = random.choice(JOIN_GREETINGS)
        msg = raw_msg.format(display_name=member.display_name)
        data["join_counts"][str(member.id)] = data["join_counts"].get(str(member.id), 0) + 1
        
        embed = make_embed("Welcome!", msg, member, "join", data["join_counts"][str(member.id)])
        gif_bytes, gif_name, gif_url = await fetch_gif(member.id)
        
        if gif_bytes:
            try:
                file_server = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                embed.set_image(url=f"attachment://{gif_name}")
                
                if text_channel:
                    await text_channel.send(embed=embed, file=file_server)
                
                try:
                    # Re-create file for DM
                    file_dm = discord.File(io.BytesIO(gif_bytes), filename=gif_name)
                    await member.send(embed=embed, file=file_dm)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Failed to send join img: {e}")
                if text_channel: await text_channel.send(embed=embed)
        else:
            if text_channel: await text_channel.send(embed=embed)

    # LEAVE Message
    if before.channel and (before.channel.id in VC_IDS) and (after.channel != before.channel):
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
                    pass
            except Exception:
                if text_channel: await text_channel.send(embed=embed)
        else:
            if text_channel: await text_channel.send(embed=embed)

        # Disconnect if empty
        try:
            vc = discord.utils.get(bot.voice_clients, guild=member.guild)
            if vc and len([m for m in vc.channel.members if not m.bot]) == 0:
                await vc.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    if not TOKEN:
        logger.error("TOKEN environment variable missing.")
    else:
        bot.run(TOKEN)
