import discord
from discord.ext import commands
from discord import app_commands
import traceback
from config import settings as config
import io
import asyncio


class ErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Register global slash command error handler
        self.bot.tree.on_error = self.on_app_command_error

    # Slash command (app command) errors
    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        print(f"[on_app_command_error] {error!r}")
        try:
            await self.report_error(error, interaction=interaction)
        except Exception as e:
            print(f"⚠️ Failed inside on_app_command_error: {e}")

    # Prefix command errors
    @commands.Cog.listener()
    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ):
        if isinstance(error, commands.CommandNotFound):
            return
        print(f"[on_command_error] {error!r}")
        try:
            await self.report_error(error, ctx=ctx)
        except Exception as e:
            print(f"⚠️ Failed inside on_command_error: {e}")


    # Global event errors (sync)
    def on_error(self, event_method: str, *args, **kwargs):
        tb = traceback.format_exc() or "No traceback available."
        print(f"[on_error] {event_method}: {tb}")
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.report_error(tb, event=event_method))
        except RuntimeError:
            # Fallback if no running loop
            asyncio.run(self.report_error(tb, event=event_method))
        except Exception as e:
            print(f"⚠️ Failed inside on_error: {e}")

    async def report_error(
        self,
        error,
        ctx: commands.Context = None,
        interaction: discord.Interaction = None,
        event: str = None,
    ):
        # Format traceback
        if isinstance(error, BaseException):
            tb = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ) if error.__traceback__ else "".join(traceback.format_exception_only(type(error), error))
        else:
            tb = str(error)

        tb = tb or "No traceback available."

        # Always log to console
        print("------ ERROR TRACEBACK ------")
        print(tb)
        print("-----------------------------")

        # Embed for Discord
        embed = discord.Embed(
            title="❌ Bot Error",
            description=f"```py\n{tb[:2000]}\n```",
            color=discord.Color.red(),
        )

        if ctx:
            cmd_name = getattr(ctx.command, "qualified_name", "Unknown")
            embed.add_field(name="Command", value=cmd_name, inline=False)
            guild_text = ctx.guild.name if ctx.guild else "DMs"
            embed.set_footer(text=f"User: {ctx.author} | Guild: {guild_text}")

        elif interaction:
            cmd_name = getattr(interaction.command, "name", "Unknown")
            embed.add_field(name="Command", value=cmd_name, inline=False)
            guild_text = interaction.guild.name if interaction.guild else "DMs"
            embed.set_footer(text=f"User: {interaction.user} | Guild: {guild_text}")

        elif event:
            embed.add_field(name="Event", value=event, inline=False)
            embed.set_footer(text="Error in event loop")

        # Determine if traceback needs a file
        file_needed = len(tb) > 2000

        @staticmethod
        def make_file() -> discord.File:
            return discord.File(io.BytesIO(tb.encode()), filename="traceback.txt")

        # Send to error channel
        channel_id = config.get("ERROR_CHANNEL_ID")
        if channel_id:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
                if file_needed:
                    await channel.send(embed=embed, file=make_file())
                else:
                    await channel.send(embed=embed)
            except Exception as e:
                print(f"⚠️ Failed to send error to channel: {e}")
        else:
            print("⚠️ Error channel not found or invalid ID.")

        # DM designated user
        user_id = config.get("ERROR_USER_ID")
        if user_id:
            try:
                user = await self.bot.fetch_user(int(user_id))
                if file_needed:
                    await user.send(embed=embed, file=make_file())
                else:
                    await user.send(embed=embed)
            except discord.Forbidden:
                print("⚠️ Could not DM the error user.")
            except Exception as e:
                print(f"⚠️ Failed to send error to user: {e}")
        else:
            print("⚠️ Error user not found or invalid ID.")


async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandler(bot))
