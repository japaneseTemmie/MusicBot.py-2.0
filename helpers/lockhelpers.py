from settings import VOICE_OPERATIONS_LOCKED, FILE_OPERATIONS_LOCKED
from error import Error

from discord.interactions import Interaction

async def check_vc_lock(reply_to_interaction: bool=False, interaction: Interaction | None=None, msg_on_locked: str | None=None) -> bool | Error:
    """ Check the `VOICE_OPERATIONS_LOCKED` flag.
    
    If True, return an error object or reply to the interaction with `msg_on_locked` or a default message and return False. """
    
    msg = msg_on_locked or "Voice connections temporarily disabled."
    
    if VOICE_OPERATIONS_LOCKED.is_set():
        if reply_to_interaction and interaction is not None:
            await interaction.response.send_message(msg) if not interaction.response.is_done() else\
            await interaction.followup.send(msg)
            return False
        else:
            return Error(msg)
    
    return True

async def check_file_lock(reply_to_interaction: bool=False, interaction: Interaction | None=None, msg_on_locked: str | None=None) -> bool | Error:
    """ Check the `FILE_OPERATIONS_LOCKED` flag.
    
    If True, return an error object or reply to an interaction with `msg_on_locked` or a default entry and return False. """
    
    msg = msg_on_locked or "Role/Playlist reading temporarily disabled."
    
    if FILE_OPERATIONS_LOCKED.is_set():
        if reply_to_interaction and interaction is not None:
            await interaction.response.send_message(msg) if not interaction.response.is_done() else\
            await interaction.followup.send(msg)
            return False
        else:
            return Error(msg)
        
    return True

async def get_vc_lock() -> bool:
    """ Return the raw value of the voice lock state """

    return VOICE_OPERATIONS_LOCKED.is_set()

async def get_file_lock() -> bool:
    """ Return the raw value of the file lock state """

    return FILE_OPERATIONS_LOCKED.is_set()

async def set_global_locks(voice: bool | None=None, file_ops: bool | None=None) -> None:
    """ Set voice or file global locks depending on given flags. 
    
    A value of `None` will not modify the current lock state. """

    if voice is not None:
        if voice:
            VOICE_OPERATIONS_LOCKED.set()
        else:
            VOICE_OPERATIONS_LOCKED.clear()

    if file_ops is not None:
        if file_ops:
            FILE_OPERATIONS_LOCKED.set()
        else:
            FILE_OPERATIONS_LOCKED.clear()
