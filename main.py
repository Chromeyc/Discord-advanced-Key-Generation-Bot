import discord
import json
import random
import string
from datetime import datetime, timedelta
from discord.ext import commands, tasks
from discord import app_commands

TOKEN = "YOUR-BOT-TOKEN-HERE"


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


try:
    with open('Database.json', 'r') as f:
        database = json.load(f)
except FileNotFoundError:
    database = {}

def save_database(db):
    """Save the database to a JSON file."""
    with open('Database.json', 'w') as f:
        json.dump(db, f, indent=4)

def is_admin(interaction):
    """Check if user is an admin or the server owner."""
    return interaction.user.guild_permissions.administrator or interaction.user == interaction.guild.owner

def generate_key():
    """Generate a random key."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

def get_expiration_time(time_str):
    """Calculate expiration time."""
    now = datetime.utcnow()
    if time_str.endswith('d'):
        return now + timedelta(days=int(time_str[:-1]))
    elif time_str.endswith('w'):
        return now + timedelta(weeks=int(time_str[:-1]))
    elif time_str.endswith('m'):
        return now + timedelta(days=int(time_str[:-1]) * 30)
    elif time_str.endswith('y'):
        return now + timedelta(days=int(time_str[:-1]) * 365)
    elif time_str == 'life':
        return None
    else:
        raise ValueError("Invalid time format.")

async def send_keys_page(interaction, keys, page_num):
    """Display paginated keys with a cleaner design."""
    per_page = 150
    total_pages = (len(keys) + per_page - 1) // per_page


    if page_num < 1 or page_num > total_pages:
        page_num = 1

    start_idx = (page_num - 1) * per_page
    end_idx = start_idx + per_page


    keys_list = '\n'.join([f"{i + 1}. {k['key']}" for i, k in enumerate(keys[start_idx:end_idx])])

    embed = discord.Embed(
        title=f"🔐 Keys (Page {page_num}/{total_pages})",
        description=keys_list,
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Showing {len(keys[start_idx:end_idx])} of {len(keys)} keys")

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_ready():
    await bot.tree.sync()  
    check_expired_keys.start()
    print(f"Bot is ready and logged in as {bot.user}")

@bot.tree.command(name="createkeys", description="Generate keys (Admin/Owner only)")
async def create_keys(interaction: discord.Interaction, amount: int, time: str):
    if not is_admin(interaction):
        await interaction.response.send_message("🚫 You do not have permission to use this command.", ephemeral=True)
        return

    server_id = str(interaction.guild.id)
    if server_id not in database:
        database[server_id] = {'keys': [], 'settings': {}}

    new_keys = []
    for _ in range(amount):
        key = generate_key()
        expiration = get_expiration_time(time)
        database[server_id]['keys'].append({
            'key': key,
            'expiration': str(expiration) if expiration else "lifetime",
            'user_id': None
        })
        new_keys.append(key)

    save_database(database)

    keys_list = '\n'.join([f"{key}" for key in new_keys]) 
    embed = discord.Embed(
        title="🎉 Keys Generated",
        description=keys_list,
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"{amount} keys created")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="viewkeys", description="View all keys (Admin/Owner only)")
async def view_keys(interaction: discord.Interaction, page: int = 1):
    if not is_admin(interaction):
        await interaction.response.send_message("🚫 You do not have permission to view keys.", ephemeral=True)
        return

    server_id = str(interaction.guild.id)
    if server_id not in database or not database[server_id]['keys']:
        await interaction.response.send_message("❌ No keys found for this server.", ephemeral=True)
        return

    await send_keys_page(interaction, database[server_id]['keys'], page)

@bot.tree.command(name="redeem", description="Redeem a key")
async def redeem_key(interaction: discord.Interaction, key: str):
    server_id = str(interaction.guild.id)
    if server_id not in database:
        await interaction.response.send_message("❌ No keys available for this server.", ephemeral=True)
        return

    for entry in database[server_id]['keys']:
        if entry['key'] == key and entry['user_id'] is None:
            entry['user_id'] = interaction.user.id
            save_database(database)

            
            role_id = database[server_id]['settings'].get('role')
            if role_id:
                role = interaction.guild.get_role(role_id)
                if role:
                    await interaction.user.add_roles(role)

            await interaction.response.send_message("✅ Key redeemed successfully! You have been assigned the role.", ephemeral=True)
            return

    await interaction.response.send_message("❌ Invalid or already redeemed key.", ephemeral=True)

@bot.tree.command(name="setup", description="Set the role for key redemption (Admin/Owner only)")
async def setup_role(interaction: discord.Interaction, role: discord.Role):
    if not is_admin(interaction):
        await interaction.response.send_message("🚫 You do not have permission to set up this role.", ephemeral=True)
        return

    server_id = str(interaction.guild.id)
    if server_id not in database:
        database[server_id] = {'keys': [], 'settings': {}}

    database[server_id]['settings']['role'] = role.id
    save_database(database)

    await interaction.response.send_message(f"✅ Role {role.name} has been set for key redemption.", ephemeral=True)

@bot.tree.command(name="info", description="Check your key status")
async def info_key(interaction: discord.Interaction):
    server_id = str(interaction.guild.id)
    if server_id not in database:
        await interaction.response.send_message("❌ No keys available for this server.", ephemeral=True)
        return

    keys_info = []
    for entry in database[server_id]['keys']:
        if entry['user_id'] == interaction.user.id:
            status = "Active" if entry['expiration'] != "lifetime" else "Lifetime"
            expiration = entry['expiration'] if status == "Active" else "N/A"
            keys_info.append(f"🔑 Key: `{entry['key']}` | Status: {status} | Expires: {expiration}")

    if not keys_info:
        await interaction.response.send_message("❌ You have no keys.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🔍 Your Key Status",
        description='\n'.join(keys_info),
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tasks.loop(minutes=1)
async def check_expired_keys():
    now = datetime.utcnow()
    for server_id, data in database.items():
        role_id = data['settings'].get('role')
        if role_id:
            guild = bot.get_guild(int(server_id))
            role = guild.get_role(role_id)
            for entry in data['keys']:
                if entry['expiration'] != "lifetime" and entry['user_id']:
                    expiration_time = datetime.strptime(entry['expiration'], '%Y-%m-%d %H:%M:%S.%f')
                    if now > expiration_time:
                        user = guild.get_member(entry['user_id'])
                        if user and role in user.roles:
                            await user.remove_roles(role)
                            print(f"Removed role from {user.name} due to key expiration.")
                            entry['user_id'] = None
                            save_database(database)

bot.run(TOKEN)
