import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import random, time, json, os
from datetime import datetime, timedelta

TOKEN = os.environ.get("DISCORD_TOKEN")
DATA_FILE = "data.json"
START_BALANCE = 500
XP_PER_MESSAGE = 10
LEVEL_MULTIPLIER = 100

# ----------------- DATA -----------------
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({
            "balances": {},
            "levels": {},
            "config": {},
            "tickets": {},
            "ticket_counts": {},
            "updates": []
        }, f)

with open(DATA_FILE, "r") as f:
    data = json.load(f)

balances = data.setdefault("balances", {})
levels = data.setdefault("levels", {})
config = data.setdefault("config", {})
tickets = data.setdefault("tickets", {})
ticket_counts = data.setdefault("ticket_counts", {})
updates = data.setdefault("updates", [])

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ----------------- BOT -----------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def emb(title, desc, color=discord.Color.blurple()):
    return discord.Embed(title=title, description=desc, color=color)

# ----------------- USER HELPERS -----------------
def ensure_user(uid):
    uid = str(uid)
    balances.setdefault(uid, {
        "wallet": START_BALANCE,
        "bank": 0,
        "last_daily": 0,
        "last_work": 0,
        "last_steal": 0
    })
    levels.setdefault(uid, {
        "xp": 0,
        "level": 1
    })
    return balances[uid]

def add_wallet(uid, amt):
    u = ensure_user(uid)
    u["wallet"] += amt
    save_data()

def set_wallet(uid, amt):
    ensure_user(uid)["wallet"] = amt
    save_data()

def get_wallet(uid):
    return ensure_user(uid)["wallet"]

def set_bank(uid, amt):
    ensure_user(uid)["bank"] = amt
    save_data()

def get_bank(uid):
    return ensure_user(uid)["bank"]

def add_xp(uid, amt):
    u = levels.setdefault(str(uid), {"xp":0,"level":1})
    u["xp"] += amt
    while u["xp"] >= u["level"] * LEVEL_MULTIPLIER:
        u["xp"] -= u["level"] * LEVEL_MULTIPLIER
        u["level"] += 1
        print(f"User {uid} leveled up to {u['level']}!")
    save_data()

def get_level(uid):
    u = levels.get(str(uid), {"xp":0,"level":1})
    return u["level"], u["xp"]

