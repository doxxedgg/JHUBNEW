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
LEVEL_MULTIPLIER = 2

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

# ----------------- ECONOMY -----------------
def ensure_user(uid):
    uid = str(uid)
    balances.setdefault(uid, {"wallet": START_BALANCE,"bank":0,"last_daily":0,"last_work":0,"last_steal":0})
    return balances[uid]

def get_wallet(uid): return ensure_user(uid)["wallet"]
def get_bank(uid): return ensure_user(uid)["bank"]
def set_wallet(uid, amt): ensure_user(uid)["wallet"]=int(amt); save_data()
def set_bank(uid, amt): ensure_user(uid)["bank"]=int(amt); save_data()
def add_wallet(uid, amt): u=ensure_user(uid); u["wallet"]+=int(amt); save_data()

# ----------------- LEVELS -----------------
def ensure_level(uid):
    uid=str(uid)
    if uid not in levels:
        levels[uid]={"xp":0,"level":1}
    return levels[uid]

def add_xp(uid, amount):
    user = ensure_level(uid)
    user["xp"]+=amount
    leveled_up=False
    while user["xp"]>=user["level"]*LEVEL_MULTIPLIER:
        user["xp"]-=user["level"]*LEVEL_MULTIPLIER
        user["level"]+=1
        leveled_up=True
    save_data()
    return leveled_up,user["level"]

# ----------------- BOT -----------------
intents=discord.Intents.default()
intents.members=True
intents.message_content=True
bot=commands.Bot(command_prefix="!", intents=intents)

def emb(title, desc, color=discord.Color.blurple()):
    return discord.Embed(title=title, description=desc, color=color)

# ----------------- EVENTS -----------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    bot.add_view(TicketView())
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return
    leveled_up, level = add_xp(message.author.id, XP_PER_MESSAGE)
    if leveled_up:
        await message.channel.send(f"🎉 {message.author.mention} leveled up! Level {level}")
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    ch_id = config.get("welcome_channel")
    if ch_id:
        ch=bot.get_channel(ch_id)
        if ch: await ch.send(f"🎉 Welcome {member.mention}!")

@bot.event
async def on_member_remove(member):
    ch_id = config.get("goodbye_channel")
    if ch_id:
        ch=bot.get_channel(ch_id)
        if ch: await ch.send(f"👋 {member.mention} has left.")

# ----------------- TICKET SYSTEM -----------------
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.green, custom_id="open_ticket")
    async def open_ticket(self, button, interaction):
        guild = interaction.guild
        overwrites={guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)}
        channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites)
        tickets[str(channel.id)]={"opener_id":str(interaction.user.id),"opened_at":datetime.utcnow().isoformat()}
        save_data()
        await interaction.response.send_message(f"🎫 Ticket created: {channel.mention}", ephemeral=True)

# ----------------- UPDATE SYSTEM -----------------
class UpdateModal(Modal):
    def __init__(self):
        super().__init__(title="Send Update")
        self.content_input=TextInput(label="Update Content", style=discord.TextStyle.paragraph)
        self.add_item(self.content_input)
    async def on_submit(self, interaction):
        ch_id=config.get("update_channel")
        if not ch_id: return await interaction.response.send_message("❌ Update channel not set.", ephemeral=True)
        ch=bot.get_channel(ch_id)
        if not ch: return await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
        content=self.content_input.value
        await ch.send(embed=emb("📢 Update", content))
        updates.append({"time":datetime.utcnow().isoformat(),"content":content})
        save_data()
        await interaction.response.send_message("✅ Update sent.", ephemeral=True)

# ----------------- CASINO -----------------
deck=[str(x) for x in range(2,11)]+["J","Q","K","A"]
symbols=["🍒","🍋","🍉","⭐","7️⃣"]

def bj_total(cards):
    total, aces=0,0
    for c in cards:
        if c in ["J","Q","K"]: total+=10
        elif c=="A": total+=11; aces+=1
        else: total+=int(c)
    while total>21 and aces: total-=10; aces-=1
    return total

class BlackjackView(View):
    def __init__(self,user,bet,player,dealer):
        super().__init__(timeout=90)
        self.user=user; self.bet=bet; self.player=player; self.dealer=dealer
    async def interaction_check(self,i):
        if i.user.id!=self.user.id:
            await i.response.send_message("🚫 Not your game", ephemeral=True)
            return False
        return True
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self,i,b):
        self.player.append(random.choice(deck))
        pt=bj_total(self.player)
        if pt>21:
            await i.response.edit_message(content=f"Busted! Your hand:{self.player} ({pt})\nDealer:{self.dealer} ({bj_total(self.dealer)})",view=None)
            self.stop()
        else: await i.response.edit_message(content=f"Your hand:{self.player} ({pt})\nDealer shows:{self.dealer[0]}",view=self)
    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self,i,b):
        pt=bj_total(self.player); dt=bj_total(self.dealer)
        while dt<17: self.dealer.append(random.choice(deck)); dt=bj_total(self.dealer)
        if dt>21 or pt>dt: add_wallet(self.user.id,self.bet*2); result=f"✅ You win ${self.bet*2}!"
        elif pt==dt: add_wallet(self.user.id,self.bet); result="🤝 Tie, bet returned."
        else: result=f"❌ You lost ${self.bet}."
        await i.response.edit_message(content=f"Your hand:{self.player} ({pt})\nDealer:{self.dealer} ({dt})\n{result}",view=None)
        self.stop()

