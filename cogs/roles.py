import discord
from discord.ext import commands
from config import settings as config
from config import sendlog


class ReactionRoleCog(commands.Cog):
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config
        self.logchannel_id = config["LOG_CHANNEL_ID"]  # ID speichern, kein Objekt

    def get_logchannel(self):
        """Gibt das TextChannel-Objekt zurück"""
        return self.bot.get_channel(self.logchannel_id)


    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):

        if payload.channel_id != self.config["ROLE_CHANNEL_ID"]:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        logchannel = self.get_logchannel()  # ✅ jetzt ein TextChannel-Objekt
        if logchannel is None:
            print("❌ Logchannel nicht gefunden!")
            return

        member = await guild.fetch_member(payload.user_id)
        if member.bot:
            return

        channel = guild.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)

        role_name = message.content.strip()
        role = discord.utils.get(guild.roles, name=role_name)

        if role is None:
            await sendlog(logchannel, f"❌ {message.author}s Role: {role_name} existiert nicht")
            return

        await member.add_roles(role)
        await sendlog(logchannel, f"✅ {member.name} hat die Rolle: {role.name} erhalten")
        await channel.send(f"✅ {member.name} hat die Rolle: {role.name} erhalten",delete_after = 12)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.channel_id != self.config["ROLE_CHANNEL_ID"]:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        logchannel = self.get_logchannel()
        if logchannel is None:
            print("❌ Logchannel nicht gefunden!")
            return

        channel = guild.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        role_name = message.content.strip()
        role = discord.utils.get(guild.roles, name=role_name)
        member = guild.get_member(payload.user_id)

        if role and member and not member.bot:
            await member.remove_roles(role)
            await sendlog(logchannel, f"❌ {member.name} hat die Rolle: {role.name} verloren")
            await channel.send(f"❌ {member.name} hat die Rolle: {role.name} verloren",delete_after = 12)


# Setup-Funktion, damit der Cog geladen werden kann
async def setup(bot):

    await bot.add_cog(ReactionRoleCog(bot, config))