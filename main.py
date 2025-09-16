import discord
from discord.ext import commands
import os
import asyncio
from config import settings
import logging
from dotenv import load_dotenv
#----logger-------------------------------------------------------------------------------------------------------------------------------------------------------------

logging.basicConfig(
    filename='discord.log',  # Log file
    filemode='w',             # 'w' = overwrite, 'a' = append
    level=logging.DEBUG,       # INFO: Minimum log level to capture
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s'
)
#--bot-setup------------------------------------------------------------------------------------------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
intents.reactions = True
intents.guilds = True
bot = commands.Bot(command_prefix=settings["PREFIX"], intents=intents,help_command=None)
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

@bot.event
async def on_ready():
    await asyncio.sleep(1)
    LOG_CHANNEL = bot.get_channel(settings["LOG_CHANNEL_ID"])
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    if LOG_CHANNEL:
        await LOG_CHANNEL.send("####----Bot restarted----####")
        await LOG_CHANNEL.send(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
        await LOG_CHANNEL.send("------")
    else:
        print("LOG_CHANNEL returned None")
    await load_cogs()


async def load_cogs():
    LOG_CHANNEL = bot.get_channel(settings["LOG_CHANNEL_ID"])
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and filename != "__init__.py":
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                print(f"✅ Loaded {filename}")
                if LOG_CHANNEL:
                    await LOG_CHANNEL.send(f"✅ Loaded {filename}")
            except Exception as e:
                print(f"❌ Failed to load {filename}: {e}")
                if LOG_CHANNEL:
                    await LOG_CHANNEL.send(f"❌ Failed to load {filename}: {e}")
    await LOG_CHANNEL.send(f"BOT IS READY")
    print("BOT IS READY")


async def main():
    async with bot:
        await bot.start(TOKEN)





asyncio.run(main())