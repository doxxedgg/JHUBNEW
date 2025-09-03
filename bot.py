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
    for uid, bal in balances.items():
        interest = int(bal.get("bank", 0) * 0.02)
        if interest > 0:
            interest = min(interest, 10000)
            bal["bank"] += interest
    save_data()

# --- UTIL ---
def make_embed(title, description, color=discord.Color.blurple()):
    return discord.Embed(title=title, description=description, color=color)

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
    await interaction.response.send_message(embed=make_embed("🔨 Ban", f"{member.mention} was banned."))

@bot.tree.command(description="Kick a member")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction, member: discord.Member, reason: str = None):
    await member.kick(reason=reason)
    await interaction.response.send_message(embed=make_embed("👢 Kick", f"{member.mention} was kicked."))

@bot.tree.command(description="Timeout (mute) a member")
@app_commands.default_permissions(moderate_members=True)
async def mute(interaction, member: discord.Member, seconds: int, reason: str = None):
    until = discord.utils.utcnow() + timedelta(seconds=seconds)
    await member.timeout(until, reason=reason)
    await interaction.response.send_message(embed=make_embed("🔇 Mute", f"{member.mention} muted for {seconds}s."))

# --- ECONOMY COMMANDS (balance, daily, work, rob, deposit, withdraw, send, leaderboard, addcash) ---
# (kept as in last version, unchanged for brevity)

# --- CASINO ---
@bot.tree.command(description="Roulette (red/black)")
async def roulette(interaction, amount: int, color: str):
    uid = interaction.user.id
    if amount <= 0 or amount > get_wallet(uid):
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid bet."))
        return

    color = color.lower()
    if color not in ["red", "black"]:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Choose red/black."))
        return

    result = random.choice(["red", "black"])
    if result == color:
        add_wallet(uid, amount)
        await interaction.response.send_message(embed=make_embed("🎡 Roulette", f"Landed on {result}! You won ${amount}"))
    else:
        set_wallet(uid, get_wallet(uid)-amount)
        await interaction.response.send_message(embed=make_embed("🎡 Roulette", f"Landed on {result}! You lost ${amount}"))

@bot.tree.command(description="Coinflip heads/tails")
async def coinflip(interaction, amount: int, guess: str):
    uid = interaction.user.id
    if amount <= 0 or amount > get_wallet(uid):
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid bet."))
        return

    guess = guess.lower()
    if guess not in ["heads", "tails"]:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Choose heads/tails."))
        return

    result = random.choice(["heads", "tails"])
    if result == guess:
        add_wallet(uid, amount)
        await interaction.response.send_message(embed=make_embed("🪙 Coinflip", f"It was {result}! You won ${amount}"))
    else:
        set_wallet(uid, get_wallet(uid)-amount)
        await interaction.response.send_message(embed=make_embed("🪙 Coinflip", f"It was {result}! You lost ${amount}"))

@bot.tree.command(description="Slots")
async def slots(interaction, amount: int):
    uid = interaction.user.id
    if amount <= 0 or amount > get_wallet(uid):
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid bet."))
        return

    symbols = ["🍒","🍋","🍇","🍉","⭐"]
    result = [random.choice(symbols) for _ in range(3)]
    if len(set(result)) == 1:
        prize = amount * 5
        add_wallet(uid, prize)
        await interaction.response.send_message(embed=make_embed("🎰 Slots", f"{' '.join(result)}\nYou won ${prize}!"))
    else:
        set_wallet(uid, get_wallet(uid)-amount)
        await interaction.response.send_message(embed=make_embed("🎰 Slots", f"{' '.join(result)}\nYou lost ${amount}"))

@bot.tree.command(description="Dice roll 2-12")
async def dice(interaction, amount: int, guess: int):
    uid = interaction.user.id
    if amount <= 0 or amount > get_wallet(uid) or guess < 2 or guess > 12:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid bet or guess."))
        return

    roll = random.randint(2,12)
    if roll == guess:
        prize = amount * 6
        add_wallet(uid, prize)
        await interaction.response.send_message(embed=make_embed("🎲 Dice", f"Rolled {roll}! You won ${prize}!"))
    else:
        set_wallet(uid, get_wallet(uid)-amount)
        await interaction.response.send_message(embed=make_embed("🎲 Dice", f"Rolled {roll}! You lost ${amount}"))

