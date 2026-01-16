""" Example module for discord.py bot """

# Import basic constants, functions and classes
from settings import CAN_LOG, LOGGER
from init.logutils import log_to_discord_log
from bot import Bot, ShardedBot

import discord
from discord import app_commands
from discord.ext import commands
from discord.interactions import Interaction
from datetime import timedelta

# Cogs allow for modularity in a discord.py-powered bot. They provide useful features to make building a bot easier.
    
# Each cog has its own listeners and async methods that work independently from
# other modules (as long as they don't overlap).

class MyCog(commands.Cog): # Subclass commands.Cog
    def __init__(self, client: Bot | ShardedBot):
        self.client = client
        # This example cog doesn't have any custom attributes. But custom attributes go here.

    async def time_out_member(self, member: discord.Member, notify: bool) -> None:
        await member.timeout(timedelta(minutes=5), reason="No media in general.")
        if notify:
            await member.send(f"You were timed out from **{member.guild.name}**.\nReason: No media in general.")

    async def check_message(self, message: discord.Message) -> None:
        if message.attachments:
            await message.delete()
            await self.time_out_member(message.author, True)

    async def check_message_channel(self, message: discord.Message) -> None:
        # Timeout a user that sends attachments in general and delete message
        if message.channel.name == "general": # Only an example, replace this with a variable.
            await self.check_message(message)

    # Define a listener. This is a special 'object' that listens for specific events that get recorded by discord.py.
    # The function will be named after the event we want to catch.
    # Ensure listeners from other cogs don't overlap with each other.
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # This function will be called every time the on_message event is received (when a user sends a message in a channel).

        # Ignore messages sent by the bot
        if message.author.bot:
            return

        try:
            await self.check_message_channel(message)
        except discord.errors.Forbidden: # We may receive an HTTP 403 'Forbidden' error if the user has DMs disabled or we cannot time out the member.
            pass # Since this is a listener, it's best if we ignore it.
        except Exception as e:
            log_to_discord_log(e, can_log=CAN_LOG, logger=LOGGER) # Log other exceptions to discord.log (if logging is explicitly enabled in config.json)

    # Define an application command. This is the command that users are going to interact with.
    @app_commands.command(name="my-command", description="My first custom command.") # Define a command with the command() decorator 
    # Pass other decorators to add checks and cooldowns.
    @app_commands.checks.cooldown(rate=1, per=5.0)
    async def say_hi(self, interaction: Interaction) -> None: # This function will be executed every time someone uses /my-command
        # Interactions are the primary way to communicate with users in an Appcommand context.
        # They hold useful information such as the user who used the command, the guild we're in, and more.
        
        user_mention = interaction.user.mention

        # Reply to the interaction. Discord expects this to happen in ~3-5 seconds after
        # the command was registered. For longer operations, await the defer() function in the
        # 'response' property and reply with the 'followup.send()' async function. """

        await interaction.response.send_message(f"Hi there, {user_mention}!")

    # Optionally, register an error handler for the command.
    @say_hi.error
    async def handle_say_hi_error(self, interaction: Interaction, error: Exception):
        # This function will be called when an exception in say_hi() is raised.
        
        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        await interaction.response.send_message("An unknown error occurred.")