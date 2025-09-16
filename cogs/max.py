import discord
from discord.ext import commands
from config import settings
class WortErkennung(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Event Listener für Nachrichten
    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignoriere Nachrichten vom Bot selbst
        if message.author == self.bot.user:
            return
        
        trigger_wort = "max"
        tm = settings["TRIGGER_MESSAGE"]
        # Prüfen ob Wort im Inhalt der Nachricht vorkommt
        if trigger_wort in message.content.lower():
            await message.delete()
            await message.channel.send(f"{tm}")

# Setup-Funktion für das Cog
async def setup(bot):
    await bot.add_cog(WortErkennung(bot))