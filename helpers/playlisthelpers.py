""" Playlist helper functions for discord.py bot """

from discord.interactions import Interaction
from typing import Any

# Playlist helpers
async def playlist_exists(content: dict[str, list], playlist_name: str) -> bool:
    """ Checks if a playlist exists in a JSON structure.

    Returns a boolean. """
    
    return playlist_name in content

async def is_playlist_full(item_limit: int, content: dict[str, list], playlist_name: str) -> bool:
    """ Checks if the given playlist is full.

    Returns a boolean. """
    
    playlist = content.get(playlist_name, [])

    if not playlist:
        return False
    
    return len(playlist) >= item_limit

async def is_content_full(limit: int, content: dict[str, list]) -> bool:
    """ Check if the `content` exceeds length `limit`.

    Returns a boolean. """
    
    return len(content) >= limit

async def is_playlist_empty(playlist: list[dict[str, Any]]) -> bool:
    """ Check if a playlist is empty.

    Returns a boolean. """
    
    return len(playlist) < 1

async def has_playlists(content: dict[str, list]) -> bool:
    """ Checks if a JSON structure has any playlists saved.

    Returns a boolean. """

    return len(content) > 0

async def lock_playlist(content: dict[str, list], locked: dict[str, bool], playlist_name: str, force: bool=False) -> None:
    """ Locks a playlist. 
    
    Normally, a playlist only gets locked if it actually exists. Unless `force` is `True`. """

    # Ensure the target playlist exists or a command that creates one is used.
    if await playlist_exists(content, playlist_name) or force:
        locked[playlist_name] = True

async def unlock_playlist(locked: dict[str, bool], content: dict[str, list], playlist_name: str) -> None:
    """ Unlocks a playlist. """

    if playlist_name in locked:
        locked[playlist_name] = False
    
    await cleanup_locked_playlists(content, locked)

async def unlock_all_playlists(locked: dict[str, bool]) -> None:
    """ Unlocks every locked playlist. """
    
    locked.clear()

async def is_playlist_locked(locked: dict[str, bool]) -> bool:
    """ Checks if any playlist is locked in 'locked' parameter.

    Returns a boolean. """
    
    return any(locked.values())

async def cleanup_locked_playlists(content: dict[str, list], locked: dict[str, bool]) -> None:
    """ Cleans up leftover playlists in `locked`. """

    to_remove = [key for key in locked if key not in content]
        
    for key in to_remove:
        del locked[key]
