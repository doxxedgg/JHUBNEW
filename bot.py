import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
import random, time, json, os

TOKEN = os.environ.get("DISCORD_TOKEN")
DATA_FILE = "data.json"
START_BALANCE = 500

# --- Data Setup ---
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

def get_wallet(uid): return balances.get(str(uid), {}).get("wallet", START_BALANCE)
def get_bank(uid): return balances.get(str(uid), {}).get("bank", 0)

def ensure_user(uid):
    balances.setdefault(str(uid), {"wallet": START_BALANCE, "bank": 0, "last_daily": 0, "last_work": 0, "last_steal": 0})

def set_wallet(uid, amt):
    ensure_user(uid)
    balances[str(uid)]["wallet"] = amt
    save_data()

def set_bank(uid, amt):
    ensure_user(uid)
    balances[str(uid)]["bank"] = amt
    save_data()

def add_wallet(uid, amt): set_wallet(uid, get_wallet(uid) + amt)

# --- Bot Setup ---
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

def make_embed(title, description, color=discord.Color.blurple()):
    return discord.Embed(title=title, description=description, color=color)

# --- Events ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_member_join(member):
    if (ch_id := config.get("welcome_channel")):
        ch = bot.get_channel(ch_id)
        if ch:
            await ch.send(embed=make_embed("👋 Welcome!", f"Welcome {member.mention}!"))

@bot.event
async def on_member_remove(member):
    if (ch_id := config.get("goodbye_channel")):
        ch = bot.get_channel(ch_id)
        if ch:
            await ch.send(embed=make_embed("😢 Goodbye", f"{member.mention} has left the server."))

# --- Moderation ---
@bot.tree.command(description="Ban a user")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction, member: discord.Member, reason: str = "No reason"):
    await member.ban(reason=reason)
    await interaction.response.send_message(embed=make_embed("🔨 Banned", f"{member} was banned. Reason: {reason}"))

@bot.tree.command(description="Kick a user")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction, member: discord.Member, reason: str = "No reason"):
    await member.kick(reason=reason)
    await interaction.response.send_message(embed=make_embed("👢 Kicked", f"{member} was kicked. Reason: {reason}"))

# --- Welcome/Goodbye Config ---
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

# --- Economy ---
@bot.tree.command(description="Check your balance")
async def balance(interaction):
    uid = str(interaction.user.id)
    ensure_user(uid)
    await interaction.response.send_message(embed=make_embed("💰 Balance", f"Wallet: ${get_wallet(uid)}\nBank: ${get_bank(uid)}"))

@bot.tree.command(description="Deposit money into bank")
async def deposit(interaction, amount: int):
    uid = str(interaction.user.id)
    ensure_user(uid)
    if amount > get_wallet(uid): return await interaction.response.send_message(embed=make_embed("❌ Error", "Not enough in wallet."))
    add_wallet(uid, -amount); set_bank(uid, get_bank(uid)+amount)
    await interaction.response.send_message(embed=make_embed("🏦 Deposit", f"Deposited ${amount}."))

@bot.tree.command(description="Withdraw money from bank")
async def withdraw(interaction, amount: int):
    uid = str(interaction.user.id)
    ensure_user(uid)
    if amount > get_bank(uid): return await interaction.response.send_message(embed=make_embed("❌ Error", "Not enough in bank."))
    set_bank(uid, get_bank(uid)-amount); add_wallet(uid, amount)
    await interaction.response.send_message(embed=make_embed("🏦 Withdraw", f"Withdrew ${amount}."))

@bot.tree.command(description="Send money to another player")
async def send(interaction, member: discord.Member, amount: int):
    uid, tid = str(interaction.user.id), str(member.id)
    ensure_user(uid); ensure_user(tid)
    if amount > get_wallet(uid): return await interaction.response.send_message(embed=make_embed("❌ Error", "Not enough to send."))
    add_wallet(uid, -amount); add_wallet(tid, amount)
    await interaction.response.send_message(embed=make_embed("💸 Transfer", f"Sent ${amount} to {member.mention}"))

