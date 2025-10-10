""" RoleManager module for discord.py bot.

Includes a class with methods to manage music and playlist permissions. """

from settings import COOLDOWNS, CAN_LOG, LOGGER
from rolemanager import RoleManager
from init.logutils import log_to_discord_log
from error import Error
from bot import Bot

import discord
from discord import app_commands
from discord.interactions import Interaction
from discord.ext import commands

class RolesCog(commands.Cog):
    def __init__(self, client: Bot):
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

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="role-set", description="Sets the default role users must have to allow music/playlist commands.")
    @app_commands.describe(
        role="The role name to set.",
        playlist="Whether or not this should be the playlist role.",
        overwrite="Whether or not to overwrite the current role.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ROLE_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def set_music_role(self, interaction: Interaction, role: discord.Role, playlist: bool, overwrite: bool=False, show: bool=False):
        result = await self.roles.set_role(interaction, role, playlist, overwrite)
        if isinstance(result, Error):
            await interaction.response.send_message(result.msg, ephemeral=True)
            return
        
        role_type = result[0]
        
        await interaction.response.send_message(f"Set **{role_type}** role to **{role.name}** (ID **{role.id}**) for this guild.", ephemeral=not show)

    @set_music_role.error
    async def handle_set_role_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="role-get", description="Shows the current music/playlist role set up for this guild.")
    @app_commands.describe(
        playlist="Whether or not the command should read the playlist role.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ROLE_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def get_music_role(self, interaction: Interaction, playlist: bool, show: bool=False):
        result = await self.roles.get_role(interaction, playlist)
        if isinstance(result, Error):
            await interaction.response.send_message(result.msg, ephemeral=True)
            return
        
        role_type = result[0]
        role = result[1]

        await interaction.response.send_message(f"Default **{role_type}** role for this guild is **{role.name}** (ID **{role.id}**).", ephemeral=not show)

    @get_music_role.error
    async def handle_get_role_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="role-wipe", description="Removes the current music/playlist role set up for this guild.")
    @app_commands.describe(
        playlist="Whether or not the command should remove the playlist role.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ROLE_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def wipe_music_role(self, interaction: Interaction, playlist: bool, show: bool=False):
        result = await self.roles.wipe_role(interaction, playlist)
        if isinstance(result, Error):
            await interaction.response.send_message(result.msg, ephemeral=True)
            return
        
        role_type = result

        await interaction.response.send_message(f"Removed **{role_type}** role for this guild.", ephemeral=not show)

    @wipe_music_role.error
    async def handle_wipe_role_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="role-reset", description="Rewrite the saved role structure if corrupt.")
    @app_commands.describe(
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ROLE_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def reset_roles(self, interaction: Interaction, show: bool=False):
        result = await self.roles.reset(interaction)
        if isinstance(result, Error):
            await interaction.response.send_message(result.msg, ephemeral=True)
            return
        
        await interaction.response.send_message("Successfully rewritten role structure.", ephemeral=not show)

    @reset_roles.error
    async def handle_reset_roles_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)