import discord
from discord import app_commands
import aiohttp
import asyncio
import json
import random
import re
import base64
import os
from datetime import datetime, timezone


BOT_TOKEN = "Dán token vô đây nè ngu ơi"


API_BASE = "https://discord.com/api/v9"
HEARTBEAT_INTERVAL = 20
AUTO_ACCEPT = True

SUPPORTED_TASKS = [
    "WATCH_VIDEO",
    "PLAY_ON_DESKTOP",
    "STREAM_ON_DESKTOP",
    "PLAY_ACTIVITY",
    "WATCH_VIDEO_ON_MOBILE",
]

active_sessions = {}


def make_progress_bar(percent, length=15):
    filled = int(round(length * percent / 100))
    bar = '▰' * filled + '▱' * (length - filled)
    return f"`{bar}` **{percent:.1f}%**"

def create_scan_embed(user):
    embed = discord.Embed(title="🛰️ Đang thiết lập kết nối...", color=0x2b2d31)
    embed.description = f"> Xin chào **{user.display_name}**!\n> Hệ thống đang đồng bộ và phân tích dữ liệu...\n\n⚡ Quá trình này sẽ diễn ra trong vài giây."
    if user.display_avatar:
        embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="Nguyen Khoi • Đang xử lý")
    return embed

def create_list_embed(quests):
    completed = sum(1 for q in quests if is_completed(q))
    todo = sum(1 for q in quests if is_completable(q) and not is_completed(q))
    expired = len(quests) - completed - todo
    
    desc = f"> Hệ thống ghi nhận tổng cộng **{len(quests)}** nhiệm vụ.\n"
    desc += f"> 🟢 Hoàn thành: **{completed}** |  ⏳ Cần chạy: **{todo}** |  🔴 Bỏ qua: **{expired}**\n\n"
    
    for q in quests[:15]:
        name = get_quest_name(q)
        task = get_task_type(q) or "UNKNOWN"
        needed = get_seconds_needed(q)
        mins = needed // 60
        
        if is_completed(q):
            icon = "✅"
            status = "Hoàn tất"
        elif not is_completable(q):
            icon = "⚠️"
            status = "Không khả dụng"
        else:
            icon = "⏳" 
            done = get_seconds_done(q)
            pct = int((done / needed) * 100) if needed > 0 else 0
            status = f"Tiến độ: {pct}%"
            
        desc += f"{icon} **{name}**\n└ 🏷️ `{task}` • ⏱️ {mins}m • {status}\n\n"
        
    if len(desc) > 4096:
        desc = desc[:4000] + "\n... (Danh sách được thu gọn)"
        
    embed = discord.Embed(title="📊 Bảng Phân Bổ Nhiệm Vụ", description=desc, color=0x2b2d31)
    embed.set_footer(text=f"Đã đồng bộ | {completed}/{len(quests)} hoàn tất")
    return embed

def create_start_embed(name, task_type, seconds_needed):
    embed = discord.Embed(title=f"🚀 Khởi động: {name}", color=0x2b2d31)
    embed.add_field(name="🎮 Thể loại", value=f"`{task_type}`", inline=True)
    embed.add_field(name="⏱️ Thời lượng", value=f"`{seconds_needed // 60}m {seconds_needed % 60}s`", inline=True)
    embed.add_field(name="", value=make_progress_bar(0.0), inline=False)
    embed.set_footer(text="Nguyen Khoi • Bắt đầu xử lý")
    return embed

def create_progress_embed(name, seconds_done, seconds_needed):
    percent = min(100.0, (seconds_done / seconds_needed) * 100) if seconds_needed > 0 else 100.0
    remaining = max(0, seconds_needed - seconds_done)
    
    embed = discord.Embed(title=f"⚡ Đang chạy: {name}", color=0x2b2d31)
    embed.description = f"{make_progress_bar(percent)}\n\n> 🎯 **Tiến độ:** `{int(seconds_done)} / {seconds_needed}s`\n> ⏳ **Còn lại:** `~{remaining // 60:.1f} phút`"
    embed.set_footer(text="Nguyen Khoi • Đang đồng bộ tiến trình")
    return embed

def create_complete_embed(name, task_type):
    embed = discord.Embed(title="🎉 Nhiệm Vụ Hoàn Tất!", color=0x57F287)
    embed.description = f"> **{name}**\n> 🏷️ Phân loại: `{task_type}`\n\n💎 Phần thưởng đã sẵn sàng để nhận trên ứng dụng Discord!"
    embed.set_footer(text="Nguyen Khoi • Thành công")
    return embed

