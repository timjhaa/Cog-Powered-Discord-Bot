import discord
from discord.ext import commands, tasks
import json
from datetime import datetime, timedelta
from config import settings
import os
import pytz

GAME_KEYWORDS = ["game"]

def current_timestamp():
    return int(datetime.utcnow().timestamp())

class ActivityTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_file = "activity_data.json"

        self.parent_dir = os.path.dirname(os.path.dirname(__file__))
        self.backup_dir = os.path.join(self.parent_dir, "weekly_backup")
        self.baseline_file = os.path.join(self.parent_dir, "weekly_backup_total.json")
        os.makedirs(self.backup_dir, exist_ok=True)

        self.activity_times = {}
        self.voice_times = {}
        self.blacklist = set(a.lower() for a in settings.get("activity_blacklist", []))

        self.leaderboard_channel_id = settings["ACTIVITY_CHANNEL_ID"]
        self.log_channel_id = settings.get("LOG_CHANNEL_ID")

        self.load_data()
        self.update_ongoing.start()
        self.auto_save.start()
        self.leaderboard_task.start()

        self.bot.loop.create_task(self._init_voice_sessions())
        self.bot.loop.create_task(self._init_activities())

    # -------------------- Initialization --------------------
    async def _init_voice_sessions(self):
        await self.bot.wait_until_ready()
        now = current_timestamp()
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if not member.bot:
                        user_id = str(member.id)
                        self.voice_times.setdefault(user_id, {"total": 0, "ongoing_start": now})

    async def _init_activities(self):
        await self.bot.wait_until_ready()
        now = current_timestamp()
        log_channel = self.bot.get_channel(self.log_channel_id) if self.log_channel_id else None

        # Reset ongoing_start
        for user_dict in (self.activity_times,):
            for activities in user_dict.values():
                for stats in activities.values():
                    stats["ongoing_start"] = None

        recorded = []
        for guild in self.bot.guilds:
            for member in guild.members:
                if member.bot:
                    continue
                user_id = str(member.id)
                self.activity_times.setdefault(user_id, {})

                for activity in member.activities:
                    if activity and activity.type != discord.ActivityType.custom:
                        act_name = getattr(activity, "name", str(activity))
                        self.activity_times[user_id].setdefault(act_name, {"main": 0, "duplicate": 0, "ongoing_start": now})
                        recorded.append((member.display_name, act_name))

        if log_channel:
            if recorded:
                msg = "\n".join([f"• {u} - {a}" for u, a in recorded])
                await log_channel.send(
                    f"🟢 **Startup Activity Tracking Initialized**\nDetected ongoing activities ({len(recorded)}):\n{msg}"
                )
            else:
                await log_channel.send("🟢 Startup complete — no ongoing activities detected.")

    # -------------------- Load / Save --------------------
    def load_data(self):
        try:
            with open(self.data_file) as f:
                data = json.load(f)
                self.activity_times = data.get("activity_times", {})
                self.voice_times = data.get("voice_times", {})
        except (FileNotFoundError, json.JSONDecodeError):
            self.activity_times, self.voice_times = {}, {}

    def save_data(self):
        try:
            with open(self.data_file, "w") as f:
                json.dump({"activity_times": self.activity_times, "voice_times": self.voice_times}, f, indent=4)
        except Exception as e:
            print(f"Error saving data: {e}")

    # -------------------- Tasks --------------------
    @tasks.loop(seconds=10)
    async def update_ongoing(self):
        await self.bot.wait_until_ready()
        await self._update_active_users_once()

    async def _update_active_users_once(self):
        now = current_timestamp()
        for user_id, activities in self.activity_times.items():
            for act_name, stats in activities.items():
                start = stats.get("ongoing_start")
                if start:
                    elapsed = now - start
                    if act_name.lower() in self.blacklist:
                        stats["duplicate"] += elapsed
                    else:
                        stats["main"] += elapsed
                    stats["ongoing_start"] = now

        for user_id, data in self.voice_times.items():
            start = data.get("ongoing_start")
            if start:
                elapsed = now - start
                data["total"] += elapsed
                data["ongoing_start"] = now

    @tasks.loop(seconds=60)
    async def auto_save(self):
        await self.bot.wait_until_ready()
        self.save_data()

    # -------------------- Helper --------------------
    def _load_json(self, path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def _combine_backups(self):
        backups = [f for f in os.listdir(self.backup_dir) if f.startswith("weekly_data_") and f.endswith(".json")]
        if not backups:
            return {"activity_times": {}, "voice_times": {}}, 0

        combined = {"activity_times": {}, "voice_times": {}}
        for file in backups:
            data = self._load_json(os.path.join(self.backup_dir, file))
            if not data:
                continue
            for uid, acts in data.get("activity_times", {}).items():
                combined["activity_times"].setdefault(uid, {})
                for act, val in acts.items():
                    stats = combined["activity_times"][uid].setdefault(act, {"main": 0, "duplicate": 0})
                    stats["main"] += val.get("main", 0)
                    stats["duplicate"] += val.get("duplicate", 0)
            for uid, v in data.get("voice_times", {}).items():
                combined["voice_times"].setdefault(uid, {"total": 0})
                combined["voice_times"][uid]["total"] += v.get("total", 0)
        return combined, len(backups)

    def _load_or_recalculate_baseline(self):
        baseline_data = self._load_json(self.baseline_file)
        combined_count = 0
        recalc_needed = True

        if baseline_data:
            stored_count = baseline_data.get("_backup_count", 0)
            current_count = len([f for f in os.listdir(self.backup_dir) if f.startswith("weekly_data_")])
            age_ok = datetime.utcnow() - datetime.utcfromtimestamp(os.path.getmtime(self.baseline_file)) < timedelta(days=7)
            if stored_count == current_count and age_ok:
                recalc_needed = False

        if not recalc_needed:
            print("[weekly] Using existing baseline")
            return baseline_data

        print("[weekly] Rebuilding baseline from backups...")
        combined_data, combined_count = self._combine_backups()
        combined_data["_backup_count"] = combined_count
        with open(self.baseline_file, "w") as f:
            json.dump(combined_data, f, indent=4)
        print(f"[weekly] Baseline rebuilt from {combined_count} backups.")
        return combined_data

    def _calculate_weekly_difference(self, current, baseline):
        weekly_activities = {}
        weekly_voice = {}
        for uid, acts in current.get("activity_times", {}).items():
            weekly_activities[uid] = {}
            prev_user = baseline.get("activity_times", {}).get(uid, {})
            for act, data in acts.items():
                prev = prev_user.get(act, {"main": 0, "duplicate": 0})
                weekly_activities[uid][act] = {"main": max(0, data["main"] - prev["main"]),
                                              "duplicate": max(0, data["duplicate"] - prev["duplicate"])}
        for uid, vdata in current.get("voice_times", {}).items():
            prev = baseline.get("voice_times", {}).get(uid, {"total": 0})
            weekly_voice[uid] = {"total": max(0, vdata["total"] - prev["total"])}
        return weekly_activities, weekly_voice

    # -------------------- Leaderboard Embeds --------------------
    async def _generate_alltime_leaderboard_embeds(self, activity_data, voice_data):
        limit = settings.get("leaderboard_limit", 10)
        embed_a = discord.Embed(title="📊 All-Time Activity Leaderboard", color=discord.Color.orange())
        sorted_users = sorted(activity_data.items(), key=lambda x: sum(v["main"] for v in x[1].values()), reverse=True)[:limit]

        for rank, (uid, acts) in enumerate(sorted_users, start=1):
            user = self.bot.get_user(int(uid))
            name = user.display_name if user else uid
            total_main = sum(v["main"] for v in acts.values())
            top_acts = sorted(acts.items(), key=lambda x: x[1]["main"], reverse=True)[:3]
            act_text = "\n".join([f"{act}: {v['main']/3600:.2f} h (dupl.: {v['duplicate']/3600:.2f} h)" for act, v in top_acts])
            embed_a.add_field(name=f"#{rank} {name} - Total: {total_main/3600:.2f} h",
                              value=f"Top Activities:\n{act_text}", inline=False)

        embed_v = discord.Embed(title="🎙️ All-Time Voice Leaderboard", color=discord.Color.teal())
        sorted_voice = sorted(voice_data.items(), key=lambda x: x[1]["total"], reverse=True)[:limit]
        for rank, (uid, v) in enumerate(sorted_voice, start=1):
            user = self.bot.get_user(int(uid))
            name = user.display_name if user else uid
            total = v["total"]
            embed_v.add_field(name=f"#{rank} {name} - Total: {total/3600:.2f} h", value="", inline=False)

        return embed_a, embed_v

    async def _generate_weekly_leaderboard_embeds(self, activity_data, voice_data):
        limit = settings.get("leaderboard_limit", 10)
        embed_a = discord.Embed(title="📊 Weekly Activity Leaderboard", color=discord.Color.orange())
        sorted_users = sorted(activity_data.items(), key=lambda x: sum(v["main"] for v in x[1].values()), reverse=True)[:limit]

        for rank, (uid, acts) in enumerate(sorted_users, start=1):
            user = self.bot.get_user(int(uid))
            name = user.display_name if user else uid
            total_main = sum(v["main"] for v in acts.values())
            daily_avg = total_main / 7 / 3600  # DAILY AVERAGE
            top_acts = sorted(acts.items(), key=lambda x: x[1]["main"], reverse=True)[:3]
            act_text = "\n".join([f"{act}: {v['main']/3600:.2f} h (dupl.: {v['duplicate']/3600:.2f} h)" for act, v in top_acts])
            embed_a.add_field(name=f"#{rank} {name} - Total: {total_main/3600:.2f} h",
                              value=f"Daily Avg: {daily_avg:.2f} h\nTop Activities:\n{act_text}", inline=False)

        embed_v = discord.Embed(title="🎙️ Weekly Voice Leaderboard", color=discord.Color.teal())
        sorted_voice = sorted(voice_data.items(), key=lambda x: x[1]["total"], reverse=True)[:limit]
        for rank, (uid, v) in enumerate(sorted_voice, start=1):
            user = self.bot.get_user(int(uid))
            name = user.display_name if user else uid
            total = v["total"]
            daily_avg = total / 7 / 3600
            embed_v.add_field(name=f"#{rank} {name} - Total: {total/3600:.2f} h",
                              value=f"Daily Avg: {daily_avg:.2f} h", inline=False)

        return embed_a, embed_v

    async def generate_leaderboard(self, ctx_or_channel, activity_data, voice_data, alltime=True):
        if alltime:
            embed_a, embed_v = await self._generate_alltime_leaderboard_embeds(activity_data, voice_data)
        else:
            embed_a, embed_v = await self._generate_weekly_leaderboard_embeds(activity_data, voice_data)
        await ctx_or_channel.send(embeds=[embed_a, embed_v])

    # -------------------- Commands --------------------
    @commands.command()
    async def leaderboard(self, ctx):
        """All-Time Leaderboard"""
        await self._update_active_users_once()
        await self.generate_leaderboard(ctx, self.activity_times, self.voice_times, alltime=True)

    @commands.command()
    async def weeklytest(self, ctx):
        """Weekly Leaderboard with Daily Average"""
        await self._update_active_users_once()
        baseline = self._load_or_recalculate_baseline()
        weekly_activities, weekly_voice = self._calculate_weekly_difference(
            {"activity_times": self.activity_times, "voice_times": self.voice_times}, baseline
        )
        await self.generate_leaderboard(ctx, weekly_activities, weekly_voice, alltime=False)
        
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

    # -------------------- Weekly Leaderboard Task --------------------
    @tasks.loop(minutes=10)
    async def leaderboard_task(self):
        await self.bot.wait_until_ready()
        berlin = pytz.timezone("Europe/Berlin")
        now = datetime.now(berlin)
        if now.weekday() == 6 and now.hour == 0:  # Sunday 00:00 Berlin
            channel = self.bot.get_channel(self.leaderboard_channel_id)
            if channel:
                await self._update_active_users_once()

                # Backup weekly
                existing = [f for f in os.listdir(self.backup_dir) if f.startswith("weekly_data_")]
                index = len(existing) + 1
                date_str = now.strftime("%d_%m_%Y")
                backup_name = f"weekly_data_{index}_{date_str}.json"
                backup_path = os.path.join(self.backup_dir, backup_name)
                try:
                    with open(backup_path, "w") as f:
                        json.dump({"activity_times": self.activity_times, "voice_times": self.voice_times}, f, indent=4)
                    print(f"[weekly] Backup created: {backup_name}")
                except Exception as e:
                    print(f"[weekly] Backup failed: {e}")

                # Compute weekly leaderboard
                baseline = self._load_or_recalculate_baseline()
                weekly_activities, weekly_voice = self._calculate_weekly_difference(
                    {"activity_times": self.activity_times, "voice_times": self.voice_times}, baseline
                )
                await self.generate_leaderboard(channel, weekly_activities, weekly_voice, alltime=False)

                # Reset weekly totals
                for uid in self.activity_times:
                    for act in self.activity_times[uid].values():
                        act["main"] = 0
                        act["duplicate"] = 0
                        act["ongoing_start"] = current_timestamp()
                for v in self.voice_times.values():
                    v["total"] = 0
                    v["ongoing_start"] = current_timestamp()

async def setup(bot):
    await bot.add_cog(ActivityTracker(bot))
