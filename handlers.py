""" Error handlers for discord.py bot """

from settings import *

# Error handlers
def check_playlist_name_length_in_string(name: str, string: str):
    clean_string = string
    if len(string) > 2000:
        clean_string = string.replace(name, f"{name[:20]}...  ")

    return clean_string

async def handle_generic_playlist_errors(interaction: Interaction,code: int | tuple,playlist_name: str='',playlist_limit: int=5,playlist_item_limit:int=100) -> bool:
    """ Handler for generic playlist errors.\n
    If `code` is a tuple, the return code must be at index 0. """
    
    msgs = {
        RETURN_CODES["READ_FAIL"]: "Failed to read playlist contents.",
        RETURN_CODES["NO_PLAYLISTS"]: "This guild does not have any saved playlists.",
        RETURN_CODES["PLAYLIST_DOES_NOT_EXIST"]: f"Could not find playlist **{playlist_name}**.",
        RETURN_CODES["PLAYLIST_IS_EMPTY"]: f"Playlist **{playlist_name}** is empty.",
        RETURN_CODES["MAX_PLAYLIST_LIMIT_REACHED"]: f"Maximum playlist limit of **{playlist_limit}** reached, please remove a playlist to free a slot.",
        RETURN_CODES["PLAYLIST_EXISTS"]: f"Playlist **{playlist_name}** already exists.",
        RETURN_CODES["WRITE_FAIL"]: "Failed to update playlist contents.",
        RETURN_CODES["NOT_FOUND"]: f"Could not find track(s) in playlist **{playlist_name}**.",
        RETURN_CODES["NOT_A_NUMBER"]: f"Index is not an integer number.",
        RETURN_CODES["INVALID_RANGE"]: f"Invalid `start_range` or `end_range`.",
        RETURN_CODES["SAME_INDEX_PLACEMENT"]: "Cannot place track because it already exists at the specified index.",
        RETURN_CODES["PLAYLIST_IS_FULL"]: f"Playlist **{playlist_name}** has reached the **{playlist_item_limit}** track limit!"
    }

    msg = msgs.get(code if isinstance(code, int) else code[0])
    if msg is not None:
        msg = check_playlist_name_length_in_string(playlist_name, msg)
        
        await interaction.followup.send(msg) if interaction.response.is_done() else\
        await interaction.response.send_message(msg)
        return False
    
    return True

async def handle_generic_extraction_errors(interaction: Interaction, code: int | tuple):
    """ Handler for generic extraction errors.\n
    If code is a tuple, the return code must be at index 0 and the query that failed (as string) must be at index 1."""
    
    msgs = {
        RETURN_CODES["BAD_EXTRACTION"]: f"An error occured while extracting query{f' `{code[1]}`' if isinstance(code, tuple) else ''}.",
        RETURN_CODES["QUERY_NOT_SUPPORTED"]: f"This command does not support {'that query type.' if not isinstance(code, tuple) else f'query type `{code[1]}`'}",
        RETURN_CODES["QUERY_IS_EMPTY"]: f"Query cannot be empty."
    }
    
    msg = msgs.get(code if isinstance(code, int) else code[0])
    if msg is not None:
        await interaction.followup.send(msg) if interaction.response.is_done() else\
        await interaction.response.send_message(msg)
        return False
    
    return True

async def handle_rename_error(interaction: Interaction, code: int, new_name: str, max_rename_length: int):
    """ Error handler for NAME_TOO_LONG error code. """
    
    msgs = {
        RETURN_CODES["NAME_TOO_LONG"]: f"Name **`{new_name[:950]}`** is too long. Must be < **{max_rename_length}** characters.",
        RETURN_CODES["SAME_NAME_RENAME"]: f"Cannot rename a playlist to the same name."
    }

    msg = msgs.get(code, None)
    if msg is not None:
        await interaction.followup.send(msg) if interaction.response.is_done() else\
        await interaction.response.send_message(msg)
        return False
    
    return True

async def handle_reposition_error(interaction: Interaction, code: int):
    """ Error handler for SAME_INDEX_REPOSITION return code. """
    
    if code == RETURN_CODES["SAME_INDEX_REPOSITION"]:
        await interaction.followup.send("Cannot reposition track to the same index.") if interaction.response.is_done() else\
        await interaction.response.send_message("Cannot reposition track to the same index.")
        return False
    
    return True

