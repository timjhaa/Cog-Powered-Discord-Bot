import discord
from discord.ext import commands
import os
import asyncio
import logging
import signal
from dotenv import load_dotenv
from config import settings

# ---- Logger setup ----
logging.basicConfig(
    filename='discord.log',
    filemode='w',
    level=logging.DEBUG,
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s'
)

# ---- Bot setup ----
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
intents.reactions = True
intents.guilds = True

bot = commands.Bot(command_prefix=settings.get("PREFIX", "!"), intents=intents, help_command=None)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ---- Helper function to load/reload cogs ----
async def load_or_reload_cog(cog_name: str = None):
    success = []
    reloaded = []
    failed = []

    if cog_name:
        cog_path = f"cogs.{cog_name}"
        try:
            if cog_path in bot.extensions:
                await bot.reload_extension(cog_path)
                reloaded.append(cog_name)
            else:
                await bot.load_extension(cog_path)
                success.append(cog_name)
        except Exception as e:
            failed.append(f"{cog_name}: {e}")
    else:
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and filename != "__init__.py":
                cog_path = f"cogs.{filename[:-3]}"
                try:
                    if cog_path in bot.extensions:
                        await bot.reload_extension(cog_path)
                        reloaded.append(filename[:-3])
                    else:
                        await bot.load_extension(cog_path)
                        success.append(filename[:-3])
                except Exception as e:
                    failed.append(f"{filename[:-3]}: {e}")

    print(f"Loaded: {success}, Reloaded: {reloaded}, Failed: {failed}")
    return {"success": success, "reloaded": reloaded, "failed": failed}

# ---- Bot events ----
@bot.event
async def on_ready():
    await asyncio.sleep(1)
    LOG_CHANNEL = bot.get_channel(settings.get("LOG_CHANNEL_ID"))
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

    if LOG_CHANNEL:
        await LOG_CHANNEL.send("####----Bot restarted----####")
        await LOG_CHANNEL.send(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
        await LOG_CHANNEL.send("------")

    activity = discord.Game(name="!help")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    
    results = await load_or_reload_cog()

    if LOG_CHANNEL:
        embed = discord.Embed(
            title="💟 Bot Ready",
            color=discord.Color.green() if not results["failed"] else discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )
        if results["success"]:
            embed.add_field(name=f"✅ Loaded ({len(results['success'])})", value="\n".join(results["success"]), inline=True)
        if results["reloaded"]:
            embed.add_field(name=f"⚠️ Reloaded ({len(results['reloaded'])})", value="\n".join(results["reloaded"]), inline=True)
        if results["failed"]:
            embed.add_field(name=f"❌ Failed ({len(results['failed'])})", value="\n".join(results["failed"]), inline=False)
        total = len(results["success"]) + len(results["reloaded"]) + len(results["failed"])
        embed.set_footer(text=f"Total cogs processed: {total}")
        await LOG_CHANNEL.send(embed=embed)
    
    print("💟 BOT IS READY")

# ---- Reload command (admin-safe) ----
@bot.command(name="reload")
async def reload_cog(ctx, cog_name: str = None):
    try:
        admin_id = int(settings.get("ADMIN_USER_ID", 0))
    except Exception:
        admin_id = 0

    if ctx.author.id != admin_id:
        await ctx.send("❌ You do not have permission to run this command.")
        return

    try:
        results = await load_or_reload_cog(cog_name)
    except Exception as e:
        await ctx.send(f"❌ Error loading cog: {e}")
        return

    embed = discord.Embed(
        title="🔄 Cog Reload Command",
        color=discord.Color.green() if not results["failed"] else discord.Color.red(),
        timestamp=discord.utils.utcnow()
    )

    if results["success"]:
        embed.add_field(name=f"✅ Loaded ({len(results['success'])})", value="\n".join(results["success"]), inline=True)
    if results["reloaded"]:
        embed.add_field(name=f"⚠️ Reloaded ({len(results['reloaded'])})", value="\n".join(results["reloaded"]), inline=True)
    if results["failed"]:
        embed.add_field(name=f"❌ Failed ({len(results['failed'])})", value="\n".join(results["failed"]), inline=False)

    total = len(results["success"]) + len(results["reloaded"]) + len(results["failed"])
    embed.set_footer(text=f"Total cogs processed: {total}")

    LOG_CHANNEL = bot.get_channel(settings.get("LOG_CHANNEL_ID"))
    if LOG_CHANNEL and LOG_CHANNEL.id != ctx.channel.id:
        await LOG_CHANNEL.send(embed=embed)
    await ctx.send(embed=embed)

# ---- Shutdown command (admin-safe) ----
@bot.command(name="shutdown")
async def shutdown(ctx):
    try:
        admin_id = int(settings.get("ADMIN_USER_ID", 0))
    except Exception:
        admin_id = 0

    if ctx.author.id != admin_id:
        await ctx.send("❌ You do not have permission to run this command.")
        return

    LOG_CHANNEL = bot.get_channel(settings.get("LOG_CHANNEL_ID"))
    if LOG_CHANNEL:
        await LOG_CHANNEL.send("####----Bot is shutting down----####")
        await LOG_CHANNEL.send(f"🛑 Shutdown initiated by: {ctx.author}")
    await ctx.send("Bot is shutting down safely...")
    await bot.close()

# ---- Friendly error handler ----
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You do not have the required permissions to run this command.")
    else:
        raise error
    
# ---- Signal handling for safe shutdown ----
def handle_exit(*args):
    LOG_CHANNEL = bot.get_channel(settings.get("LOG_CHANNEL_ID"))
    if LOG_CHANNEL:
        asyncio.create_task(LOG_CHANNEL.send("⚡ Bot is shutting down due to termination signal."))
    print("💀 Bot terminated via signal.")
    asyncio.create_task(bot.close())

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

# ---- Bot start ----
async def main():
    async with bot:
        await bot.start(TOKEN)

asyncio.run(main())