def create_early_exit_embed(user, quests):
    total = len(quests)
    completed = sum(1 for q in quests if is_completed(q))
    expired = total - completed
    
    embed = discord.Embed(title="🛡️ BÁO CÁO TỔNG KẾT", color=0x9B59B6)
    desc = f"> Xin chào **{user.display_name}**, tất cả quest đã được hoàn thành từ trước!\n\n"
    desc += f"> ✅ **{completed}/{total}** quest đã xong\n"
    desc += f"> ⚠️ **{expired}** quest hết hạn hoặc không hỗ trợ\n\n"
    desc += "Không có nhiệm vụ nào cần xử lý thêm trong phiên này.\n\n"
    desc += "🔎 **KẾT QUẢ QUÉT**\n"
    desc += f"```text\nTổng số Quest:    {total}\nĐã hoàn thành:    {completed}\nHết hạn:          {expired}\nCần làm lần này:  0\n```\n"
    desc += "🔐 **BẢO MẬT HỆ THỐNG**\n> Token của bạn đã được **xóa hoàn toàn** khỏi bộ nhớ."
    
    embed.description = desc
    if user.display_avatar:
        embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="Nguyen Khoi • Hoạt động an toàn")
    return embed

def create_final_summary_embed(user, successes, todo_initial):
    embed = discord.Embed(title="🏆 Báo Cáo Tổng Kết Phiên", color=0xFEE75C)
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url if user.display_avatar else None)
    
    desc = f"> ⚡ **Hệ thống đã tự động giải quyết ({len(successes)}/{todo_initial} thành công)**\n\n"
    for name in successes:
        desc += f"✅ **{name}**\n"
        
    if not successes:
        desc += "Phân tích không tìm thấy nhiệm vụ khả dụng nào mới để thực hiện."
        
    embed.description = desc
    embed.set_footer(text=f"User ID: {user.id} • Hoạt động hoàn tất")
    return embed

async def fetch_latest_build_number():
    fallback = 504649
    try:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        async with aiohttp.ClientSession() as session:
            async with session.get("https://discord.com/app", headers={"User-Agent": ua}, timeout=15) as r:
                if r.status != 200: return fallback
                text = await r.text()
                scripts = re.findall(r'/assets/([a-f0-9]+)\.js', text)
                if not scripts:
                    scripts_alt = re.findall(r'src="(/assets/[^"]+\.js)"', text)
                    scripts = [s.split('/')[-1].replace('.js', '') for s in scripts_alt]
                if not scripts: return fallback
                for asset_hash in scripts[-5:]:
                    try:
                        async with session.get(f"https://discord.com/assets/{asset_hash}.js", headers={"User-Agent": ua}, timeout=15) as ar:
                            ar_text = await ar.text()
                            m = re.search(r'buildNumber["\s:]+["\s]*(\d{5,7})', ar_text)
                            if m: return int(m.group(1))
                    except Exception: continue
        return fallback
    except Exception:
        return fallback

def make_super_properties(build_number):
    obj = {
        "os": "Windows", "browser": "Discord Client", "release_channel": "stable",
        "client_version": "1.0.9175", "os_version": "10.0.26100", "os_arch": "x64", "app_arch": "x64",
        "system_locale": "en-US",
        "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) discord/1.0.9175 Chrome/128.0.6613.186 Electron/32.2.7 Safari/537.36",
        "browser_version": "32.2.7", "client_build_number": build_number, "native_build_number": 59498, "client_event_source": None,
    }
    return base64.b64encode(json.dumps(obj).encode()).decode()

class DiscordAPI:
    def __init__(self, token, build_number):
        self.token = token
        self.build_number = build_number
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        sp = make_super_properties(build_number)
        self.headers = {
            "Authorization": token, "Content-Type": "application/json", "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9", "User-Agent": ua, "X-Super-Properties": sp,
            "X-Discord-Locale": "en-US", "X-Discord-Timezone": "Asia/Ho_Chi_Minh",
            "Origin": "https://discord.com", "Referer": "https://discord.com/channels/@me",
        }
        self.session = aiohttp.ClientSession(headers=self.headers)

    async def get(self, path): return await self.session.get(f"{API_BASE}{path}")
    async def post(self, path, payload=None): return await self.session.post(f"{API_BASE}{path}", json=payload)
    async def validate_token(self):
        try:
            async with await self.get("/users/@me") as r: return r.status == 200
        except Exception: return False
    async def close(self): await self.session.close()

