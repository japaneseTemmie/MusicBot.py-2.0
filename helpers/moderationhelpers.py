""" Moderation helper functions for discord.py bot """

import discord
from typing import Callable

# Moderation utilities
async def get_banned_users(guild: discord.Guild) -> list[discord.User] | list:
    """ Get a list of `discord.User` objects from a guild's ban entries. """

    members = []
    async for ban_entry in guild.bans():
        members.append(ban_entry.user)

    return members

async def get_role(roles: list[discord.Role], role: str, get_by_id: bool=False) -> discord.Role | None:
    return discord.utils.get(roles, name=role) if not get_by_id and not role.isdigit() else\
    discord.utils.get(roles, id=int(role))

async def get_user_to_unban(banned_users: list[discord.User], member: str | int) -> discord.User:
    """ Match a given user's name or ID to users in a ban entry list and return the object. """
    
    member_obj = None
    funcs = [
        lambda: discord.utils.get(banned_users, id=int(member) if member.isdigit() else None),
        lambda: discord.utils.get(banned_users, name=member.strip()),
        lambda: discord.utils.get(banned_users, global_name=member.strip())
    ]

    for func in funcs:
        member_obj = func()

        if member_obj is not None:
            break

    return member_obj

async def remove_markdown_or_mentions(text: str, markdown: bool, mentions: bool) -> str:
    """ Remove Discord's markdown and mention formatting. """
    
    clean_text = text

    if mentions:
        clean_text = discord.utils.escape_mentions(clean_text)
    if markdown:
        clean_text = discord.utils.escape_markdown(clean_text)

    return clean_text

async def get_purge_check(user: discord.Member | None, word: str | None) -> Callable:
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
