""" Playlist helpers for discord.py bot """

from typing import Any

# Playlist helpers
def playlist_exists(content: dict[str, list], playlist_name: str) -> bool:
    """ Check if a playlist exists in a JSON playlist structure.

    Return a boolean. """
    
    return playlist_name in content

def is_playlist_full(item_limit: int, content: dict[str, list], playlist_name: str) -> bool:
    """ Check if the given playlist is full.

    If playlist does not exist, return False.

    Return a boolean. """
    
    playlist = content.get(playlist_name, [])

    if not playlist:
        return False
    
    return len(playlist) >= item_limit

def is_content_full(limit: int, content: dict[str, list]) -> bool:
    """ Check if the `content` playlist structure exceeds length `limit`.

    Return a boolean. """
    
    return len(content) >= limit

def is_playlist_empty(playlist: list[dict[str, Any]]) -> bool:
    """ Check if a playlist is empty.

    Return a boolean. """
    
    return len(playlist) < 1

def has_playlists(content: dict[str, list]) -> bool:
    """ Check if a JSON playlist structure has any playlists saved.

    Return a boolean. """

    return len(content) > 0