def _get(d, *keys):
    if d is None: return None
    for k in keys:
        if k in d: return d[k]
    return None

def get_task_config(quest): return _get(quest.get("config", {}), "taskConfig", "task_config")

def get_quest_name(quest):
    cfg = quest.get("config", {})
    msgs = cfg.get("messages", {})
    name = _get(msgs, "questName", "quest_name")
    if name: return name.strip()
    game = _get(msgs, "gameTitle", "game_title")
    if game: return game.strip()
    return cfg.get("application", {}).get("name") or f"Quest#{quest.get('id', '?')}"

def get_expires_at(quest): return _get(quest.get("config", {}), "expiresAt", "expires_at")

def get_user_status(quest):
    us = _get(quest, "userStatus", "user_status")
    return us if isinstance(us, dict) else {}

def is_completable(quest):
    expires = get_expires_at(quest)
    if expires:
        try:
            exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if exp_dt <= datetime.now(timezone.utc): return False
        except: pass
    tc = get_task_config(quest)
    if not tc or "tasks" not in tc: return False
    return any(tc["tasks"].get(t) is not None for t in SUPPORTED_TASKS)

def is_enrolled(quest): return bool(_get(get_user_status(quest), "enrolledAt", "enrolled_at"))
def is_completed(quest): return bool(_get(get_user_status(quest), "completedAt", "completed_at"))

def get_task_type(quest):
    tc = get_task_config(quest)
    if not tc or "tasks" not in tc: return None
    for t in SUPPORTED_TASKS:
        if tc["tasks"].get(t) is not None: return t
    return None

def get_seconds_needed(quest):
    tc = get_task_config(quest)
    task_type = get_task_type(quest)
    return tc["tasks"][task_type].get("target", 0) if tc and task_type else 0

def get_seconds_done(quest):
    task_type = get_task_type(quest)
    if not task_type: return 0
    progress = get_user_status(quest).get("progress", {})
    return progress.get(task_type, {}).get("value", 0) if progress else 0

