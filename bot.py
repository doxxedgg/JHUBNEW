# bot.py
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View
import random
import time
import json
import os
from datetime import timedelta

# -------- CONFIG --------
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    print("❌ DISCORD_TOKEN not found in environment variables. Exiting.")
    exit()

DATA_FILE = "data.json"
AUTOSAVE_INTERVAL = 60  # seconds

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------- STORAGE (loaded from JSON) --------
# data structure:
# {
#   "balances": { "<user_id>": {"wallet": int, "bank": int} },
#   "daily": { "<user_id>": last_claim_timestamp },
#   "config": { "welcome": {"<guild_id>": channel_id}, "goodbye": {...}, "log": {...} }
# }
data = {"balances": {}, "daily": {}, "config": {"welcome": {}, "goodbye": {}, "log": {}}}

def load_data():
    global data
    if not os.path.exists(DATA_FILE):
        save_data()  # create initial file
        return
    try:
        with open(DATA_FILE, "r") as f:
            loaded = json.load(f)
            # minimal validation/merge
            if isinstance(loaded, dict):
                # merge so default keys remain
                data.update(loaded)
            print("💾 Data loaded from", DATA_FILE)
    except Exception as e:
        print("⚠️ Error loading data:", e)

def save_data():
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print("⚠️ Error saving data:", e)

# autosave task
@tasks.loop(seconds=AUTOSAVE_INTERVAL)
async def autosave():
    save_data()

# -------- ECONOMY HELPERS --------
START_WALLET = 100
DAILY_AMOUNT = 100

def ensure_user_entry(uid: int):
    s = str(uid)
    if s not in data["balances"]:
        data["balances"][s] = {"wallet": START_WALLET, "bank": 0}

def get_wallet(uid: int) -> int:
    ensure_user_entry(uid)
    return int(data["balances"][str(uid)]["wallet"])

def get_bank(uid: int) -> int:
    ensure_user_entry(uid)
    return int(data["balances"][str(uid)]["bank"])

def set_wallet(uid: int, amount: int):
    ensure_user_entry(uid)
    data["balances"][str(uid)]["wallet"] = max(0, int(amount))
    save_data()

def set_bank(uid: int, amount: int):
    ensure_user_entry(uid)
    data["balances"][str(uid)]["bank"] = max(0, int(amount))
    save_data()

def add_wallet(uid: int, amount: int):
    set_wallet(uid, get_wallet(uid) + int(amount))

def add_bank(uid: int, amount: int):
    set_bank(uid, get_bank(uid) + int(amount))

def total_balance(uid: int) -> int:
    return get_wallet(uid) + get_bank(uid)

# config helpers
def set_config(kind: str, guild_id: int, channel_id: int):
    data.setdefault("config", {"welcome": {}, "goodbye": {}, "log": {}})
    data["config"].setdefault(kind, {})
    data["config"][kind][str(guild_id)] = channel_id
    save_data()

def get_config_channel(kind: str, guild_id: int):
    return data.get("config", {}).get(kind, {}).get(str(guild_id))

# daily helpers
def get_last_daily(uid: int) -> float:
    return float(data.get("daily", {}).get(str(uid), 0))

def set_last_daily(uid: int, ts: float):
    data.setdefault("daily", {})
    data["daily"][str(uid)] = ts
    save_data()

# -------- LOGGING HELPERS --------
async def send_log_embed(guild: discord.Guild, embed: discord.Embed):
    chan_id = get_config_channel("log", guild.id)
    if not chan_id:
        return
    channel = guild.get_channel(int(chan_id))
    if channel:
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

# -------- MODERATION / UTILITY COMMANDS (slash) --------
@bot.tree.command(description="Ban a member")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    await interaction.response.defer(ephemeral=True)
    try:
        await member.ban(reason=reason)
        await interaction.followup.send(f"🔨 Banned {member.mention}")
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed to ban: {e}")

@bot.tree.command(description="Unban a user by ID")
@app_commands.default_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str):
    await interaction.response.defer(ephemeral=True)
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        await interaction.followup.send(f"✅ Unbanned {user}")
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed to unban: {e}")

