import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View
import random
import time
import json
import os

# --- CONFIG ---
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    print("❌ DISCORD_TOKEN not found in environment variables.")
    exit()

DATA_FILE = "data.json"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- STORAGE ---
settings = {"logs": {}, "welcome": {}, "goodbye": {}}
balances = {}
daily_claims = {}

DAILY_AMOUNT = 100
START_BALANCE = 100

# --- JSON PERSISTENCE ---
def load_data():
    global balances, daily_claims, settings
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            balances.update({int(k): v for k, v in data.get("balances", {}).items()})
            daily_claims.update({int(k): v for k, v in data.get("daily_claims", {}).items()})
            settings.update(data.get("settings", {}))
            print("💾 Data loaded")
    except FileNotFoundError:
        print("⚠️ Data file not found, starting fresh.")
    except Exception as e:
        print(f"⚠️ Error loading data: {e}")

def save_data():
    try:
        data = {"balances": balances, "daily_claims": daily_claims, "settings": settings}
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"⚠️ Error saving data: {e}")

# Auto-save every 60 seconds
@tasks.loop(seconds=60)
async def autosave():
    save_data()

# --- ECONOMY HELPERS ---
def get_balance(user_id: int) -> int:
    return balances.get(user_id, START_BALANCE)

def set_balance(user_id: int, amount: int):
    balances[user_id] = max(0, amount)
    save_data()  # save on update

def add_balance(user_id: int, amount: int):
    set_balance(user_id, get_balance(user_id) + amount)

# --- LOG HELPER ---
async def send_log(guild: discord.Guild, embed: discord.Embed):
    channel_id = settings["logs"].get(str(guild.id))
    if not channel_id:
        return
    channel = guild.get_channel(channel_id)
    if channel:
        await channel.send(embed=embed)

# --- MODERATION COMMANDS ---
@bot.tree.command(description="Ban a member")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"🔨 Banned {member.mention}")

@bot.tree.command(description="Unban a user by ID")
@app_commands.default_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str):
    user = await bot.fetch_user(int(user_id))
    await interaction.guild.unban(user)
    await interaction.response.send_message(f"✅ Unbanned {user}")

@bot.tree.command(description="Kick a member")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 Kicked {member.mention}")

@bot.tree.command(description="Timeout (mute) a member for seconds")
@app_commands.default_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member, seconds: int, reason: str = None):
    until = discord.utils.utcnow() + discord.timedelta(seconds=seconds)
    await member.timeout(until, reason=reason)
    await interaction.response.send_message(f"🔇 Muted {member.mention} for {seconds}s")

@bot.tree.command(description="Remove timeout (unmute)")
@app_commands.default_permissions(moderate_members=True)
async def unmute(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None)
    await interaction.response.send_message(f"⏱️ Unmuted {member.mention}")

@bot.tree.command(description="Delete last N messages")
@app_commands.default_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 Deleted {len(deleted)} messages", ephemeral=True)

@bot.tree.command(description="Set channel slowmode in seconds")
@app_commands.default_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, seconds: int):
    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.response.send_message(f"🐢 Slowmode set to {seconds}s")

@bot.tree.command(description="Lock or unlock this channel")
@app_commands.default_permissions(manage_channels=True)
async def lockdown(interaction: discord.Interaction, enable: bool):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = None if not enable else False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message("🔒 Locked" if enable else "🔓 Unlocked")