class QuestAutocompleter:
    def __init__(self, api, interaction):
        self.api = api
        self.interaction = interaction
        self.user = interaction.user
        self.completed_ids = set()
        self.session_successes = []
        self.todo_initial = 0
        self.running = True

    async def send_dm(self, embed):
        try: return await self.user.send(embed=embed)
        except: return None

    async def fetch_quests(self):
        try:
            async with await self.api.get("/quests/@me") as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("quests", []) if isinstance(data, dict) else data if isinstance(data, list) else []
                return []
        except: return []

    async def enroll_quest(self, quest):
        qid = quest["id"]
        for _ in range(3):
            if not self.running: return False
            try:
                payload = {
                    "location": 11, "is_targeted": False,
                    "traffic_metadata_raw": quest.get("traffic_metadata_raw"),
                    "traffic_metadata_sealed": quest.get("traffic_metadata_sealed"),
                }
                async with await self.api.post(f"/quests/{qid}/enroll", payload) as r:
                    if r.status == 429:
                        await asyncio.sleep((await r.json()).get("retry_after", 5) + 1)
                        continue
                    return r.status in (200, 201, 204)
            except: return False
        return False

    async def auto_accept(self, quests):
        if not AUTO_ACCEPT: return quests
        unaccepted = [q for q in quests if not is_enrolled(q) and not is_completed(q) and is_completable(q)]
        for q in unaccepted:
            if not self.running: break
            await self.enroll_quest(q)
            await asyncio.sleep(3)
        await asyncio.sleep(2)
        return await self.fetch_quests()

    async def track_progress(self, quest, task_type, payload_builder, endpoint, interval):
        name = get_quest_name(quest)
        qid = quest["id"]
        seconds_needed = get_seconds_needed(quest)
        seconds_done = get_seconds_done(quest)
        msg = await self.send_dm(create_start_embed(name, task_type, seconds_needed))
        last_update_val = seconds_done
        while seconds_done < seconds_needed and self.running:
            try:
                payload = payload_builder(seconds_done, seconds_needed)
                async with await self.api.post(f"/quests/{qid}/{endpoint}", payload) as r:
                    if r.status == 200:
                        body = await r.json()
                        if endpoint == "video-progress":
                            if body.get("completed_at"): break
                            seconds_done = min(seconds_needed, payload["timestamp"])
                        else:
                            progress_data = body.get("progress", {})
                            if progress_data and task_type in progress_data:
                                seconds_done = progress_data[task_type].get("value", seconds_done)
                            if body.get("completed_at") or seconds_done >= seconds_needed: break
                        if msg and int(seconds_done) > int(last_update_val):
                            await msg.edit(embed=create_progress_embed(name, seconds_done, seconds_needed))
                            last_update_val = seconds_done
                    elif r.status == 429:
                        await asyncio.sleep((await r.json()).get("retry_after", 5) + 1)
            except: pass
            await asyncio.sleep(interval)
        try:
            terminal_payload = payload_builder(seconds_needed, seconds_needed)
            if endpoint == "heartbeat": terminal_payload["terminal"] = True
            await self.api.post(f"/quests/{qid}/{endpoint}", terminal_payload)
        except: pass
        if msg: await msg.edit(embed=create_complete_embed(name, task_type))
        else: await self.send_dm(create_complete_embed(name, task_type))
        self.session_successes.append(name)

    async def complete_video(self, quest):
        def build_payload(done, needed):
            return {"timestamp": min(needed, done + 7 + random.random())}
        await self.track_progress(quest, get_task_type(quest), build_payload, "video-progress", 1)

    async def complete_heartbeat(self, quest):
        pid = random.randint(1000, 30000)
        def build_payload(done, needed):
            return {"stream_key": f"call:0:{pid}", "terminal": False}
        await self.track_progress(quest, get_task_type(quest), build_payload, "heartbeat", HEARTBEAT_INTERVAL)

    async def complete_activity(self, quest):
        def build_payload(done, needed):
            return {"stream_key": "call:0:1", "terminal": False}
        await self.track_progress(quest, "PLAY_ACTIVITY", build_payload, "heartbeat", HEARTBEAT_INTERVAL)

    async def process_quest(self, quest):
        qid = quest.get("id")
        task_type = get_task_type(quest)
        if not task_type or qid in self.completed_ids: return
        if task_type in ("WATCH_VIDEO", "WATCH_VIDEO_ON_MOBILE"): await self.complete_video(quest)
        elif task_type in ("PLAY_ON_DESKTOP", "STREAM_ON_DESKTOP"): await self.complete_heartbeat(quest)
        elif task_type == "PLAY_ACTIVITY": await self.complete_activity(quest)
        self.completed_ids.add(qid)

    async def run(self):
        await self.send_dm(create_scan_embed(self.user))
        quests = await self.fetch_quests()
        if not quests:
            await self.send_dm(discord.Embed(title="❌ Lỗi", description="Không tìm thấy nhiệm vụ!", color=discord.Color.red()))
            self.running = False
            return
        self.todo_initial = sum(1 for q in quests if is_completable(q) and not is_completed(q))
        if self.todo_initial == 0:
            await self.send_dm(create_early_exit_embed(self.user, quests))
            self.running = False
            await self.api.close()
            if self.user.id in active_sessions: del active_sessions[self.user.id]
            return
        await self.send_dm(create_list_embed(quests))
        quests = await self.auto_accept(quests)
        while self.running:
            quests = await self.fetch_quests()
            if not quests: break
            actionable = [q for q in quests if is_enrolled(q) and not is_completed(q) and is_completable(q) and q.get("id") not in self.completed_ids]
            if not actionable: break
            for q in actionable:
                if not self.running: break
                await self.process_quest(q)
        if self.running:
            await self.interaction.channel.send(embed=create_final_summary_embed(self.user, self.session_successes, self.todo_initial))
        self.running = False
        await self.api.close()
        if self.user.id in active_sessions: del active_sessions[self.user.id]

# ==================== MODAL QUEST ====================
class QuestTokenModal(discord.ui.Modal, title="🎮 NHẬP TOKEN DISCORD"):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.TextInput(
            label="Discord Token",
            placeholder="Nhập token của bạn...",
            style=discord.TextStyle.paragraph,
            required=True
        ))

    async def on_submit(self, interaction: discord.Interaction):
        token = self.children[0].value.strip()
        
        if not token:
            await interaction.response.send_message("❌ Token không được để trống!", ephemeral=True)
            return
        
        if interaction.user.id in active_sessions:
            await interaction.response.send_message("⚠️ Một tiến trình khác đang hoạt động. Dùng `/cancel` trước!", ephemeral=True)
            return

        await interaction.response.send_message("✅ Đã nhận token! Đang xử lý... Vui lòng kiểm tra DM!", ephemeral=True)
        
        build_number = await fetch_latest_build_number()
        api = DiscordAPI(token, build_number)
        
        is_valid = await api.validate_token()
        if not is_valid:
            await api.close()
            await interaction.followup.send("⚠️ Token không hợp lệ hoặc đã hết hạn!", ephemeral=True)
            return

        completer = QuestAutocompleter(api, interaction)
        task = asyncio.create_task(completer.run())
        
        active_sessions[interaction.user.id] = {
            "task": task,
            "completer": completer,
            "api": api
        }

