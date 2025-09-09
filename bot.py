import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import random, time, json, os
from datetime import timedelta, datetime

TOKEN = os.environ.get("DISCORD_TOKEN")
DATA_FILE = "data.json"
START_BALANCE = 500
START_XP = 0
START_LEVEL = 1

# ----------------- Load or create data -----------------
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({
            "balances": {},
            "xp": {},
            "levels": {},
            "config": {},
            "tickets": {},       # ticket_channel_id -> { opener_id, opened_at }
            "ticket_counts": {}  # staff_id -> count
        }, f, indent=4)

with open(DATA_FILE, "r") as f:
    data = json.load(f)

balances = data.setdefault("balances", {})
xp_data = data.setdefault("xp", {})
levels = data.setdefault("levels", {})
config = data.setdefault("config", {})
tickets = data.setdefault("tickets", {})
ticket_counts = data.setdefault("ticket_counts", {})

# ----------------- Save Data -----------------
def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ----------------- Economy Helpers -----------------
def ensure_user(uid):
    uid = str(uid)
    balances.setdefault(uid, {"wallet": START_BALANCE, "bank": 0})
    xp_data.setdefault(uid, START_XP)
    levels.setdefault(uid, START_LEVEL)
    return balances[uid]

def get_wallet(uid): return ensure_user(uid)["wallet"]
def get_bank(uid): return ensure_user(uid)["bank"]
def set_wallet(uid, amt): ensure_user(uid)["wallet"] = int(amt); save_data()
def set_bank(uid, amt): ensure_user(uid)["bank"] = int(amt); save_data()
def add_wallet(uid, amt): ensure_user(uid)["wallet"] += int(amt); save_data()

# ----------------- XP & Leveling -----------------
def add_xp(uid, amount):
    uid = str(uid)
    xp_data[uid] = xp_data.get(uid, START_XP) + amount
    level_up(uid)

def level_up(uid):
    uid = str(uid)
    current_level = levels.get(uid, START_LEVEL)
    required_xp = 50 * current_level
    while xp_data.get(uid, 0) >= required_xp:
        levels[uid] = current_level + 1
        xp_data[uid] -= required_xp
        current_level += 1
        required_xp = 50 * current_level

# ----------------- Config Helpers -----------------
def set_config(key, value):
    config[key] = value
    save_data()

def get_config(key):
    return config.get(key)

# ----------------- Bot Setup -----------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # Needed for prefix commands like !cmds

bot = commands.Bot(command_prefix="!", intents=intents)

def emb(title, desc, color=discord.Color.blurple()):
    return discord.Embed(title=title, description=desc, color=color)

# ----------------- Bot Ready -----------------
@bot.event
async def on_ready():
    guild_id = config.get("test_guild")  # Optional: set a test guild ID for fast slash commands
    if guild_id:
        guild = discord.Object(id=guild_id)
        await bot.tree.sync(guild=guild)
        print(f"✅ Commands synced to guild {guild_id}")
    else:
        await bot.tree.sync()
        print("✅ Global commands synced")

    print(f"✅ Logged in as {bot.user} | Ready")

# ----------------- Welcome & Goodbye -----------------
@bot.event
async def on_member_join(member: discord.Member):
    ch_id = config.get("welcome_channel")
    if ch_id:
        ch = bot.get_channel(ch_id)
        if ch:
            await ch.send(f"🎉 Welcome {member.mention} to the server!")
    # Give XP for joining
    add_xp(member.id, 10)

@bot.event
async def on_member_remove(member: discord.Member):
    ch_id = config.get("goodbye_channel")
    if ch_id:
        ch = bot.get_channel(ch_id)
        if ch:
            await ch.send(f"👋 {member.mention} has left the server.")

# ----------------- Ticket System -----------------
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.green, custom_id="open_ticket")
    async def open_ticket(self, button: Button, interaction: discord.Interaction):
        # Check if user already has a ticket
        for tid, tdata in tickets.items():
            if tdata["opener_id"] == str(interaction.user.id):
                await interaction.response.send_message("❌ You already have an open ticket.", ephemeral=True)
                return

        # Create ticket channel
        guild = interaction.guild
        category_id = config.get("ticket_category")
        category = guild.get_channel(category_id) if category_id else None
        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            topic=f"Ticket opened by {interaction.user} ({interaction.user.id})"
        )

        tickets[str(channel.id)] = {
            "opener_id": str(interaction.user.id),
            "opened_at": int(time.time())
        }
        save_data()

        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)
        await channel.send(f"Hello {interaction.user.mention}, our staff will be with you shortly. Use `/close` to close the ticket.")

