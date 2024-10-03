import discord
import json
import random
import string
import arrow
from discord.ext import commands, tasks

TOKEN = "YOUR-BOT-TOKEN"  # Replace with your actual bot token

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
    now = arrow.utcnow()  # Get current time in UTC
    time_str = time_str.lower()  # Convert to lowercase for consistency

    if time_str.endswith('s'):
        return now.shift(seconds=int(time_str[:-1]))
    elif time_str.endswith('min'):
        return now.shift(minutes=int(time_str[:-3]))
    elif time_str.endswith('h'):
        return now.shift(hours=int(time_str[:-1]))
    elif time_str.endswith('d'):
        return now.shift(days=int(time_str[:-1]))
    elif time_str.endswith('w'):
        return now.shift(weeks=int(time_str[:-1]))
    elif time_str.endswith('m'):
        return now.shift(months=int(time_str[:-1]))
    elif time_str.endswith('y'):
        return now.shift(years=int(time_str[:-1]))
    elif time_str == 'life':
        return None
    else:
        raise ValueError("Invalid time format. Please use numbers followed by 's', 'min', 'h', 'd', 'w', 'm', or 'y'.")

async def send_keys_page(interaction, keys, page_num):
    """Display paginated keys with a cleaner design."""
    per_page = 150
    total_pages = (len(keys) + per_page - 1) // per_page

    if page_num < 1 or page_num > total_pages:
        page_num = 1

    start_idx = (page_num - 1) * per_page
    end_idx = start_idx + per_page

    keys_list = '\n'.join([f"{i + 1}. {k['key']} | Expires: {format_remaining_time(arrow.get(k['expiration']) if k['expiration'] != 'lifetime' else None)}" for i, k in enumerate(keys[start_idx:end_idx])])

    embed = discord.Embed(
        title=f"🔐 Keys (Page {page_num}/{total_pages})",
        description=keys_list,
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Showing {len(keys[start_idx:end_idx])} of {len(keys)} keys")

    await interaction.response.send_message(embed=embed, ephemeral=True)

def format_remaining_time(expiration):
    """Format the remaining time in a readable way."""
    if expiration is None:
        return "Lifetime"
    remaining = expiration - arrow.utcnow()
    if remaining.total_seconds() <= 0:
        return "Expired"
    hours, remainder = divmod(remaining.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}h {int(minutes)}m {int(seconds)}s remaining"

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
            expiration = arrow.get(entry['expiration']) if entry['expiration'] != "lifetime" else None
            status = "Active" if expiration else "Lifetime"
            remaining = format_remaining_time(expiration) if expiration else "N/A"
            keys_info.append(f"🔑 Key: `{entry['key']}` | Status: {status} | Remaining: {remaining}")

    if not keys_info:
        await interaction.response.send_message("❌ You have no keys.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🔍 Your Key Status",
        description='\n'.join(keys_info),
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tasks.loop(seconds=20)
async def check_expired_keys():
    now = arrow.utcnow()  # Current time in UTC
    for server_id, data in database.items():
        role_id = data['settings'].get('role')
        if role_id:
            guild = bot.get_guild(int(server_id))
            if guild is None:
                print(f"Guild not found for server_id: {server_id}")
                continue  # Skip if guild not found

            role = guild.get_role(role_id)
            if role is None:
                print(f"Role not found for role_id: {role_id}")
                continue  # Skip if role not found

            for entry in data['keys']:
                if entry['expiration'] != "lifetime" and entry['user_id']:
                    expiration_time = arrow.get(entry['expiration'])
                    
                    try:
                        user = await guild.fetch_member(entry['user_id'])  # Fetch member directly
                    except discord.NotFound:
                        print(f"User with ID {entry['user_id']} not found in guild {guild.name}.")
                        continue  # Skip to the next entry
                    except Exception as e:
                        print(f"An error occurred while fetching user: {str(e)}")
                        continue  # Skip to the next entry

                    if now > expiration_time:
                        # Remove the role from the user if they have it
                        if role in user.roles:
                            try:
                                await user.remove_roles(role)
                                await user.send(f"🚫 Your key has expired! The role '{role.name}' has been removed.")
                                print(f"Removed role from {user.name} due to key expiration.")
                            except discord.Forbidden:
                                print(f"Could not remove role or send DM to {user.name}. Check permissions.")
                            except Exception as e:
                                print(f"An error occurred while removing role: {str(e)}")

                        entry['user_id'] = None  # Mark the key as unused
                        save_database(database)
                        print(f"User {user.name}'s key expired and was marked as unused.")
                    else:
                        print(f"Key for {user.name} is still active.")




# Start the bot
bot.run(TOKEN)
