""" Utilities module for discord.py bot\n
Includes a short class for help commands. """

from settings import COOLDOWNS, HELP, log_to_discord_log
from bot import Bot

from discord import app_commands
from discord.interactions import Interaction
from discord.ext import commands

class UtilsCog(commands.Cog):
    def __init__(self, client: Bot):
        self.client = client

    @app_commands.command(name="ping", description="Shows bot latency in ms.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PING_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    async def send_latency(self, interaction: Interaction):
        latency = round(self.client.latency * 1000, 1)
        await interaction.response.send_message(f"Pong!\nLatency: **{latency}**ms")

    @send_latency.error
    async def handle_send_latency_error(self, interaction: Interaction, error):
        if isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)

        log_to_discord_log(error)

        await interaction.response.send_message("An unknown error occurred.")

    @app_commands.command(name="help", description="Show general help or help entry for <command>.")
    @app_commands.describe(
        command="The command name."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["HELP_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    async def show_help(self, interaction: Interaction, command: str="general"):
        if HELP is None:
            await interaction.response.send_message("No help available.", ephemeral=True)
            return
        
        clean_command = command.lower().strip()

        if clean_command not in HELP:
            await interaction.response.send_message(
                f"Could not find help for {command}.\n"
                f"Available commands: {', '.join(HELP.keys())}", ephemeral=True
            )
            return
        
        entry = HELP.get(clean_command)

        await interaction.response.send_message(entry, ephemeral=True)

    @show_help.error
    async def handle_show_help_error(self, interaction: Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        log_to_discord_log(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)
