# bot.py
import os
import discord
from discord.ext import commands
import asyncio
import logging
import random
from datetime import datetime

# -------------------------
# Basic logging
# -------------------------
logging.basicConfig(level=logging.INFO)

# -------------------------
# Anime-style join/leave messages
# (You can add up to 100+ strings each)
# -------------------------
JOIN_GREETINGS = [
    "✨ Welcome, {display_name}-san! May your presence bring fortune to this hall.",
    "━━✦ 𝓐𝓷𝓲𝓶𝓮 𝐚𝐮𝐫𝐚 ━━ {display_name} has arrived! Ready for the next episode?",
    "🌸 {display_name}, bloom with us — welcome to the VC!",
    "⚔️ {display_name} joins the battlefield. Prepare your cheers!",
    "😺 Nya~ {display_name} came to play! Welcome!",
    "🌙 Under the moon, {display_name} appears. Welcome!",
    "🎴 Destiny calls — {display_name} has arrived to the circle!",
    "🔥 {display_name}, your aura flared — welcome!",
    "🎀 A new scene begins: starring {display_name}!",
    "🏮 Welcome, {display_name}-chan! Let's make memories today.",
    "🍥 {display_name}, like a spirited hero, has joined the party!",
    "🕊️ {display_name}, your presence calms the storm. Welcome.",
    "🌟 The spotlight found {display_name}. Take your bow!",
    "🌀 {display_name} appeared in a dramatic cut-in! Welcome!",
    "🎭 {display_name} entered — curtains up!",
    "📜 Welcome, {display_name}. A new tale starts now.",
    "🌸 A sakura petal floats — {display_name} has joined.",
    "💫 {display_name} joins with a sparkle. Make a wish!",
    "🎮 {display_name} queued into the VC — game on!",
    "📸 {display_name} popped in — strike a pose!",
    "🛡️ Hail {display_name}, defender of the voice channel!",
    "🌈 {display_name} arrives like a rainbow after rain. Welcome!",
    "🍵 Pour some tea — {display_name} is here!",
    "💌 {display_name} delivered cuteness. Welcome!",
    "🔮 The crystal foretold: {display_name} will arrive today.",
    "🎵 A new melody begins — {display_name} joined the choir.",
    "🌪️ Entering with style: {display_name} has landed!",
    "🧩 {display_name} filled the missing piece. Welcome!",
    "✨ Welcome back, {display_name}! The story continues.",
    "🐉 Rumor has it a dragon named {display_name} joined us.",
    "🎇 Fireworks for {display_name} — welcome to the VC!",
    "🌌 {display_name} traveled across stars to join — welcome!",
    "🎒 New adventurer {display_name} arrived. Equip your smile!",
    "🕶️ {display_name} slid in like a cool protagonist. Welcome!",
    "🍣 Sushi time — {display_name} has joined the table!",
    "🧸 {display_name} cuddled into the VC. Warm welcomes!",
    "☁️ {display_name} floats in on a cloud of hype. Welcome!",
    "📚 {display_name} enters chapter {random_ch}: Welcome!",
]

LEAVE_GREETINGS = [
    "🌙 Farewell, {display_name}-san. May your path be peaceful.",
    "🏮 {display_name} fades to credits — until next time!",
    "🍃 {display_name} drifts away like an autumn leaf. See you.",
    "✨ {display_name}, your cameo ends — come back soon!",
    "😿 Nya... {display_name} left. We'll miss you!",
    "⚔️ {display_name} departs the battlefield. Rest well, warrior.",
    "🌸 The sakura falls — {display_name} has left the VC.",
    "🔚 Scene change: {display_name} has exited the stage.",
    "🎒 {display_name} logged off the quest. Good luck on your journey!",
    "💌 {display_name} sent a goodbye kiss. Till later!",
    "🕊️ {display_name} flew away on gentle wings. Farewell.",
    "📜 The scroll closes for now — goodbye, {display_name}.",
    "🌟 Curtain call for {display_name}. See you at the next act!",
    "🎮 {display_name} left the lobby — comeback whenever!",
    "🍵 Tea's getting cold — {display_name} departed.",
    "🔮 The vision fades — {display_name} is gone for now.",
    "🎵 The final note played — {display_name} leaves the choir.",
    "🛡️ {display_name} retires from duty. Honor and rest.",
    "🌈 {display_name} chased a rainbow — gone for now!",
    "🧩 {display_name} walked away; a puzzle remains.",
    "🐉 The dragon sleeps — {display_name} has left the realm.",
    "🎇 Firework ended — goodbye, {display_name}!",
    "📸 {display_name} left the photo — save the memory!",
    "🕶️ {display_name} vanished like a cool shadow. Bye!",
    "🍣 Took the last sushi — {display_name} left the table!",
    "🧸 {display_name} took their teddy and left. Come back soon!",
    "☁️ Drifted away — {display_name} left the clouds.",
    "📚 Chapter closed — goodbye, {display_name}.",
    "🌌 {display_name} returned to the stars. Farewell!",
    "💫 Until the next sparkle, {display_name} — bye!",
    "🔚 {display_name} left the server scene. See ya!",
    "🏁 {display_name} crossed the finish line and logged off.",
]

