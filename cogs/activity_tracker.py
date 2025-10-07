import discord
from discord.ext import commands, tasks
import json
from datetime import datetime
from config import settings
import os
import shutil

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
        self.leaderboard_channel_id = settings["ACTIVITY_CHANNEL_ID"]

        self.load_data()

        # Start tasks
        self.auto_save.change_interval(seconds=self.save_interval)
        self.update_ongoing.change_interval(seconds=self.update_interval)
        self.auto_save.start()
        self.update_ongoing.start()
        self.leaderboard_task.start()

        # Initialize sessions
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
        log_channel_id = settings.get("LOG_CHANNEL_ID")
        log_channel = self.bot.get_channel(log_channel_id) if log_channel_id else None

        # Step 1: Reset all ongoing_start values to None
        for user_dict in (self.activity_times, self.weekly_totals):
            for activities in user_dict.values():
                for stats in activities.values():
                    stats["ongoing_start"] = None

        # Step 2: Detect all currently running activities
        recorded = []
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
                    if act and act.type != discord.ActivityType.custom
                }

                if not current_activities:
                    continue

                for act_name in current_activities:
                    for data in (self.activity_times[user_id], self.weekly_totals[user_id]):
                        data.setdefault(act_name, {"main": 0, "duplicate": 0, "ongoing_start": now})
                        data[act_name]["ongoing_start"] = now
                    recorded.append((member.display_name, act_name))

        # Step 3: Log results
        if log_channel:
            if recorded:
                msg = "\n".join([f"• **{user}** - {act}" for user, act in recorded])
                await log_channel.send(
                    f"🟢 **Startup Activity Tracking Initialized**\n"
                    f"Detected and updated ongoing activities ({len(recorded)}):\n{msg}"
                )
            else:
                await log_channel.send("🟢 Startup complete — no ongoing activities detected.")
        else:
            print("[Startup] No log channel configured in settings (LOG_CHANNEL_ID missing).")

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

    @tasks.loop(seconds=60)
    async def auto_save(self):
        await self.bot.wait_until_ready()
        self.save_data()

    @tasks.loop(seconds=10)
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
                target_dict = self.activity_times.setdefault(user_id, {}).setdefault(
                    act_name, {"main": 0, "duplicate": 0, "ongoing_start": now}
                )
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

    def _update_activity_on_change(self, user_id, activities, start=True):
        now = current_timestamp()
        self.activity_times.setdefault(user_id, {})
        self.weekly_totals.setdefault(user_id, {})
        for act_name in activities:
            for data in (self.activity_times[user_id], self.weekly_totals[user_id]):
                entry = data.setdefault(act_name, {"main": 0, "duplicate": 0, "ongoing_start": None})
                if start:
                    entry["ongoing_start"] = now
                else:
                    start_time = entry.get("ongoing_start")
                    if start_time:
                        elapsed = now - start_time
                        if act_name.lower() in self.blacklist:
                            entry["duplicate"] += elapsed
                        else:
                            entry["main"] += elapsed
                        entry["ongoing_start"] = None

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

    # -------------------- Backup + Leaderboard --------------------

    @tasks.loop(minutes=60)
    async def leaderboard_task(self):
        now = datetime.utcnow()
        if now.weekday() == 6 and now.hour == 0:  # Sunday 00:00 UTC
            channel = self.bot.get_channel(self.leaderboard_channel_id)
            if channel:
                await self._update_active_users_once()

                backup_dir = os.path.join(os.path.dirname(__file__), "weekly_backup")
                os.makedirs(backup_dir, exist_ok=True)
                existing = [f for f in os.listdir(backup_dir) if f.startswith("weekly_data_")]
                index = len(existing) + 1

                date_str = now.strftime("%d_%m_%Y")
                backup_name = f"weekly_data_{index}_{date_str}.json"
                backup_path = os.path.join(backup_dir, backup_name)

                try:
                    shutil.copy2(self.weekly_file, backup_path)
                    print(f"[Backup] Created weekly backup: {backup_name}")
                except Exception as e:
                    print(f"[Backup] Failed to create backup: {e}")

                await self.generate_leaderboard(channel, self.weekly_totals, self.weekly_voice, "Weekly")
                self.weekly_totals = {}
                self.weekly_voice = {}
                self.save_data()

    @commands.command()
    async def backupweekly(self, ctx):
        now = datetime.utcnow()
        backup_dir = os.path.join(os.path.dirname(__file__), "weekly_backup")
        os.makedirs(backup_dir, exist_ok=True)
        existing = [f for f in os.listdir(backup_dir) if f.startswith("weekly_data_")]
        index = len(existing) + 1
        date_str = now.strftime("%d_%m_%Y")
        backup_name = f"weekly_data_{index}_{date_str}.json"
        backup_path = os.path.join(backup_dir, backup_name)
        try:
            shutil.copy2(self.weekly_file, backup_path)
            await ctx.send(f"✅ Backup created: `{backup_name}`", delete_after=30)
        except Exception as e:
            await ctx.send(f"❌ Backup failed: {e}", delete_after=30)

    # -------------------- Leaderboard / Stats --------------------

    async def _generate_leaderboard_embeds(self, activity_data, voice_data, title_prefix=""):
        limit = settings.get("leaderboard_limit", 10)
        show_avg = "weekly" in title_prefix.lower()
        activity_board = []
        for user_id, activities in activity_data.items():
            user = self.bot.get_user(int(user_id))
            if not user:
                continue
            cleaned = {n: v for n, v in activities.items() if isinstance(v, dict)}
            if not cleaned:
                continue
            total_time = sum(v["main"] for v in cleaned.values())
            daily_avg = total_time / 7 if show_avg else None
            top3 = sorted(cleaned.items(), key=lambda x: x[1]["main"], reverse=True)[:3]
            top_text = "\n".join(
                [f"*{n}*: {v['main']/3600:.2f} h (dupl.: {v['duplicate']/3600:.2f} h)"
                 if n.lower() in self.blacklist else
                 f"{n}: {v['main']/3600:.2f} h (dupl.: {v['duplicate']/3600:.2f} h)"
                 for n, v in top3]
            ) if top3 else "No activity"
            activity_board.append((total_time, daily_avg, user.display_name, top_text))

        activity_board.sort(reverse=True, key=lambda x: x[0])
        embed_activity = discord.Embed(
            title="📊 WEEKLY Activity Leaderboard" if show_avg else "📊 ALL-TIME Activity Leaderboard",
            color=discord.Color.orange()
        )
        for rank, (total, avg, name, text) in enumerate(activity_board[:limit], start=1):
            val = f"Top Activities:\n{text}"
            if show_avg and avg:
                val = f"Daily Avg: {avg/3600:.2f} h\n" + val
            embed_activity.add_field(
                name=f"#{rank} {name} - Total: {total/3600:.2f} h", value=val, inline=False
            )

        # Voice leaderboard
        voice_board = []
        for user_id, v in voice_data.items():
            user = self.bot.get_user(int(user_id))
            if not user:
                continue
            total = v.get("total", 0)
            if total == 0:
                continue
            avg = total / 7 if show_avg else None
            voice_board.append((total, avg, user.display_name))

        voice_board.sort(reverse=True, key=lambda x: x[0])
        embed_voice = discord.Embed(
            title="🎙️ WEEKLY Voice Leaderboard" if show_avg else "🎙️ ALL-TIME Voice Leaderboard",
            color=discord.Color.teal()
        )
        for rank, (total, avg, name) in enumerate(voice_board[:limit], start=1):
            val = f"Total Voice Time: {total/3600:.2f} h"
            if show_avg and avg:
                val += f"\nDaily Avg: {avg/3600:.2f} h"
            embed_voice.add_field(name=f"#{rank} {name}", value=val, inline=False)

        return embed_activity, embed_voice

    async def generate_leaderboard(self, ctx_or_channel, activity_data, voice_data, title_prefix=""):
        embed_a, embed_v = await self._generate_leaderboard_embeds(activity_data, voice_data, title_prefix)
        await ctx_or_channel.send(embeds=[embed_a, embed_v])

    @commands.command()
    async def leaderboard(self, ctx):
        await self._update_active_users_once()
        await self.generate_leaderboard(ctx, self.activity_times, self.voice_times, "All-Time")

    @commands.command()
    async def weeklytest(self, ctx):
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
        all_acts = sorted(activities.items(), key=lambda x: x[1]["main"], reverse=True)
        top_text = "\n".join(
            [f"*{n}*: {v['main']/3600:.2f} h (dupl.: {v['duplicate']/3600:.2f} h)"
             if n.lower() in self.blacklist else
             f"{n}: {v['main']/3600:.2f} h (dupl.: {v['duplicate']/3600:.2f} h)"
             for n, v in all_acts]
        ) if all_acts else "No activity"
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
        if message.channel.id != self.leaderboard_channel_id:
            return
        if message.author == self.bot.user and message.embeds:
            if any("Weekly" in e.title for e in message.embeds if e.title):
                return
        if message.author != self.bot.user:
            try:
                await message.delete(delay=100)
            except (discord.Forbidden, discord.HTTPException):
                pass
            return
        if message.author == self.bot.user:
            try:
                await message.delete(delay=3600)
            except (discord.Forbidden, discord.HTTPException):
                pass

async def setup(bot):
    await bot.add_cog(ActivityTracker(bot))
