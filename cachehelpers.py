""" Cache helper functions for discord.py bot. """

from settings import *

# Caching tools
def store_cache(content: Any, id: str | int, cache: dict) -> None:
    if content:
        cache[id] = content
    else:
        invalidate_cache(id, cache) # Don't cache empty content

def get_cache(cache: dict, id: str | int) -> Any | None:
    return cache.get(id)
    
def invalidate_cache(id: str | int, cache: dict) -> None:
    cache.pop(id, None)