@bot.tree.command(description="Leaderboard")
async def leaderboard(interaction):
    top = sorted(balances.items(), key=lambda x: x[1].get("wallet",0)+x[1].get("bank",0), reverse=True)[:10]
    desc = "\n".join([f"{i+1}. <@{uid}> - ${vals['wallet']+vals['bank']}" for i,(uid,vals) in enumerate(top)])
    await interaction.response.send_message(embed=make_embed("🏆 Leaderboard", desc))

# --- Cooldowns: Work & Steal ---
@bot.tree.command(description="Work for cash (8m cooldown)")
async def work(interaction):
    uid = str(interaction.user.id)
    ensure_user(uid)
    now = int(time.time())
    if now - balances[uid]["last_work"] < 480:
        rem = 480 - (now - balances[uid]["last_work"])
        return await interaction.response.send_message(embed=make_embed("⏳ Cooldown", f"Wait {rem//60}m {rem%60}s."), ephemeral=True)
    earnings = random.randint(50,150)
    add_wallet(uid, earnings)
    balances[uid]["last_work"] = now; save_data()
    await interaction.response.send_message(embed=make_embed("💼 Work", f"You earned ${earnings}"))

@bot.tree.command(description="Steal from a player (15m cooldown)")
async def steal(interaction, member: discord.Member):
    uid, tid = str(interaction.user.id), str(member.id)
    ensure_user(uid); ensure_user(tid)
    now = int(time.time())
    if now - balances[uid]["last_steal"] < 900:
        rem = 900 - (now - balances[uid]["last_steal"])
        return await interaction.response.send_message(embed=make_embed("⏳ Cooldown", f"Wait {rem//60}m {rem%60}s."), ephemeral=True)
    if get_wallet(tid) < 50: return await interaction.response.send_message(embed=make_embed("❌ Error", "Target too poor."))
    if random.random()<0.5:
        amt = random.randint(20, min(100,get_wallet(tid)))
        add_wallet(uid, amt); add_wallet(tid, -amt)
        res = f"💰 You stole ${amt} from {member.mention}!"
    else:
        fine = random.randint(20,100); add_wallet(uid,-fine)
        res = f"🚓 Caught! You paid ${fine}."
    balances[uid]["last_steal"] = now; save_data()
    await interaction.response.send_message(embed=make_embed("🕵️ Steal", res))

# --- Admin Cash Resets (with logging) ---
@bot.tree.command(description="Reset a player's cash")
@app_commands.default_permissions(administrator=True)
async def resetcash(interaction, member: discord.Member):
    set_wallet(member.id, START_BALANCE); set_bank(member.id, 0)
    msg = f"{member.mention}'s cash reset."
    if (ch_id:=config.get("ticket_log_channel")) and (ch:=bot.get_channel(ch_id)):
        await ch.send(embed=make_embed("♻️ Reset Log", f"{interaction.user.mention} reset {member.mention}'s cash."))
    await interaction.response.send_message(embed=make_embed("♻️ Reset Cash", msg))

@bot.tree.command(description="Reset everyone's cash")
@app_commands.default_permissions(administrator=True)
async def resetcashall(interaction):
    for uid in balances: set_wallet(uid, START_BALANCE); set_bank(uid,0)
    if (ch_id:=config.get("ticket_log_channel")) and (ch:=bot.get_channel(ch_id)):
        await ch.send(embed=make_embed("♻️ Reset Log", f"{interaction.user.mention} reset ALL balances."))
    await interaction.response.send_message(embed=make_embed("♻️ Reset Cash", "All balances reset."))