@bot.tree.command(description="HighLow card game")
async def highlow(interaction, amount: int, guess: str):
    uid = interaction.user.id
    if amount <= 0 or amount > get_wallet(uid):
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid bet."))
        return

    card = random.randint(1,13)
    next_card = random.randint(1,13)
    guess = guess.lower()
    if (guess == "high" and next_card > card) or (guess == "low" and next_card < card):
        add_wallet(uid, amount)
        await interaction.response.send_message(embed=make_embed("🃏 HighLow", f"Card was {card}, next {next_card}. You won ${amount}!"))
    else:
        set_wallet(uid, get_wallet(uid)-amount)
        await interaction.response.send_message(embed=make_embed("🃏 HighLow", f"Card was {card}, next {next_card}. You lost ${amount}"))

# --- BLACKJACK ---
class BlackjackView(View):
    def __init__(self, uid, bet, dealer, player):
        super().__init__(timeout=60)
        self.uid, self.bet, self.dealer, self.player = uid, bet, dealer, player
        self.add_item(Button(label="Hit", style=discord.ButtonStyle.green, custom_id="hit"))
        self.add_item(Button(label="Stand", style=discord.ButtonStyle.red, custom_id="stand"))

    async def interaction_check(self, interaction):
        return interaction.user.id == self.uid

    async def on_timeout(self):
        pass

@bot.tree.command(description="Blackjack")
async def blackjack(interaction, amount: int):
    uid = interaction.user.id
    if amount <= 0 or amount > get_wallet(uid):
        await interaction.response.send_message(embed=make_embed("❌ Error", "Invalid bet."))
        return

    deck = [2,3,4,5,6,7,8,9,10,10,10,10,11]*4
    random.shuffle(deck)
    dealer, player = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]

    def value(hand):
        total = sum(hand)
        aces = hand.count(11)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    async def finish(win):
        if win == "win":
            add_wallet(uid, amount)
            msg = f"You win ${amount}!"
        elif win == "lose":
            set_wallet(uid, get_wallet(uid)-amount)
            msg = f"You lose ${amount}."
        else:
            msg = "It's a tie."
        await interaction.followup.send(embed=make_embed("🃏 Blackjack", msg))

    embed = make_embed("🃏 Blackjack", f"Dealer: {dealer[0]} + ?\nPlayer: {player} (Total {value(player)})")
    await interaction.response.send_message(embed=embed, view=BlackjackView(uid, amount, dealer, player))

# --- TICKET SYSTEM ---
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="🎫 Open Ticket", style=discord.ButtonStyle.green, custom_id="open_ticket"))

@bot.tree.command(description="Post the ticket panel")
@app_commands.default_permissions(administrator=True)
async def ticketpanel(interaction):
    embed = make_embed("🎫 Support Tickets", "Click below to open a ticket.")
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("✅ Ticket panel created.", ephemeral=True)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.type == discord.InteractionType.component:
        return
    if interaction.data.get("custom_id") == "open_ticket":
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="Tickets")
        if category is None:
            category = await guild.create_category("Tickets")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", category=category, overwrites=overwrites)
        await channel.send(embed=make_embed("🎫 Ticket Opened", f"{interaction.user.mention} opened a ticket."))
        log_ticket(channel.id, interaction.user.id)
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

@bot.tree.command(description="Close a ticket")
async def closeticket(interaction):
    if "ticket-" in interaction.channel.name:
        await interaction.channel.delete()
    else:
        await interaction.response.send_message(embed=make_embed("❌ Error", "Not a ticket channel."), ephemeral=True)

def log_ticket(channel_id, staff_id):
    ch = tickets.setdefault(str(channel_id), {})
    ch[str(staff_id)] = ch.get(str(staff_id), 0) + 1
    save_data()

@bot.tree.command(description="Show ticket logs")
@app_commands.default_permissions(administrator=True)
async def ticketlog(interaction):
    logs = []
    for ch_id, ch_data in tickets.items():
        ch_name = f"<#{ch_id}>" if bot.get_channel(int(ch_id)) else f"Channel {ch_id}"
        logs.append(f"**{ch_name}**\n" + "\n".join([f"<@{sid}>: {count}" for sid,count in ch_data.items()]))
    await interaction.response.send_message(embed=make_embed("📑 Ticket Logs", "\n\n".join(logs) or "No tickets logged."))

# --- PREFIX HELP ---
@bot.command()
async def cmds(ctx):
    embed = make_embed("📜 Commands", "Use `/` slash commands for moderation, economy, casino, and tickets.")
    await ctx.send(embed=embed)

# --- RUN ---
bot.run(TOKEN)