async def handle_not_found_error(interaction: Interaction, code: int):
    """ Error handler for NOT_FOUND and NOT_A_NUMBER return code. """
    
    msgs = {
        RETURN_CODES["NOT_FOUND"]: "Could not find track(s) in queue.",
        RETURN_CODES["NOT_A_NUMBER"]: "Index is not an integer number."
    }

    msg = msgs.get(code, None)
    if msg is not None:
        await interaction.followup.send(msg) if interaction.response.is_done() else\
        await interaction.response.send_message(msg)
        return False
    
    return True

async def handle_get_previous_error(interaction: Interaction, code: int):
    """ Error handler for previousinfo command. """
    
    msgs = {
        RETURN_CODES["HISTORY_IS_EMPTY"]: "Track history is empty. Nothing to show.",
        RETURN_CODES["NOT_ENOUGH_TRACKS"]: "There's no previous track to show."
    }

    msg = msgs.get(code, None)
    if msg is not None:
        await interaction.followup.send(msg) if interaction.response.is_done() else\
        await interaction.response.send_message(msg)

        return False
    
    return True

async def handle_get_next_error(interaction: Interaction, code: int):
    msgs = {
        RETURN_CODES["NEXT_IS_RANDOM"]: "Next track will be random.",
        RETURN_CODES["QUEUE_IS_EMPTY"]: "Queue is empty. Nothing to preview."
    }

    msg = msgs.get(code, None)
    if msg is not None:
        await interaction.followup.send(msg) if interaction.response.is_done() else\
        await interaction.response.send_message(msg)
        
        return False
    
    return True

async def handle_load_error(cog: commands.Cog, error: Exception) -> None:
    """ Error handler for load_cog() in case it makes a smol fucky wucky """
    
    name = cog.__class__.__name__
    if isinstance(error, TypeError):
        log(f"Failed to load cog {name}:\nInvalid object.")
    elif isinstance(error, discord.ClientException):
        log(f"Failed to load cog {name}:\nAlready loaded.")
    elif isinstance(error, commands.CommandError):
        log(f"Failed to load cog {name}:\nAn error occured while loading the cog.")
    else:
        log(f"Failed to load cog {name}:\nUnknown error.")

    if CAN_LOG and LOGGER is not None:
        LOGGER.exception(error)

async def handle_sync_error(error: Exception) -> None:
    if isinstance(error, discord.errors.HTTPException):
        log(f"Failed to sync application commands:\nAPI error.")
    elif isinstance(error, app_commands.errors.CommandSyncFailure):
        log(f"Failed to sync application commands:\nInvalid command data.")
    elif isinstance(error, discord.errors.Forbidden):
        log(f"Failed to sync application commands:\nMissing app command scope.")
    elif isinstance(error, app_commands.errors.MissingApplicationID):
        log(f"Failed to sync application commands:\nMissing Application ID.")
    else:
        log(f"Failed to sync application commands:\nUnknown error.")

    if CAN_LOG and LOGGER is not None:
        LOGGER.exception(error)

async def handle_moderation_command_error(interaction: Interaction, error: Exception):
    if isinstance(error, app_commands.errors.BotMissingPermissions):
        await interaction.response.send_message("I don't have the necessary permissions to perform that operation!", ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send("I don't have the necessary permissions to perform that operation!")
        return
    elif isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("You don't have the necessary permissions to perform that operation!", ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send("You don't have the necessary permissions to perform that operation!")
        return
    elif isinstance(error, app_commands.errors.CommandOnCooldown):
        await interaction.response.send_message(str(error), ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send(str(error))
        return
    
    if isinstance(error, app_commands.errors.CommandInvokeError):
        if isinstance(error.original, discord.errors.Forbidden):
            await interaction.response.send_message("I'm unable to do that!", ephemeral=True) if not interaction.response.is_done() else\
            await interaction.followup.send("I'm unable to do that!")
        elif isinstance(error.original, discord.errors.HTTPException):
            await interaction.response.send_message("Something went wrong while requesting changes.", ephemeral=True) if not interaction.response.is_done() else\
            await interaction.followup.send("Something went wrong while requesting changes.")

        return

    if CAN_LOG and LOGGER is not None:
        LOGGER.exception(error)

    await interaction.response.send_message(f"An error occurred.", ephemeral=True) if not interaction.response.is_done() else\
    await interaction.followup.send("An error occured.")