# ==================== MODAL HYPESQUAD ====================
class HypeSquadModal(discord.ui.Modal, title="🏠 LẤY HUY HIỆU HYPESQUAD"):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.TextInput(
            label="Discord Token",
            placeholder="Nhập token của bạn...",
            required=True
        ))
        self.add_item(discord.ui.TextInput(
            label="Màu nhà (Tím/Đỏ/Xanh)",
            placeholder="Nhập: Tím, Đỏ, hoặc Xanh",
            required=True
        ))

    async def on_submit(self, interaction: discord.Interaction):
        token = self.children[0].value.strip()
        color = self.children[1].value.strip().lower()
        
        color_map = {"tím": 1, "tim": 1, "đỏ": 2, "do": 2, "xanh": 3}
        house_id = color_map.get(color)
        
        if not house_id:
            await interaction.response.send_message("❌ Màu không hợp lệ! Chọn: Tím, Đỏ, Xanh", ephemeral=True)
            return
        
        house_name = {1: "Bravery (Tím) 🛡️", 2: "Brilliance (Đỏ) 💡", 3: "Balance (Xanh) ⚖️"}[house_id]
        
        await interaction.response.defer(ephemeral=True)
        
        headers = {"Authorization": token, "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://discord.com/api/v9/users/@me", headers=headers) as r:
                    if r.status != 200:
                        await interaction.followup.send("❌ Token sai hoặc hết hạn!", ephemeral=True)
                        return
                    user = await r.json()
                
                payload = {"house_id": house_id}
                async with session.post("https://discord.com/api/v9/hypesquad/online", headers=headers, json=payload) as r:
                    if r.status == 204:
                        embed = discord.Embed(title="✅ THÀNH CÔNG!", color=0x57F287)
                        embed.description = f"👤 **{user['username']}**\n🏠 Đã gia nhập: {house_name}\n✨ Huy hiệu sẽ hiển thị sau vài phút!"
                        await interaction.followup.send(embed=embed)
                    else:
                        await interaction.followup.send(f"❌ Thất bại! Mã lỗi: {r.status}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Lỗi: {e}", ephemeral=True)

# ==================== MODAL SCOLD ====================
class ScoldModal(discord.ui.Modal, title="💢 CHỬI - SCOLD"):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.TextInput(
            label="Discord Token",
            placeholder="Nhập token của tài khoản muốn chửi...",
            required=True
        ))
        self.add_item(discord.ui.TextInput(
            label="Channel ID",
            placeholder="Nhập ID kênh cần spam...",
            required=True
        ))
        self.add_item(discord.ui.TextInput(
            label="Nội dung chửi",
            placeholder="Nhập nội dung (mỗi dòng 1 câu)",
            style=discord.TextStyle.paragraph,
            required=True
        ))
        self.add_item(discord.ui.TextInput(
            label="Delay (giây)",
            placeholder="Thời gian giữa các lần gửi (VD: 1)",
            required=False,
            default="1"
        ))

    async def on_submit(self, interaction: discord.Interaction):
        token = self.children[0].value.strip()
        channel_id = self.children[1].value.strip()
        content = self.children[2].value.strip()
        delay = float(self.children[3].value.strip() or "1")
        
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        
        if not token:
            await interaction.response.send_message("❌ Token không được để trống!", ephemeral=True)
            return
        
        if not channel_id.isdigit():
            await interaction.response.send_message("❌ Channel ID phải là số!", ephemeral=True)
            return
        
        if not lines:
            await interaction.response.send_message("❌ Nội dung không được để trống!", ephemeral=True)
            return
        
        await interaction.response.send_message(f"💢 Đã nhận token! Bắt đầu spam {len(lines)} câu vào kênh {channel_id} với delay {delay}s...\n🛑 Dùng `/cancel` để dừng!", ephemeral=True)
        
        task = asyncio.create_task(scold_spam(token, channel_id, lines, delay, interaction))
        spam_tasks[interaction.user.id] = task

