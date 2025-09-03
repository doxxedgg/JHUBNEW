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
        return {"balances": {}, "config": {}, "tickets": {}}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {"balances": {}, "config": {}, "tickets": {}}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()
balances = data.setdefault("balances", {})
config = data.setdefault("config", {})
tickets = data.setdefault("tickets", {})

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
    save_data()
    # Bank interest: 2% hourly, capped at 10k
    for uid, bal in balances.items():
        interest = int(bal.get("bank", 0) * 0.02)
        if interest > 0:
            interest = min(interest, 10000)
            bal["bank"] += interest
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

# --- CHANNEL CONFIG ---
@bot.tree.command(description="Set welcome channel")
@app_commands.default_permissions(administrator=True)
async def setwelcome(interaction, channel: discord.TextChannel):
    config["welcome_channel"] = channel.id
    save_data()
    await interaction.response.send_message(f"✅ Welcome channel set to {channel.mention}")

@bot.tree.command(description="Set goodbye channel")
@app_commands.default_permissions(administrator=True)
async def setgoodbye(interaction, channel: discord.TextChannel):
    config["goodbye_channel"] = channel.id
    save_data()
    await interaction.response.send_message(f"✅ Goodbye channel set to {channel.mention}")

# --- MODERATION ---
@bot.tree.command(description="Ban a member")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction, member: discord.Member, reason: str = None):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"🔨 Banned {member.mention}")

@bot.tree.command(description="Kick a member")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction, member: discord.Member, reason: str = None):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 Kicked {member.mention}")

@bot.tree.command(description="Timeout (mute) a member")
@app_commands.default_permissions(moderate_members=True)
async def mute(interaction, member: discord.Member, seconds: int, reason: str = None):
    until = discord.utils.utcnow() + timedelta(seconds=seconds)
    await member.timeout(until, reason=reason)
    await interaction.response.send_message(f"🔇 Muted {member.mention} for {seconds}s")

# --- FUN ---
@bot.tree.command(description="Say something as the bot")
async def say(interaction, *, text: str): await interaction.response.send_message(text)

# --- ECONOMY ---
@bot.tree.command(description="Check your balance")
async def balance(interaction):
    uid = interaction.user.id
    await interaction.response.send_message(f"💰 Wallet: ${get_wallet(uid)} | 🏦 Bank: ${get_bank(uid)}")

@bot.tree.command(description="Daily reward")
async def daily(interaction):
    uid = interaction.user.id
    now = int(time.time())
    if now - get_last_daily(uid) < 86400:
        await interaction.response.send_message("❌ You already claimed daily today.")
        return
    reward = random.randint(100, 500)
    add_wallet(uid, reward)
    set_last_daily(uid, now)
    await interaction.response.send_message(f"🎁 You received ${reward} daily reward!")

@bot.tree.command(description="Work for money")
async def work(interaction):
    uid = interaction.user.id
    reward = random.randint(50, 200)
    add_wallet(uid, reward)
    await interaction.response.send_message(f"👷 You worked and earned ${reward}!")

