import discord
from discord.ext import commands
import json
import ast
from config import save_config
from config import settings as config
import asyncio

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def echo(self, ctx, *, message: str):
        if not message:
            await ctx.send("Message is missing!", delete_after=7)
            return
        await ctx.send(message)

    @commands.command()
    async def clear(self, ctx, amount: int = 100):
        ADMIN_USER_ID = int(config["ADMIN_USER_ID"])

        if ctx.author.id != ADMIN_USER_ID:
            await ctx.send("⛔ You don't have permission to use this command.", delete_after=5)
            return

        # Clamp between 1 and 100
        amount = min(max(amount, 1), 100)

        # Fetch messages using async iteration (no flatten)
        messages = [msg async for msg in ctx.channel.history(limit=amount + 1)]  # +1 to include command message

        deleted_count = 0
        for msg in messages:
            try:
                await msg.delete()
                deleted_count += 1
            except discord.NotFound:
                continue
            except discord.Forbidden:
                await ctx.send("⛔ I don't have permission to delete some messages.", delete_after=5)
                break
            except discord.HTTPException:
                continue

        await ctx.send(f"✅ Deleted {max(deleted_count - 1, 0)} messages.", delete_after=5)

    @commands.command()
    async def setuproles(self, ctx):
        if ctx.channel.id == config["ROLE_CHANNEL_ID"] and ctx.author.guild_permissions.administrator:
            deleted = await ctx.channel.purge(limit=100)
            await ctx.send(f"{len(deleted)} Nachrichten gelöscht.", delete_after=5)
            await ctx.send(f"In diesem Channel kannst du dir Rollen vergeben, so kannst du Entscheiden was dich interressiert.")
            await ctx.send(f"Reagiere mit :thumbsup: um eine Rolle zu erhalten bzw. entferne die Reaktion um sie zu verlieren.")
            await ctx.send("-----------------------------------------------------------------------------------------------------------------------------")
            await ctx.send("-----------------------------------------------------------------------------------------------------------------------------")
            await ctx.send(f":a: ALLGEMEIN:")
            await ctx.send("------------------------")
            await ctx.send(f"Gooner")
            await ctx.send(f"---> Mit dieser Rolle erlangst du Einblick in alle Channel")
            await ctx.send("------------")
            await ctx.send("Informatik-Junkie")
            await ctx.send("------------")
            await ctx.send(f":b: Spiele:")
            await ctx.send("------------------------")
            await ctx.send("Minecraft")
            await ctx.send("------------")
            await ctx.send("Terraria")
            await ctx.send("------------")
            await ctx.send("Satisfactory")
            await ctx.send("------------")
            await ctx.send("PEAK")
            await ctx.send("------------")
            await ctx.send("Riot-Games")

    # ---- Bot Config Commands ----
    def is_config_channel(self, ctx):
        return ctx.channel.id == config["CONFIG_CHANNEL_ID"]

    @commands.command(name="help")
    async def custom_help(self, ctx):
        embed = discord.Embed(
            title="Gooner Bot Hilfe:",
            color=discord.Color.blue(),
            timestamp=ctx.message.created_at
        )

        if self.is_config_channel(ctx):
            embed.description = "Hier sind die Config-Befehle:"
            embed.add_field(name="!getc <key>", value="Zeigt den Wert für <key> an", inline=False)
            embed.add_field(name="!setc <key> <wert>", value="Ändert <wert> der Config (nur für nicht-Listen Werte)", inline=False)
            embed.add_field(name="!setlistc <key> <wert>", value="Ersetzt eine LISTE mit einer neuen Liste (Eingabe als Liste)", inline=False)
            embed.add_field(name="!addlistc <key> <wert>", value="Fügt <wert> zu einer LISTE hinzu", inline=False)
            embed.add_field(name="!remlistc <key> <wert>", value="Entfernt <wert> von einer LISTE", inline=False)
            embed.add_field(name="!showc", value="Zeigt die gesamte Config an", inline=False)
            embed.add_field(name="!clear <amount>", value="[RESTRICTED] deletes <amount> messages in the current channel, max 100", inline=False)
            embed.add_field(name="!reload <cog>", value="[RESTRICTED] reloads <cog>, reloads all when no cog is given", inline=False)
            embed.add_field(name="!shutdown", value="[RESTRICTED] shuts the bot down safely", inline=False)
        else:
            embed.description = "Hier sind die allgemeinen Bot-Befehle:"
            embed.add_field(name="!echo <nachricht>", value="Bot wiederholt deine Nachricht", inline=False)
            embed.add_field(name="!stats <member>", value="showes playtime stats off <member>, if no <member> is given, shows stats of author", inline=False)
            embed.add_field(name="!leaderboard", value="showes alltime-playtime leaderboard", inline=False)
            embed.add_field(name="!addbirthday <MM-DD>", value="Speichert deinen Geburtstag, um dich daran zu erinnern", inline=False)
            embed.add_field(name="!removebirthday", value="Löscht deinen gespeicherten Geburtstag", inline=False)

        embed.add_field(name="SEE FULL DOCUMENTATION", value="https://github.com/timjhaa/Cog-Powered-Discord-Bot", inline=False)
        embed.set_footer(text=f"Angefordert von {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)

    @commands.command()
    async def getc(self, ctx, key: str):
        if self.is_config_channel(ctx):
            if key in config:
                await ctx.send(f"{key} = {config[key]}")
            else:
                await ctx.send("Wrong Key")

    @commands.command()
    async def setc(self, ctx, key: str, *, value: str):
        if self.is_config_channel(ctx):
            if key in ["servernamelist_sec", "filter_list", "nni", "gni"]:
                await ctx.send(f"{key} ist eine Liste, anderer Befehl wird erwartet.")
            elif key in config:
                config[key] = value
                save_config(config)
                await ctx.send(f"{key} wurde auf '{value}' geändert.")
                if key == "prefix":
                    self.bot.command_prefix = value
            else:
                await ctx.send("Key does not exist.")

    @commands.command()
    async def setlistc(self, ctx, key: str, *, value: str):
        if self.is_config_channel(ctx):
            if key in config and isinstance(config[key], list):
                try:
                    parsed_value = ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    parsed_value = value
                if isinstance(parsed_value, list):
                    config[key] = parsed_value
                    save_config(config)
                    await ctx.send(f"{key} wurde auf '{parsed_value}' geändert.")
                    if key == "prefix":
                        self.bot.command_prefix = parsed_value
                else:
                    await ctx.send("Falsche Eingabe!")
            else:
                await ctx.send("Dieser Schlüssel existiert nicht in der Config oder ist keine Liste.")

    @commands.command()
    async def addlistc(self, ctx, key: str, value: str):
        if self.is_config_channel(ctx):
            if key in config and isinstance(config[key], list):
                if value in config[key]:
                    await ctx.send(f"'{value}' ist bereits in {key}.")
                else:
                    config[key].append(value)
                    save_config(config)
                    await ctx.send(f"'{value}' wurde zu {key} hinzugefügt.")
            else:
                await ctx.send(f"'{key}' ist keine Liste in der Config.")


    @commands.command()
    async def remlistc(self, ctx, key: str, value: str):
        if self.is_config_channel(ctx):
            if key in config and isinstance(config[key], list):
                if value in config[key]:
                    config[key].remove(value)
                    save_config(config)
                    await ctx.send(f"'{value}' wurde aus {key} entfernt.")
                else:
                    await ctx.send(f"'{value}' ist nicht in {key} enthalten.")
            else:
                await ctx.send(f"'{key}' ist keine Liste in der Config.")

    @commands.command()
    async def showc(self, ctx):
        if self.is_config_channel(ctx):
            await ctx.send("```json\n" + json.dumps(config, indent=4, ensure_ascii=False) + "```")

async def setup(bot):
    await bot.add_cog(General(bot))