# ----------------- ECONOMY COMMANDS -----------------
@bot.tree.command(description="Check balance (wallet & bank)")
async def balance(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    u = ensure_user(member.id)
    await interaction.response.send_message(
        embed=emb("💰 Balance", f"{member.mention}\nWallet: ${u['wallet']}\nBank: ${u['bank']}")
    )

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
    reward = random.randint(250, 1000)
    add_wallet(interaction.user.id, reward)
    u["last_daily"] = now
    save_data()
    add_xp(interaction.user.id, XP_PER_MESSAGE)
    await interaction.response.send_message(
        embed=emb("🎁 Daily", f"You received **${reward}**! +{XP_PER_MESSAGE} XP")
    )

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
    earnings = random.randint(50, 200)
    add_wallet(interaction.user.id, earnings)
    u["last_work"] = now
    save_data()
    add_xp(interaction.user.id, XP_PER_MESSAGE)
    await interaction.response.send_message(
        embed=emb("💼 Work", f"You earned **${earnings}**! +{XP_PER_MESSAGE} XP")
    )

@bot.tree.command(description="Steal from another user (15m cooldown)")
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
        amt = random.randint(20, min(500, t["wallet"]))
        add_wallet(interaction.user.id, amt)
        add_wallet(member.id, -amt)
        msg = f"💰 You stole **${amt}** from {member.mention}! +{XP_PER_MESSAGE} XP"
        add_xp(interaction.user.id, XP_PER_MESSAGE)
    else:
        fine = random.randint(10, 50)
        add_wallet(interaction.user.id, -fine)
        msg = f"🚓 You were caught and fined **${fine}**."
    u["last_steal"] = now
    save_data()
    await interaction.response.send_message(embed=emb("🕵️ Steal", msg))

@bot.tree.command(description="Deposit money to bank")
async def deposit(interaction: discord.Interaction, amount: int):
    if amount <= 0 or get_wallet(interaction.user.id) < amount:
        return await interaction.response.send_message(embed=emb("❌ Error", "Invalid amount."), ephemeral=True)
    add_wallet(interaction.user.id, -amount)
    set_bank(interaction.user.id, get_bank(interaction.user.id) + amount)
    add_xp(interaction.user.id, XP_PER_MESSAGE)
    await interaction.response.send_message(embed=emb("🏦 Deposit", f"Deposited **${amount}**! +{XP_PER_MESSAGE} XP"))

@bot.tree.command(description="Withdraw money from bank")
async def withdraw(interaction: discord.Interaction, amount: int):
    if amount <= 0 or get_bank(interaction.user.id) < amount:
        return await interaction.response.send_message(embed=emb("❌ Error", "Invalid amount."), ephemeral=True)
    set_bank(interaction.user.id, get_bank(interaction.user.id) - amount)
    add_wallet(interaction.user.id, amount)
    add_xp(interaction.user.id, XP_PER_MESSAGE)
    await interaction.response.send_message(embed=emb("🏦 Withdraw", f"Withdrew **${amount}**! +{XP_PER_MESSAGE} XP"))

@bot.tree.command(description="Send money to another user")
async def send(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount <= 0 or get_wallet(interaction.user.id) < amount:
        return await interaction.response.send_message(embed=emb("❌ Error", "Invalid amount."), ephemeral=True)
    add_wallet(interaction.user.id, -amount)
    add_wallet(member.id, amount)
    add_xp(interaction.user.id, XP_PER_MESSAGE)
    await interaction.response.send_message(embed=emb("💸 Transfer", f"Sent **${amount}** to {member.mention}! +{XP_PER_MESSAGE} XP"))

@bot.tree.command(description="Show top 10 balances")
async def leaderboard(interaction: discord.Interaction):
    tops = sorted(
        balances.items(),
        key=lambda kv: kv[1].get("wallet", 0) + kv[1].get("bank", 0),
        reverse=True
    )[:10]
    lines = []
    for i, (uid, vals) in enumerate(tops, start=1):
        total = vals.get("wallet", 0) + vals.get("bank", 0)
        lines.append(f"{i}. <@{uid}> — ${total}")
    if not lines:
        lines.append("No players yet.")
    await interaction.response.send_message(embed=emb("🏆 Leaderboard", "\n".join(lines)))

# ----------------- LEVEL SYSTEM -----------------
@bot.tree.command(description="Check your level and XP")
async def level(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    lvl, xp = get_level(member.id)
    await interaction.response.send_message(
        embed=emb("📈 Level", f"{member.mention} — Level {lvl}, XP {xp}/{lvl*LEVEL_MULTIPLIER}")
    )

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    add_xp(message.author.id, XP_PER_MESSAGE)
    save_data()
    await bot.process_commands(message)  # allow prefix commands if needed

# ----------------- TICKET SYSTEM -----------------
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.green, custom_id="open_ticket")
    async def open_ticket(self, button: Button, interaction: discord.Interaction):
        ticket_id = f"{interaction.user.id}-{int(time.time())}"
        channel_name = f"ticket-{interaction.user.name}".lower()
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True)
        }
        channel = await interaction.guild.create_text_channel(channel_name, overwrites=overwrites)
        tickets[channel.id] = {"opener_id": interaction.user.id, "opened_at": int(time.time())}
        ticket_counts[str(interaction.user.id)] = ticket_counts.get(str(interaction.user.id), 0) + 1
        save_data()
        await interaction.response.send_message(f"✅ Ticket opened: {channel.mention}", ephemeral=True)
        await channel.send(f"Hello {interaction.user.mention}, staff will be with you shortly.")

@bot.tree.command(description="Show ticket panel")
@app_commands.default_permissions(administrator=True)
async def ticketpanel(interaction: discord.Interaction):
    await interaction.response.send_message("🎫 Ticket Panel", view=TicketView())