@bot.tree.command(description="Rob another user")
async def rob(interaction, member: discord.Member):
    uid, target = interaction.user.id, member.id
    if get_wallet(target) < 50:
        await interaction.response.send_message("❌ Target too poor.")
        return
    if random.random() < 0.5:
        stolen = random.randint(20, get_wallet(target)//2)
        set_wallet(target, get_wallet(target)-stolen)
        add_wallet(uid, stolen)
        await interaction.response.send_message(f"💀 You robbed {member.mention} and got ${stolen}!")
    else:
        fine = random.randint(20, 100)
        set_wallet(uid, get_wallet(uid)-fine)
        await interaction.response.send_message(f"🚓 You got caught! Lost ${fine}.")

@bot.tree.command(description="Deposit money to bank")
async def deposit(interaction, amount: int):
    uid = interaction.user.id
    if amount <= 0 or amount > get_wallet(uid): await interaction.response.send_message("❌ Invalid amount."); return
    set_wallet(uid, get_wallet(uid)-amount); set_bank(uid, get_bank(uid)+amount)
    await interaction.response.send_message(f"🏦 Deposited ${amount}")

@bot.tree.command(description="Withdraw money from bank")
async def withdraw(interaction, amount: int):
    uid = interaction.user.id
    if amount <= 0 or amount > get_bank(uid): await interaction.response.send_message("❌ Invalid amount."); return
    set_bank(uid, get_bank(uid)-amount); set_wallet(uid, get_wallet(uid)+amount)
    await interaction.response.send_message(f"🏦 Withdrew ${amount}")

@bot.tree.command(description="Send cash to another user")
async def send(interaction, member: discord.Member, amount: int):
    sender = interaction.user.id
    if amount <= 0 or amount > get_wallet(sender): await interaction.response.send_message("❌ Invalid amount."); return
    set_wallet(sender, get_wallet(sender)-amount); add_wallet(member.id, amount)
    await interaction.response.send_message(f"💸 Sent ${amount} to {member.mention}")

@bot.tree.command(description="Show leaderboard")
async def leaderboard(interaction):
    top = sorted(balances.items(), key=lambda x: (x[1].get("wallet", 0)+x[1].get("bank", 0)), reverse=True)[:10]
    msg = "💰 **Leaderboard** 💰\n"
    for i,(uid,bal) in enumerate(top,start=1):
        total = bal.get("wallet",0)+bal.get("bank",0)
        try: user = await bot.fetch_user(int(uid)); msg+=f"{i}. {user.name} — ${total}\n"
        except: msg+=f"{i}. Unknown — ${total}\n"
    await interaction.response.send_message(msg)

@bot.tree.command(description="Admin: Add cash")
@app_commands.default_permissions(administrator=True)
async def addcash(interaction, member: discord.Member, amount: int):
    if amount <= 0: await interaction.response.send_message("❌ Must be positive."); return
    add_wallet(member.id, amount)
    await interaction.response.send_message(f"💵 Added ${amount} to {member.mention}")

# --- GAMES ---
# Blackjack
def deal_card(): return random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11])
def hand_value(hand):
    val = sum(hand)
    aces = hand.count(11)
    while val > 21 and aces: val-=10; aces-=1
    return val

class BlackjackView(View):
    def __init__(self, player, bet): super().__init__(timeout=20); self.player=player; self.bet=bet; self.player_hand=[deal_card(),deal_card()]; self.dealer_hand=[deal_card(),deal_card()]
    def hands(self): return f"Your hand: {self.player_hand} ({hand_value(self.player_hand)})\nDealer shows: {self.dealer_hand[0]}"
    @discord.ui.button(label="Hit",style=discord.ButtonStyle.green)
    async def hit(self,interaction,button): 
        if interaction.user!=self.player: return await interaction.response.send_message("Not your game!",ephemeral=True)
        self.player_hand.append(deal_card())
        if hand_value(self.player_hand)>21: self.disable_all_items(); await interaction.response.edit_message(content=f"{self.hands()}\n💥 You busted! Lost ${self.bet}")
        else: await interaction.response.edit_message(content=self.hands(),view=self)
    @discord.ui.button(label="Stand",style=discord.ButtonStyle.red)
    async def stand(self,interaction,button):
        if interaction.user!=self.player: return await interaction.response.send_message("Not your game!",ephemeral=True)
        while hand_value(self.dealer_hand)<17: self.dealer_hand.append(deal_card())
        self.disable_all_items()
        p,d=hand_value(self.player_hand),hand_value(self.dealer_hand)
        if d>21 or p>d: add_wallet(self.player.id,self.bet*2); result=f"✅ You win ${self.bet}!"
        elif p==d: add_wallet(self.player.id,self.bet); result="🤝 It's a tie."
        else: result=f"❌ You lost ${self.bet}."
        await interaction.response.edit_message(content=f"Your hand {self.player_hand} ({p})\nDealer {self.dealer_hand} ({d})\n{result}",view=self)

@bot.tree.command(description="Play Blackjack")
async def blackjack(interaction, bet:int):
    uid=interaction.user.id
    if bet<=0 or bet>get_wallet(uid): return await interaction.response.send_message("❌ Invalid bet.")
    set_wallet(uid,get_wallet(uid)-bet)
    view=BlackjackView(interaction.user,bet)
    await interaction.response.send_message(view.hands(),view=view)

# Roulette
@bot.tree.command(description="Roulette (red/black)")
async def roulette(interaction, color:str, bet:int):
    uid=interaction.user.id
    if bet<=0 or bet>get_wallet(uid): return await interaction.response.send_message("❌ Invalid bet.")
    color=color.lower(); if color not in ["red","black"]: return await interaction.response.send_message("❌ Choose red/black.")
    set_wallet(uid,get_wallet(uid)-bet)
    result=random.choice(["red","black"])
    if result==color: add_wallet(uid,bet*2); await interaction.response.send_message(f"🎡 Ball landed {result}! You win ${bet}")
    else: await interaction.response.send_message(f"🎡 Ball landed {result}! You lose ${bet}")

