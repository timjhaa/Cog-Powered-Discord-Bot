import discord
from discord.ext import commands
import json
import ast
from config import  save_config
from config import settings as config



class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @commands.command()
    async def echo(self, ctx, *, message: str):
        if message is None:
            await ctx.send("Message is missing!",delete_after = 7)
        """Repeats what you say"""
        await ctx.send(message)


    @commands.command()
    async def setuproles(self,ctx):
        if ctx.channel.id == config["ROLE_CHANNEL_ID"]:
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

#Bot Config Commands:
    def is_config_channel(self, ctx):
        return ctx.channel.id == config["CONFIG_CHANNEL_ID"]
    
    @commands.command(name="help")
    async def custom_help(self, ctx):
        if self.is_config_channel(ctx):
            help_text = (
                "**Config-Befehle:**\n"
                "`!getc <key>` → Zeigt <wert> für <key> an\n"
                "`!setc <key> <wert>` → Ändert <wert> der Config , nur für nicht listen Werte!\n"
                "`!setlistc <key> <wert>` → Ersetzt <wert> LISTEN mit neuer Liste(Eingabe als Liste)\n"
                "`!addlistc <key> <wert>` → Fügt <wert> zu LISTEN hinzu\n"
                "`!remlistc <key> <wert>` → Entfernt <wert> von LISTEN\n"
                "`!showc` → Zeigt gesamte Config an\n"
            )
            await ctx.send(help_text)

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
                    self.bot.command_prefix = value  # Prefix live ändern
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