# ----------------- UPDATE SYSTEM -----------------
class UpdateModal(Modal):
    def __init__(self):
        super().__init__(title="Send Update")
        self.update_input = TextInput(label="Update Text", style=discord.TextStyle.paragraph)
        self.add_item(self.update_input)

    async def on_submit(self, interaction: discord.Interaction):
        update_text = self.update_input.value
        updates.append({"text": update_text, "time": int(time.time()), "author": str(interaction.user.id)})
        save_data()
        channel_id = config.get("update_channel")
        if channel_id:
            ch = bot.get_channel(channel_id)
            if ch:
                await ch.send(embed=emb("📢 Update", update_text))
        await interaction.response.send_message("✅ Update sent.", ephemeral=True)

@bot.tree.command(description="Send an update (admin)")
@app_commands.default_permissions(administrator=True)
async def update(interaction: discord.Interaction):
    modal = UpdateModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(description="Set the update channel (admin)")
@app_commands.default_permissions(administrator=True)
async def setupdatechannel(interaction: discord.Interaction, channel: discord.TextChannel):
    config["update_channel"] = channel.id
    save_data()
    await interaction.response.send_message(f"✅ Update channel set → {channel.mention}")

# ----------------- CASINO GAMES -----------------
deck = [str(x) for x in range(2,11)] + ["J","Q","K","A"]

def bj_total(cards):
    total, aces = 0,0
    for c in cards:
        if c in ["J","Q","K"]:
            total += 10
        elif c=="A":
            total += 11; aces+=1
        else:
            total += int(c)
    while total>21 and aces>0:
        total-=10; aces-=1
    return total

class BlackjackView(View):
    def __init__(self, user, bet, player_cards, dealer_cards):
        super().__init__(timeout=90)
        self.user = user
        self.bet = bet
        self.player = player_cards
        self.dealer = dealer_cards

    async def interaction_check(self, i: discord.Interaction):
        if i.user.id != self.user.id:
            await i.response.send_message("🚫 Not your game", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, i: discord.Interaction, _):
        self.player.append(random.choice(deck))
        pt = bj_total(self.player)
        if pt>21:
            await i.response.edit_message(embed=emb("🃏 Blackjack - Busted", f"Your: {self.player} ({pt})\nDealer: {self.dealer} ({bj_total(self.dealer)})\n❌ You lost ${self.bet}"), view=None)
            self.stop()
        else:
            await i.response.edit_message(embed=emb("🃏 Blackjack", f"Your: {self.player} ({pt})\nDealer shows: {self.dealer[0]}"), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, i: discord.Interaction, _):
        pt = bj_total(self.player)
        dt = bj_total(self.dealer)
        while dt<17:
            self.dealer.append(random.choice(deck))
            dt=bj_total(self.dealer)
        if dt>21 or pt>dt:
            add_wallet(self.user.id, self.bet*2)
            result=f"✅ You win ${self.bet*2}!"
        elif pt==dt:
            add_wallet(self.user.id, self.bet)
            result="🤝 Tie, bet returned."
        else:
            result=f"❌ You lost ${self.bet}."
        await i.response.edit_message(embed=emb("🃏 Blackjack - Result", f"Your: {self.player} ({pt})\nDealer: {self.dealer} ({dt})\n{result}"), view=None)
        self.stop()

