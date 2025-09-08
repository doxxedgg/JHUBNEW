import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import random, time, json, os
from datetime import timedelta

 =========================
# Config
 =========================
TOKEN = os.environ.get("DISCORD_TOKEN")
DATA_FILE = "data.json"
START_BALANCE = 500

# =========================
# Data setup (auto-create)
# =========================
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump(
            {
                "balances": {},
                "config": {},
                "tickets": {},       # ticket_channel_id -> { opener_id, opened_at }
                "ticket_counts": {}  # staff_id -> count
            },
            f
        )

with open(DATA_FILE, "r") as f:
    data = json.load(f)

balances: dict = data.setdefault("balances", {})
config: dict = data.setdefault("config", {})
tickets: dict = data.setdefault("tickets", {})
ticket_counts: dict = data.setdefault("ticket_counts", {})

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def ensure_user(uid):
    uid = str(uid)
    balances.setdefault(uid, {
        "wallet": START_BALANCE,
        "bank": 0,
        "last_daily": 0,
        "last_work": 0,
        "last_steal": 0
    })
    return balances[uid]

def get_wallet(uid): return ensure_user(uid)["wallet"]
def get_bank(uid): return ensure_user(uid)["bank"]
def set_wallet(uid, amt):
    ensure_user(uid)["wallet"] = int(amt); save_data()
def set_bank(uid, amt):
    ensure_user(uid)["bank"] = int(amt); save_data()
def add_wallet(uid, amt):
    u = ensure_user(uid); u["wallet"] = int(u["wallet"] + int(amt)); save_data()

# =========================
# Bot setup
=========================
intents = discord.Intents.default()
intents.members = True
intents.message_content = False  # we only need prefix for !cmds
bot = commands.Bot(command_prefix="!", intents=intents)

def emb(title, desc, color=discord.Color.blurple()):
    return discord.Embed(title=title, description=desc, color=color)

=========================
# Events
# =========================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user} | Slash commands synced.")

@bot.event
async def on_member_join(member: discord.Member):
    ch_id = config.get("welcome_channel")
    if ch_id:
        ch = bot.get_channel(ch_id)
        if ch:
            await ch.send(embed=emb("🎉 Welcome!", f"Welcome {member.mention}!"))

@bot.event
async def on_member_remove(member: discord.Member):
    ch_id = config.get("goodbye_channel")
    if ch_id:
        ch = bot.get_channel(ch_id)
        if ch:
            await ch.send(embed=emb("👋 Goodbye", f"{member.mention} has left the server."))
# =========================
# Basic config commands
# =========================
@bot.tree.command(description="Set the welcome channel")
@app_commands.default_permissions(administrator=True)
async def setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    config["welcome_channel"] = channel.id
    save_data()
    await interaction.response.send_message(embed=emb("✅ Set", f"Welcome channel → {channel.mention}"))

@bot.tree.command(description="Set the goodbye channel")
@app_commands.default_permissions(administrator=True)
async def setgoodbye(interaction: discord.Interaction, channel: discord.TextChannel):
    config["goodbye_channel"] = channel.id
    save_data()
    await interaction.response.send_message(embed=emb("✅ Set", f"Goodbye channel → {channel.mention}"))

# =========================
# Moderation
# =========================
@bot.tree.command(description="Ban a member")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.ban(reason=reason)
    await interaction.response.send_message(embed=emb("🔨 Ban", f"{member.mention} was banned.\nReason: {reason}"))

@bot.tree.command(description="Kick a member")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.kick(reason=reason)
    await interaction.response.send_message(embed=emb("👢 Kick", f"{member.mention} was kicked.\nReason: {reason}"))

@bot.tree.command(description="Mute a member (timeout in minutes)")
@app_commands.default_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason"):
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    await member.timeout(until, reason=reason)
    await interaction.response.send_message(embed=emb("🔇 Mute", f"{member.mention} muted for {minutes}m.\nReason: {reason}"))

@bot.tree.command(description="Unmute a member")
@app_commands.default_permissions(moderate_members=True)
async def unmute(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None)
    await interaction.response.send_message(embed=emb("🔈 Unmute", f"{member.mention} has been unmuted."))

