import discord
from discord.ext import commands, tasks
import json
from datetime import datetime
from config import settings

class BirthdayChecker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_birthdays.start()  # start background task

    def cog_unload(self):
        self.check_birthdays.cancel()

    def load_birthdays(self):
        try:
            with open("birthdays.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_birthdays(self, birthdays):
        with open("birthdays.json", "w") as f:
            json.dump(birthdays, f, indent=4)

    @tasks.loop(hours=8)
    async def check_birthdays(self):
        await self.bot.wait_until_ready()
        lc = self.bot.get_channel(settings["LOG_CHANNEL_ID"])

        birthdays = self.load_birthdays()
        today = datetime.now().strftime("%m-%d")  # format MM-DD

        # channel ID where birthday messages will be sent
        channel_id = settings["BIRTHDAY_CHANNEL_ID"] 
 
        channel = self.bot.get_channel(channel_id)

        if not channel:
            return

        for user_id, data in birthdays.items():
            birth_date, greeted = data

            if birth_date == today and not greeted:
                user = self.bot.get_user(int(user_id))
                ms = settings["BIRTHDAY_MESSAGE"]
                if user:
                    await channel.send(f"@everyone 🎉 It's {user.name}'s birthday today! 🎂")  
                    await channel.send(f"{ms}")                                     
                    await lc.send(f"➡️It's {user.name}'s birthday today! 🎂")
                else:
                    await channel.send(f"@everyone 🎉 It's someone's birthday today! 🎂")  
                    await channel.send(f"{ms}")
                    await lc.send(f"➡️It's someone's birthday today!--> could not find user")
                birthdays[user_id][1] = True
            elif birth_date != today and greeted: 
                birthdays[user_id][1] = False
        if lc:
            await lc.send(f"➡️Birthdays checked")
        self.save_birthdays(birthdays)
 
    @check_birthdays.before_loop
    async def before_check_birthdays(self):
        await self.bot.wait_until_ready()
    
    # Command to add birthday
    @commands.command(name="addbirthday")
    async def add_birthday(self, ctx, date: str):
        """
        Add your birthday in MM-DD format.
        Example: !addbirthday 09-16
        """
        if ctx.author.bot == True:
            return
        try:
            datetime.strptime(date, "%m-%d")  # validate date format
        except ValueError:
            await ctx.send("❌ Please use a valid date format: MM-DD")
            return

        birthdays = self.load_birthdays()
        user_id = str(ctx.author.id)

        birthdays[user_id] = [date, False]
        self.save_birthdays(birthdays)

        await ctx.send(f"✅ Your birthday has been set to {date}, {ctx.author.mention}!")

    # Command to remove birthday
    @commands.command(name="removebirthday")
    async def remove_birthday(self, ctx):
        """
        Remove your stored birthday.
        Example: !removebirthday
        """
        birthdays = self.load_birthdays()
        user_id = str(ctx.author.id)

        if user_id in birthdays:
            del birthdays[user_id]
            self.save_birthdays(birthdays)
            await ctx.send(f"✅ Your birthday has been removed, {ctx.author.mention}!")
        else:
            await ctx.send("❌ You don't have a birthday stored!")


async def setup(bot):
    await bot.add_cog(BirthdayChecker(bot))
