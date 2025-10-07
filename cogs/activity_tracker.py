import discord
from discord.ext import commands, tasks
import json
from datetime import datetime
from config import settings

GAME_KEYWORDS = ["game"]

def current_timestamp():
    return int(datetime.utcnow().timestamp())
 
class ActivityTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_file = "activity_data.json"
        self.weekly_file = "weekly_data.json"
        self.blacklist = set(a.lower() for a in settings.get("activity_blacklist", []))

        self.activity_times = {}
        self.voice_times = {}
        self.weekly_totals = {}
        self.weekly_voice = {}

        self.save_interval = settings.get("save_interval", 60)
        self.update_interval = settings.get("update_interval", 10)
        self.leaderboard_channel_id = settings["LEADERBOARD_CHANNEL_ID"]

        self.load_data()

        # Start tasks
        self.auto_save.change_interval(seconds=self.save_interval)
        self.update_ongoing.change_interval(seconds=self.update_interval)
        self.auto_save.start()
        self.update_ongoing.start()
        self.leaderboard_task.start()

        self.bot.loop.create_task(self._init_voice_sessions())
        self.bot.loop.create_task(self._init_activities())

    def cog_unload(self):
        self.auto_save.cancel()
        self.update_ongoing.cancel()
        self.leaderboard_task.cancel()
        self.save_data()

    # -------------------- Initialization --------------------

    async def _init_voice_sessions(self):
        await self.bot.wait_until_ready()
        now = current_timestamp()
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if member.bot:
                        continue
                    user_id = str(member.id)
                    self._init_voice(user_id, now)

    async def _init_activities(self):
        await self.bot.wait_until_ready()
        now = current_timestamp()
        for guild in self.bot.guilds:
            for member in guild.members:
                if member.bot:
                    continue
                user_id = str(member.id)
                self.activity_times.setdefault(user_id, {})
                self.weekly_totals.setdefault(user_id, {})

                current_activities = {
                    getattr(act, "name", str(act))
                    for act in member.activities
                    if act.type != discord.ActivityType.custom
                }

                for act_name in current_activities:
                    for data in (self.activity_times[user_id], self.weekly_totals[user_id]):
                        data.setdefault(act_name, {"main": 0, "duplicate": 0, "ongoing_start": now})
                        data[act_name]["ongoing_start"] = now

    def _init_voice(self, user_id, now):
        self.voice_times.setdefault(user_id, {"total": 0, "ongoing_start": now})
        self.weekly_voice.setdefault(user_id, {"total": 0, "ongoing_start": now})

    # -------------------- Data Load / Save --------------------

    def load_data(self):
        def load_file(path, default):
            try:
                with open(path) as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return default

        data = load_file(self.data_file, {})
        self.activity_times = data.get("activity_times", {})
        self.voice_times = data.get("voice_times", {})

        weekly = load_file(self.weekly_file, {})
        self.weekly_totals = weekly.get("activity_times", {})
        self.weekly_voice = weekly.get("voice_times", {})

        # Reset ongoing_start on restart
        for user_dict in (self.activity_times, self.weekly_totals):
            for activities in user_dict.values():
                for stats in activities.values():
                    stats["ongoing_start"] = None

        for user_dict in (self.voice_times, self.weekly_voice):
            for stats in user_dict.values():
                stats["ongoing_start"] = None

    def save_data(self):
        try:
            with open(self.data_file, "w") as f:
                json.dump({"activity_times": self.activity_times, "voice_times": self.voice_times}, f, indent=4)
            with open(self.weekly_file, "w") as f:
                json.dump({"activity_times": self.weekly_totals, "voice_times": self.weekly_voice}, f, indent=4)
        except Exception as e:
            print(f"Error saving data: {e}")

    # -------------------- Tasks --------------------

    @tasks.loop(seconds=60)  # placeholder, set dynamically in __init__
    async def auto_save(self):
        await self.bot.wait_until_ready()
        self.save_data()

    @tasks.loop(seconds=10)  # placeholder, set dynamically in __init__
    async def update_ongoing(self):
        await self.bot.wait_until_ready()
        await self._update_active_users_once()

    async def _update_active_users_once(self):
        now = current_timestamp()

        # Activities
        for user_id, activities in self.weekly_totals.items():
            for act_name, stats in activities.items():
                start = stats.get("ongoing_start")
                if start is None:
                    continue
                elapsed = now - start
                target_dict = self.activity_times.setdefault(user_id, {}).setdefault(act_name, {"main": 0, "duplicate": 0, "ongoing_start": now})
                if act_name.lower() in self.blacklist:
                    stats["duplicate"] += elapsed
                    target_dict["duplicate"] += elapsed
                else:
                    stats["main"] += elapsed
                    target_dict["main"] += elapsed
                stats["ongoing_start"] = target_dict["ongoing_start"] = now

        # Voice
        for user_id, data in self.voice_times.items():
            start = data.get("ongoing_start")
            if not start:
                continue
            elapsed = now - start
            data["total"] += elapsed
            weekly_data = self.weekly_voice.setdefault(user_id, {"total": 0, "ongoing_start": start})
            weekly_data["total"] += elapsed
            data["ongoing_start"] = weekly_data["ongoing_start"] = now

    # -------------------- Activity Update Helpers --------------------

    def _update_activity_on_change(self, user_id, acts, start=True):
        now = current_timestamp()
        self.activity_times.setdefault(user_id, {})
        self.weekly_totals.setdefault(user_id, {})
        for act_name in acts:
            for data in (self.activity_times[user_id], self.weekly_totals[user_id]):
                entry = data.setdefault(act_name, {"main": 0, "duplicate": 0, "ongoing_start": None})
                if start:
                    entry["ongoing_start"] = now
                else:
                    ongoing = entry.get("ongoing_start")
                    if ongoing:
                        elapsed = now - ongoing
                        if act_name.lower() in self.blacklist:
                            entry["duplicate"] += elapsed
                        else:
                            entry["main"] += elapsed
                    entry["ongoing_start"] = None

    # -------------------- Event Listeners --------------------

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        if after.bot:
            return
        user_id = str(after.id)
        old_acts = {getattr(a, "name", str(a)) for a in before.activities if a.type != discord.ActivityType.custom}
        new_acts = {getattr(a, "name", str(a)) for a in after.activities if a.type != discord.ActivityType.custom}
        self._update_activity_on_change(user_id, new_acts - old_acts, start=True)
        self._update_activity_on_change(user_id, old_acts - new_acts, start=False)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        user_id = str(member.id)
        now = current_timestamp()
        self.voice_times.setdefault(user_id, {"total": 0, "ongoing_start": None})
        self.weekly_voice.setdefault(user_id, {"total": 0, "ongoing_start": None})

        if before.channel is None and after.channel is not None:
            ongoing = now
        elif before.channel is not None and after.channel is None:
            ongoing = None
            start = self.voice_times[user_id]["ongoing_start"]
            if start:
                elapsed = now - start
                self.voice_times[user_id]["total"] += elapsed
                self.weekly_voice[user_id]["total"] += elapsed
        elif before.channel != after.channel:
            start = self.voice_times[user_id]["ongoing_start"]
            if start:
                elapsed = now - start
                self.voice_times[user_id]["total"] += elapsed
                self.weekly_voice[user_id]["total"] += elapsed
            ongoing = now
        else:
            return

        self.voice_times[user_id]["ongoing_start"] = ongoing
        self.weekly_voice[user_id]["ongoing_start"] = ongoing

    # -------------------- Leaderboard Task --------------------

    @tasks.loop(minutes=60)
    async def leaderboard_task(self):
        now = datetime.utcnow()
        if now.weekday() == 6 and now.hour == 0:
            channel = self.bot.get_channel(self.leaderboard_channel_id)
            if channel:
                await self._update_active_users_once()
                await self.generate_leaderboard(channel, self.weekly_totals, self.weekly_voice, "Weekly")
                self.weekly_totals = {}
                self.weekly_voice = {}
                self.save_data()

    # -------------------- Leaderboard / Stats --------------------

    async def _generate_leaderboard_embeds(self, activity_data, voice_data, title_prefix=""):
        limit = settings.get("leaderboard_limit", 10)
        show_avg = "weekly" in title_prefix.lower()

        activity_board = []
        for user_id, activities in activity_data.items():
            user = self.bot.get_user(int(user_id))
            if not user:
                continue
            cleaned_activities = {n: v for n, v in activities.items() if isinstance(v, dict)}
            if not cleaned_activities:
                continue
            total_time = sum(v["main"] for v in cleaned_activities.values())
            daily_avg = total_time / 7 if show_avg else None
            top3 = sorted(cleaned_activities.items(), key=lambda x: x[1]["main"], reverse=True)[:3]
            top_text = "\n".join(
                [f"*{name}*: {v['main']/3600:.2f} h (dupl.: {v['duplicate']/3600:.2f} h)"
                 if name.lower() in self.blacklist else
                 f"{name}: {v['main']/3600:.2f} h (dupl.: {v['duplicate']/3600:.2f} h)"
                 for name, v in top3]
            ) if top3 else "No activity"
            activity_board.append((total_time, daily_avg, user.display_name, top_text))

        activity_board.sort(reverse=True, key=lambda x: x[0])
        embed_activity = discord.Embed(
            title="📊 WEEKLY Activity Leaderboard" if show_avg else "📊 ALL-TIME Activity Leaderboard",
            color=discord.Color.orange()
        )
        for rank, (total_time, daily_avg, name, top_text) in enumerate(activity_board[:limit], start=1):
            value_text = f"Top Activities:\n{top_text}"
            if show_avg and daily_avg is not None:
                value_text = f"Daily Avg: {daily_avg/3600:.2f} h\n" + value_text
            embed_activity.add_field(
                name=f"#{rank} {name} - Total: {total_time/3600:.2f} h",
                value=value_text,
                inline=False
            )

        voice_board = []
        for user_id, voice_val in voice_data.items():
            user = self.bot.get_user(int(user_id))
            if not user:
                continue
            total_voice = voice_val.get("total", 0) if isinstance(voice_val, dict) else voice_val
            if total_voice == 0:
                continue
            daily_avg_voice = total_voice / 7 if show_avg else None
            voice_board.append((total_voice, daily_avg_voice, user.display_name))

        voice_board.sort(reverse=True, key=lambda x: x[0])
        embed_voice = discord.Embed(
            title="🎙️ WEEKLY Voice Leaderboard" if show_avg else "🎙️ ALL-TIME Voice Leaderboard",
            color=discord.Color.teal()
        )
        for rank, (total_voice, daily_avg_voice, name) in enumerate(voice_board[:limit], start=1):
            value_text = f"Total Voice Time: {total_voice/3600:.2f} h"
            if show_avg and daily_avg_voice is not None:
                value_text += f"\nDaily Avg: {daily_avg_voice/3600:.2f} h"
            embed_voice.add_field(name=f"#{rank} {name}", value=value_text, inline=False)

        return embed_activity, embed_voice

    async def generate_leaderboard(self, ctx_or_channel, activity_data, voice_data, title_prefix=""):
        embed_activity, embed_voice = await self._generate_leaderboard_embeds(activity_data, voice_data, title_prefix)
        await ctx_or_channel.send(embeds=[embed_activity, embed_voice])

    @commands.command()
    async def leaderboard(self, ctx):
        await self._update_active_users_once()
        await self.generate_leaderboard(ctx, self.activity_times, self.voice_times, "All-Time")

    @commands.command()
    async def weeklytest(self, ctx):
        ADMIN_USER_ID = int(settings["ADMIN_USER_ID"])
        if ctx.author.id != ADMIN_USER_ID:
            await ctx.send("⛔ You don't have permission to use this command.", delete_after=5)
            return
        await self._update_active_users_once()
        await self.generate_leaderboard(ctx, self.weekly_totals, self.weekly_voice, "Weekly")

    @commands.command()
    async def stats(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        user_id = str(member.id)
        activities = self.activity_times.get(user_id, {})
        voice_data = self.voice_times.get(user_id, {"total": 0, "ongoing_start": None})
        if not activities and not voice_data:
            await ctx.send(f"No stats found for {member.display_name}.", delete_after=3600)
            return

        all_activities = sorted(activities.items(), key=lambda x: x[1]["main"], reverse=True)
        top_text = "\n".join(
            [f"*{name}*: {v['main']/3600:.2f} h (dupl.: {v['duplicate']/3600:.2f} h)"
            if name.lower() in self.blacklist else
            f"{name}: {v['main']/3600:.2f} h (dupl.: {v['duplicate']/3600:.2f} h)"
            for name, v in all_activities]
        ) if all_activities else "No activity"

        total_voice = voice_data.get("total", 0)
        if voice_data.get("ongoing_start"):
            total_voice += current_timestamp() - voice_data["ongoing_start"]

        embed = discord.Embed(title=f"Stats for {member.display_name}", color=discord.Color.blue())
        embed.add_field(name="Top Activities", value=top_text, inline=False)
        embed.add_field(name="Total Voice Time", value=f"{total_voice/3600:.2f} h", inline=False)
        await ctx.send(embed=embed, delete_after=3600)

    # -------------------- Cleanup Messages --------------------

@commands.Cog.listener()
async def on_message(self, message: discord.Message):
    # Only act in the leaderboard channel
    if not message.guild or message.channel.id != self.leaderboard_channel_id:
        return

    # Never delete the Weekly leaderboard embeds
    if message.author == self.bot.user and message.embeds:
        if any("Weekly" in embed.title for embed in message.embeds if embed.title):
            return  # keep weekly embeds forever

    # Handle user messages
    if message.author != self.bot.user:
        try:
            await message.delete(delay=100)  # delete user messages after 100 sec
        except (discord.Forbidden, discord.HTTPException):
            pass
        return

    # Handle bot messages (other than Weekly leaderboards)
    if message.author == self.bot.user:
        # Delete bot messages (like leaderboard commands or test outputs) after 1 hour
        try:
            await message.delete(delay=3600)
        except (discord.Forbidden, discord.HTTPException):
            pass

async def setup(bot):
    await bot.add_cog(ActivityTracker(bot))
