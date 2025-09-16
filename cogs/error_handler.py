import discord
from discord.ext import commands
from discord import app_commands
import traceback
import config


class ErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Global handler for slash commands
        @bot.tree.error
        async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            print(f"[on_app_command_error] {error!r}")
            await self.report_error(error, interaction=interaction)

    # Prefix command errors
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandNotFound):
            return
        print(f"[on_command_error] {error!r}")
        await self.report_error(error, ctx=ctx)

    # Global event errors
    @commands.Cog.listener()
    async def on_error(self, event_method: str, *args, **kwargs):
        error = traceback.format_exc()
        print(f"[on_error] {event_method}: {error}")
        await self.report_error(error, event=event_method)

    async def report_error(self, error, ctx: commands.Context = None, interaction: discord.Interaction = None, event: str = None):
        if isinstance(error, Exception):
            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        else:
            tb = str(error)

        # Always log
        print("------ ERROR TRACEBACK ------")
        print(tb)
        print("-----------------------------")

        embed = discord.Embed(
            title="❌ Bot Error",
            description=f"```py\n{tb[:4000]}\n```",
            color=discord.Color.red()
        )

        if ctx:
            embed.add_field(name="Command", value=ctx.message.content, inline=False)
            embed.set_footer(text=f"User: {ctx.author} | Guild: {ctx.guild}")
        elif interaction:
            embed.add_field(name="Command", value=interaction.command.name if interaction.command else "Unknown", inline=False)
            embed.set_footer(text=f"User: {interaction.user} | Guild: {interaction.guild}")
        elif event:
            embed.add_field(name="Event", value=event, inline=False)
            embed.set_footer(text="Error in event loop")

        # Send to error channel
        channel = self.bot.get_channel(config.ERROR_CHANNEL_ID)
        if channel:
            try:
                await channel.send(embed=embed)
            except Exception as e:
                print(f"⚠️ Failed to send error to channel: {e}")

        # DM designated user
        user = self.bot.get_user(config.ERROR_USER_ID)
        if user:
            try:
                await user.send(embed=embed)
            except discord.Forbidden:
                print("⚠️ Could not DM the error user (maybe DMs are disabled).")


async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandler(bot))