async def scold_spam(token, channel_id, messages, delay, interaction):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    
    async with aiohttp.ClientSession() as session:
        async with session.get("https://discord.com/api/v9/users/@me", headers=headers) as r:
            if r.status != 200:
                await interaction.followup.send("❌ Token sai hoặc hết hạn!", ephemeral=True)
                return
            user = await r.json()
            await interaction.followup.send(f"✅ Đăng nhập: {user['username']}\n💢 Bắt đầu spam...\n🛑 Dùng `/cancel` để dừng.", ephemeral=True)
        
        idx = 0
        while True:
            try:
                msg = messages[idx % len(messages)]
                payload = {"content": msg[:1999]}
                
                async with session.post(url, json=payload, headers=headers) as r:
                    if r.status == 200:
                        print(f"[SCOLD] ✅ {user['username']}: {msg[:50]}...")
                    elif r.status == 429:
                        retry = (await r.json()).get("retry_after", 1)
                        await asyncio.sleep(retry)
                        continue
                    elif r.status == 401:
                        await interaction.followup.send("❌ Token hết hạn! Dừng spam.", ephemeral=True)
                        break
                    elif r.status == 403:
                        await interaction.followup.send("❌ Không có quyền gửi tin nhắn vào kênh này!", ephemeral=True)
                        break
                    else:
                        print(f"[SCOLD] Lỗi {r.status}")
                
                idx += 1
                await asyncio.sleep(delay)
                
            except asyncio.CancelledError:
                await interaction.followup.send("🛑 Đã dừng spam!", ephemeral=True)
                break
            except Exception as e:
                print(f"[SCOLD] Lỗi: {e}")
                await asyncio.sleep(delay)

# ==================== MENU ====================
class MainSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="🎮 Làm nhiệm vụ (Quest)", value="quest", description="Tự động làm nhiệm vụ Discord", emoji="🎮"),
            discord.SelectOption(label="🏠 Lấy huy hiệu HypeSquad", value="hypesquad", description="Nhận huy hiệu theo màu nhà", emoji="🏠"),
            discord.SelectOption(label="💢 Chửi (Scold)", value="scold", description="Dùng token để spam nội dung chửi", emoji="💢"),
            discord.SelectOption(label="❌ Hủy", value="cancel", description="Đóng menu", emoji="❌"),
        ]
        super().__init__(placeholder="📋 Chọn chức năng bạn muốn...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "quest":
            await interaction.response.send_modal(QuestTokenModal())
        elif self.values[0] == "hypesquad":
            await interaction.response.send_modal(HypeSquadModal())
        elif self.values[0] == "scold":
            await interaction.response.send_modal(ScoldModal())
        elif self.values[0] == "cancel":
            await interaction.response.edit_message(view=None)

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(MainSelect())

# ==================== BOT ====================
class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

@bot.tree.command(name="menu", description="📋 Hiển thị menu chính")
async def cmd_menu(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📋 KÊNH-CHAT-CHUNG",
        description="**🔴 10 Online**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=0x2b2d31
    )
    embed.add_field(
        name="🎮 **Chọn chức năng:**",
        value="""
        > • **Làm nhiệm vụ (Quest)** - Tự động hoàn thành nhiệm vụ Discord
        > • **Lấy huy hiệu HypeSquad** - Nhận huy hiệu theo màu nhà
        > • **Chửi (Scold)** - Dùng token spam nội dung vào kênh
        """,
        inline=False
    )
    embed.add_field(
        name="📱 **Hướng dẫn lấy token:**",
        value="[Click vào đây để xem video hướng dẫn lấy token](https://files.catbox.moe/lsl6pa.mp4)",
        inline=False
    )
    embed.set_footer(text="Nguyen Khoi • Chọn từ menu thả xuống")
    
    await interaction.response.send_message(embed=embed, view=MainView())

@bot.tree.command(name="cancel", description="🛑 Dừng tất cả tiến trình đang chạy")
async def cmd_cancel(interaction: discord.Interaction):
    user_id = interaction.user.id
    stopped = False
    
    # Dừng quest
    if user_id in active_sessions:
        session = active_sessions[user_id]
        session["completer"].running = False
        session["task"].cancel()
        await session["api"].close()
        del active_sessions[user_id]
        stopped = True
    
    # Dừng spam
    if user_id in spam_tasks:
        spam_tasks[user_id].cancel()
        del spam_tasks[user_id]
        stopped = True
    
    if stopped:
        await interaction.response.send_message("🛑 **Đã dừng tất cả tiến trình thành công!**", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Không có tiến trình nào đang chạy!", ephemeral=True)

@bot.event
async def on_ready():
    print(f"✅ Bot đã sẵn sàng: {bot.user}")
    await bot.tree.sync()

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
