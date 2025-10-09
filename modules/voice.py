""" Voice module for discord.py bot.

Handles voice clients and guild resource allocation. """

from settings import COOLDOWNS, CAN_LOG, LOGGER
from bot import Bot
from init.logutils import log, log_to_discord_log
from helpers.voicehelpers import check_users_in_channel, greet_new_user_in_vc, disconnect_routine, handle_channel_move
from helpers.guildhelpers import user_has_role, check_vc_lock, get_default_state, check_guild_state, update_guild_state, check_channel
from helpers.playlisthelpers import is_playlist_locked

import discord
from discord import app_commands
from discord.ext import commands
from discord.interactions import Interaction

class VoiceCog(commands.Cog):
    def __init__(self, client: Bot):
        self.client = client
        self.guild_states = self.client.guild_states

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """ Listener function that is called every time a user (including the bot) joins or leaves a voice channel.
        
        Handles different cases such as member count check, disconnect cleanup, or state management on channel move. """
        
        bot_voice_channel = member.guild.voice_client.channel if member.guild.voice_client else None
        
        if member.id != self.client.user.id:
            if (bot_voice_channel is not None and before.channel == bot_voice_channel) and\
                member.guild.id in self.guild_states:
                """ User left. Check member count in voice channel. """
                
                await check_users_in_channel(self.guild_states, member)
            elif (bot_voice_channel is not None and after.channel == bot_voice_channel) and\
                member.guild.id in self.guild_states:
                """ New user joined, why not greet them? """
                
                await greet_new_user_in_vc(self.guild_states, member)
        else:
            if (before.channel is not None and after.channel is None) and\
                member.guild.id in self.guild_states:
                """ Bot has disconnected. Wait and then clean up. """
                
                await disconnect_routine(self.client, self.guild_states, member)
            elif (before.channel is not None and after.channel is not None) and\
                member.guild.id in self.guild_states:
                """ Bot has been moved. Resume session in new channel. """

                await handle_channel_move(self.guild_states, member, before, after)

    @app_commands.command(name="join", description="Invites the bot to join your voice channel.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def join_channel(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_vc_lock(interaction):
            return
        
        await interaction.response.defer(thinking=True)

        channel = interaction.user.voice.channel if interaction.user.voice else None
        current_channel = interaction.guild.voice_client.channel if interaction.guild.voice_client else None
        permissions = channel.permissions_for(interaction.guild.me) if channel is not None else None

        if channel is None:
            await interaction.followup.send("Join a voice channel first.")
        elif channel.type == discord.ChannelType.stage_voice:
            await interaction.followup.send(f"I can't join channel **{channel.name}**! Stage channels scare me!")
        elif (channel is not None and current_channel is not None) and channel == current_channel:
            await interaction.followup.send("I'm already in your voice channel!")
        elif current_channel is not None:
            await interaction.followup.send(f"I'm already in **{current_channel.name}**!")
        elif permissions is not None and (not permissions.connect or not permissions.speak):
            await interaction.followup.send(f"I don't have permission to join your channel!")
        else:
            log(f"[CONNECT][SHARD ID {interaction.guild.shard_id}] Requested to join channel ID {channel.id} in guild ID {channel.guild.id}")

            voice_client = await channel.connect(timeout=10)
            if voice_client.is_connected():
                self.guild_states[interaction.guild.id] = await get_default_state(voice_client, interaction.channel)
                
                log(f"[GUILDSTATE] Allocated space for guild ID {interaction.guild.id} in guild states.")

                await interaction.followup.send(f"Connected to **{channel.name}**!")

                await check_users_in_channel(self.guild_states, interaction) # awful fix to avoid users trapping the bot in a vc when using the join command

    @join_channel.error
    async def handle_join_channel_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        log(f"[CONNECT][SHARD ID {interaction.guild.shard_id}] Failed to connect to voice channel ID {interaction.channel.id} in guild ID {interaction.guild.id}")

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func(
            f"Something went wrong while connecting. "
            f"{f'Leave **{interaction.user.voice.channel.name}**, join back,' if interaction.user.voice else 'Join the voice channel'} and invite me again.", ephemeral=True
        )

    @app_commands.command(name="leave", description="Makes the bot leave your voice channel.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def leave_channel(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use /progress to see the status.") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first.") or\
            not await check_vc_lock(interaction):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        if voice_client.is_connected():
            log(f"[DISCONNECT][SHARD ID {interaction.guild.shard_id}] Requested to leave channel ID {voice_client.channel.id} in guild ID {interaction.guild.id}")

            if voice_client.is_playing() or voice_client.is_paused():
                await update_guild_state(self.guild_states, interaction, True, "stop_flag")
                voice_client.stop()

            await update_guild_state(self.guild_states, interaction, True, "user_disconnect")

            await voice_client.disconnect()
            log(f"[DISCONNECT][SHARD ID {interaction.guild.shard_id}] Left channel ID {voice_client.channel.id}")
            await interaction.followup.send(f"Disconnected from **{voice_client.channel.name}**.")

    @leave_channel.error
    async def handle_leave_channel_error(self, interaction: Interaction, error: Exception):
        if isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        send_func = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

        await send_func("An unknown error occurred", ephemeral=True)