# --- Add Cash Command ---
@bot.tree.command(description="Admin: Add cash to a player's wallet")
@app_commands.default_permissions(administrator=True)
async def addcash(interaction, member: discord.Member, amount: int):
    if amount == 0:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Amount must not be 0."), ephemeral=True)
        return

    add_wallet(member.id, amount)
    action = "added to" if amount > 0 else "removed from"
    msg = f"${abs(amount)} {action} {member.mention}'s wallet."

    # Log to ticket_log_channel if set
    log_ch = bot.get_channel(config.get("ticket_log_channel"))
    if log_ch:
        await log_ch.send(embed=make_embed("💰 Cash Adjustment Log", f"Admin {interaction.user.mention} {action} {abs(amount)} for {member.mention}."))

    await interaction.response.send_message(embed=make_embed("💰 Cash Adjusted", msg))



# --- Casino: Blackjack ---
deck = [str(x) for x in range(2,11)] + ["J","Q","K","A"]
def calc_blackjack(cards):
    total, aces = 0,0
    for c in cards:
        total += 10 if c in ["J","Q","K"] else 11 if c=="A" else int(c)
        if c=="A": aces+=1
    while total>21 and aces: total-=10; aces-=1
    return total

class BlackjackView(View):
    def __init__(self,user,bet,player,dealer):
        super().__init__(timeout=60)
        self.user,self.bet,self.player,self.dealer=user,bet,player,dealer
    async def interaction_check(self,i): return i.user==self.user
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self,i,b):
        self.player.append(random.choice(deck)); total=calc_blackjack(self.player)
        if total>21:
            e=make_embed("🃏 Bust!",f"Your cards {self.player} ({total})\nLost ${self.bet}")
            return await i.response.edit_message(embed=e,view=None)
        e=make_embed("🃏 Blackjack",f"Your cards {self.player} ({total})\nDealer shows {self.dealer[0]}")
        await i.response.edit_message(embed=e,view=self)
    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self,i,b):
        pt=calc_blackjack(self.player); dt=calc_blackjack(self.dealer)
        while dt<17: self.dealer.append(random.choice(deck)); dt=calc_blackjack(self.dealer)
        if dt>21 or pt>dt: add_wallet(self.user.id,self.bet*2); res=f"✅ You win ${self.bet*2}"
        elif pt==dt: add_wallet(self.user.id,self.bet); res="🤝 Tie, bet returned"
        else: res=f"❌ You lost ${self.bet}"
        e=make_embed("🃏 Result",f"Your {self.player} ({pt})\nDealer {self.dealer} ({dt})\n{res}")
        await i.response.edit_message(embed=e,view=None)

@bot.tree.command(description="Play Blackjack")
async def blackjack(interaction, bet:int):
    uid=str(interaction.user.id); ensure_user(uid)
    if bet>get_wallet(uid) or bet<=0: return await interaction.response.send_message(embed=make_embed("❌","Invalid bet"),ephemeral=True)
    add_wallet(uid,-bet); player=[random.choice(deck),random.choice(deck)]; dealer=[random.choice(deck),random.choice(deck)]
    view=BlackjackView(interaction.user,bet,player,dealer)
    e=make_embed("🃏 Blackjack",f"Your {player} ({calc_blackjack(player)})\nDealer shows {dealer[0]}")
    await interaction.response.send_message(embed=e,view=view)

# --- Other Casino Games (Roulette, Slots, Coinflip, Dice, HighLow) ---
@bot.tree.command(description="Roulette (red/black)")
async def roulette(interaction, bet:int, color:str):
    uid=str(interaction.user.id); ensure_user(uid)
    if bet>get_wallet(uid) or bet<=0: return await interaction.response.send_message(embed=make_embed("❌","Invalid bet"))
    if color not in ["red","black"]: return await interaction.response.send_message(embed=make_embed("❌","Choose red/black"))
    add_wallet(uid,-bet); result=random.choice(["red","black"])
    if result==color: add_wallet(uid,bet*2); msg=f"Landed {result}, you won ${bet*2}"
    else: msg=f"Landed {result}, you lost ${bet}"
    await interaction.response.send_message(embed=make_embed("🎡 Roulette",msg))

