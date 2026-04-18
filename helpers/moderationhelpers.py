""" Moderation helpers for discord.py bot """

import discord
from typing import Callable

# Moderation utilities
def get_role(roles: list[discord.Role], role: str, get_by_id: bool=False) -> discord.Role | None:
    return discord.utils.get(roles, name=role) if not get_by_id and not role.isdigit() else\
    discord.utils.get(roles, id=int(role))

def remove_markdown_or_mentions(text: str, markdown: bool, mentions: bool) -> str:
    """ Remove Discord's markdown and mention formatting. """
    
    clean_text = text

    if mentions:
        clean_text = discord.utils.escape_mentions(clean_text)
    if markdown:
        clean_text = discord.utils.escape_markdown(clean_text)

    return clean_text

def get_purge_check(user: discord.Member | None, word: str | None) -> Callable:
    """ Return a check for the purge function, allowing to filter
    which messages to delete. """
    
    def check(m: discord.Message) -> bool:
        if user and word:
            return m.author == user and word.lower() in m.content.lower()
        elif user:
            return m.author == user
        elif word:
            return word.lower() in m.content.lower()
        return True
    
    return check