# Coinflip
@bot.tree.command(description="Coinflip heads/tails")
async def coinflip(interaction, guess:str, bet:int):
    uid=interaction.user.id
    if bet<=0 or bet>get_wallet(uid): return await interaction.response.send_message("❌ Invalid bet.")
    guess=guess.lower(); if guess not in ["heads","tails"]: return await interaction.response.send_message("❌ Must be heads/tails.")
    set_wallet(uid,get_wallet(uid)-bet)
    result=random.choice(["heads","tails"])
    if result==guess: add_wallet(uid,bet*2); await interaction.response.send_message(f"🪙 It was {result}! You win ${bet}")
    else: await interaction.response.send_message(f"🪙 It was {result}! You lose ${bet}")

# Slots
@bot.tree.command(description="Play slots")
async def slots(interaction, bet:int):
    uid=interaction.user.id
    if bet<=0 or bet>get_wallet(uid): return await interaction.response.send_message("❌ Invalid bet.")
    set_wallet(uid,get_wallet(uid)-bet)
    symbols=["🍒","🍋","🔔","⭐","7️⃣"]
    roll=[random.choice(symbols) for _ in range(3)]
    if len(set(roll))==1: add_wallet(uid,bet*5); res=f"🎰 {' '.join(roll)} JACKPOT! Won ${bet*5}"
    elif len(set(roll))==2: add_wallet(uid,bet*2); res=f"🎰 {' '.join(roll)} Nice! Won ${bet*2}"
    else: res=f"🎰 {' '.join(roll)} Lost ${bet}"
    await interaction.response.send_message(res)

# Dice
@bot.tree.command(description="Dice roll (2-12)")
async def dice(interaction, guess:int, bet:int):
    uid=interaction.user.id
    if bet<=0 or bet>get_wallet(uid): return await interaction.response.send_message("❌ Invalid bet.")
    if guess<2 or guess>12: return await interaction.response.send_message("❌ Guess between 2-12.")
    set_wallet(uid,get_wallet(uid)-bet)
    roll=random.randint(1,6)+random.randint(1,6)
    if roll==guess: add_wallet(uid,bet*6); res=f"🎲 Rolled {roll}! You win ${bet*6}"
    else: res=f"🎲 Rolled {roll}! You lose ${bet}"
    await interaction.response.send_message(res)

# HighLow
@bot.tree.command(description="HighLow (guess next card)")
async def highlow(interaction, bet:int, guess:str):
    uid=interaction.user.id
    if bet<=0 or bet>get_wallet(uid): return await interaction.response.send_message("❌ Invalid bet.")
    guess=guess.lower(); if guess not in ["high","low"]: return await interaction.response.send_message("❌ Guess high/low.")
    set_wallet(uid,get_wallet(uid)-bet)
    card=random.randint(1,13); next_card=random.randint(1,13)
    win=(next_card>card and guess=="high") or (next_card<card and guess=="low")
    if win: add_wallet(uid,bet*2); res=f"🃏 Card {card}, next {next_card}. You win ${bet}"
    else: res=f"🃏 Card {card}, next {next_card}. You lose ${bet}"
    await interaction.response.send_message(res)

# --- TICKET LOGGING ---
def log_ticket(channel_id, staff_id):
    ch = tickets.setdefault(str(channel_id), {})
    ch[str(staff_id)] = ch.get(str(staff_id), 0) + 1
    save_data()

@bot.tree.command(description="Show ticket logs")
@app_commands.default_permissions(administrator=True)
async def ticketlog(interaction, channel: discord.TextChannel = None):
    if channel:
        ch_data = tickets.get(str(channel.id), {})
        if not ch_data: await interaction.response.send_message("No tickets logged here."); return
        msg = f"🎫 Ticket log for {channel.mention}\n"
        for sid,count in ch_data.items():
            try: staff = await bot.fetch_user(int(sid)); msg+=f"{staff.name}: {count}\n"
            except: msg+=f"Unknown {sid}: {count}\n"
        await interaction.response.send_message(msg)
    else:
        msg="🎫 **All Ticket Logs**\n"
        for ch_id,ch_data in tickets.items():
            ch=bot.get_channel(int(ch_id)); ch_name=ch.name if ch else f"Channel {ch_id}"
            msg+=f"\n**{ch_name}**\n"
            for sid,count in ch_data.items():
                try: staff=await bot.fetch_user(int(sid)); msg+=f"{staff.name}: {count}\n"
                except: msg+=f"Unknown {sid}: {count}\n"
        await interaction.response.send_message(msg)

# --- PREFIX HELP ---
@bot.command()
async def cmds(ctx):
    await ctx.send("📜 Use `/` slash commands for moderation, economy, casino, tickets")

# --- RUN ---
bot.run(TOKEN)