# Roulette
async def roulette_game(interaction, color, bet):
    color=color.lower()
    if color not in ["red","black"]: return await interaction.response.send_message("Pick red/black",ephemeral=True)
    if bet<=0 or bet>get_wallet(interaction.user.id): return await interaction.response.send_message("Invalid bet",ephemeral=True)
    add_wallet(interaction.user.id,-bet)
    result=random.choices(["red","black","green"],weights=[48,48,4])[0]
    if result==color: add_wallet(interaction.user.id, bet*2); msg=f"✅ Ball landed on {result}, you win ${bet*2}!"
    elif result=="green": add_wallet(interaction.user.id, bet*5); msg=f"🍀 Ball landed green, mega win ${bet*5}!"
    else: msg=f"❌ Ball landed {result}, you lost ${bet}."
    await interaction.response.send_message(msg)

# Slots
async def slots_game(interaction, bet):
    if bet<=0 or bet>get_wallet(interaction.user.id): return await interaction.response.send_message("Invalid bet",ephemeral=True)
    add_wallet(interaction.user.id,-bet)
    roll=[random.choice(symbols) for _ in range(3)]
    if len(set(roll))==1: add_wallet(interaction.user.id, bet*5); msg=f"{' '.join(roll)} Jackpot! Won ${bet*5}!"
    elif len(set(roll))==2: add_wallet(interaction.user.id, bet*2); msg=f"{' '.join(roll)} Nice! Won ${bet*2}."
    else: msg=f"{' '.join(roll)} Unlucky, lost ${bet}."
    await interaction.response.send_message(msg)

# Coinflip
async def coinflip_game(interaction, choice, bet):
    choice=choice.lower()
    if choice not in ["heads","tails"]: return await interaction.response.send_message("Pick heads/tails",ephemeral=True)
    if bet<=0 or bet>get_wallet(interaction.user.id): return await interaction.response.send_message("Invalid bet",ephemeral=True)
    add_wallet(interaction.user.id,-bet)
    res=random.choice(["heads","tails"])
    if res==choice: add_wallet(interaction.user.id, bet*2); msg=f"{res} — won ${bet*2}!"
    else: msg=f"{res} — lost ${bet}."
    await interaction.response.send_message(msg)

# Dice
async def dice_game(interaction, guess, bet):
    if guess<1 or guess>6: return await interaction.response.send_message("Guess 1-6",ephemeral=True)
    if bet<=0 or bet>get_wallet(interaction.user.id): return await interaction.response.send_message("Invalid bet",ephemeral=True)
    add_wallet(interaction.user.id,-bet)
    roll=random.randint(1,6)
    if roll==guess: add_wallet(interaction.user.id, bet*6); msg=f"Rolled {roll}, correct! Won ${bet*6}!"
    else: msg=f"Rolled {roll}, lost ${bet}."
    await interaction.response.send_message(msg)

# HighLow
async def highlow_game(interaction, guess, bet):
    guess=guess.lower()
    if guess not in ["high","low"]: return await interaction.response.send_message("Guess high/low",ephemeral=True)
    if bet<=0 or bet>get_wallet(interaction.user.id): return await interaction.response.send_message("Invalid bet",ephemeral=True)
    add_wallet(interaction.user.id,-bet)
    roll=random.randint(1,100)
    res="high" if roll>50 else "low"
    if guess==res: add_wallet(interaction.user.id, bet*2); msg=f"Number {roll} ({res}) — won ${bet*2}!"
    else: msg=f"Number {roll} ({res}) — lost ${bet}."
    await interaction.response.send_message(msg)

# ----------------- SLASH COMMANDS EXAMPLES -----------------
@bot.tree.command(description="Blackjack")
async def blackjack(interaction: discord.Interaction, bet:int):
    if bet<=0 or bet>get_wallet(interaction.user.id): return await interaction.response.send_message("Invalid bet",ephemeral=True)
    add_wallet(interaction.user.id,-bet)
    player=[random.choice(deck), random.choice(deck)]
    dealer=[random.choice(deck), random.choice(deck)]
    view=BlackjackView(interaction.user, bet, player, dealer)
    await interaction.response.send_message(f"Your hand: {player} ({bj_total(player)})\nDealer shows: {dealer[0]}", view=view)

@bot.tree.command(description="Roulette red/black")
async def roulette(interaction: discord.Interaction, color:str, bet:int):
    await roulette_game(interaction, color, bet)

@bot.tree.command(description="Slots")
async def slots(interaction: discord.Interaction, bet:int):
    await slots_game(interaction, bet)

@bot.tree.command(description="Coinflip heads/tails")
async def coinflip(interaction: discord.Interaction, choice:str, bet:int):
    await coinflip_game(interaction, choice, bet)

@bot.tree.command(description="Dice 1-6")
async def dice(interaction: discord.Interaction, guess:int, bet:int):
    await dice_game(interaction, guess, bet)

@bot.tree.command(description="HighLow high/low")
async def highlow(interaction: discord.Interaction, guess:str, bet:int):
    await highlow_game(interaction, guess, bet)

# ----------------- RUN -----------------
if not TOKEN: raise RuntimeError("DISCORD_TOKEN not set")
bot.run(TOKEN)
