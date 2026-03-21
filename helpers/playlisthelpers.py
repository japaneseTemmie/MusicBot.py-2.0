""" Playlist helper functions for discord.py bot """

from discord.interactions import Interaction
from typing import Any

# Playlist helpers
def playlist_exists(content: dict[str, list], playlist_name: str) -> bool:
    """ Checks if a playlist exists in a JSON structure.

    Returns a boolean. """
    
    return playlist_name in content

def is_playlist_full(item_limit: int, content: dict[str, list], playlist_name: str) -> bool:
    """ Checks if the given playlist is full.

    Returns a boolean. """
    
    playlist = content.get(playlist_name, [])

    if not playlist:
        return False
    
    return len(playlist) >= item_limit

def is_content_full(limit: int, content: dict[str, list]) -> bool:
    """ Check if the `content` exceeds length `limit`.

    Returns a boolean. """
    
    return len(content) >= limit

def is_playlist_empty(playlist: list[dict[str, Any]]) -> bool:
    """ Check if a playlist is empty.

    Returns a boolean. """
    
    return len(playlist) < 1

def has_playlists(content: dict[str, list]) -> bool:
    """ Checks if a JSON structure has any playlists saved.

    Returns a boolean. """

    return len(content) > 0
