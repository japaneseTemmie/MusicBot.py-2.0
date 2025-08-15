""" Rolemanager module for discord.py bot.\n
Includes a class with methods to manage music and playlist permissions. """

from settings import *
from roles import *
from bot import Bot

class RoleManagerCog(commands.Cog):
    def __init__(self, client: Bot):
        self.client = client

    async def get_role(self, roles: list, value: str, get_by_id: bool=False) -> discord.Role | None:
        role = discord.utils.get(roles, name=value) if not get_by_id and not value.isdigit() else\
        discord.utils.get(roles, id=int(value))

        return role

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
        roles = await open_roles(interaction)
        if isinstance(roles, Error):
            await interaction.response.send_message(roles.msg, ephemeral=True)
            return
        
        role_to_set = "playlist" if playlist else "music"

        if role_to_set in roles and not overwrite:
            await interaction.response.send_message(f"Default **{role_to_set}** role already set!", ephemeral=True)
            return

        backup = None if not CONFIG["enable_file_backups"] else deepcopy(roles)
        
        roles[role_to_set] = str(role.id) # Store ID instead of name so the bot doesn't pick the wrong role to check when there's 2 or more roles with the same name

        success = await write_roles(interaction, roles, backup)
        if isinstance(success, Error):
            await interaction.response.send_message(success.msg, ephemeral=True)
            return
        
        await interaction.response.send_message(f"Set **{role_to_set}** role to **{role.name}** for this guild.", ephemeral=not show)

    @set_music_role.error
    async def handle_set_role_error(self, interaction: Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        elif isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("You do not have permission to modify this!", ephemeral=True)
            return

        log_to_discord_log(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="role-get", description="Shows the current music/playlist role set up for this guild.")
    @app_commands.describe(
        playlist="Whether or not the command should read the playlist role.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ROLE_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def get_music_role(self, interaction: Interaction, playlist: bool, show: bool=False):
        roles = await open_roles(interaction)
        if isinstance(roles, Error):
            await interaction.response.send_message(roles.msg, ephemeral=True)
            return

        role_to_look_for = "playlist" if playlist else "music"
        if role_to_look_for not in roles:
            await interaction.response.send_message(f"Default **{role_to_look_for}** role has not been set for this guild yet!", ephemeral=True)
            return
        
        role = roles[role_to_look_for]
        role_obj = await self.get_role(interaction.guild.roles, role, True)
        if role_obj is None:
            await interaction.response.send_message(f"Role **{role}** not found in guild!", ephemeral=True)
            return

        await interaction.response.send_message(f"Default **{role_to_look_for}** role for this guild is **{role_obj.name}**.", ephemeral=not show)

    @get_music_role.error
    async def handle_get_role_error(self, interaction: Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        elif isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("You do not have permission to modify this!", ephemeral=True)
            return

        log_to_discord_log(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="role-wipe", description="Removes the current music/playlist role set up for this guild.")
    @app_commands.describe(
        playlist="Whether or not the command should remove the playlist role.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ROLE_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def wipe_music_role(self, interaction: Interaction, playlist: bool, show: bool=False):
        roles = await open_roles(interaction)
        if isinstance(roles, Error):
            await interaction.response.send_message(roles.msg, ephemeral=True)
            return

        backup = None if not CONFIG["enable_file_backups"] else deepcopy(roles)
        role_to_delete = "playlist" if playlist else "music"
        if role_to_delete not in roles:
            display_role = role_to_delete.replace("p", "P") if playlist else\
            role_to_delete.replace("m", "M")

            await interaction.response.send_message(f"**{display_role}** role is already empty!", ephemeral=True)
            return

        del roles[role_to_delete]

        success = await write_roles(interaction, roles, backup)
        if isinstance(success, Error):
            await interaction.response.send_message(success.msg, ephemeral=True)
            return

        await interaction.response.send_message(f"Removed **{role_to_delete}** role for this guild.", ephemeral=not show)

    @wipe_music_role.error
    async def handle_wipe_role_error(self, interaction: Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        elif isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("You do not have permission to modify this!", ephemeral=True)
            return

        log_to_discord_log(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="role-reset", description="Rewrite the saved role structure if corrupt.")
    @app_commands.describe(
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ROLE_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def reset_roles(self, interaction: Interaction, show: bool=False):
        success = await write_roles(interaction, {}, None)

        if isinstance(success, Error):
            await interaction.response.send_message(success.msg, ephemeral=True)
            return

        await interaction.response.send_message("Successfully rewritten role structure.", ephemeral=not show)

    @reset_roles.error
    async def handle_reset_roles_error(self, interaction: Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        elif isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("You do not have permission to modify this!", ephemeral=True)
            return

        log_to_discord_log(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)