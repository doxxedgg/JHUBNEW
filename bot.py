import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View
import random, time, json, os
from datetime import timedelta

# --- CONFIG ---
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    print("❌ DISCORD_TOKEN not found in environment variables.")
    exit()

DATA_FILE = "data.json"
START_BALANCE = 500

# --- DATA HANDLING ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"balances": {}, "config": {}}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {"balances": {}, "config": {}}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()
balances = data.setdefault("balances", {})
config = data.setdefault("config", {})

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

def add_wallet(uid, amt):
    set_wallet(uid, get_wallet(uid) + amt)

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- AUTOSAVE ---
@tasks.loop(seconds=60)
async def autosave():
    save_data()

# --- EVENTS ---
@bot.event
async def on_ready():
    autosave.start()
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands")
    except Exception as e:
        print(f"❌ Sync failed: {e}")
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_member_join(member):
    ch_id = config.get("welcome_channel")
    if ch_id:
        channel = bot.get_channel(ch_id)
        if channel:
            await channel.send(f"🎉 Welcome {member.mention}!")

@bot.event
async def on_member_remove(member):
    ch_id = config.get("goodbye_channel")
    if ch_id:
        channel = bot.get_channel(ch_id)
        if channel:
            await channel.send(f"👋 Goodbye {member.name}!")

# --- CHANNEL SETUP ---
@bot.tree.command(description="Set welcome channel")
@app_commands.default_permissions(administrator=True)
async def setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    config["welcome_channel"] = channel.id
    save_data()
    await interaction.response.send_message(f"✅ Welcome channel set to {channel.mention}")

@bot.tree.command(description="Set goodbye channel")
@app_commands.default_permissions(administrator=True)
async def setgoodbye(interaction: discord.Interaction, channel: discord.TextChannel):
    config["goodbye_channel"] = channel.id
    save_data()
    await interaction.response.send_message(f"✅ Goodbye channel set to {channel.mention}")

# --- MODERATION ---
@bot.tree.command(description="Ban a member")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"🔨 Banned {member.mention}")

@bot.tree.command(description="Kick a member")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 Kicked {member.mention}")

@bot.tree.command(description="Timeout (mute) a member")
@app_commands.default_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member, seconds: int, reason: str = None):
    until = discord.utils.utcnow() + timedelta(seconds=seconds)
    await member.timeout(until, reason=reason)
    await interaction.response.send_message(f"🔇 Muted {member.mention} for {seconds}s")

# --- FUN COMMANDS ---
@bot.tree.command(description="Say something as the bot")
async def say(interaction: discord.Interaction, *, text: str):
    await interaction.response.send_message(text)

# --- ECONOMY ---
@bot.tree.command(description="Check your balance")
async def balance(interaction: discord.Interaction):
    uid = interaction.user.id
    wallet, bank = get_wallet(uid), get_bank(uid)
    await interaction.response.send_message(f"💰 Wallet: ${wallet} | 🏦 Bank: ${bank}")

@bot.tree.command(description="Daily reward")
async def daily(interaction: discord.Interaction):
    uid = interaction.user.id
    now = int(time.time())
    if now - get_last_daily(uid) < 86400:
        await interaction.response.send_message("❌ You already claimed daily today.")
        return
    reward = random.randint(100, 500)
    add_wallet(uid, reward)
    set_last_daily(uid, now)
    await interaction.response.send_message(f"🎁 You received ${reward} daily reward!")

@bot.tree.command(description="Deposit money to bank")
async def deposit(interaction: discord.Interaction, amount: int):
    uid = interaction.user.id
    if amount <= 0 or amount > get_wallet(uid):
        await interaction.response.send_message("❌ Invalid amount.")
        return
    set_wallet(uid, get_wallet(uid) - amount)
    set_bank(uid, get_bank(uid) + amount)
    await interaction.response.send_message(f"🏦 Deposited ${amount}")

@bot.tree.command(description="Withdraw money from bank")
async def withdraw(interaction: discord.Interaction, amount: int):
    uid = interaction.user.id
    if amount <= 0 or amount > get_bank(uid):
        await interaction.response.send_message("❌ Invalid amount.")
        return
    set_bank(uid, get_bank(uid) - amount)
    set_wallet(uid, get_wallet(uid) + amount)
    await interaction.response.send_message(f"🏦 Withdrew ${amount}")

@bot.tree.command(description="Send cash to another user")
async def send(interaction: discord.Interaction, member: discord.Member, amount: int):
    sender = interaction.user.id
    if amount <= 0 or amount > get_wallet(sender):
        await interaction.response.send_message("❌ Invalid amount.")
        return
    set_wallet(sender, get_wallet(sender) - amount)
    add_wallet(member.id, amount)
    await interaction.response.send_message(f"💸 Sent ${amount} to {member.mention}")

@bot.tree.command(description="Show leaderboard")
async def leaderboard(interaction: discord.Interaction):
    top = sorted(balances.items(), key=lambda x: (x[1].get("wallet", 0) + x[1].get("bank", 0)), reverse=True)[:10]
    msg = "💰 **Leaderboard** 💰\n"
    for i, (uid, bal) in enumerate(top, start=1):
        total = bal.get("wallet", 0) + bal.get("bank", 0)
        try:
            user = await bot.fetch_user(int(uid))
            msg += f"**{i}.** {user.name} — ${total}\n"
        except:
            msg += f"**{i}.** Unknown User — ${total}\n"
    await interaction.response.send_message(msg)