# ----------------- Close Ticket Command -----------------
@bot.tree.command(description="Close a ticket (staff only)")
@app_commands.default_permissions(administrator=True)
async def close(interaction: discord.Interaction):
    channel_id = str(interaction.channel.id)
    if channel_id not in tickets:
        await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
        return

    opener_id = tickets[channel_id]["opener_id"]
    del tickets[channel_id]
    save_data()
    await interaction.channel.delete()
    log_channel_id = config.get("ticket_log_channel")
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            await log_channel.send(f"Ticket closed by {interaction.user.mention}, opener: <@{opener_id}>")

# ----------------- Economy Commands -----------------
@bot.tree.command(description="Check balance")
async def balance(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    u = ensure_user(member.id)
    lvl = levels.get(str(member.id), START_LEVEL)
    xp = xp_data.get(str(member.id), START_XP)
    await interaction.response.send_message(
        f"{member.mention}\nWallet: ${u['wallet']}\nBank: ${u['bank']}\nLevel: {lvl} | XP: {xp}"
    )

@bot.tree.command(description="Claim daily reward (24h)")
async def daily(interaction: discord.Interaction):
    u = ensure_user(interaction.user.id)
    now = int(time.time())
    last = u.get("last_daily", 0)
    if now - last < 86400:
        remaining = 86400 - (now - last)
        return await interaction.response.send_message(
            f"⏳ You must wait {remaining//3600}h {(remaining%3600)//60}m.", ephemeral=True
        )
    reward = random.randint(2500, 50000)
    add_wallet(interaction.user.id, reward)
    u["last_daily"] = now
    add_xp(interaction.user.id, 20)  # XP gain for claiming daily
    save_data()
    await interaction.response.send_message(f"🎁 You received **${reward}**!")

@bot.tree.command(description="Send money to another user")
async def send(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount <= 0:
        return await interaction.response.send_message("❌ Amount must be > 0.", ephemeral=True)
    if get_wallet(interaction.user.id) < amount:
        return await interaction.response.send_message("❌ Not enough funds.", ephemeral=True)
    add_wallet(interaction.user.id, -amount)
    add_wallet(member.id, amount)
    add_xp(interaction.user.id, 5)  # XP for sending money
    save_data()
    await interaction.response.send_message(f"💸 Sent ${amount} to {member.mention}!")

# ----------------- Leaderboard -----------------
@bot.tree.command(description="Show top balances")
async def leaderboard(interaction: discord.Interaction):
    top = sorted(
        balances.items(),
        key=lambda kv: kv[1].get("wallet", 0) + kv[1].get("bank", 0),
        reverse=True
    )[:10]

    lines = []
    for i, (uid, vals) in enumerate(top, start=1):
        total = vals.get("wallet", 0) + vals.get("bank", 0)
        lvl = levels.get(uid, START_LEVEL)
        lines.append(f"{i}. <@{uid}> — ${total} | Level {lvl}")

    await interaction.response.send_message(f"🏆 Leaderboard:\n" + "\n".join(lines))

# ----------------- Casino Helper -----------------
deck = [str(x) for x in range(2, 11)] + ["J", "Q", "K", "A"]

def bj_total(cards):
    total, aces = 0, 0
    for c in cards:
        if c in ["J", "Q", "K"]:
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

# ----------------- Blackjack -----------------
class BlackjackView(View):
    def __init__(self, user, bet, player_cards, dealer_cards):
        super().__init__(timeout=90)
        self.user = user
        self.bet = bet
        self.player = player_cards
        self.dealer = dealer_cards

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.user.id:
            await i.response.send_message("🚫 Not your game.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, i: discord.Interaction, b: Button):
        self.player.append(random.choice(deck))
        pt = bj_total(self.player)
        if pt > 21:
            await i.response.edit_message(
                embed=emb("🃏 Blackjack - Busted",
                          f"Your: {self.player} ({pt})\nDealer: {self.dealer} ({bj_total(self.dealer)})\n❌ You lost ${self.bet}."),
                view=None
            )
            self.stop()
            return
        await i.response.edit_message(embed=emb("🃏 Blackjack", f"Your: {self.player} ({pt})\nDealer shows: {self.dealer[0]}"), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, i: discord.Interaction, b: Button):
        pt = bj_total(self.player)
        dt = bj_total(self.dealer)
        while dt < 17:
            self.dealer.append(random.choice(deck))
            dt = bj_total(self.dealer)
        if dt > 21 or pt > dt:
            add_wallet(self.user.id, self.bet*2)
            add_xp(self.user.id, 10)
            result = f"✅ You win ${self.bet*2}!"
        elif pt == dt:
            add_wallet(self.user.id, self.bet)
            result = "🤝 Tie. Bet returned."
        else:
            result = f"❌ You lost ${self.bet}."
        await i.response.edit_message(
            embed=emb("🃏 Blackjack - Result", f"Your: {self.player} ({pt})\nDealer: {self.dealer} ({dt})\n{result}"),
            view=None
        )
        self.stop()

@bot.tree.command(description="Play Blackjack")
async def blackjack(interaction: discord.Interaction, bet: int):
    if bet <= 0 or bet > get_wallet(interaction.user.id):
        return await interaction.response.send_message("❌ Invalid bet.", ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    player = [random.choice(deck), random.choice(deck)]
    dealer = [random.choice(deck), random.choice(deck)]
    view = BlackjackView(interaction.user, bet, player, dealer)
    await interaction.response.send_message(f"Your: {player} ({bj_total(player)})\nDealer shows: {dealer[0]}", view=view)

# ----------------- Roulette -----------------
@bot.tree.command(description="Roulette (red/black)")
async def roulette(interaction: discord.Interaction, color: str, bet: int):
    color = color.lower()
    if color not in ["red", "black"]:
        return await interaction.response.send_message("❌ Pick red or black.", ephemeral=True)
    if bet <= 0 or bet > get_wallet(interaction.user.id):
        return await interaction.response.send_message("❌ Invalid bet.", ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    result = random.choices(["red","black","green"], weights=[45,45,10])[0]
    if result == color:
        win = bet*2
        add_wallet(interaction.user.id, win)
        add_xp(interaction.user.id, 5)
        msg = f"Ball landed {result} — you won ${win}!"
    elif result == "green":
        win = bet*5
        add_wallet(interaction.user.id, win)
        add_xp(interaction.user.id, 10)
        msg = f"Ball landed green — mega win ${win}!"
    else:
        msg = f"Ball landed {result} — you lost ${bet}."
    await interaction.response.send_message(msg)

# ----------------- Slots -----------------
@bot.tree.command(description="Slots")
async def slots(interaction: discord.Interaction, bet: int):
    if bet <= 0 or bet > get_wallet(interaction.user.id):
        return await interaction.response.send_message("❌ Invalid bet.", ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    symbols = ["🍒","🍋","🍉","⭐","7️⃣"]
    roll = [random.choice(symbols) for _ in range(3)]
    if len(set(roll)) == 1:
        win = bet*5
        add_wallet(interaction.user.id, win)
        add_xp(interaction.user.id, 10)
        msg = f"{' '.join(roll)} — Jackpot! You won ${win}!"
    elif len(set(roll)) == 2:
        win = bet*2
        add_wallet(interaction.user.id, win)
        add_xp(interaction.user.id, 5)
        msg = f"{' '.join(roll)} — Nice! You won ${win}."
    else:
        msg = f"{' '.join(roll)} — Unlucky! You lost ${bet}."
    await interaction.response.send_message(msg)

# ----------------- Coinflip -----------------
@bot.tree.command(description="Coinflip (heads/tails)")
async def coinflip(interaction: discord.Interaction, choice: str, bet: int):
    choice = choice.lower()
    if choice not in ["heads","tails"]:
        return await interaction.response.send_message("❌ Pick heads or tails.", ephemeral=True)
    if bet <= 0 or bet > get_wallet(interaction.user.id):
        return await interaction.response.send_message("❌ Invalid bet.", ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    res = random.choice(["heads","tails"])
    if res == choice:
        add_wallet(interaction.user.id, bet*2)
        add_xp(interaction.user.id, 5)
        msg = f"Coin landed {res} — you won ${bet*2}!"
    else:
        msg = f"Coin landed {res} — you lost ${bet}."
    await interaction.response.send_message(msg)

# ----------------- Dice -----------------
@bot.tree.command(description="Dice (guess 1-6)")
async def dice(interaction: discord.Interaction, guess: int, bet: int):
    if guess < 1 or guess > 6:
        return await interaction.response.send_message("❌ Guess must be 1–6.", ephemeral=True)
    if bet <= 0 or bet > get_wallet(interaction.user.id):
        return await interaction.response.send_message("❌ Invalid bet.", ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    roll = random.randint(1, 6)
    if roll == guess:
        win = bet*6
        add_wallet(interaction.user.id, win)
        add_xp(interaction.user.id, 10)
        msg = f"Rolled {roll} — correct! You won ${win}!"
    else:
        msg = f"Rolled {roll} — you lost ${bet}."
    await interaction.response.send_message(msg)

# ----------------- HighLow -----------------
@bot.tree.command(description="HighLow (guess high/low 1–100)")
async def highlow(interaction: discord.Interaction, guess: str, bet: int):
    guess = guess.lower()
    if guess not in ["high","low"]:
        return await interaction.response.send_message("❌ Guess high or low.", ephemeral=True)
    if bet <= 0 or bet > get_wallet(interaction.user.id):
        return await interaction.response.send_message("❌ Invalid bet.", ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    roll = random.randint(1, 100)
    result = "high" if roll > 50 else "low"
    if guess == result:
        win = bet*2
        add_wallet(interaction.user.id, win)
        add_xp(interaction.user.id, 5)
        msg = f"Number {roll} ({result}) — you won ${win}!"
    else:
        msg = f"Number {roll} ({result}) — you lost ${bet}."
    await interaction.response.send_message(msg)

# ----------------- PP Check -----------------
@bot.tree.command(description="Check your PP size")
async def ppcheck(interaction: discord.Interaction):
    pp_size = random.randint(1,12)
    emoji = "🦐" if pp_size < 4 else "🍆"
    add_xp(interaction.user.id, 1)
    await interaction.response.send_message(f"Your pp size is {pp_size} inches {emoji}")

# ----------------- Tickets -----------------
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.green, custom_id="open_ticket")
    async def open_ticket(self, button: Button, interaction: discord.Interaction):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        channel_name = f"ticket-{interaction.user.name}-{interaction.user.discriminator}"
        channel = await guild.create_text_channel(channel_name, overwrites=overwrites)
        tickets[channel.id] = {"opener_id": interaction.user.id, "opened_at": int(time.time())}
        save_data()
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

# ----------------- Welcome & Goodbye -----------------
@bot.event
async def on_member_join(member: discord.Member):
    ch_id = config.get("welcome_channel")
    if ch_id:
        ch = bot.get_channel(ch_id)
        if ch:
            await ch.send(f"🎉 Welcome {member.mention} to the server!")

@bot.event
async def on_member_remove(member: discord.Member):
    ch_id = config.get("goodbye_channel")
    if ch_id:
        ch = bot.get_channel(ch_id)
        if ch:
            await ch.send(f"👋 {member.mention} has left the server.")

# ----------------- Update Panel -----------------
class UpdateView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Post Update", style=discord.ButtonStyle.primary, custom_id="post_update")
    async def post_update(self, button: Button, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You must be an admin.", ephemeral=True)
            return

        modal = UpdateModal()
        await interaction.response.send_modal(modal)

class UpdateModal(Modal):
    def __init__(self):
        super().__init__(title="Post Update")
        self.update_input = TextInput(
            label="Enter update message",
            placeholder="Write your update here...",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.update_input)

    async def on_submit(self, interaction: discord.Interaction):
        channel_id = config.get("update_channel")
        if not channel_id:
            await interaction.response.send_message("❌ Update channel not set.", ephemeral=True)
            return
        channel = bot.get_channel(channel_id)
        if not channel:
            await interaction.response.send_message("❌ Invalid update channel.", ephemeral=True)
            return
        embed = discord.Embed(title="📢 Update", description=self.update_input.value, color=discord.Color.green())
        await channel.send(embed=embed)
        await interaction.response.send_message("✅ Update posted.", ephemeral=True)

# Command to show Update Panel
@bot.tree.command(description="Open Update Panel")
@app_commands.default_permissions(administrator=True)
async def updatepanel(interaction: discord.Interaction):
    await interaction.response.send_message("Update Panel:", view=UpdateView(), ephemeral=True)


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Error: DISCORD_TOKEN environment variable not found.")
        exit(1)
    bot.run(token)