# --- CHANNEL CONFIG ---
@bot.tree.command(description="Set a log channel")
@app_commands.default_permissions(administrator=True)
async def setlog(interaction: discord.Interaction, channel: discord.TextChannel):
    settings["logs"][str(interaction.guild.id)] = channel.id
    save_data()
    await interaction.response.send_message(f"📝 Log channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(description="Set a welcome channel")
@app_commands.default_permissions(administrator=True)
async def setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    settings["welcome"][str(interaction.guild.id)] = channel.id
    save_data()
    await interaction.response.send_message(f"👋 Welcome channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(description="Set a goodbye channel")
@app_commands.default_permissions(administrator=True)
async def setgoodbye(interaction: discord.Interaction, channel: discord.TextChannel):
    settings["goodbye"][str(interaction.guild.id)] = channel.id
    save_data()
    await interaction.response.send_message(f"👋 Goodbye channel set to {channel.mention}", ephemeral=True)

# --- LOG EVENTS ---
@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild or message.author.bot: return
    embed = discord.Embed(title="Message Deleted", color=discord.Color.red())
    embed.add_field(name="User", value=message.author.mention, inline=False)
    embed.add_field(name="Channel", value=message.channel.mention, inline=False)
    embed.add_field(name="Content", value=message.content or "*empty*", inline=False)
    await send_log(message.guild, embed)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if not before.guild or before.author.bot or before.content==after.content: return
    embed = discord.Embed(title="Message Edited", color=discord.Color.orange())
    embed.add_field(name="User", value=before.author.mention, inline=False)
    embed.add_field(name="Channel", value=before.channel.mention, inline=False)
    embed.add_field(name="Before", value=before.content or "*empty*", inline=False)
    embed.add_field(name="After", value=after.content or "*empty*", inline=False)
    await send_log(before.guild, embed)

@bot.event
async def on_member_join(member: discord.Member):
    cid = settings["welcome"].get(str(member.guild.id))
    if cid:
        channel = member.guild.get_channel(cid)
        if channel: await channel.send(f"👋 Welcome {member.mention} to **{member.guild.name}**!")
    embed = discord.Embed(title="Member Joined", description=member.mention, color=discord.Color.green())
    await send_log(member.guild, embed)

@bot.event
async def on_member_remove(member: discord.Member):
    cid = settings["goodbye"].get(str(member.guild.id))
    if cid:
        channel = member.guild.get_channel(cid)
        if channel: await channel.send(f"😢 {member.mention} has left **{member.guild.name}**.")
    embed = discord.Embed(title="Member Left", description=member.mention, color=discord.Color.red())
    await send_log(member.guild, embed)

# --- NICKNAME / SAY / ROLE ---
@bot.tree.command(description="Change a member's nickname")
@app_commands.default_permissions(manage_nicknames=True)
async def nick(interaction: discord.Interaction, member: discord.Member, new_nick: str):
    old = member.nick or member.name
    await member.edit(nick=new_nick)
    await interaction.response.send_message(f"✏️ Changed nickname from **{old}** to **{new_nick}**")

@bot.tree.command(description="Make the bot say something")
async def say(interaction: discord.Interaction, *, message: str):
    await interaction.response.send_message(message)

@bot.tree.command(description="Add a role to a member")
@app_commands.default_permissions(manage_roles=True)
async def addrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.add_roles(role)
    await interaction.response.send_message(f"➕ Added role {role.mention} to {member.mention}")

@bot.tree.command(description="Remove a role from a member")
@app_commands.default_permissions(manage_roles=True)
async def removerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.remove_roles(role)
    await interaction.response.send_message(f"➖ Removed role {role.mention} from {member.mention}")

# --- ECONOMY ---
@bot.tree.command(description="Check your balance")
async def balance(interaction: discord.Interaction):
    await interaction.response.send_message(f"💰 {interaction.user.mention}, you have **${get_balance(interaction.user.id)}**")

@bot.tree.command(description="Add cash to a user (admin)")
@app_commands.default_permissions(administrator=True)
async def addcash(interaction: discord.Interaction, member: discord.Member, amount: int):
    add_balance(member.id, amount)
    await interaction.response.send_message(f"✅ Added ${amount} to {member.mention}. Balance: ${get_balance(member.id)}")

@bot.tree.command(description="Remove cash from a user (admin)")
@app_commands.default_permissions(administrator=True)
async def removecash(interaction: discord.Interaction, member: discord.Member, amount: int):
    set_balance(member.id, get_balance(member.id)-amount)
    await interaction.response.send_message(f"❌ Removed ${amount} from {member.mention}. Balance: ${get_balance(member.id)}")

@bot.tree.command(description="Claim daily reward")
async def daily(interaction: discord.Interaction):
    uid = interaction.user.id
    now = time.time()
    last = daily_claims.get(uid,0)
    if now - last < 24*60*60:
        remain = 24*60*60 - (now-last)
        h,m,s = int(remain//3600),int((remain%3600)//60),int(remain%60)
        await interaction.response.send_message(f"⏳ Already claimed. Come back in {h}h {m}m {s}s.")
        return
    add_balance(uid, DAILY_AMOUNT)
    daily_claims[uid]=now
    save_data()
    await interaction.response.send_message(f"🎉 Claimed daily reward ${DAILY_AMOUNT}! 💰 New Balance: ${get_balance(uid)}")

# --- INTERACTIVE BLACKJACK ---
@bot.tree.command(description="Play Blackjack interactively")
async def blackjack(interaction: discord.Interaction, bet: int):
    uid = interaction.user.id
    balance = get_balance(uid)
    if bet <=0: await interaction.response.send_message("❌ Bet must be positive."); return
    if bet>balance: await interaction.response.send_message("❌ Not enough cash!"); return

    def draw_card(): return random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11])
    def hand_value(hand):
        total = sum(hand); aces = hand.count(11)
        while total>21 and aces: total-=10; aces-=1
        return total

    player, dealer = [draw_card(), draw_card()], [draw_card(), draw_card()]

    class BJView(View):
        def __init__(self):
            super().__init__()
            self.stopped=False

        async def interaction_check(self, interaction2: discord.Interaction) -> bool:
            if interaction2.user.id != uid:
                await interaction2.response.send_message("❌ This is not your game!", ephemeral=True)
                return False
            return True

        async def update(self, msg):
            await msg.edit(content=f"🃏 **Blackjack**\nYour hand: {player} (total {hand_value(player)})\nDealer shows: {dealer[0]} ?", view=self)

        @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
        async def hit(self, i: discord.Interaction, b: Button):
            player.append(draw_card())
            if hand_value(player)>21: self.stopped=True; await self.finish_game(i)
            else: await self.update(message)

        @discord.ui.button(label="Stand", style=discord.ButtonStyle.gray)
        async def stand(self, i: discord.Interaction, b: Button):
            self.stopped=True; await self.finish_game(i)

        async def finish_game(self,i):
            while hand_value(dealer)<17: dealer.append(draw_card())
            ptot, dtot = hand_value(player), hand_value(dealer)
            if ptot>21: set_balance(uid,balance-bet); result=f"💥 Busted! You lose ${bet}."
            elif dtot>21 or ptot>dtot: set_balance(uid,balance+bet); result=f"🎉 You win! {ptot} vs {dtot}. Gain ${bet}."
            elif ptot<dtot: set_balance(uid,balance-bet); result=f"😢 You lose. {ptot} vs {dtot}. Lose ${bet}."
            else: result=f"🤝 Tie! {ptot} vs {dtot}. No cash lost."
            save_data()
            await i.response.edit_message(
                content=f"🃏 **Blackjack Finished**\nYour hand: {player} (total {ptot})\nDealer hand: {dealer} (total {dtot})\n\n{result}\n💰 New Balance: ${get_balance(uid)}",
                view=None
            )

    view = BJView()
    message = await interaction.response.send_message(f"🃏 **Blackjack**\nYour hand: {player} (total {hand_value(player)})\nDealer shows: {dealer[0]} ?", view=view)

# --- DYNAMIC !CMDS ---
@bot.command(name="cmds")
async def cmds(ctx: commands.Context):
    cmds_list = "**Slash Commands:**\n"
    for cmd in bot.tree.walk_commands():
        cmds_list += f"/{cmd.name} - {cmd.description}\n"
    await ctx.send(cmds_list)

# --- STARTUP ---
@bot.event
async def on_ready():
    load_data()
    autosave.start()
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")

@bot.event
async def on_disconnect():
    save_data()

bot.run(TOKEN)