@bot.tree.command(description="Play Blackjack")
async def blackjack(interaction: discord.Interaction, bet: int):
    if bet<=0 or bet>get_wallet(interaction.user.id):
        return await interaction.response.send_message(embed=emb("❌ Invalid bet"), ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    player=[random.choice(deck), random.choice(deck)]
    dealer=[random.choice(deck), random.choice(deck)]
    view=BlackjackView(interaction.user, bet, player, dealer)
    await interaction.response.send_message(embed=emb("🃏 Blackjack", f"Your: {player} ({bj_total(player)})\nDealer shows: {dealer[0]}"), view=view)

# ----------------- Slots -----------------
@bot.tree.command(description="Slots")
async def slots(interaction: discord.Interaction, bet: int):
    if bet <= 0 or bet > get_wallet(interaction.user.id):
        return await interaction.response.send_message(embed=emb("❌ Invalid bet"), ephemeral=True)
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

# ----------------- Roulette -----------------
@bot.tree.command(description="Roulette (red/black)")
async def roulette(interaction: discord.Interaction, color: str, bet: int):
    color = color.lower()
    if color not in ["red", "black"]:
        return await interaction.response.send_message(embed=emb("❌ Pick red or black"), ephemeral=True)
    if bet <= 0 or bet > get_wallet(interaction.user.id):
        return await interaction.response.send_message(embed=emb("❌ Invalid bet"), ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    result = random.choices(["red", "black", "green"], weights=[48,48,4], k=1)[0]
    if result == color:
        win = bet*2
        add_wallet(interaction.user.id, win)
        msg = f"Ball landed on **{result}** — you won **${win}**!"
    elif result=="green":
        win=bet*14
        add_wallet(interaction.user.id, win)
        msg=f"Ball landed on **green** 🍀 — mega win **${win}**!"
    else:
        msg=f"Ball landed on **{result}** — you lost **${bet}**."
    await interaction.response.send_message(embed=emb("🎡 Roulette", msg))

# ----------------- Coinflip -----------------
@bot.tree.command(description="Coinflip (heads/tails)")
async def coinflip(interaction: discord.Interaction, choice: str, bet: int):
    choice = choice.lower()
    if choice not in ["heads","tails"]:
        return await interaction.response.send_message(embed=emb("❌ Pick heads or tails"), ephemeral=True)
    if bet<=0 or bet>get_wallet(interaction.user.id):
        return await interaction.response.send_message(embed=emb("❌ Invalid bet"), ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    result = random.choice(["heads","tails"])
    if result == choice:
        add_wallet(interaction.user.id, bet*2)
        msg = f"Coin landed **{result}** — you won **${bet*2}**!"
    else:
        msg = f"Coin landed **{result}** — you lost **${bet}**."
    await interaction.response.send_message(embed=emb("🪙 Coinflip", msg))

# ----------------- Dice -----------------
@bot.tree.command(description="Dice (guess 1-6)")
async def dice(interaction: discord.Interaction, guess: int, bet: int):
    if guess<1 or guess>6:
        return await interaction.response.send_message(embed=emb("❌ Guess must be 1–6"), ephemeral=True)
    if bet<=0 or bet>get_wallet(interaction.user.id):
        return await interaction.response.send_message(embed=emb("❌ Invalid bet"), ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    roll = random.randint(1,6)
    if roll==guess:
        win = bet*6
        add_wallet(interaction.user.id, win)
        msg = f"Rolled **{roll}** — correct! You won **${win}**!"
    else:
        msg = f"Rolled **{roll}** — you lost **${bet}**."
    await interaction.response.send_message(embed=emb("🎲 Dice", msg))

# ----------------- HighLow -----------------
@bot.tree.command(description="HighLow (guess high/low 1-100)")
async def highlow(interaction: discord.Interaction, guess: str, bet: int):
    guess = guess.lower()
    if guess not in ["high","low"]:
        return await interaction.response.send_message(embed=emb("❌ Pick high or low"), ephemeral=True)
    if bet<=0 or bet>get_wallet(interaction.user.id):
        return await interaction.response.send_message(embed=emb("❌ Invalid bet"), ephemeral=True)
    add_wallet(interaction.user.id, -bet)
    roll = random.randint(1,100)
    res = "high" if roll>50 else "low"
    if guess==res:
        add_wallet(interaction.user.id, bet*2)
        msg = f"Number **{roll}** ({res}) — you won **${bet*2}**!"
    else:
        msg = f"Number **{roll}** ({res}) — you lost **${bet}**."
    await interaction.response.send_message(embed=emb("🎯 HighLow", msg))



if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Error: DISCORD_TOKEN environment variable not found.")
        exit(1)
    bot.run(token)
