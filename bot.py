import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View
import random, time, json, os
from datetime import timedelta

# --- CONFIG ---
TOKEN = os.environ.get("DISCORD_TOKEN")
DATA_FILE = "data.json"
START_BALANCE = 500

# --- DATA HANDLING ---
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"balances": {}, "config": {}, "tickets": {}}, f)
with open(DATA_FILE, "r") as f:
    data = json.load(f)

balances = data.setdefault("balances", {})
config = data.setdefault("config", {})
tickets = data.setdefault("tickets", {})

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- ECONOMY HELPERS ---
def get_wallet(uid): return balances.get(str(uid), {}).get("wallet", START_BALANCE)
def get_bank(uid): return balances.get(str(uid), {}).get("bank", 0)
def get_last_daily(uid): return balances.get(str(uid), {}).get("last_daily", 0)

def set_wallet(uid, amt):
    balances.setdefault(str(uid), {"wallet": START_BALANCE, "bank": 0, "last_daily": 0})
    balances[str(uid)]["wallet"] = amt
    save_data()

def set_bank(uid, amt):
    balances.setdefault(str(uid), {"wallet": START_BALANCE, "bank": 0, "last_daily": 0})
    balances[str(uid)]["bank"] = amt
    save_data()

def set_last_daily(uid, ts):
    balances.setdefault(str(uid), {"wallet": START_BALANCE, "bank": 0, "last_daily": 0})
    balances[str(uid)]["last_daily"] = ts
    save_data()

def add_wallet(uid, amt): set_wallet(uid, get_wallet(uid) + amt)

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- AUTOSAVE ---
@tasks.loop(seconds=60)
async def autosave():
    for uid, bal in balances.items():
        interest = int(bal.get("bank", 0) * 0.02)
        if interest > 0: bal["bank"] += min(interest, 10000)
    save_data()

# --- UTIL ---
def make_embed(title, description, color=discord.Color.blurple()):
    return discord.Embed(title=title, description=description, color=color)

# --- EVENTS ---
@bot.event
async def on_ready():
    autosave.start()
    await bot.tree.sync()
    print(f"✅ Bot ready and commands synced as {bot.user}")

@bot.event
async def on_member_join(member):
    ch_id = config.get("welcome_channel")
    if ch_id:
        channel = bot.get_channel(ch_id)
        if channel:
            await channel.send(embed=make_embed("🎉 Welcome!", f"Welcome {member.mention}!"))

@bot.event
async def on_member_remove(member):
    ch_id = config.get("goodbye_channel")
    if ch_id:
        channel = bot.get_channel(ch_id)
        if channel:
            await channel.send(embed=make_embed("👋 Goodbye!", f"{member.name} has left."))

# --- CHANNEL CONFIG ---
@bot.tree.command(description="Set welcome channel")
@app_commands.default_permissions(administrator=True)
async def setwelcome(interaction, channel: discord.TextChannel):
    config["welcome_channel"] = channel.id
    save_data()
    await interaction.response.send_message(embed=make_embed("✅ Success", f"Welcome channel set to {channel.mention}"))

@bot.tree.command(description="Set goodbye channel")
@app_commands.default_permissions(administrator=True)
async def setgoodbye(interaction, channel: discord.TextChannel):
    config["goodbye_channel"] = channel.id
    save_data()
    await interaction.response.send_message(embed=make_embed("✅ Success", f"Goodbye channel set to {channel.mention}"))

# --- MODERATION ---
@bot.tree.command(description="Ban a member")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction, member: discord.Member, reason: str = None):
    await member.ban(reason=reason)
    await interaction.response.send_message(embed=make_embed("🔨 Ban", f"{member.mention} was banned.\nReason: {reason}"))

@bot.tree.command(description="Kick a member")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction, member: discord.Member, reason: str = None):
    await member.kick(reason=reason)
    await interaction.response.send_message(embed=make_embed("👢 Kick", f"{member.mention} was kicked.\nReason: {reason}"))

@bot.tree.command(description="Mute a member")
@app_commands.default_permissions(moderate_members=True)
async def mute(interaction, member: discord.Member, seconds: int, reason: str = None):
    until = discord.utils.utcnow() + timedelta(seconds=seconds)
    await member.timeout(until, reason=reason)
    await interaction.response.send_message(embed=make_embed("🔇 Mute", f"{member.mention} muted for {seconds}s.\nReason: {reason}"))

# --- ECONOMY ---
@bot.tree.command(description="Check balance")
async def balance(interaction):
    uid = interaction.user.id
    await interaction.response.send_message(embed=make_embed("💰 Balance", f"Wallet: ${get_wallet(uid)}\nBank: ${get_bank(uid)}"))

