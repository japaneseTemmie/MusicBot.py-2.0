""" Role module for discord.py bot.

Includes a class with methods to manage music and playlist permissions. """

from settings import CAN_LOG, LOGGER
from init.constants import COOLDOWNS
from managers.rolemanager import RoleManager
from error import Error
from bot import Bot, ShardedBot
from init.logutils import log_to_discord_log

import discord
from discord import app_commands
from discord.interactions import Interaction
from discord.ext import commands

class RolesCog(commands.Cog):
    def __init__(self, client: Bot | ShardedBot):
        self.client = client
        self.roles = RoleManager(self.client)

    async def handle_command_error(self, interaction: Interaction, error: Exception) -> None:
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        elif isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("You do not have permission to modify this!", ephemeral=True)
            return

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        await interaction.followup.send("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="role-set", description="Sets the default role users must have to allow music/playlist commands.")
    @app_commands.describe(
        role="The role name to set.",
        playlist="Whether or not this should be the playlist role.",
        overwrite="Whether or not to overwrite the current role. (default False)",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ROLE_SET_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def set_music_role(self, interaction: Interaction, role: discord.Role, playlist: bool, overwrite: bool=False, show: bool=False):
        await interaction.response.defer(ephemeral=not show)

        content = await self.roles.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        result = await self.roles.set_role(interaction, content, role, playlist, overwrite)
        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
            return
        
        write_success = result[0]
        if isinstance(write_success, Error):
            await interaction.followup.send(write_success.msg)
            return
        
        role_type = result[1]
        
        await interaction.followup.send(f"Set **{role_type}** role to **{role.name}** (ID **{role.id}**) for this guild.")

    @set_music_role.error
    async def handle_set_role_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="role-get", description="Shows the current music/playlist role set up for this guild.")
    @app_commands.describe(
        playlist="Whether or not the command should read the playlist role.",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ROLE_GET_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def get_music_role(self, interaction: Interaction, playlist: bool, show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        content = await self.roles.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return

        result = await self.roles.get_role(interaction, content, playlist)
        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
            return
        
        role_type = result[0]
        role = result[1]

        await interaction.followup.send(f"Default **{role_type}** role for this guild is **{role.name}** (ID **{role.id}**).")

    @get_music_role.error
    async def handle_get_role_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="role-remove", description="Removes the current music/playlist role set up for this guild.")
    @app_commands.describe(
        playlist="Whether or not the command should remove the playlist role.",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ROLE_REMOVE_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def remove_music_role(self, interaction: Interaction, playlist: bool, show: bool=False):
        await interaction.response.defer(ephemeral=not show)

        content = await self.roles.read(interaction)
        if isinstance(content, Error):
            await interaction.followup.send(content.msg)
            return
        
        result = await self.roles.remove_role(interaction, content, playlist)
        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
            return
        
        write_success = result[0]
        if isinstance(write_success, Error):
            await interaction.followup.send(write_success.msg)
            return
        
        role_type = result[1]

        await interaction.followup.send(f"Removed **{role_type}** role for this guild.")

    @remove_music_role.error
    async def handle_remove_role_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="role-reset", description="Rewrites the saved role structure.")
    @app_commands.describe(
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ROLE_RESET_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def reset_roles(self, interaction: Interaction, show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        result = await self.roles.reset(interaction)
        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
            return
        
        await interaction.followup.send("Successfully rewritten role structure.")

    @reset_roles.error
    async def handle_reset_roles_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)