# -------------------------
# Environment / IDs
# -------------------------
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN environment variable not set")

# Replace with your target VC text channel ID (where you want the chat embeds posted)
VC_CHANNEL_ID = 1353875050809524267

try:
    SERVER_ID = int(os.getenv("SERVER_ID"))
except:
    SERVER_ID = None

# -------------------------
# Intents & Bot
# -------------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# Helpers
# -------------------------
def make_embed(title: str, description: str, member: discord.Member, kind: str = "join"):
    """
    Create a styled embed for join/leave.
    kind: 'join' or 'leave' controls color/emoji
    """
    emoji = "✨" if kind == "join" else "👋"
    color = discord.Color.from_rgb(255, 182, 193) if kind == "join" else discord.Color.from_rgb(176, 196, 222)
    embed = discord.Embed(
        title=f"{emoji} {title}",
        description=description,
        color=color,
        timestamp=datetime.utcnow()
    )
    # Use the user's avatar as thumbnail (works in modern discord.py)
    try:
        embed.set_thumbnail(url=member.display_avatar.url)
    except Exception:
        pass

    embed.set_footer(text=f"{member.display_name} • {member.id}")
    return embed

# -------------------------
# Runtime commands to add new messages (in-memory only)
# -------------------------
@bot.command(name="addjoin")
@commands.has_permissions(administrator=True)
async def add_join(ctx, *, text: str):
    """Add a new join greeting (admin only). Use {display_name} inside text."""
    JOIN_GREETINGS.append(text)
    await ctx.send(f"✅ Added join greeting. Total join greetings: {len(JOIN_GREETINGS)}")

@bot.command(name="addleave")
@commands.has_permissions(administrator=True)
async def add_leave(ctx, *, text: str):
    """Add a new leave greeting (admin only). Use {display_name} inside text."""
    LEAVE_GREETINGS.append(text)
    await ctx.send(f"✅ Added leave greeting. Total leave greetings: {len(LEAVE_GREETINGS)}")

@bot.command(name="listmsgs")
@commands.has_permissions(administrator=True)
async def list_msgs(ctx):
    """List counts of greetings."""
    await ctx.send(f"Join messages: {len(JOIN_GREETINGS)} | Leave messages: {len(LEAVE_GREETINGS)}")

# -------------------------
# Events
# -------------------------
@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user} — Anime embed greetings are active.")
    # sanity check for channel
    ch = bot.get_channel(VC_CHANNEL_ID)
    if ch:
        logging.info(f"Target channel OK: {ch.name} ({ch.id})")
    else:
        logging.warning("Target channel not found. Make sure VC_CHANNEL_ID is correct and bot has access.")

@bot.event
async def on_voice_state_update(member, before, after):
    # ignore bots
    if member.bot:
        return

    # optional server check
    if SERVER_ID and member.guild.id != SERVER_ID:
        return

    channel = bot.get_channel(VC_CHANNEL_ID)

    # JOIN
    if before.channel is None and after.channel == channel:
        # choose random greeting — optionally include random chapter number
        greeting_template = random.choice(JOIN_GREETINGS)
        greeting = greeting_template.format(display_name=member.display_name, random_ch=random.randint(1,99))

        # make an embed for both DM and channel
        title = "Welcome!"
        embed = make_embed(title, greeting, member, kind="join")

        # send DM (embed preferred)
        try:
            await member.send(embed=embed)
        except Exception as e:
            # DMs closed — fallback to plain text in DM attempt (will also likely fail)
            logging.info(f"Couldn't DM {member.display_name}: {e}")

        # send embed to VC text channel
        try:
            await channel.send(embed=embed)
        except Exception as e:
            logging.info(f"Couldn't send join embed to channel: {e}")

    # LEAVE
    if before.channel == channel and after.channel is None:
        farewell_template = random.choice(LEAVE_GREETINGS)
        farewell = farewell_template.format(display_name=member.display_name, random_ch=random.randint(1,99))

        title = "Goodbye!"
        embed = make_embed(title, farewell, member, kind="leave")

        # DM farewell
        try:
            await member.send(embed=embed)
        except Exception as e:
            logging.info(f"Couldn't DM farewell to {member.display_name}: {e}")

        # channel farewell
        try:
            await channel.send(embed=embed)
        except Exception as e:
            logging.info(f"Couldn't send leave embed to channel: {e}")

# -------------------------
# Run
# -------------------------
bot.run(TOKEN)
