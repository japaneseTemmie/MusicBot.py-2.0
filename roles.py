""" Role helper checks and I/O operations for discord.py bot. """

from settings import *
from iohelpers import *
from helpers import *

async def user_has_role(interaction: Interaction, playlist: bool=False) -> bool:
    """ Check role ownership\n
    If the role is in the guild or in the config file and the user has it, return True.\n
    if none of the above conditions are met, return False. """

    roles = await open_roles(interaction)
    if isinstance(roles, Error):
        await interaction.response.send_message("I cannot verify your roles temporarily.", ephemeral=True) # A corrupted file can be abused to get access, therefore we cannot return True here.
        return False

    role_to_look_for = "playlist" if playlist else "music"
    role_id = roles.get(role_to_look_for, None)

    if not roles or\
        role_id is None:
        return True

    user_roles = interaction.user.roles
    role = discord.utils.get(interaction.guild.roles, id=int(role_id))

    if role in user_roles:
        return True
    
    await interaction.response.send_message(f"You do not have the required **{role_to_look_for}** role to use this command!", ephemeral=True)
    return False

async def open_roles(interaction: Interaction) -> dict | Error:
    """ Safely open a guild's roles file and return content.\n
    Cache the content of a successful read, return cache if already present.
    Returns: file contents or Error. """
    
    if FILE_OPERATIONS_LOCKED_PERMANENTLY.is_set():
        return Error("Role reading temporarily disabled.")
    
    await ensure_lock(interaction, ROLE_LOCKS)
    file_lock = ROLE_LOCKS[interaction.guild.id]

    async with file_lock:
        content = get_cache(ROLE_FILE_CACHE, interaction.guild.id)
        if content:
            return content

        path = join(PATH, "guild_data", str(interaction.guild.id))
        file = join(path, "roles.json")
        
        success = await asyncio.to_thread(ensure_paths, path, file)
        if success == False:
            return Error("Failed to create guild data.")

        content = await asyncio.to_thread(open_file, file, True)
        if content is None:
            return Error("Failed to read role contents.")
    
        store_cache(content, interaction.guild.id, ROLE_FILE_CACHE)

        return content

async def write_roles(interaction: Interaction, content: dict, backup: dict | None) -> bool | Error:
    """ Safely write `content` to a guild's roles file.\n
    Cache new content if successful.\n
    Returns a boolean [True] or Error. """
    
    if FILE_OPERATIONS_LOCKED_PERMANENTLY.is_set():
        return Error("Role writing temporarily disabled.")
    
    await ensure_lock(interaction, ROLE_LOCKS)
    file_lock = ROLE_LOCKS[interaction.guild.id]
    
    async with file_lock:
        path = join(PATH, "guild_data", str(interaction.guild.id))
        file = join(path, "roles.json")

        success = await asyncio.to_thread(ensure_paths, path, file)
        if success == False:
            return Error("Failed to create guild data.")

        result = await asyncio.to_thread(write_file, file, content, True)

        if result == False:
            if backup is not None:
                await asyncio.to_thread(write_file, file, backup, True)

            return Error("Failed to apply changes to roles.")
        
        store_cache(content, interaction.guild.id, ROLE_FILE_CACHE)

        return True