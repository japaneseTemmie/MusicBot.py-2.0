""" Cache helpers for discord.py bot. """

from typing import Any, Hashable

# Caching tools
def store_cache(content: Any, identifier: Hashable, cache: dict) -> None:
    if content:
        cache[identifier] = content
    else:
        invalidate_cache(identifier, cache) # Don't cache empty content

def get_cache(cache: dict, identifier: Hashable) -> Any | None:
    return cache.get(identifier)
    
def invalidate_cache(identifier: Hashable, cache: dict) -> None:
    cache.pop(identifier, None)