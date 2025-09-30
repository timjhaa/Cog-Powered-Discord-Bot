import discord
from discord.ext import commands, tasks
import json
import asyncio
from datetime import datetime
from config import settings

GAME_KEYWORDS = ["game"]

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
        self.weekly_start_times = {}

        self.save_interval = settings.get("save_interval", 60)
        self.update_interval = settings.get("update_interval", 10)
        self.leaderboard_channel_id = settings["ACTIVITY_CHANNEL_ID"]

        self.load_data()

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

    async def _init_voice_sessions(self):
        await self.bot.wait_until_ready()
        now = int(datetime.utcnow().timestamp())
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if member.bot:
                        continue
                    user_id = str(member.id)
                    self.voice_times.setdefault(user_id, {"total": 0, "ongoing_start": now})
                    self.weekly_voice.setdefault(user_id, 0)

    async def _init_activities(self):
        await self.bot.wait_until_ready()
        now = int(datetime.utcnow().timestamp())
        for guild in self.bot.guilds:
            for member in guild.members:
                if member.bot:
                    continue
                user_id = str(member.id)
                self.activity_times.setdefault(user_id, {})
                self.weekly_totals.setdefault(user_id, {})
                self.weekly_start_times.setdefault(user_id, {})
                for act in member.activities:
                    if act.type == discord.ActivityType.custom:
                        continue
                    act_name = getattr(act, "name", str(act))
                    self.weekly_start_times[user_id][act_name + "_start"] = now
                    self.activity_times[user_id].setdefault(act_name, [0, 0])
                    self.weekly_totals[user_id].setdefault(act_name, [0, 0])

    def load_data(self):
        try:
            with open(self.data_file, "r") as f:
                data = json.load(f)
                self.activity_times = {uid: {a: v for a, v in acts.items()} for uid, acts in data.get("activity_times", {}).items()}
                self.voice_times = data.get("voice_times", {})
        except (FileNotFoundError, json.JSONDecodeError):
            self.activity_times = {}
            self.voice_times = {}

        try:
            with open(self.weekly_file, "r") as f:
                data = json.load(f)
                self.weekly_totals = data.get("activity_times", {})
                self.weekly_voice = data.get("voice_times", {})
        except (FileNotFoundError, json.JSONDecodeError):
            self.weekly_totals = {}
            self.weekly_voice = {}

    def save_data(self):
        try:
            with open(self.data_file, "w") as f:
                json.dump({"activity_times": self.activity_times, "voice_times": self.voice_times}, f, indent=4)
            with open(self.weekly_file, "w") as f:
                json.dump({"activity_times": self.weekly_totals, "voice_times": self.weekly_voice}, f, indent=4)
        except Exception as e:
            print(f"Error saving data: {e}")

    @tasks.loop(seconds=10)
    async def auto_save(self):
        await self.bot.wait_until_ready()
        self.save_data()

    @tasks.loop(seconds=10)
    async def update_ongoing(self):
        await self.bot.wait_until_ready()
        await self._update_active_users_once()

    async def _update_active_users_once(self):
        now = int(datetime.utcnow().timestamp())
        for user_id, activities in self.weekly_start_times.items():
            ongoing = [k for k in activities if k.endswith("_start")]
            if not ongoing:
                continue
            act_names = [act.replace("_start", "") for act in ongoing]
            game_activities = [act for act in act_names if any(g in act.lower() for g in GAME_KEYWORDS)]
            real_act = max(game_activities, key=lambda a: self.weekly_totals.get(user_id, {}).get(a, [0,0])[0]) if game_activities else max(act_names, key=lambda a: self.weekly_totals.get(user_id, {}).get(a, [0,0])[0])
            for act_start in ongoing:
                act_name = act_start.replace("_start", "")
                start_time = activities[act_start]
                elapsed = now - start_time
                self.weekly_totals.setdefault(user_id, {})
                self.weekly_totals[user_id].setdefault(act_name, [0, 0])
                if act_name.lower() in self.blacklist:
                    self.weekly_totals[user_id][act_name][1] += elapsed
                else:
                    if act_name == real_act:
                        self.weekly_totals[user_id][act_name][0] += elapsed
                    else:
                        self.weekly_totals[user_id][act_name][1] += elapsed
                activities[act_start] = now

        for user_id, data in self.voice_times.items():
            start = data.get("ongoing_start")
            if start:
                elapsed = now - start
                self.voice_times[user_id]["total"] += elapsed
                self.weekly_voice[user_id] = self.weekly_voice.get(user_id, 0) + elapsed
                self.voice_times[user_id]["ongoing_start"] = now

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        if after.bot:
            return
        user_id = str(after.id)
        now = int(datetime.utcnow().timestamp())
        old_activities = {getattr(a, "name", str(a)) for a in before.activities if a.type != discord.ActivityType.custom}
        new_activities = {getattr(a, "name", str(a)) for a in after.activities if a.type != discord.ActivityType.custom}
        started = new_activities - old_activities
        stopped = old_activities - new_activities
        self.activity_times.setdefault(user_id, {})
        self.weekly_totals.setdefault(user_id, {})
        self.weekly_start_times.setdefault(user_id, {})
        for act_name in started:
            self.activity_times[user_id].setdefault(act_name, [0, 0])
            self.weekly_totals[user_id].setdefault(act_name, [0, 0])
            self.weekly_start_times[user_id][act_name + "_start"] = now
        for act_name in stopped:
            start = self.weekly_start_times[user_id].pop(act_name + "_start", None)
            if start:
                elapsed = now - start
                self.activity_times[user_id].setdefault(act_name, [0, 0])
                self.weekly_totals[user_id].setdefault(act_name, [0, 0])
                if act_name.lower() in self.blacklist:
                    self.activity_times[user_id][act_name][1] += elapsed
                    self.weekly_totals[user_id][act_name][1] += elapsed
                else:
                    self.activity_times[user_id][act_name][0] += elapsed
                    self.weekly_totals[user_id][act_name][0] += elapsed

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        user_id = str(member.id)
        now = int(datetime.utcnow().timestamp())
        self.voice_times.setdefault(user_id, {"total": 0, "ongoing_start": None})
        self.weekly_voice.setdefault(user_id, 0)
        if before.channel is None and after.channel is not None:
            self.voice_times[user_id]["ongoing_start"] = now
        elif before.channel is not None and after.channel is None:
            start = self.voice_times[user_id]["ongoing_start"]
            if start:
                elapsed = now - start
                self.voice_times[user_id]["total"] += elapsed
                self.weekly_voice[user_id] += elapsed
                self.voice_times[user_id]["ongoing_start"] = None
        elif before.channel != after.channel:
            start = self.voice_times[user_id]["ongoing_start"]
            if start:
                elapsed = now - start
                self.voice_times[user_id]["total"] += elapsed
                self.weekly_voice[user_id] += elapsed
            self.voice_times[user_id]["ongoing_start"] = now

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

    async def _generate_leaderboard_embeds(self, activity_data, voice_data, title_prefix=""):
        limit = settings.get("leaderboard_limit", 10)
        activity_board = []
        for user_id, activities in activity_data.items():
            cleaned_activities = {name: v for name, v in activities.items() if isinstance(v, list)}
            if not cleaned_activities:
                continue
            user = self.bot.get_user(int(user_id))
            if not user:
                continue
            total_time = sum(v[0] for v in cleaned_activities.values())
            daily_avg = total_time / 7
            top3 = sorted(cleaned_activities.items(), key=lambda x: x[1][0], reverse=True)[:3]
            top_text = "\n".join([f"*{name}*: {v[0] / 3600:.2f} h (dupl.: {v[1] / 3600:.2f} h)" if name.lower() in self.blacklist else f"{name}: {v[0] / 3600:.2f} h (dupl.: {v[1] / 3600:.2f} h)" for name, v in top3]) if top3 else "No activity"
            activity_board.append((total_time, daily_avg, user.display_name, top_text))
        activity_board.sort(reverse=True, key=lambda x: x[0])
        embed_activity = discord.Embed(title=f"{title_prefix} Activity Leaderboard", color=discord.Color.orange())
        for rank, (total_time, daily_avg, name, top_text) in enumerate(activity_board[:limit], start=1):
            embed_activity.add_field(name=f"#{rank} {name} - Total: {total_time / 3600:.2f} h", value=f"Daily Avg: {daily_avg / 3600:.2f} h\nTop Activities:\n{top_text}", inline=False)

        voice_board = []
        for user_id, voice_value in voice_data.items():
            total_voice = voice_value if isinstance(voice_value, int) else voice_value.get("total", 0)
            if total_voice == 0:
                continue
            user = self.bot.get_user(int(user_id))
            if not user:
                continue
            daily_avg_voice = total_voice / 7
            voice_board.append((total_voice, daily_avg_voice, user.display_name))
        voice_board.sort(reverse=True, key=lambda x: x[0])
        embed_voice = discord.Embed(title=f"{title_prefix} Voice Leaderboard", color=discord.Color.teal())
        for rank, (total_voice, daily_avg_voice, name) in enumerate(voice_board[:limit], start=1):
            embed_voice.add_field(name=f"#{rank} {name}", value=f"Total Voice Time: {total_voice / 3600:.2f} h\nDaily Avg: {daily_avg_voice / 3600:.2f} h", inline=False)

        return embed_activity, embed_voice

    async def generate_leaderboard(self, ctx_or_channel, activity_data, voice_data, title_prefix=""):
        embed_activity, embed_voice = await self._generate_leaderboard_embeds(activity_data, voice_data, title_prefix)
        await ctx_or_channel.send(embeds=[embed_activity, embed_voice])

    @commands.command()
    async def leaderboard(self, ctx, scope: str = "alltime"):
        await self._update_active_users_once()
        if scope.lower() == "weekly":
            await self.generate_leaderboard(ctx, self.weekly_totals, self.weekly_voice, "Weekly")
        else:
            await self.generate_leaderboard(ctx, self.activity_times, self.voice_times, "All-Time")

    @commands.command()
    async def weeklytest(self, ctx):
        await self._update_active_users_once()
        await self.generate_leaderboard(ctx, self.weekly_totals, self.weekly_voice, "Weekly (Test)")

    @commands.command()
    async def stats(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        user_id = str(member.id)
        if user_id not in self.activity_times and user_id not in self.voice_times:
            await ctx.send(f"No stats found for {member.display_name}.", delete_after=3600)
            return
        activities = self.activity_times.get(user_id, {})
        top3 = sorted(activities.items(), key=lambda x: x[1][0], reverse=True)[:3]
        top_text = "\n".join([f"*{name}*: {v[0] / 3600:.2f} h (dupl.: {v[1] / 3600:.2f} h)" if name.lower() in self.blacklist else f"{name}: {v[0] / 3600:.2f} h (dupl.: {v[1] / 3600:.2f} h)" for name, v in top3]) if top3 else "No activity"
        voice_data = self.voice_times.get(user_id, {"total": 0, "ongoing_start": None})
        total_voice = voice_data.get("total", 0)
        ongoing_start = voice_data.get("ongoing_start")
        if ongoing_start:
            total_voice += int(datetime.utcnow().timestamp() - ongoing_start)
        embed = discord.Embed(title=f"Stats for {member.display_name}", color=discord.Color.blue())
        embed.add_field(name="Top Activities", value=top_text, inline=False)
        embed.add_field(name="Total Voice Time", value=f"{total_voice / 3600:.2f} h", inline=False)
        await ctx.send(embed=embed, delete_after=3600)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.channel.id != self.leaderboard_channel_id:
            return
        if message.author == self.bot.user and message.embeds:
            if any("Weekly" in embed.title for embed in message.embeds if embed.title):
                return
        if message.author != self.bot.user:
            try:
                await message.delete(delay=100)
            except discord.Forbidden:
                print("Missing permissions to delete messages in leaderboard channel.")
            except discord.HTTPException:
                pass


async def setup(bot):
    await bot.add_cog(ActivityTracker(bot))
