import os
import discord
from discord.ext import commands
import edge_tts
import asyncio
import tempfile
from collections import deque
import logging
import random

# Set up logging
logging.basicConfig(level=logging.INFO)

# --- Configuration for Random Greetings ---
# Using more neutral greetings since the voice part is still under debug
JOIN_GREETINGS = [
    "Hello {display_name}, welcome to the VC!",
    "It seems {display_name} has joined us. Hi there.",
    "Welcome to the channel, {display_name}.",
]

LEAVE_GREETINGS = [
    "Goodbye {display_name}. See you next time.",
    "{display_name} has left the channel.",
    "Take care, {display_name}.",
]
# ------------------------------------------

# -------------------------
# Environment Variables
# -------------------------
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN environment variable not set")

try:
    # Set both IDs to the same channel ID from the user's latest message
    VC_ID = 1353875050809524267 # Hardcoded the confirmed VC ID
    TEXT_CHANNEL_ID = 1353875050809524267 # Same as VC_ID
except (TypeError, ValueError):
    # This block is now mostly for safety, as we hardcoded the ID
    raise RuntimeError("Critical: VC ID or Text Channel ID is invalid.")

try:
    SERVER_ID = int(os.getenv("SERVER_ID"))
except (TypeError, ValueError):
    SERVER_ID = None 

# -------------------------
# Intents & Bot
# -------------------------
intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
intents.members = True # Must be ON in Discord Developer Portal
intents.message_content = True 

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# Audio Queue
# -------------------------
audio_queue = deque()
is_playing = False

# -------------------------
# TTS Function
# -------------------------
async def speak(text):
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        filename = f.name
    
    communicate = edge_tts.Communicate(text, voice="en-US-JennyNeural") 
    await communicate.save(filename)
    return filename

# -------------------------
# Play Queue
# -------------------------
async def play_queue(vc):
    global is_playing
    if is_playing:
        return
    is_playing = True
    while audio_queue:
        audio_file = audio_queue.popleft()
        try:
            # Using simple 'ffmpeg' executable name, relying on nixPkgs install
            vc.play(
                discord.FFmpegPCMAudio(audio_file, executable="ffmpeg"), 
                after=lambda e: print(f'Player error: {e}') if e else None
            )
            
            while vc.is_playing():
                await asyncio.sleep(0.2)
        except Exception as e:
            # If this error appears, the FFmpeg installation is the problem.
            print("Error playing audio: FFmpeg not accessible or failed to run.", e) 
        finally:
            try:
                os.remove(audio_file)
            except Exception:
                pass
    is_playing = False

# -------------------------
# Events
# -------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    
    target_channel = bot.get_channel(VC_ID)
    if target_channel:
        print(f"SUCCESS: Target Channel found: {target_channel.name} (Used for both VC and Text)")
    else:
        print("CRITICAL: Target Channel ID is invalid. Check bot permissions and ID.")


@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    if SERVER_ID and member.guild.id != SERVER_ID:
        return

    target_channel = bot.get_channel(VC_ID)
    
    if not target_channel:
        return
        
    vc = target_channel.guild.voice_client

    # --- User joined the target VC ---
    if before.channel is None and after.channel == target_channel:
        
        # 1. Prepare greeting
        greeting = random.choice(JOIN_GREETINGS).format(display_name=member.display_name)
        
        # 2. Text Greeting (NEW REQUIREMENT)
        try:
            await target_channel.send(f"🔊 **{greeting}**")
        except Exception as e:
            print(f"Error sending text greeting: {e}")

        # 3. Voice Logic (Try to speak and join VC)
        audio_file = await speak(greeting)
        audio_queue.append(audio_file)

        if not vc:
            try:
                vc = await target_channel.connect()
            except Exception as e:
                print("Failed to connect to VC:", e)
                return

        await play_queue(vc)

    # --- User left the target VC ---
    if before.channel == target_channel and after.channel is None:
        
        # 1. Prepare farewell
        farewell = random.choice(LEAVE_GREETINGS).format(display_name=member.display_name)
        
        # 2. Text Farewell (NEW REQUIREMENT)
        try:
            await target_channel.send(f"👋 **{farewell}**")
        except Exception as e:
            print(f"Error sending text farewell: {e}")
        
        # 3. Voice Logic (Play and Disconnect)
        audio_file = await speak(farewell)
        audio_queue.append(audio_file)

        if vc:
            await play_queue(vc)

        await asyncio.sleep(2)
        try:
            # Disconnect if the bot is the only one left
            if vc and vc.channel and len(vc.channel.members) == 1 and vc.channel.members[0].id == bot.user.id:
                await vc.disconnect()
        except Exception as e:
            print("Error disconnecting:", e)

# -------------------------
# Run Bot
# -------------------------
bot.run(TOKEN)