@bot.tree.command(description="Kick a member")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    await interaction.response.defer(ephemeral=True)
    try:
        await member.kick(reason=reason)
        await interaction.followup.send(f"👢 Kicked {member.mention}")
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed to kick: {e}")

@bot.tree.command(description="Timeout (mute) a member for seconds")
@app_commands.default_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member, seconds: int, reason: str = None):
    await interaction.response.defer(ephemeral=True)
    try:
        until = discord.utils.utcnow() + timedelta(seconds=seconds)
        await member.timeout(until, reason=reason)
        await interaction.followup.send(f"🔇 Muted {member.mention} for {seconds}s")
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed to timeout: {e}")

@bot.tree.command(description="Remove timeout (unmute)")
@app_commands.default_permissions(moderate_members=True)
async def unmute(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    try:
        await member.timeout(None)
        await interaction.followup.send(f"⏱️ Unmuted {member.mention}")
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed to unmute: {e}")

@bot.tree.command(description="Delete last N messages")
@app_commands.default_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    try:
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🧹 Deleted {len(deleted)} messages", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed to purge: {e}", ephemeral=True)

@bot.tree.command(description="Set channel slowmode in seconds")
@app_commands.default_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, seconds: int):
    await interaction.response.defer(ephemeral=True)
    try:
        await interaction.channel.edit(slowmode_delay=seconds)
        await interaction.followup.send(f"🐢 Slowmode set to {seconds}s", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed to set slowmode: {e}", ephemeral=True)

@bot.tree.command(description="Lock or unlock this channel")
@app_commands.default_permissions(manage_channels=True)
async def lockdown(interaction: discord.Interaction, enable: bool):
    await interaction.response.defer(ephemeral=True)
    try:
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None if not enable else False
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.followup.send("🔒 Locked" if enable else "🔓 Unlocked", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed to change lockdown: {e}", ephemeral=True)

# config commands
@bot.tree.command(description="Set a log channel")
@app_commands.default_permissions(administrator=True)
async def setlog(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    try:
        set_config("log", interaction.guild.id, channel.id)
        await interaction.followup.send(f"📝 Log channel saved: {channel.mention}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed: {e}", ephemeral=True)

@bot.tree.command(description="Set a welcome channel")
@app_commands.default_permissions(administrator=True)
async def setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    try:
        set_config("welcome", interaction.guild.id, channel.id)
        await interaction.followup.send(f"👋 Welcome channel saved: {channel.mention}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed: {e}", ephemeral=True)

@bot.tree.command(description="Set a goodbye channel")
@app_commands.default_permissions(administrator=True)
async def setgoodbye(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    try:
        set_config("goodbye", interaction.guild.id, channel.id)
        await interaction.followup.send(f"👋 Goodbye channel saved: {channel.mention}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed: {e}", ephemeral=True)

# logging events
@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    embed = discord.Embed(title="Message Deleted", color=discord.Color.red())
    embed.add_field(name="User", value=message.author.mention, inline=False)
    embed.add_field(name="Channel", value=message.channel.mention, inline=False)
    embed.add_field(name="Content", value=message.content or "*empty*", inline=False)
    await send_log_embed(message.guild, embed)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if not before.guild or before.author.bot or before.content == after.content:
        return
    embed = discord.Embed(title="Message Edited", color=discord.Color.orange())
    embed.add_field(name="User", value=before.author.mention, inline=False)
    embed.add_field(name="Channel", value=before.channel.mention, inline=False)
    embed.add_field(name="Before", value=before.content or "*empty*", inline=False)
    embed.add_field(name="After", value=after.content or "*empty*", inline=False)
    await send_log_embed(before.guild, embed)

@bot.event
async def on_member_join(member: discord.Member):
    cid = get_config_channel("welcome", member.guild.id)
    if cid:
        ch = member.guild.get_channel(int(cid))
        if ch:
            try:
                await ch.send(f"👋 Welcome {member.mention} to **{member.guild.name}**!")
            except Exception:
                pass
    embed = discord.Embed(title="Member Joined", description=member.mention, color=discord.Color.green())
    await send_log_embed(member.guild, embed)

@bot.event
async def on_member_remove(member: discord.Member):
    cid = get_config_channel("goodbye", member.guild.id)
    if cid:
        ch = member.guild.get_channel(int(cid))
        if ch:
            try:
                await ch.send(f"😢 {member.mention} has left **{member.guild.name}**.")
            except Exception:
                pass
    embed = discord.Embed(title="Member Left", description=member.mention, color=discord.Color.red())
    await send_log_embed(member.guild, embed)

# nickname/say/role
@bot.tree.command(description="Change a member's nickname")
@app_commands.default_permissions(manage_nicknames=True)
async def nick(interaction: discord.Interaction, member: discord.Member, new_nick: str):
    await interaction.response.defer(ephemeral=True)
    try:
        old = member.nick or member.name
        await member.edit(nick=new_nick)
        await interaction.followup.send(f"✏️ Changed nickname from **{old}** to **{new_nick}**", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed: {e}", ephemeral=True)

@bot.tree.command(description="Make the bot say something")
async def say(interaction: discord.Interaction, *, message: str):
    await interaction.response.send_message(message)

@bot.tree.command(description="Add a role to a member")
@app_commands.default_permissions(manage_roles=True)
async def addrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await interaction.response.defer(ephemeral=True)
    try:
        await member.add_roles(role)
        await interaction.followup.send(f"➕ Added role {role.mention} to {member.mention}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed: {e}", ephemeral=True)

@bot.tree.command(description="Remove a role from a member")
@app_commands.default_permissions(manage_roles=True)
async def removerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await interaction.response.defer(ephemeral=True)
    try:
        await member.remove_roles(role)
        await interaction.followup.send(f"➖ Removed role {role.mention} from {member.mention}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed: {e}", ephemeral=True)

# -------- ECONOMY COMMANDS --------
@bot.tree.command(description="Check your wallet and bank balance")
async def balance(interaction: discord.Interaction):
    w = get_wallet(interaction.user.id)
    b = get_bank(interaction.user.id)
    await interaction.response.send_message(f"💰 {interaction.user.mention}\nWallet: ${w}\nBank: ${b}\nTotal: ${w + b}")

@bot.tree.command(description="Deposit money into your bank")
async def deposit(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    uid = interaction.user.id
    if amount <= 0:
        await interaction.followup.send("❌ Amount must be positive.", ephemeral=True); return
    if amount > get_wallet(uid):
        await interaction.followup.send("❌ Not enough in wallet.", ephemeral=True); return
    set_wallet(uid, get_wallet(uid) - amount)
    set_bank(uid, get_bank(uid) + amount)
    await interaction.followup.send(f"🏦 Deposited ${amount}. Wallet: ${get_wallet(uid)} | Bank: ${get_bank(uid)}", ephemeral=True)

@bot.tree.command(description="Withdraw money from your bank")
async def withdraw(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    uid = interaction.user.id
    if amount <= 0:
        await interaction.followup.send("❌ Amount must be positive.", ephemeral=True); return
    if amount > get_bank(uid):
        await interaction.followup.send("❌ Not enough in bank.", ephemeral=True); return
    set_bank(uid, get_bank(uid) - amount)
    set_wallet(uid, get_wallet(uid) + amount)
    await interaction.followup.send(f"🏦 Withdrew ${amount}. Wallet: ${get_wallet(uid)} | Bank: ${get_bank(uid)}", ephemeral=True)

@bot.tree.command(description="Send cash from your wallet to another user")
async def send(interaction: discord.Interaction, member: discord.Member, amount: int):
    await interaction.response.defer(ephemeral=True)
    sender = interaction.user.id
    receiver = member.id
    if amount <= 0:
        await interaction.followup.send("❌ Amount must be positive.", ephemeral=True); return
    if amount > get_wallet(sender):
        await interaction.followup.send("❌ Not enough in wallet.", ephemeral=True); return
    set_wallet(sender, get_wallet(sender) - amount)
    set_wallet(receiver, get_wallet(receiver) + amount)
    await interaction.followup.send(f"💸 Sent ${amount} to {member.mention}. Your wallet: ${get_wallet(sender)}", ephemeral=True)

@bot.tree.command(description="Add cash to a user (admin)")
@app_commands.default_permissions(administrator=True)
async def addcash(interaction: discord.Interaction, member: discord.Member, amount: int):
    await interaction.response.defer(ephemeral=True)
    add_wallet(member.id, amount)
    await interaction.followup.send(f"✅ Added ${amount} to {member.mention}. Wallet: ${get_wallet(member.id)}", ephemeral=True)

@bot.tree.command(description="Remove cash from a user (admin)")
@app_commands.default_permissions(administrator=True)
async def removecash(interaction: discord.Interaction, member: discord.Member, amount: int):
    await interaction.response.defer(ephemeral=True)
    set_wallet(member.id, get_wallet(member.id) - amount)
    await interaction.followup.send(f"❌ Removed ${amount} from {member.mention}. Wallet: ${get_wallet(member.id)}", ephemeral=True)

@bot.tree.command(description="Claim daily reward")
async def daily(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    uid = interaction.user.id
    now = time.time()
    last = get_last_daily(uid)
    if now - last < 24 * 3600:
        remaining = 24 * 3600 - (now - last)
        h = int(remaining // 3600)
        m = int((remaining % 3600) // 60)
        s = int(remaining % 60)
        await interaction.followup.send(f"⏳ Already claimed. Come back in {h}h {m}m {s}s.", ephemeral=True)
        return
    add_wallet(uid, DAILY_AMOUNT)
    set_last_daily(uid, now)
    await interaction.followup.send(f"🎉 Claimed daily ${DAILY_AMOUNT}! Wallet: ${get_wallet(uid)}", ephemeral=True)

# -------- GAMES --------
# Roulette: bet and choose "red", "black", or "green"
@bot.tree.command(description="Play roulette (bet and choose red|black|green)")
async def roulette(interaction: discord.Interaction, bet: int, choice: str):
    await interaction.response.defer()
    uid = interaction.user.id
    if bet <= 0:
        await interaction.followup.send("❌ Bet must be positive.")
        return
    if bet > get_wallet(uid):
        await interaction.followup.send("❌ Not enough wallet cash.")
        return
    choice = choice.lower()
    if choice not in ("red", "black", "green"):
        await interaction.followup.send("❌ Invalid choice. Choose red, black, or green.")
        return

    # Simulate wheel: 0 is green, 1-36 alternate red/black (approx)
    spin = random.randint(0, 36)
    if spin == 0:
        result = "green"
    else:
        # simple parity color mapping: even -> black, odd -> red (not exact real roulette but fine)
        result = "black" if spin % 2 == 0 else "red"

    if choice == result:
        if result == "green":
            payout = bet * 14
        else:
            payout = bet * 2
        add_wallet(uid, payout)
        outcome = f"🎉 It landed on **{spin} ({result})**! You won ${payout}."
    else:
        set_wallet(uid, get_wallet(uid) - bet)
        outcome = f"😢 It landed on **{spin} ({result})**. You lost ${bet}."

    await interaction.followup.send(f"{outcome}\n💰 Wallet: ${get_wallet(uid)}")

# Interactive Blackjack with Hit/Stand buttons
@bot.tree.command(description="Play Blackjack (interactive Hit/Stand)")
async def blackjack(interaction: discord.Interaction, bet: int):
    await interaction.response.defer()
    uid = interaction.user.id
    if bet <= 0:
        await interaction.followup.send("❌ Bet must be positive.")
        return
    if bet > get_wallet(uid):
        await interaction.followup.send("❌ Not enough wallet cash.")
        return

    def draw_card():
        return random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11])  # 11 = Ace

    def hand_value(hand):
        total = sum(hand)
        aces = hand.count(11)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    player = [draw_card(), draw_card()]
    dealer = [draw_card(), draw_card()]

    class BlackjackView(View):
        def __init__(self, uid, bet):
            super().__init__(timeout=120)
            self.uid = uid
            self.bet = bet
            self.msg = None

        async def interaction_check(self, i: discord.Interaction) -> bool:
            if i.user.id != self.uid:
                await i.response.send_message("❌ This is not your game.", ephemeral=True)
                return False
            return True

        async def update_message(self):
            if self.msg:
                await self.msg.edit(content=f"🃏 **Blackjack**\nYour hand: {player} (total {hand_value(player)})\nDealer shows: {dealer[0]} ?", view=self)

        @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
        async def hit(self, i: discord.Interaction, b: Button):
            player.append(draw_card())
            if hand_value(player) > 21:
                await self.finish(i)
            else:
                await i.response.defer()
                await self.update_message()

        @discord.ui.button(label="Stand", style=discord.ButtonStyle.gray)
        async def stand(self, i: discord.Interaction, b: Button):
            await self.finish(i)

        async def finish(self, i: discord.Interaction):
            # dealer plays
            while hand_value(dealer) < 17:
                dealer.append(draw_card())
            p_total = hand_value(player)
            d_total = hand_value(dealer)
            if p_total > 21:
                set_wallet(uid, get_wallet(uid) - bet)
                result = f"💥 You busted with {p_total}. You lose ${bet}."
            elif d_total > 21 or p_total > d_total:
                add_wallet(uid, bet)
                result = f"🎉 You win! {p_total} vs {d_total}. You gain ${bet}."
            elif p_total < d_total:
                set_wallet(uid, get_wallet(uid) - bet)
                result = f"😢 You lose. {p_total} vs {d_total}. You lose ${bet}."
            else:
                result = f"🤝 It's a tie! {p_total} vs {d_total}. No cash lost."
            save_data()
            # edit the message to final state and remove buttons
            try:
                await i.response.edit_message(
                    content=(f"🃏 **Blackjack Finished**\nYour hand: {player} (total {p_total})\n"
                             f"Dealer hand: {dealer} (total {d_total})\n\n{result}\n💰 Wallet: ${get_wallet(uid)}"),
                    view=None
                )
            except Exception:
                # fallback if interaction already responded
                try:
                    await self.msg.edit(content=(f"🃏 **Blackjack Finished**\nYour hand: {player} (total {p_total})\n"
                                                 f"Dealer hand: {dealer} (total {d_total})\n\n{result}\n💰 Wallet: ${get_wallet(uid)}"),
                                         view=None)
                except Exception:
                    pass

    view = BlackjackView(uid, bet)
    # send initial message and store message reference
    message = await interaction.followup.send(f"🃏 **Blackjack**\nYour hand: {player} (total {hand_value(player)})\nDealer shows: {dealer[0]} ?", view=view)
    # The followup send returns a message object; store it
    view.msg = message

# -------- LEADERBOARD & HELP --------
@bot.tree.command(description="Show the richest players (wallet + bank)")
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    entries = []
    for uid_str, bal in data.get("balances", {}).items():
        try:
            uid = int(uid_str)
            total = int(bal.get("wallet", 0)) + int(bal.get("bank", 0))
            entries.append((uid, total))
        except Exception:
            continue
    entries.sort(key=lambda x: x[1], reverse=True)
    top = entries[:10]
    if not top:
        await interaction.followup.send("No balances recorded yet.")
        return
    lines = []
    for idx, (uid, total) in enumerate(top, start=1):
        try:
            user = await bot.fetch_user(uid)
            name = user.name
        except Exception:
            name = str(uid)
        lines.append(f"**{idx}.** {name} — ${total}")
    await interaction.followup.send("💰 **Leaderboard**\n" + "\n".join(lines))

# dynamic !cmds that lists slash commands
@bot.command(name="cmds")
async def cmds(ctx: commands.Context):
    lines = ["**Slash Commands:**"]
    for cmd in bot.tree.walk_commands():
        lines.append(f"/{cmd.name} — {cmd.description or 'No description'}")
    await ctx.send("\n".join(lines))

# -------- STARTUP / SHUTDOWN --------
@bot.event
async def on_ready():
    load_data()
    autosave.start()
    try:
        await bot.tree.sync()
    except Exception:
        pass
    print(f"✅ Bot ready: {bot.user} (id: {bot.user.id})")

@bot.event
async def on_disconnect():
    save_data()

# ensure data saved on exit signals too (best-effort)
import atexit
atexit.register(lambda: save_data())

# Run
if __name__ == "__main__":
    bot.run(TOKEN)
