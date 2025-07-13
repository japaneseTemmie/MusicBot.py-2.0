""" Role helper checks and I/O operations for discord.py bot """

from settings import *
from iohelpers import open_file, write_file, ensure_paths
from helpers import ensure_lock, store_cache, get_cache

async def user_has_role(interaction: Interaction, playlist: bool=False) -> bool:
    """ Check role ownership """
    """ If the role isn't in the guild or not in the config file or the user has it, allow command execution.
    if none of the below conditions are met, return False. (Role exists in config file and in guild but
    user does not have it.) """

    roles = await open_roles(interaction)
    if roles == RETURN_CODES["READ_FAIL"]:
        return True

    role_to_look_for = "playlist" if playlist else "music"
    role_id = roles.get(role_to_look_for, None)

    if not roles or\
        role_id is None:
        return True

    user_roles = interaction.user.roles
    role = discord.utils.get(interaction.guild.roles, id=int(role_id))

    if role in user_roles:
        return True
    
    await interaction.response.send_message(f"You do not have the required **{role_to_look_for}** role to use this command!")
    return False

async def open_roles(interaction: Interaction) -> int | dict:
    """ Open the roles.json file safely. Return cache if content is cached, cache the content if not. """
    
    if FILE_OPERATIONS_LOCKED_PERMANENTLY.is_set():
        return RETURN_CODES["READ_FAIL"]
    
    content = get_cache(ROLE_FILE_CACHE, interaction.guild.id)
    if content:
        return content

    await ensure_lock(interaction, ROLE_LOCKS)
    file_lock = ROLE_LOCKS[interaction.guild.id]

    async with file_lock:
        path = join(PATH, "guild_data", str(interaction.guild.id))
        file = join(path, "roles.json")
        
        success = await asyncio.to_thread(ensure_paths, path, file)
        if success == RETURN_CODES["WRITE_FAIL"]:
            return RETURN_CODES["READ_FAIL"]

        content = await asyncio.to_thread(open_file, file, True)
        if content == RETURN_CODES["READ_FAIL"]:
            return RETURN_CODES["READ_FAIL"]
    
        store_cache(content, interaction.guild.id, ROLE_FILE_CACHE)

        return content

async def write_roles(interaction: Interaction, content: dict, backup: dict | None) -> int:
    """ Write content to roles.json. Cache new content if successful. """
    
    if VOICE_OPERATIONS_LOCKED_PERMANENTLY.is_set():
        return RETURN_CODES["WRITE_FAIL"]
    
    await ensure_lock(interaction, ROLE_LOCKS)
    file_lock = ROLE_LOCKS[interaction.guild.id]
    
    async with file_lock:
        path = join(PATH, "guild_data", str(interaction.guild.id))
        file = join(path, "roles.json")

        success = await asyncio.to_thread(ensure_paths, path, file)
        if success == RETURN_CODES["WRITE_FAIL"]:
            return RETURN_CODES["WRITE_FAIL"]

        result = await asyncio.to_thread(write_file, file, content, True)

        if result == RETURN_CODES["WRITE_FAIL"]:
            if backup is not None:
                await asyncio.to_thread(write_file, file, backup, True)

            return RETURN_CODES["WRITE_FAIL"]
        
        store_cache(content, interaction.guild.id, ROLE_FILE_CACHE)

        return RETURN_CODES["WRITE_SUCCESS"]
