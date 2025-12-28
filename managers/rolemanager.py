""" Role manager module for discord.py bot """

from settings import ENABLE_FILE_BACKUPS, ROLE_LOCKS, ROLE_FILE_CACHE
from helpers.guildhelpers import read_guild_json, write_guild_json
from helpers.moderationhelpers import get_role
from error import Error

import discord
from discord.interactions import Interaction
from typing import Any
from copy import deepcopy

class RoleManager:
    def __init__(self, client):
        self.client = client

    async def read(self, interaction: Interaction) -> dict[str, Any] | Error:
        """ Read the contents of `roles.json`.
         
        Returns the role structure or Error. """
        
        return await read_guild_json(
            interaction,
            "roles.json",
            ROLE_LOCKS,
            ROLE_FILE_CACHE,
            "Role reading temporarily disabled.",
            "Failed to read role contents."
        )
        
    async def write(self, interaction: Interaction, content: dict[str, Any], backup: dict[str, Any] | None=None) -> bool | Error:
        """ Write the modified content to `roles.json`.
         
        Returns True or Error. """
        
        return await write_guild_json(
            interaction,
            content,
            "roles.json",
            ROLE_LOCKS,
            ROLE_FILE_CACHE,
            "Role writing temporarily disabled.",
            "Failed to apply changes to roles.",
            backup
        )
    
    async def set_role(self, interaction: Interaction, role: discord.Role, playlist: bool, overwrite: bool) -> tuple[str, discord.Role] | Error:
        """ Set a music or playlist role.
        
        Returns a tuple with role type (music or playlist) and the role object or Error. """
    
        roles = await self.read(interaction)
        if isinstance(roles, Error):
            return roles
        
        role_to_set = "playlist" if playlist else "music"

        if role_to_set in roles and not overwrite:
            return Error(f"Default **{role_to_set}** role already set!")

        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(roles)
        
        roles[role_to_set] = str(role.id) # Store ID instead of name so the bot doesn't pick the wrong role to check when there's 2 or more roles with the same name

        result = await self.write(interaction, roles, backup)
        if isinstance(result, Error):
            return result
        
        return role_to_set, role
    
    async def get_role(self, interaction: Interaction, playlist: bool) -> tuple[str, discord.Role] | Error:
        """ Return a set music or playlist role.
         
        Returns a tuple with role type (music or playlist) and role object or Error. """
        
        roles = await self.read(interaction)
        if isinstance(roles, Error):
            return roles

        role_to_look_for = "playlist" if playlist else "music"
        if role_to_look_for not in roles:
            return Error(f"Default **{role_to_look_for}** role has not been set for this guild yet!")
        
        role_id = roles[role_to_look_for]
        role_obj = await get_role(interaction.guild.roles, role_id, True)
        
        if role_obj is None:
            return Error(f"Role (ID **{role_id}**) not found in guild!")

        return role_to_look_for, role_obj
    
    async def wipe_role(self, interaction: Interaction, playlist: bool) -> str | Error:
        """ Wipe a music or playlist role from the role structure.
         
        Returns removed role type (music or playlist) or Error. """
        
        roles = await self.read(interaction)
        if isinstance(roles, Error):
            return roles

        backup = None if not ENABLE_FILE_BACKUPS else deepcopy(roles)
        role_to_delete = "playlist" if playlist else "music"
        if role_to_delete not in roles:
            display_role = role_to_delete[0].upper() + role_to_delete[1:]

            return Error(f"**{display_role}** role is already empty!")

        del roles[role_to_delete]

        result = await self.write(interaction, roles, backup)
        if isinstance(result, Error):
            return result

        return role_to_delete
    
    async def reset(self, interaction: Interaction) -> bool | Error:
        """ Reset role structure.
         
        Returns True or Error. """
        
        result = await self.write(interaction, {})
        if isinstance(result, Error):
            return result

        return True