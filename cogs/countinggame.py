import discord
from discord.ext import commands
import json
import os
from config import settings

DATA_FILE = "counter.json"

 
 
class CountingGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_data()



    def load_data(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                self.data = json.load(f)
        else:
            self.data = {
                "channel_id": settings["COUNTING_GAME_CHANNEL_ID"],
                "current_number": 0,
                "last_user": None,
                "highscore": 0
            }

    def save_data(self):   
        with open(DATA_FILE, "w") as f:
            json.dump(self.data, f, indent=4)



    @commands.command()
    async def startcount(self, ctx):
        """Set the counting channel and start the game."""
        self.data["channel_id"] = ctx.channel.id
        self.data["last_user"] = None
        self.save_data()
        await ctx.send("Counting game started! Start with 1.")

    @commands.command()
    async def highscore(self, ctx):
        """displays highscore"""
        hs = self.data["highscore"]
        await ctx.send(f"highscore: {hs}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if message.content.startswith("!"):
            #await self.bot.process_commands(message)
            return
        
        if self.data["channel_id"] != message.channel.id :
            return

        # Try to convert message to integer
        # Check if same user twice
        if message.author.id == self.data["last_user"] and message.content != "restart" and message.content != "test":    #id is for testing    and message.author.id != 681888551981547563
            await message.delete()
            await message.channel.send(f"{message.author.mention}, you cannot count twice in a row!",delete_after = 7)
            # Do NOT reset the count, just warn

        else:
            if message.content == "test" and message.author.id == 681888551981547563:
                self.data["last_user"] = None
                await message.delete()
            else:
                try:
                    number = int(message.content)
                    # Check if correct number
                    if number != self.data["current_number"] + 1:
                        self.data["current_number"] = 0
                        self.data["last_user"] = None
                        await message.add_reaction("⛔")
                        await message.channel.send(f"{message.author.mention} counted wrong! Restarting at 1.")
                    
                    else:
                        # Correct count
                        await message.add_reaction("✅")
                        self.data["current_number"] = number
                        self.data["last_user"] = message.author.id

                        # Update highscore
                        if number > self.data["highscore"]:
                            self.data["highscore"] = number

                except ValueError:
                    # Not a number → restart counting
                    self.data["current_number"] = 0
                    self.data["last_user"] = None
                    await message.add_reaction("⛔")
                    await message.channel.send(f"{message.author.mention} broke the count! Restarting at 1.")
        
        self.save_data()
async def setup(bot: commands.Bot):
    await bot.add_cog(CountingGame(bot))