@bot.tree.command(description="Slots")
async def slots(interaction, bet:int):
    uid=str(interaction.user.id); ensure_user(uid)
    if bet>get_wallet(uid) or bet<=0: return await interaction.response.send_message(embed=make_embed("❌","Invalid bet"))
    add_wallet(uid,-bet); icons=["🍎","🍌","🍒","🍇","⭐"]; roll=[random.choice(icons) for _ in range(3)]
    if len(set(roll))==1: win=bet*5; add_wallet(uid,win); res=f"{roll} Jackpot! Won ${win}"
    elif len(set(roll))==2: win=bet*2; add_wallet(uid,win); res=f"{roll} Partial win! Won ${win}"
    else: res=f"{roll} Lost ${bet}"
    await interaction.response.send_message(embed=make_embed("🎰 Slots",res))

@bot.tree.command(description="Coinflip")
async def coinflip(interaction, bet:int, choice:str):
    uid=str(interaction.user.id); ensure_user(uid)
    if bet>get_wallet(uid) or bet<=0: return await interaction.response.send_message(embed=make_embed("❌","Invalid bet"))
    if choice not in ["heads","tails"]: return await interaction.response.send_message(embed=make_embed("❌","Choose heads/tails"))
    add_wallet(uid,-bet); flip=random.choice(["heads","tails"])
    if flip==choice: add_wallet(uid,bet*2); msg=f"Coin {flip}, you won ${bet*2}"
    else: msg=f"Coin {flip}, you lost ${bet}"
    await interaction.response.send_message(embed=make_embed("🪙 Coinflip",msg))

@bot.tree.command(description="Dice (guess 1-6)")
async def dice(interaction, bet:int, guess:int):
    uid=str(interaction.user.id); ensure_user(uid)
    if bet>get_wallet(uid) or bet<=0 or guess not in range(1,7): return await interaction.response.send_message(embed=make_embed("❌","Invalid"))
    add_wallet(uid,-bet); roll=random.randint(1,6)
    if roll==guess: win=bet*6; add_wallet(uid,win); msg=f"Rolled {roll}, correct! Won ${win}"
    else: msg=f"Rolled {roll}, lost ${bet}"
    await interaction.response.send_message(embed=make_embed("🎲 Dice",msg))

@bot.tree.command(description="HighLow (guess)")
async def highlow(interaction, bet:int, guess:str):
    uid=str(interaction.user.id); ensure_user(uid)
    if bet>get_wallet(uid) or bet<=0: return await interaction.response.send_message(embed=make_embed("❌","Invalid bet"))
    if guess not in ["high","low"]: return await interaction.response.send_message(embed=make_embed("❌","Choose high/low"))
    add_wallet(uid,-bet); roll=random.randint(1,100); result="high" if roll>50 else "low"
    if guess==result: win=bet*2; add_wallet(uid,win); msg=f"{roll} ({result}), you won ${win}"
    else: msg=f"{roll} ({result}), lost ${bet}"
    await interaction.response.send_message(embed=make_embed("🎯 HighLow",msg))

# --- Ticket System ---
@bot.tree.command(description="Set ticket log channel")
@app_commands.default_permissions(administrator=True)
async def setticketlog(interaction, channel: discord.TextChannel):
    config["ticket_log_channel"]=channel.id; save_data()
    await interaction.response.send_message(embed=make_embed("✅","Ticket log set."))

@bot.tree.command(description="Log a ticket manually")
@app_commands.default_permissions(manage_messages=True)
async def logticket(interaction, staff:discord.Member, ticket_channel:discord.TextChannel, count:int):
    tid=str(ticket_channel.id); tickets.setdefault(tid,{})
    tickets[tid][str(staff.id)]=tickets[tid].get(str(staff.id),0)+count; save_data()
    if (ch_id:=config.get("ticket_log_channel")) and (ch:=bot.get_channel(ch_id)):
        await ch.send(embed=make_embed("📝 Ticket Logged",f"{staff.mention} logged {count} in {ticket_channel.mention}"))
    await interaction.response.send_message(embed=make_embed("✅","Ticket logged"),ephemeral=True)

# --- Run ---
bot.run(TOKEN)
