""" Role helper checks and I/O operations for discord.py bot. """

from settings import PATH, ROLE_LOCKS, ROLE_FILE_CACHE
from error import Error
from helpers import check_file_lock, ensure_lock
from cachehelpers import get_cache, store_cache
from iohelpers import open_file, write_file, ensure_paths

import discord
import asyncio
from discord.interactions import Interaction
from os.path import join

async def user_has_role(interaction: Interaction, playlist: bool=False) -> bool:
    """ Check role ownership.
    
    If the role is in the guild or in the config file and the user has it, return True.
    
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
    """ Safely open a guild's roles file and return content.
    
    Cache the content of a successful read, return cache if already present.
    
    Returns: file contents or Error. """
    
    locked_error = await check_file_lock("Role reading temporarily disabled.")
    if isinstance(locked_error, Error):
        return locked_error
    
    await ensure_lock(interaction, ROLE_LOCKS)
    file_lock = ROLE_LOCKS[interaction.guild.id]

    async with file_lock:
        content = get_cache(ROLE_FILE_CACHE, interaction.guild.id)
        if content:
            return content

        path = join(PATH, "guild_data", str(interaction.guild.id))
        file = join(path, "roles.json")
        
        success = await asyncio.to_thread(ensure_paths, path, "roles.json", {})
        if success == False:
            return Error("Failed to create guild data.")

        content = await asyncio.to_thread(open_file, file, True)
        if content is None:
            return Error("Failed to read role contents.")
    
        store_cache(content, interaction.guild.id, ROLE_FILE_CACHE)

        return content

async def write_roles(interaction: Interaction, content: dict, backup: dict | None) -> bool | Error:
    """ Safely write `content` to a guild's roles file.
    
    Cache new content if successful.
    
    Returns a boolean [True] or Error. """
    
    locked_error = await check_file_lock("Role writing temporarily disabled.")
    if isinstance(locked_error, Error):
        return locked_error
    
    await ensure_lock(interaction, ROLE_LOCKS)
    file_lock = ROLE_LOCKS[interaction.guild.id]
    
    async with file_lock:
        path = join(PATH, "guild_data", str(interaction.guild.id))
        file = join(path, "roles.json")

        success = await asyncio.to_thread(ensure_paths, path, "roles.json", {})
        if success == False:
            return Error("Failed to create guild data.")

        result = await asyncio.to_thread(write_file, file, content, True)

        if result == False:
            if backup is not None:
                await asyncio.to_thread(write_file, file, backup, True)

            return Error("Failed to apply changes to roles.")
        
        store_cache(content, interaction.guild.id, ROLE_FILE_CACHE)

        return True