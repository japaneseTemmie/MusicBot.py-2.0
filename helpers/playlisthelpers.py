""" Playlist helper functions for discord.py bot """

from error import Error
from helpers.queuehelpers import sanitize_name

from discord.interactions import Interaction

# Playlist helpers
async def playlist_exists(content: dict, playlist_name: str) -> bool:
    """ Checks if a playlist exists in a JSON structure.

    Returns a boolean. """
    
    return playlist_name in content

async def is_playlist_full(item_limit: int, content: dict | Error, playlist_name: str) -> bool:
    """ Checks if the given playlist is full.

    Returns a boolean. """
    
    if isinstance(content, Error):
        return False # go to error handler
    
    playlist = content.get(playlist_name, [])

    if not playlist:
        return False
    
    return len(playlist) >= item_limit

async def is_content_full(limit: int, content: dict | Error) -> bool:
    """ Check if the `content` exceeds length `limit`.

    Returns a boolean. """
    
    if isinstance(content, Error):
        return False
    
    return len(content) >= limit

async def is_playlist_empty(playlist: list[dict]) -> bool:
    """ Check if a playlist is empty.

    Returns a boolean. """
    
    return len(playlist) < 1

async def has_playlists(content: dict) -> bool:
    """ Checks if a JSON structure has any playlists saved.

    Returns a boolean. """

    return len(content) > 0

async def lock_playlist(interaction: Interaction, content: dict | Error, locked: dict, playlist_name: str) -> None:
    """ Locks a playlist.
     
    Does nothing if `content` is invalid. """
    
    if isinstance(content, Error):
        return
    
    playlist_name = await sanitize_name(playlist_name)

    # Ensure the target playlist exists or a command that creates one is used.
    if  (await playlist_exists(content, playlist_name) or\
            interaction.command.name in ("playlist-save", "playlist-save-current", "playlist-add-yt-playlist", "playlist-add", "playlist-create")):
        locked[playlist_name] = True

async def unlock_playlist(locked: dict, content: dict | Error, playlist_name: str) -> None:
    """ Unlocks a playlist. """
    
    playlist_name = await sanitize_name(playlist_name)
    if playlist_name in locked:
        locked[playlist_name] = False
    
    await cleanup_locked_playlists(content, locked)

async def unlock_all_playlists(locked: dict) -> None:
    """ Unlocks every locked playlist. """
    
    locked.clear()

async def is_playlist_locked(locked: dict) -> bool:
    """ Checks if any playlist is locked in 'locked' parameter.

    Returns a boolean. """
    
    return any(locked.values())

async def cleanup_locked_playlists(content: dict | Error, locked: dict) -> None:
    """ Cleans up leftover playlists in `locked`.
     
    Does nothing if `content` is invalid. """
    
    if isinstance(content, Error):
        return

    to_remove = [key for key in locked if key not in content]
        
    for key in to_remove:
        del locked[key]
