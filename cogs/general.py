import discord
from discord.ext import commands
import json
import ast
from config import save_config
from config import settings as config
import asyncio
import os
import shutil
from datetime import datetime
import zipfile

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---- Helper to update presence ----
    async def update_presence(self):
        # Get current STATUS
        stat_index = config.get("STATUS", [0, ["online"]])[0]
        stat_list = config.get("STATUS", [0, ["online"]])[1]
        status_name = stat_list[stat_index] if 0 <= stat_index < len(stat_list) else "online"
        status_enum = getattr(discord.Status, status_name.lower(), discord.Status.online)

        # Get current ACTIVITY_TYPE
        type_index = config.get("ACTIVITY_TYPE", [0, ["playing"]])[0]
        type_list = config.get("ACTIVITY_TYPE", [0, ["playing"]])[1]
        activity_type_name = type_list[type_index] if 0 <= type_index < len(type_list) else "playing"

        type_enum_map = {
            "playing": discord.ActivityType.playing,
            "listening": discord.ActivityType.listening,
            "watching": discord.ActivityType.watching,
            "streaming": discord.ActivityType.streaming,
            "competing": discord.ActivityType.competing
        }
        activity_type_enum = type_enum_map.get(activity_type_name.lower(), discord.ActivityType.playing)

        # Get activity string
        activity_str = str(config.get("ACTIVITY", "!help"))
        activity = discord.Activity(type=activity_type_enum, name=activity_str)

        await self.bot.change_presence(status=status_enum, activity=activity)

    # ---- General Commands ----
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

        amount = min(max(amount, 1), 100)
        messages = [msg async for msg in ctx.channel.history(limit=amount + 1)]

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
            await ctx.send("In diesem Channel kannst du dir Rollen vergeben, so kannst du Entscheiden was dich interressiert.")
            await ctx.send("Reagiere mit :thumbsup: um eine Rolle zu erhalten bzw. entferne die Reaktion um sie zu verlieren.")
            await ctx.send("-----------------------------------------------------------------------------------------------------------------------------")
            await ctx.send("-----------------------------------------------------------------------------------------------------------------------------")
            await ctx.send(":a: ALLGEMEIN:")
            await ctx.send("------------------------")
            await ctx.send("Gooner")
            await ctx.send("---> Mit dieser Rolle erlangst du Einblick in alle Channel")
            await ctx.send("------------")
            await ctx.send("Informatik-Junkie")
            await ctx.send("------------")
            await ctx.send(":b: Spiele:")
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
            embed.add_field(name="!setc <key> <wert>", value="Ändert <wert> der Config (STATUS & ACTIVITY_TYPE unterstützen Index)", inline=False)
            embed.add_field(name="!setlistc <key> <wert>", value="Ersetzt eine LISTE mit einer neuen Liste (Eingabe als Liste)", inline=False)
            embed.add_field(name="!addlistc <key> <wert>", value="Fügt <wert> zu einer LISTE hinzu", inline=False)
            embed.add_field(name="!remlistc <key> <wert>", value="Entfernt <wert> von einer LISTE", inline=False)
            embed.add_field(name="!showc", value="Zeigt die gesamte Config an", inline=False)
            embed.add_field(name="!clear <amount>", value="[RESTRICTED] deletes <amount> messages in the current channel, max 100", inline=False)
            embed.add_field(name="!reload <cog>", value="[RESTRICTED] reloads <cog>, reloads all when no cog is given", inline=False)
            embed.add_field(name="!shutdown", value="[RESTRICTED] shuts the bot down safely", inline=False)
            embed.add_field(name="!backup", value="[RESTRICTED] creates a zip backup of all .json files", inline=False)
            embed.add_field(name="!weeklytest", value="[RESTRICTED] creates leaderboard with weekly data", inline=False)
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
        if not self.is_config_channel(ctx):
            return

        if key in ["servernamelist_sec", "filter_list", "nni", "gni"]:
            await ctx.send(f"{key} ist eine Liste, anderer Befehl wird erwartet.")
            return

        if key not in config:
            await ctx.send("Key does not exist.")
            return

        old_value = config[key]

        # ---- Handle STATUS or ACTIVITY_TYPE as 2D list ----
        if key in ["STATUS", "ACTIVITY_TYPE"]:
            try:
                index = int(value)
            except ValueError:
                await ctx.send(f"⚠️ {key} index must be a number!")
                return

            lst = config[key][1]
            if not 0 <= index < len(lst):
                await ctx.send(f"⚠️ Invalid index! Must be between 0 and {len(lst)-1}")
                return

            try:
                config[key][0] = index
                await self.update_presence()
                save_config(config)
                await ctx.send(f"✅ {key} changed to `{lst[index]}`")
            except Exception as e:
                config[key] = old_value
                save_config(config)
                await ctx.send(f"⚠️ Failed to set {key}: {e}. Old value restored.")
            return

        # ---- Handle normal values ----
        value = value.strip()
        if value == "[]":
            new_value = []
        elif value.isdigit():
            new_value = int(value)
        else:
            new_value = value

        config[key] = new_value
        save_config(config)

        if key == "prefix":
            self.bot.command_prefix = config[key]

        await ctx.send(f"{key} wurde auf '{new_value}' geändert.")

    @commands.command()
    async def setlistc(self, ctx, key: str, *, value: str):
        if self.is_config_channel(ctx):
            if key in config and isinstance(config[key], list):
                try:
                    parsed_value = ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    await ctx.send("Falsche Eingabe!")
                    return

                if isinstance(parsed_value, list):
                    for i in range(len(parsed_value)):
                        if isinstance(parsed_value[i], str) and parsed_value[i].isdigit():
                            parsed_value[i] = int(parsed_value[i])
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
    async def addlistc(self, ctx, key: str, *, value: str):
        if self.is_config_channel(ctx):
            if key in config and isinstance(config[key], list):
                value_to_add = int(value) if value.isdigit() else value
                if value_to_add in config[key]:
                    await ctx.send(f"'{value_to_add}' ist bereits in {key}.")
                else:
                    config[key].append(value_to_add)
                    save_config(config)
                    await ctx.send(f"'{value_to_add}' wurde zu {key} hinzugefügt.")
            else:
                await ctx.send(f"'{key}' ist keine Liste in der Config.")

    @commands.command()
    async def remlistc(self, ctx, key: str, *, value: str):
        if self.is_config_channel(ctx):
            if key in config and isinstance(config[key], list):
                value_to_remove = int(value) if value.isdigit() else value
                if value_to_remove in config[key]:
                    config[key].remove(value_to_remove)
                    save_config(config)
                    await ctx.send(f"'{value_to_remove}' wurde aus {key} entfernt.")
                else:
                    await ctx.send(f"'{value_to_remove}' ist nicht in {key} enthalten.")
            else:
                await ctx.send(f"'{key}' ist keine Liste in der Config.")

    @commands.command()
    async def showc(self, ctx):
        if self.is_config_channel(ctx):
            await ctx.send("```json\n" + json.dumps(config, indent=4, ensure_ascii=False) + "```")

    @commands.command()
    async def backup(self, ctx):
        ADMIN_USER_ID = int(config["ADMIN_USER_ID"])
        if ctx.author.id != ADMIN_USER_ID:
            await ctx.send("⛔ You don't have permission to use this command.", delete_after=5)
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cog_dir = os.path.join(base_dir, "cogs")
        backup_root = os.path.join(base_dir, "backups")
        os.makedirs(backup_root, exist_ok=True)

        temp_folder = os.path.join(backup_root, f"backup_{timestamp}")
        os.makedirs(temp_folder, exist_ok=True)

        json_files = []
        for folder in [base_dir, cog_dir]:
            for file in os.listdir(folder):
                if file.endswith(".json"):
                    src_path = os.path.join(folder, file)
                    dest_path = os.path.join(temp_folder, f"{file}")
                    shutil.copy2(src_path, dest_path)
                    json_files.append(file)

        zip_filename = os.path.join(backup_root, f"backup_{timestamp}.zip")
        with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file in os.listdir(temp_folder):
                zipf.write(os.path.join(temp_folder, file), arcname=file)

        shutil.rmtree(temp_folder)

        await ctx.send(f"✅ Backup erstellt: `{os.path.basename(zip_filename)}` mit {len(json_files)} Dateien.")

async def setup(bot):
    await bot.add_cog(General(bot))