@bot.tree.command(description="Admin: Add cash to a user")
@app_commands.default_permissions(administrator=True)
async def addcash(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be positive.")
        return
    add_wallet(member.id, amount)
    await interaction.response.send_message(f"💵 Added ${amount} to {member.mention}")

# --- GAMES ---
deck = [2,3,4,5,6,7,8,9,10,"J","Q","K","A"]

def hand_value(hand):
    val, aces = 0, 0
    for card in hand:
        if card in ["J", "Q", "K"]: val += 10
        elif card == "A": val, aces = val+11, aces+1
        else: val += card
    while val > 21 and aces: val, aces = val-10, aces-1
    return val

class BlackjackView(View):
    def __init__(self, player, dealer, uid, bet):
        super().__init__(timeout=30)
        self.player, self.dealer, self.uid, self.bet = player, dealer, uid, bet, 
        self.done = False

    async def interaction_check(self, interaction): return interaction.user.id == self.uid

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction, button: Button):
        self.player.append(random.choice(deck))
        if hand_value(self.player) > 21:
            set_wallet(self.uid, get_wallet(self.uid) - self.bet)
            await interaction.response.edit_message(content=f"💥 Bust! Your hand: {self.player} ({hand_value(self.player)})\nDealer: {self.dealer}\nYou lost ${self.bet}.", view=None)
            self.stop()
        else:
            await interaction.response.edit_message(content=f"🃏 Your hand: {self.player} ({hand_value(self.player)})\nDealer shows: {self.dealer[0]}\nBet: ${self.bet}", view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, interaction, button: Button):
        while hand_value(self.dealer) < 17: self.dealer.append(random.choice(deck))
        pval, dval = hand_value(self.player), hand_value(self.dealer)
        if dval > 21 or pval > dval: add_wallet(self.uid, self.bet); result=f"🎉 You win ${self.bet}!"
        elif pval == dval: result="🤝 It's a tie!"
        else: set_wallet(self.uid, get_wallet(self.uid) - self.bet); result=f"😢 Dealer wins. Lost ${self.bet}."
        await interaction.response.edit_message(content=f"🃏 Your hand: {self.player} ({pval})\nDealer: {self.dealer} ({dval})\n{result}", view=None)
        self.stop()

@bot.tree.command(description="Play Blackjack")
async def blackjack(interaction, bet: int):
    uid = interaction.user.id
    if bet <= 0 or bet > get_wallet(uid): await interaction.response.send_message("❌ Invalid bet."); return
    player, dealer = [random.choice(deck), random.choice(deck)], [random.choice(deck)]
    await interaction.response.send_message(f"🃏 Your hand: {player} ({hand_value(player)})\nDealer shows: {dealer[0]}\nBet: ${bet}", view=BlackjackView(player,dealer,uid,bet))

@bot.tree.command(description="Play roulette (red/black/green)")
async def roulette(interaction, bet: int, choice: str):
    uid = interaction.user.id
    if bet <= 0 or bet > get_wallet(uid): await interaction.response.send_message("❌ Invalid bet."); return
    result = random.choice(["red","black"]*7+["green"])
    if choice.lower()==result:
        payout = bet*14 if result=="green" else bet*2
        add_wallet(uid,payout); msg=f"🎉 It landed on {result}! You won ${payout}."
    else: set_wallet(uid,get_wallet(uid)-bet); msg=f"😢 It landed on {result}. You lost ${bet}."
    await interaction.response.send_message(msg+f"\n💰 Wallet: ${get_wallet(uid)}")

@bot.tree.command(description="Play coinflip (heads/tails)")
async def coinflip(interaction, bet: int, guess: str):
    uid = interaction.user.id
    if bet <= 0 or bet > get_wallet(uid): await interaction.response.send_message("❌ Invalid bet."); return
    result = random.choice(["heads","tails"])
    if guess.lower()==result: add_wallet(uid,bet); msg=f"🪙 It was {result}! You won ${bet}!"
    else: set_wallet(uid,get_wallet(uid)-bet); msg=f"🪙 It was {result}. You lost ${bet}."
    await interaction.response.send_message(msg)

@bot.tree.command(description="Play slots")
async def slots(interaction, bet: int):
    uid = interaction.user.id
    if bet <= 0 or bet > get_wallet(uid): await interaction.response.send_message("❌ Invalid bet."); return
    symbols = ["🍒","🍋","🔔","⭐","7️⃣"]
    result = [random.choice(symbols) for _ in range(3)]
    msg = "🎰 " + " | ".join(result)
    if len(set(result))==1: payout=bet*5; add_wallet(uid,payout); msg+=f"\n🎉 JACKPOT! You won ${payout}!"
    elif len(set(result))==2: payout=bet*2; add_wallet(uid,payout); msg+=f"\n✨ Two match! You won ${payout}!"
    else: set_wallet(uid,get_wallet(uid)-bet); msg+=f"\n😢 You lost ${bet}."
    await interaction.response.send_message(msg)

# --- PREFIX HELP ---
@bot.command()
async def cmds(ctx):
    await ctx.send("📜 Commands: /ban /kick /mute /say /balance /daily /deposit /withdraw /send /leaderboard /addcash /blackjack /roulette /coinflip /slots /setwelcome /setgoodbye")

# --- RUN ---
bot.run(TOKEN)