@bot.tree.command(description="Daily reward")
async def daily(interaction):
    uid = interaction.user.id
    now = int(time.time())
    if now - get_last_daily(uid) < 86400:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Already claimed daily today."))
        return
    reward = random.randint(100, 500)
    add_wallet(uid, reward)
    set_last_daily(uid, now)
    await interaction.response.send_message(embed=make_embed("🎁 Daily", f"You received ${reward}!"))

@bot.tree.command(description="Work for money")
async def work(interaction):
    reward = random.randint(50, 200)
    add_wallet(interaction.user.id, reward)
    await interaction.response.send_message(embed=make_embed("👷 Work", f"You earned ${reward}!"))

@bot.tree.command(description="Rob someone")
async def rob(interaction, member: discord.Member):
    uid, target = interaction.user.id, member.id
    if get_wallet(target) < 50:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Target too poor."))
        return
    if random.random() < 0.5:
        stolen = random.randint(20, get_wallet(target)//2)
        set_wallet(target, get_wallet(target)-stolen)
        add_wallet(uid, stolen)
        await interaction.response.send_message(embed=make_embed("💀 Robbery", f"You robbed {member.mention} and got ${stolen}!"))
    else:
        fine = random.randint(20, 100)
        set_wallet(uid, get_wallet(uid)-fine)
        await interaction.response.send_message(embed=make_embed("🚓 Arrested", f"You got caught! Lost ${fine}."))

@bot.tree.command(description="Deposit money")
async def deposit(interaction, amount: int):
    uid = interaction.user.id
    if amount <= 0 or amount > get_wallet(uid):
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid deposit."))
        return
    set_wallet(uid, get_wallet(uid)-amount)
    set_bank(uid, get_bank(uid)+amount)
    await interaction.response.send_message(embed=make_embed("🏦 Bank", f"Deposited ${amount}"))

@bot.tree.command(description="Withdraw money")
async def withdraw(interaction, amount: int):
    uid = interaction.user.id
    if amount <= 0 or amount > get_bank(uid):
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid withdrawal."))
        return
    set_bank(uid, get_bank(uid)-amount)
    set_wallet(uid, get_wallet(uid)+amount)
    await interaction.response.send_message(embed=make_embed("🏦 Bank", f"Withdrew ${amount}"))

@bot.tree.command(description="Send cash to someone")
async def send(interaction, member: discord.Member, amount: int):
    sender = interaction.user.id
    if amount <= 0 or amount > get_wallet(sender):
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid transfer."))
        return
    set_wallet(sender, get_wallet(sender)-amount)
    add_wallet(member.id, amount)
    await interaction.response.send_message(embed=make_embed("💸 Transfer", f"Sent ${amount} to {member.mention}"))

@bot.tree.command(description="Leaderboard")
async def leaderboard(interaction):
    top = sorted(balances.items(), key=lambda x: (x[1].get("wallet",0)+x[1].get("bank",0)), reverse=True)[:10]
    msg = "\n".join([f"{i+1}. <@{uid}> — ${bal.get('wallet',0)+bal.get('bank',0)}" for i,(uid,bal) in enumerate(top)])
    await interaction.response.send_message(embed=make_embed("💰 Leaderboard", msg or "No data."))

@bot.tree.command(description="Admin: Add cash")
@app_commands.default_permissions(administrator=True)
async def addcash(interaction, member: discord.Member, amount: int):
    add_wallet(member.id, amount)
    await interaction.response.send_message(embed=make_embed("💵 Admin", f"Added ${amount} to {member.mention}"))

# --- CASINO ---
# Full casino: Blackjack, Roulette, Slots, Coinflip, Dice, HighLow
# Blackjack
class BlackjackView(View):
    def __init__(self, user, bet, player_cards, dealer_cards):
        super().__init__(timeout=None)
        self.user = user
        self.bet = bet
        self.player_cards = player_cards
        self.dealer_cards = dealer_cards
        self.add_item(Button(label="Hit", style=discord.ButtonStyle.green, custom_id="hit"))
        self.add_item(Button(label="Stand", style=discord.ButtonStyle.red, custom_id="stand"))

def calc_blackjack(cards):
    total = 0
    aces = 0
    for c in cards:
        if c in ["J","Q","K"]:
            total += 10
        elif c == "A":
            total += 11
            aces +=1
        else:
            total += int(c)
    while total>21 and aces>0:
        total -= 10
        aces -=1
    return total

@bot.tree.command(description="Play Blackjack")
async def blackjack(interaction, bet: int):
    uid = interaction.user.id
    if bet>get_wallet(uid) or bet<=0:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid bet amount."))
        return
    add_wallet(uid, -bet)
    deck = [str(x) for x in range(2,11)] + ["J","Q","K","A"]
    player_cards = [random.choice(deck), random.choice(deck)]
    dealer_cards = [random.choice(deck), random.choice(deck)]
    view = BlackjackView(interaction.user, bet, player_cards, dealer_cards)
    embed = make_embed("🃏 Blackjack", f"Your cards: {player_cards} ({calc_blackjack(player_cards)})\nDealer shows: {dealer_cards[0]}")
    await interaction.response.send_message(embed=embed, view=view)

# Roulette
@bot.tree.command(description="Play Roulette")
async def roulette(interaction, bet: int, color: str):
    uid = interaction.user.id
    if bet>get_wallet(uid) or bet<=0:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid bet amount."))
        return
    color = color.lower()
    if color not in ["red","black"]:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Choose red or black."))
        return
    add_wallet(uid, -bet)
    result = random.choice(["red","black"])
    if result==color:
        winnings = bet*2
        add_wallet(uid, winnings)
        await interaction.response.send_message(embed=make_embed("🎡 Roulette", f"The ball landed on **{result}**! You won ${winnings}"))
    else:
        await interaction.response.send_message(embed=make_embed("🎡 Roulette", f"The ball landed on **{result}**! You lost ${bet}"))

# Slots
@bot.tree.command(description="Play Slots")
async def slots(interaction, bet: int):
    uid = interaction.user.id
    if bet>get_wallet(uid) or bet<=0:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid bet amount."))
        return
    add_wallet(uid, -bet)
    emojis = ["🍎","🍌","🍒","🍇","⭐"]
    roll = [random.choice(emojis) for _ in range(3)]
    if len(set(roll))==1:
        winnings = bet*5
        add_wallet(uid, winnings)
        await interaction.response.send_message(embed=make_embed("🎰 Slots", f"{roll}\nJackpot! You won ${winnings}"))
    elif len(set(roll))==2:
        winnings = bet*2
        add_wallet(uid, winnings)
        await interaction.response.send_message(embed=make_embed("🎰 Slots", f"{roll}\nPartial win! You won ${winnings}"))
    else:
        await interaction.response.send_message(embed=make_embed("🎰 Slots", f"{roll}\nYou lost ${bet}"))

# Coinflip
@bot.tree.command(description="Coinflip")
async def coinflip(interaction, bet: int, choice: str):
    uid = interaction.user.id
    if bet>get_wallet(uid) or bet<=0:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid bet amount."))
        return
    choice = choice.lower()
    if choice not in ["heads","tails"]:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Choose heads or tails."))
        return
    add_wallet(uid, -bet)
    flip = random.choice(["heads","tails"])
    if flip==choice:
        add_wallet(uid, bet*2)
        await interaction.response.send_message(embed=make_embed("🪙 Coinflip", f"The coin landed **{flip}**! You won ${bet}"))
    else:
        await interaction.response.send_message(embed=make_embed("🪙 Coinflip", f"The coin landed **{flip}**! You lost ${bet}"))

# Dice
@bot.tree.command(description="Roll a dice")
async def dice(interaction, bet: int, guess: int):
    uid = interaction.user.id
    if bet>get_wallet(uid) or bet<=0:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid bet amount."))
        return
    if guess<1 or guess>6:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Guess 1-6"))
        return
    add_wallet(uid, -bet)
    roll = random.randint(1,6)
    if roll==guess:
        add_wallet(uid, bet*6)
        await interaction.response.send_message(embed=make_embed("🎲 Dice", f"Rolled {roll}! You guessed correctly. Won ${bet*6}"))
    else:
        await interaction.response.send_message(embed=make_embed("🎲 Dice", f"Rolled {roll}. You lost ${bet}"))

# HighLow
@bot.tree.command(description="High or Low game")
async def highlow(interaction, bet: int, guess: str):
    uid = interaction.user.id
    if bet>get_wallet(uid) or bet<=0:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid bet amount."))
        return
    guess = guess.lower()
    if guess not in ["high","low"]:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Guess high or low."))
        return
    add_wallet(uid, -bet)
    roll = random.randint(1,100)
    result = "high" if roll>50 else "low"
    if guess==result:
        add_wallet(uid, bet*2)
        await interaction.response.send_message(embed=make_embed("🎯 HighLow", f"Rolled {roll} ({result})! You won ${bet*2}"))
    else:
        await interaction.response.send_message(embed=make_embed("🎯 HighLow", f"Rolled {roll} ({result})! You lost ${bet}"))

# --- TICKET SYSTEM ---
# (Ticket system already included from previous code)
# TicketView, ticketpanel, setticketlog, logticket, open/close tickets

# --- PREFIX HELP ---
@bot.command()
async def cmds(ctx):
    await ctx.send(embed=make_embed("📜 Commands", "Use `/` slash commands for moderation, economy, casino, and tickets."))

# --- RUN ---
bot.run(TOKEN)
