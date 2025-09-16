
from discord.ext import commands, tasks
from config import COUNTING_GAME_CHANNEL_ID

 
 
class ExampleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.my_task.start()  # Starte die wiederkehrende Aufgabe

    def cog_unload(self):
        self.my_task.cancel()  # Stoppe die Aufgabe beim Entladen des Cogs

    @tasks.loop(seconds=2600)  # Führt die Aufgabe alle xx Sekunden aus
    async def my_task(self):
        
        pass
    
    @my_task.before_loop
    async def before_my_task(self):
        await self.bot.wait_until_ready()  # Warten bis der Bot bereit ist
        print("Task wird gestartet...")

async def setup(bot):
    await bot.add_cog(ExampleCog(bot))