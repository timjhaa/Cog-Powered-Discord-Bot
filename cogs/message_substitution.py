import discord
from discord.ext import commands
from config import settings
class WortErkennung(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    # Event Listener for messages
    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore Bot messages
        if message.author == self.bot.user or message.author.bot:
            return
        
        trigger_wort = settings["trigger_word"]
        tm = settings["TRIGGER_MESSAGE"]
        #is trigger_word in message
        if trigger_wort in message.content.lower():
            await message.delete()
            await message.channel.send(f"{tm}")

# Setup-Funktion for Cog
async def setup(bot):
    await bot.add_cog(WortErkennung(bot))