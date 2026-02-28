""" Cache helper functions for discord.py bot. """

from typing import Any, Hashable

# Caching tools
def store_cache(content: Any, id: Hashable, cache: dict) -> None:
    if content:
        cache[id] = content
    else:
        invalidate_cache(id, cache) # Don't cache empty content

def get_cache(cache: dict, id: Hashable) -> Any | None:
    return cache.get(id)
    
def invalidate_cache(id: Hashable, cache: dict) -> None:
    cache.pop(id, None)