@bot.tree.command(description="Change a member's nickname")
@app_commands.default_permissions(manage_nicknames=True)
async def nick(interaction: discord.Interaction, member: discord.Member, new_nick: str):
    await member.edit(nick=new_nick)
    await interaction.response.send_message(embed=emb("✏️ Nickname", f"{member.mention}'s nickname changed to **{new_nick}**."))

@bot.tree.command(description="Make the bot repeat something")
@app_commands.default_permissions(manage_messages=True)
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(embed=emb("📣 Say", "Sent."), ephemeral=True)
    await interaction.channel.send(message)

@bot.tree.command(description="Add a role to a member")
@app_commands.default_permissions(manage_roles=True)
async def addrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.add_roles(role)
    await interaction.response.send_message(embed=emb("➕ Role", f"Added {role.mention} to {member.mention}"))

@bot.tree.command(description="Remove a role from a member")
@app_commands.default_permissions(manage_roles=True)
async def removerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.remove_roles(role)
    await interaction.response.send_message(embed=emb("➖ Role", f"Removed {role.mention} from {member.mention}"))

$# =========================$
# Economy
$# =========================$
@bot.tree.command(description="Check balance (optionally another user's)")
async def balance(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    u = ensure_user(member.id)
    await interaction.response.send_message(embed=emb("💰 Balance", f"{member.mention}\nWallet: ${u['wallet']}\nBank: ${u['bank']}"))

@bot.tree.command(description="Claim daily reward (24h)")
async def daily(interaction: discord.Interaction):
    u = ensure_user(interaction.user.id)
    now = int(time.time())
    if now - u["last_daily"] < 86400:
        remaining = 86400 - (now - u["last_daily"])
        return await interaction.response.send_message(
            embed=emb("⏳ Daily Cooldown", f"Come back in {remaining//3600}h {(remaining%3600)//60}m."),
            ephemeral=True
        )
    reward = random.randint(150, 300)
    add_wallet(interaction.user.id, reward)
    u["last_daily"] = now; save_data()
    await interaction.response.send_message(embed=emb("🎁 Daily", f"You received **${reward}**!"))

@bot.tree.command(description="Work for money (8 minute cooldown)")
async def work(interaction: discord.Interaction):
    u = ensure_user(interaction.user.id)
    now = int(time.time())
    if now - u["last_work"] < 480:
        remaining = 480 - (now - u["last_work"])
        return await interaction.response.send_message(
            embed=emb("⏳ Work Cooldown", f"Wait {remaining//60}m {remaining%60}s."),
            ephemeral=True
        )
    earnings = random.randint(60, 160)
    add_wallet(interaction.user.id, earnings)
    u["last_work"] = now; save_data()
    await interaction.response.send_message(embed=emb("💼 Work", f"You earned **${earnings}**!"))

@bot.tree.command(description="Steal from someone (15 minute cooldown)")
async def steal(interaction: discord.Interaction, member: discord.Member):
    if member.id == interaction.user.id:
        return await interaction.response.send_message(embed=emb("❌ Error", "You can't steal from yourself."), ephemeral=True)
    u = ensure_user(interaction.user.id)
    t = ensure_user(member.id)
    now = int(time.time())
    if now - u["last_steal"] < 900:
        remaining = 900 - (now - u["last_steal"])
        return await interaction.response.send_message(
            embed=emb("⏳ Steal Cooldown", f"Wait {remaining//60}m {remaining%60}s."),
            ephemeral=True
        )
    if t["wallet"] < 50:
        return await interaction.response.send_message(embed=emb("❌ Failed", "Target is too poor."), ephemeral=True)

    if random.random() < 0.5:
        amt = random.randint(20, min(120, t["wallet"]))
        add_wallet(interaction.user.id, amt)
        add_wallet(member.id, -amt)
        msg = f"💰 You stole **${amt}** from {member.mention}!"
    else:
        fine = random.randint(20, 100)
        add_wallet(interaction.user.id, -fine)
        msg = f"🚓 You were caught and fined **${fine}**."

    u["last_steal"] = now; save_data()
    await interaction.response.send_message(embed=emb("🕵️ Steal", msg))

@bot.tree.command(description="Deposit to bank")
async def deposit(interaction: discord.Interaction, amount: int):
    if amount <= 0 or get_wallet(interaction.user.id) < amount:
        return await interaction.response.send_message(embed=emb("❌ Error", "Invalid amount."), ephemeral=True)
    add_wallet(interaction.user.id, -amount)
    set_bank(interaction.user.id, get_bank(interaction.user.id) + amount)
    await interaction.response.send_message(embed=emb("🏦 Deposit", f"Deposited **${amount}**."))

@bot.tree.command(description="Withdraw from bank")
async def withdraw(interaction: discord.Interaction, amount: int):
    if amount <= 0 or get_bank(interaction.user.id) < amount:
        return await interaction.response.send_message(embed=emb("❌ Error", "Invalid amount."), ephemeral=True)
    set_bank(interaction.user.id, get_bank(interaction.user.id) - amount)
    add_wallet(interaction.user.id, amount)
    await interaction.response.send_message(embed=emb("🏦 Withdraw", f"Withdrew **${amount}**."))

@bot.tree.command(description="Send cash to someone")
async def send(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount <= 0:
        return await interaction.response.send_message(embed=emb("❌ Error", "Amount must be > 0."), ephemeral=True)
    if get_wallet(interaction.user.id) < amount:
        return await interaction.response.send_message(embed=emb("❌ Error", "Not enough funds."), ephemeral=True)
    add_wallet(interaction.user.id, -amount)
    add_wallet(member.id, amount)
    await interaction.response.send_message(embed=emb("💸 Transfer", f"Sent **${amount}** to {member.mention}."))

@bot.tree.command(description="Top balances")
async def leaderboard(interaction: discord.Interaction):
    tops = sorted(
        balances.items(),
        key=lambda kv: kv[1].get("wallet", 0) + kv[1].get("bank", 0),
        reverse=True
    )[:10]
    if not tops:
        return await interaction.response.send_message(embed=emb("🏆 Leaderboard", "No players yet."))
    lines = []
    for i, (uid, vals) in enumerate(tops, start=1):
        total = vals.get("wallet", 0) + vals.get("bank", 0)
        lines.append(f"{i}. <@{uid}> — ${total}")
    await interaction.response.send_message(embed=emb("🏆 Leaderboard", "\n".join(lines)))

def get_log_channel():
    ch_id = config.get("ticket_log_channel")
    return bot.get_channel(ch_id) if ch_id else None

@bot.tree.command(description="Admin: Add or remove cash from a user (+/-)")
@app_commands.default_permissions(administrator=True)
async def addcash(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount == 0:
        return await interaction.response.send_message(embed=emb("❌ Error", "Amount cannot be 0."), ephemeral=True)
    add_wallet(member.id, amount)
    action = "added to" if amount > 0 else "removed from"
    msg = f"${abs(amount)} {action} {member.mention}'s wallet."
    log = get_log_channel()
    if log:
        await log.send(embed=emb("💰 Cash Adjustment", f"Admin {interaction.user.mention} {action} **${abs(amount)}** for {member.mention}."))
    await interaction.response.send_message(embed=emb("💰 Cash Adjusted", msg))

@bot.tree.command(description="Admin: Reset one player's cash")
@app_commands.default_permissions(administrator=True)
async def resetcash(interaction: discord.Interaction, member: discord.Member):
    set_wallet(member.id, START_BALANCE)
    set_bank(member.id, 0)
    log = get_log_channel()
    if log:
        await log.send(embed=emb("♻️ Reset Cash Log", f"{interaction.user.mention} reset {member.mention}'s cash."))
    await interaction.response.send_message(embed=emb("♻️ Reset Cash", f"{member.mention}'s cash was reset."))

@bot.tree.command(description="Admin: Reset ALL players' cash")
@app_commands.default_permissions(administrator=True)
async def resetcashall(interaction: discord.Interaction):
    for uid in list(balances.keys()):
        set_wallet(uid, START_BALANCE)
        set_bank(uid, 0)
    log = get_log_channel()
    if log:
        await log.send(embed=emb("♻️ Reset Cash Log", f"{interaction.user.mention} reset **ALL** players' cash."))
    await interaction.response.send_message(embed=emb("♻️ Reset Cash", "All players' cash reset."))

# Blackjack
deck = [str(x) for x in range(2, 11)] + ["J", "Q", "K", "A"]

def bj_total(cards):
    total, aces = 0, 0
    for c in cards:
        if c in ["J","Q","K"]:
            total += 10
        elif c == "A":
            total += 11
            aces += 1
        else:
            total += int(c)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

class BlackjackView(View):
    def __init__(self, user: discord.User, bet: int, player_cards: list[str], dealer_cards: list[str]):
        super().__init__(timeout=90)
        self.user = user
        self.bet = bet
        self.player = player_cards
        self.dealer = dealer_cards

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.user.id:
            await i.response.send_message(embed=emb("🚫 Not your game", "Wait for this game to finish."), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def btn_hit(self, i: discord.Interaction, _button: Button):
        pt = bj_total(self.player)
        if pt > 21:
            # bust
            await i.response.edit_message(
                embed=emb("🃏 Blackjack - Busted",
                          f"**Your:** {self.player} ({pt})\n**Dealer:** {self.dealer} ({bj_total(self.dealer)})\n\n❌ You lost **${self.bet}**."),
                view=None
            )
            self.stop()
        else:
            await i.response.edit_message(
                embed=emb("🃏 Blackjack",
                          f"**Your:** {self.player} ({pt})\n**Dealer shows:** {self.dealer[0]}"),
                view=self
            )

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def btn_stand(self, i: discord.Interaction, _button: Button):
        pt = bj_total(self.player)
        dt = bj_total(self.dealer)
        while dt < 17:
            self.dealer.append(random.choice(deck))
            dt = bj_total(self.dealer)

        if dt > 21 or pt > dt:
            add_wallet(self.user.id, self.bet * 2)
            result = f"✅ You win **${self.bet * 2}**!"
        elif pt == dt:
            add_wallet(self.user.id, self.bet)
            result = "🤝 It's a tie. Your bet is returned."
        else:
            result = f"❌ You lost **${self.bet}**."

        await i.response.edit_message(
            embed=emb("🃏 Blackjack - Result",
                      f"**Your:** {self.player} ({pt})\n**Dealer:** {self.dealer} ({dt})\n\n{result}"),
            view=None
        )
        self.stop()

@bot.tree.command(description="Play Blackjack")
async def blackjack(interaction: discord.Interaction, bet: int):
    if bet <= 0 or bet > get_wallet(interaction.user.id):
        return await interaction.response.send_message(embed=emb("❌ Error", "Invalid bet."), ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    player = [random.choice(deck), random.choice(deck)]
    dealer = [random.choice(deck), random.choice(deck)]
    view = BlackjackView(interaction.user, bet, player, dealer)
    await interaction.response.send_message(
        embed=emb("🃏 Blackjack", f"**Your:** {player} ({bj_total(player)})\n**Dealer shows:** {dealer[0]}"),
        view=view
    )

# Roulette
@bot.tree.command(description="Roulette (red/black)")
async def roulette(interaction: discord.Interaction, color: str, bet: int):
    color = color.lower()
    if color not in ["red", "black"]:
        return await interaction.response.send_message(embed=emb("❌ Error", "Pick **red** or **black**."), ephemeral=True)
    if bet <= 0 or bet > get_wallet(interaction.user.id):
        return await interaction.response.send_message(embed=emb("❌ Error", "Invalid bet."), ephemeral=True)

    add_wallet(interaction.user.id, -bet)
    result = random.choices(["red", "black", "green"], weights=[80, 15, 5], k=1)[0]  # 80% red, 15% black, 5% green
    if result == color:
        win = bet * 2
        add_wallet(interaction.user.id, win)
        msg = f"Ball landed on **{result}** — you won **${win}**!"
    elif result == "green":
        win = bet * 5
        add_wallet(interaction.user.id, win)
        msg = f"Ball landed on **green** 🍀 — mega win **${win}**!"
    else:
        msg = f"Ball landed on **{result}** — you lost **${bet}**."
    await interaction.response.send_message(embed=emb("🎡 Roulette", msg))

# Slots
@bot.tree.command(description="Slots")
async def slots(interaction: discord.Interaction, bet: int):
    if bet <= 0 or bet > get_wallet(interaction.user.id):
        return await interaction.response.send_message(embed=emb("❌ Error", "Invalid bet."), ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    symbols = ["🍒", "🍋", "🍉", "⭐", "7️⃣"]
    roll = [random.choice(symbols) for _ in range(3)]
    if len(set(roll)) == 1:
        win = bet * 5
        add_wallet(interaction.user.id, win)
        msg = f"{' '.join(roll)}\nJackpot! You won **${win}**!"
    elif len(set(roll)) == 2:
        win = bet * 2
        add_wallet(interaction.user.id, win)
        msg = f"{' '.join(roll)}\nNice! You won **${win}**."
    else:
        msg = f"{' '.join(roll)}\nUnlucky! You lost **${bet}**."
    await interaction.response.send_message(embed=emb("🎰 Slots", msg))

# Coinflip
@bot.tree.command(description="Coinflip (heads/tails)")
async def coinflip(interaction: discord.Interaction, choice: str, bet: int):
    choice = choice.lower()
    if choice not in ["heads", "tails"]:
        return await interaction.response.send_message(embed=emb("❌ Error", "Pick **heads** or **tails**."), ephemeral=True)
    if bet <= 0 or bet > get_wallet(interaction.user.id):
        return await interaction.response.send_message(embed=emb("❌ Error", "Invalid bet."), ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    res = random.choice(["heads", "tails"])
    if res == choice:
        add_wallet(interaction.user.id, bet * 2)
        msg = f"Coin landed **{res}** — you won **${bet * 2}**!"
    else:
        msg = f"Coin landed **{res}** — you lost **${bet}**."
    await interaction.response.send_message(embed=emb("🪙 Coinflip", msg))

# Dice
@bot.tree.command(description="Dice (guess 1-6)")
async def dice(interaction: discord.Interaction, guess: int, bet: int):
    if guess < 1 or guess > 6:
        return await interaction.response.send_message(embed=emb("❌ Error", "Guess must be 1–6."), ephemeral=True)
    if bet <= 0 or bet > get_wallet(interaction.user.id):
        return await interaction.response.send_message(embed=emb("❌ Error", "Invalid bet."), ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    roll = random.randint(1, 6)
    if roll == guess:
        win = bet * 6
        add_wallet(interaction.user.id, win)
        msg = f"Rolled **{roll}** — correct! You won **${win}**!"
    else:
        msg = f"Rolled **{roll}** — you lost **${bet}**."
    await interaction.response.send_message(embed=emb("🎲 Dice", msg))

# HighLow
@bot.tree.command(description="HighLow (guess high/low on 1–100)")
async def highlow(interaction: discord.Interaction, guess: str, bet: int):
    guess = guess.lower()
    if guess not in ["high", "low"]:
        return await interaction.response.send_message(embed=emb("❌ Error", "Guess **high** or **low**."), ephemeral=True)
    if bet <= 0 or bet > get_wallet(interaction.user.id):
        return await interaction.response.send_message(embed=emb("❌ Error", "Invalid bet."), ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    roll = random.randint(1, 100)
    res = "high" if roll > 50 else "low"
    if guess == res:
        add_wallet(interaction.user.id, bet * 2)
        msg = f"Number **{roll}** ({res}) — you won **${bet * 2}**!"
    else:
        msg = f"Number **{roll}** ({res}) — you lost **${bet}**."
    await interaction.response.send_message(embed=emb("🎯 HighLow", msg))

# PP Checker
@bot.tree.command(description="Check your pp size")
async def ppcheck(interaction: discord.Interaction):
    pp_size = random.randint(1, 12)
    if pp_size < 4:
        emoji = "🦐"  # Shrimp emoji
    else:
        emoji = "🍆"  # Eggplant emoji
    await interaction.response.send_message(embed=emb("📏 PP Check", f"Your pp size is {pp_size} inches. {emoji}"))

# !cmds (prefix) shows slash commands
@bot.command(name="cmds")
async def cmds(ctx: commands.Context):
    lines = [
        "**Moderation**: `/ban`, `/kick`, `/mute`, `/unmute`, `/nick`, `/say`, `/addrole`, `/removerole`",
        "**Welcome/Goodbye**: `/setwelcome`, `/setgoodbye`",
        "**Economy**: `/balance`, `/daily`, `/work`, `/steal`, `/deposit`, `/withdraw`, `/send`, `/leaderboard`",
        "**Admin Economy**: `/addcash`, `/resetcash`, `/resetcashall`",
        "**Casino**: `/blackjack`, `/roulette`, `/slots`, `/coinflip`, `/dice`, `/highlow`",
        "**PP Check**: `/ppcheck`"
    ]
    await ctx.send(embed=emb("📜 Commands", "\n".join(lines)))

# Run
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is not set.")
bot.run(TOKEN)
