""" Utilities module for discord.py bot\n
Includes a short class for help commands. """

from settings import COOLDOWNS, HELP, CAN_LOG, LOGGER
from init.logutils import log_to_discord_log
from bot import Bot, ShardedBot

from discord import app_commands
from discord.interactions import Interaction
from discord.ext import commands

class UtilsCog(commands.Cog):
    def __init__(self, client: Bot | ShardedBot):
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

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        await interaction.response.send_message("An unknown error occurred.")

    @app_commands.command(name="help", description="Show specified help entry.")
    @app_commands.describe(
        entry="The help entry's name."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["HELP_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    async def show_help(self, interaction: Interaction, entry: str="general"):
        if HELP is None:
            await interaction.response.send_message("No help available.", ephemeral=True)
            return
        
        entry = entry.lower().strip()

        if entry not in HELP:
            await interaction.response.send_message(
                f"Could not find help for {entry}.\n"
                f"Available commands: {', '.join(HELP.keys())}", ephemeral=True
            )
            return
        
        help_string = HELP.get(entry)

        await interaction.response.send_message(help_string, ephemeral=True)

    @show_help.error
    async def handle_show_help_error(self, interaction: Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)
