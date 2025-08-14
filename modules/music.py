""" Simple music module for discord.py bot.\n
Includes a class with methods for managing a queue and track playback."""

from settings import *
from helpers import *
from roles import *
from embedgenerator import *
from playlist import PlaylistManager
from bot import Bot

class MusicCog(commands.Cog):
    def __init__(self, client: Bot):
        self.client = client
        self.guild_states = self.client.guild_states
        self.max_track_limit = 100
        self.max_history_track_limit = 200
        self.max_query_limit = 25
        
        self.playlist = PlaylistManager(self.client)

    async def close_voice_clients(self):
        """ Close any leftover VCs and cleanup their open audio sources, if any. """
        
        VOICE_OPERATIONS_LOCKED_PERMANENTLY.set()
        log(f"Voice state permanently locked: {VOICE_OPERATIONS_LOCKED_PERMANENTLY.is_set()}")
        
        log("Closing voice clients..")
        
        async def _close(vc: discord.VoiceClient):
            log(f"Closing connection to channel ID {vc.channel.id}")
            
            can_edit_status = self.guild_states[vc.guild.id]["allow_voice_status_edit"]

            await update_guild_states(self.guild_states, vc, (True, True), ("handling_disconnect_action", "pending_cleanup"))
            
            if vc.is_playing() or vc.is_paused():
                await update_guild_state(self.guild_states, vc, True, "stop_flag")
                vc.stop()

            if can_edit_status:
                await update_guild_state(self.guild_states, vc, None, "voice_status")
                await set_voice_status(self.guild_states, vc)

            try:
                await asyncio.wait_for(vc.disconnect(force=True), timeout=3) # API responds near immediately but the loop hangs for good 10 seconds if we don't pass a minimum timeout
            except asyncio.TimeoutError:
                pass
            
            vc.cleanup()
            
        await asyncio.gather(*[_close(vc) for vc in self.client.voice_clients])

        log("done")

    async def cog_unload(self):
        await self.close_voice_clients()
        self.guild_states.clear()

        log(f"[{self.__class__.__name__.upper()}] Cleaned all guild states.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        bot_voice_channel = member.guild.voice_client.channel if member.guild.voice_client else None
        
        if member.id != self.client.user.id:
            if (bot_voice_channel is not None and before.channel == bot_voice_channel) and\
                (after.channel is None or after.channel is not None) and\
                member.guild.id in self.guild_states:
                """ User left, check member count in voice channel. """
                
                await check_users_in_channel(self.guild_states, member)
            elif (before.channel is None or before.channel is not None) and\
                (bot_voice_channel is not None and after.channel == bot_voice_channel) and\
                member.guild.id in self.guild_states:
                """ New user joined, why not greet them? """
                
                await greet_new_user_in_vc(self.guild_states, member)
        else:
            if before.channel is not None and\
                after.channel is None and\
                member.guild.id in self.guild_states:
                """ Bot has disconnected, wait and then clean up. """
                
                await disconnect_routine(self.client, self.guild_states, member)

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
            log(f"[CONNECT][SHARD ID {interaction.guild.id}] Requested to join channel ID {channel.id} in guild ID {channel.guild.id}")

            voice_client = await channel.connect(timeout=15)
            if voice_client.is_connected():
                self.guild_states[interaction.guild.id] = await get_default_state(voice_client, interaction.channel)
                
                log(f"[GUILDSTATE] Allocated space for guild ID {interaction.guild.id} in guild states.")

                await interaction.followup.send(f"Connected to **{channel.name}**!")

                await check_users_in_channel(self.guild_states, interaction) # awful fix to avoid users trapping the bot in a vc when using the join command

    @join_channel.error
    async def handle_join_channel_error(self, interaction: Interaction, error):
        if isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        log(f"[CONNECT] Failed to connect to voice channel ID {interaction.channel.id} in guild ID {interaction.guild.id}")

        await interaction.followup.send(f"Something went wrong while connecting. "
                                        f"{f'Leave **{interaction.user.voice.channel.name}**, join back,' if interaction.user.voice else 'Join the voice channel'} and invite me again.")

    @app_commands.command(name="leave", description="Makes the bot leave your voice channel.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def leave_channel(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use /progress to see the status.") or\
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

            await update_guild_state(self.guild_states, interaction, True, "user_disconnect")
            if voice_client.is_playing() or voice_client.is_paused():
                await update_guild_state(self.guild_states, interaction, True, "stop_flag")
                voice_client.stop()

            await voice_client.disconnect()
            await interaction.followup.send(f"Disconnected from **{voice_client.channel.name}**.")

    @leave_channel.error
    async def handle_leave_channel_error(self, interaction: Interaction, error):
        if isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.followup.send("Something went wrong while disconnecting.")

    @app_commands.command(name="add", description="Adds a track to the queue. See entry in /help for more info.")
    @app_commands.describe(
        queries="A semicolon separated list of URLs or search queries. Refer to help entry for valid URLs.",
        search_provider="The website to search for each search query on. URLs ignore this."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.choices(search_provider=[
            app_commands.Choice(name="SoundCloud search", value="soundcloud"),
            app_commands.Choice(name="YouTube search", value="youtube")
        ]
    )
    @app_commands.guild_only
    async def add_track(self, interaction: Interaction, queries: str, search_provider: app_commands.Choice[str]=None):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status.") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked! Please wait for the other action first."):
            return

        await interaction.response.defer(thinking=True)
        
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        is_looping_queue = self.guild_states[interaction.guild.id]["is_looping_queue"]

        queries_split = await check_input_length(interaction, self.max_query_limit, split(queries))

        is_queue_length_ok = await check_queue_length(interaction, self.max_track_limit, queue)
        if not is_queue_length_ok:
            return

        await update_guild_states(self.guild_states, interaction, (True, True), ("is_modifying", "is_extracting"))

        allowed_query_types = ("YouTube", "YouTube search", "YouTube Playlist", "SoundCloud", "SoundCloud search", "Bandcamp")
        provider = search_provider.value if search_provider else None

        found = await fetch_queries(self.guild_states, interaction, queries_split, allowed_query_types=allowed_query_types, provider=provider)

        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        if isinstance(found, Error):
            await interaction.followup.send(found.msg)
        elif isinstance(found, list):
            added = await add_results_to_queue(interaction, found, queue, self.max_track_limit)
            
            if is_looping_queue:
                await update_loop_queue_add(self.guild_states, interaction)

            if not voice_client.is_playing() and\
                not voice_client.is_paused():
                await self.play_next(interaction)
            
            embed = generate_added_track_embed(results=added)

            await interaction.followup.send(embed=embed)

    @add_track.error
    async def handle_add_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            
            """ This only gets triggered if the bot somehow cleaned up the guild state while
            performing a task that's still not yet completed (like extracting something).
             
            Achievable by forcefully disconnecting the bot using the Discord UI while it's extracting something through the Discord client.
            Is it something to worry about? Not really. The state is clean and no errors pile up. Normally, regular users can't force disconnect
            the bot. Only through /leave (which is locked in that state). """
            
            return # Don't care just don't fill up the logs.
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send("An unknown error occurred.")

    async def play_track(
            self, 
            interaction: Interaction, 
            voice_client: discord.VoiceClient, 
            track: dict, 
            position: int=0, 
            state: str | None=None
        ) -> None:
        if not voice_client or\
            not voice_client.is_connected() or\
            track is None:
            return

        history = self.guild_states[interaction.guild.id]["queue_history"]
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        track_to_loop = self.guild_states[interaction.guild.id]["track_to_loop"]
        general_start_time, general_start_date = self.guild_states[interaction.guild.id]["general_start_time"], self.guild_states[interaction.guild.id]["general_start_date"]
        can_edit_status = self.guild_states[interaction.guild.id]["allow_voice_status_edit"]

        position = max(0, min(position, format_to_seconds(track["duration"])))
        ffmpeg_options = await get_ffmpeg_options(position)

        try:
            is_stream_valid = await validate_stream(track["url"])
            if not is_stream_valid: # This won't work anymore. Need a new stream. Slow, but required or else everything breaks :3
                track = await resolve_expired_url(track["webpage_url"])

            source = discord.FFmpegPCMAudio(track["url"], options=ffmpeg_options["options"], before_options=ffmpeg_options["before_options"])
            voice_client.stop()
            voice_client.play(source, after=lambda e: self.handle_playback_end(e, interaction))
        except Exception as e:
            await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")
            if is_looping:
                await update_guild_state(self.guild_states, interaction, False, "is_looping")

            self.handle_playback_end(e, interaction)
            return

        if not general_start_time or not general_start_date:
            await update_guild_states(self.guild_states, interaction, (get_time(), datetime.now()), ("general_start_time", "general_start_date"))

        await update_guild_states(self.guild_states, interaction, (get_time() - position, position), ("start_time", "elapsed_time"))
        
        """Update track to loop if looping is enabled
        Cases in which this is useful:
        We already have a track set to loop, we use /playnow or something that overrides this, now we need to update the track to loop."""

        if is_looping and track_to_loop != track:
            await update_guild_state(self.guild_states, interaction, track, "track_to_loop")

        await update_guild_state(self.guild_states, interaction, track, "current_track")
        
        """ Only append if the maximum amount of tracks in the track history is not reached, if
            the position is less or equal to 0, if it's not looping the current track, and we're not
            altering the current track with commands like restart, seek, etc. """

        if not position > 0 and\
            not is_looping and\
            state is None:

            if len(history) >= self.max_history_track_limit:
                history.clear()

            history.append(track)

        if can_edit_status:
            await update_guild_state(self.guild_states, interaction, f"Listening to '{track['title']}'", "voice_status")
            await set_voice_status(self.guild_states, interaction)

    async def play_next(self, interaction: Interaction) -> None:
        if interaction.guild.id not in self.guild_states:
            return
        
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        is_random = self.guild_states[interaction.guild.id]["is_random"]
        track_to_loop = self.guild_states[interaction.guild.id]["track_to_loop"]
        can_update_status = self.guild_states[interaction.guild.id]["allow_voice_status_edit"]
        stop_flag = self.guild_states[interaction.guild.id]["stop_flag"]
        voice_client_locked = self.guild_states[interaction.guild.id]["voice_client_locked"]
        user_forced = self.guild_states[interaction.guild.id]["user_interrupted_playback"]
        start_time = self.guild_states[interaction.guild.id]["start_time"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        current_time = get_time() - start_time

        if stop_flag:
            await update_guild_state(self.guild_states, interaction, False, "stop_flag")
            return
        elif voice_client_locked:
            return

        no_users_in_channel = await check_users_in_channel(self.guild_states, interaction)
        if no_users_in_channel:
            return
        
        if not queue and not\
            is_looping and not\
            queue_to_loop:
            await update_guild_states(self.guild_states, interaction, (None, 0, 0), ("current_track", "start_time", "elapsed_time"))
            
            if can_update_status:
                await update_guild_state(self.guild_states, interaction, None, "voice_status")
                await set_voice_status(self.guild_states, interaction)

            await interaction.channel.send("Queue is empty.") if interaction.is_expired()\
            else await interaction.followup.send("Queue is empty.")
            return

        if current_track is not None:
            playback_ended_unexpectedly = not user_forced and current_time < format_to_seconds(current_track["duration"])

            if playback_ended_unexpectedly:
                await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")

                try:
                    new_track = await resolve_expired_url(current_track["webpage_url"])
                    await self.play_track(interaction, voice_client, new_track, current_time, "retry")
                    return
                except Exception:
                    pass
                finally:
                    await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")
        
        if user_forced:
            await update_guild_state(self.guild_states, interaction, False, "user_interrupted_playback")

        if not queue and queue_to_loop:
            new_queue = deepcopy(queue_to_loop)
            await update_guild_state(self.guild_states, interaction, new_queue, "queue")

            queue = self.guild_states[interaction.guild.id]["queue"]

        if track_to_loop and is_looping:
            track = track_to_loop
        elif is_random:
            track = queue.pop(queue.index(choice(queue)))
        else:
            track = queue.pop(0)

        await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")
        await self.play_track(interaction, voice_client, track)
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        if not is_looping:
            await interaction.channel.send(f"Now playing: **{track['title']}**") if interaction.is_expired()\
            else await interaction.followup.send(f"Now playing: **{track['title']}**")

    def handle_playback_end(self, error: Exception | None, interaction: Interaction) -> None:
        if error is not None:
            asyncio.run_coroutine_threadsafe(interaction.followup.send("An error occurred while handling playback end. Skipping..") if interaction.response.is_done() else\
                                            interaction.response.send_message("An error occurred while handling playback end. Skipping.."), self.client.loop)
            
            if CAN_LOG and LOGGER is not None:
                LOGGER.exception(error)

        asyncio.run_coroutine_threadsafe(self.play_next(interaction), self.client.loop)

    @app_commands.command(name="playnow", description="Plays the given query without saving it to the queue first. See entry in /help for more info.")
    @app_commands.describe(
        query="URL or search query. Refer to help entry for valid URLs.",
        search_provider="The website to search for the search query on. URLs ignore this.",
        keep_current_track="Whether or not to keep the current track (if any) in the queue."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.choices(
        search_provider=[
            app_commands.Choice(name="SoundCloud search", value="soundcloud"),
            app_commands.Choice(name="YouTube search", value="youtube")
        ]
    )
    @app_commands.guild_only
    async def play_track_now(self, interaction: Interaction, query: str, search_provider: app_commands.Choice[str]=None, keep_current_track: bool=True):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status.") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nPlease wait for the current action first."):
            return
        
        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]

        if current_track is not None and keep_current_track:
            is_queue_length_ok = await check_queue_length(interaction, self.max_track_limit, self.guild_states[interaction.guild.id]["queue"])
            if not is_queue_length_ok or\
                not await check_guild_state(self.guild_states, interaction):
                return
            await update_guild_state(self.guild_states, interaction, True)

        await update_guild_state(self.guild_states, interaction, True, "is_extracting")

        allowed_query_types = ("YouTube", "YouTube search", "SoundCloud", "SoundCloud search", "Bandcamp")
        provider = search_provider.value if search_provider else None
        extracted_track = await fetch_query(self.guild_states, interaction, query, allowed_query_types=allowed_query_types, provider=provider)

        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        if isinstance(extracted_track, dict):
            if current_track is not None and keep_current_track:
                queue.insert(0, current_track)
                await update_guild_state(self.guild_states, interaction, False)

            await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")
            if voice_client.is_playing() or voice_client.is_paused():
                await update_guild_state(self.guild_states, interaction, True, "stop_flag")
            
            await self.play_track(interaction, voice_client, extracted_track)

            await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

            await interaction.followup.send(f"Now playing: **{extracted_track["title"]}**")
        elif isinstance(extracted_track, Error):
            await interaction.followup.send(extracted_track.msg)

    @play_track_now.error
    async def handle_play_track_now_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) and\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_states(self.guild_states, interaction, (False, False, False), ("is_modifying", "is_extracting", "voice_client_locked"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send("An unknown error occurred.")

    @app_commands.command(name="skip", description="Skips to next track in the queue.")
    @app_commands.describe(
        amount="The amount of tracks to skip. Starts from the current track. Must be <= 25 and /random must not be enabled."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def skip_track(self, interaction: Interaction, amount: int=1):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        queue = self.guild_states[interaction.guild.id]["queue"]
        is_random = self.guild_states[interaction.guild.id]["is_random"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]

        await update_guild_states(self.guild_states, interaction, (True, True), ("is_modifying", "user_interrupted_playback"))

        skipped = []
        if amount > 1 and not is_random:
            for _ in range(1, min(amount, 25)):
                if len(queue) > 0:
                    track_info = queue.pop(0)
                    skipped.append(track_info)
            else:
                skipped.insert(0, current_track)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        voice_client.stop()

        await update_guild_state(self.guild_states, interaction, False)

        if skipped:
            embed = generate_skipped_tracks_embed(skipped)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"Skipped track **{current_track['title']}**.")

    @skip_track.error
    async def handle_skip_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False)

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send("An unknown error occurred.")

    @app_commands.command(name="nextinfo", description="Shows information about the next track.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_next_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_reading_queue", msg="Queue is already being read, please wait.") or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return
        
        await update_guild_state(self.guild_states, interaction, True, "is_reading_queue")
        
        is_random = self.guild_states[interaction.guild.id]["is_random"]
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]
        track_to_loop = self.guild_states[interaction.guild.id]["track_to_loop"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        
        next_track = await get_next(is_random, is_looping, track_to_loop, queue, queue_to_loop)
        if isinstance(next_track, Error):
            await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")
            
            await interaction.response.send_message(next_track.msg)
            return
        
        embed = generate_yoink_embed(next_track)

        await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")

        await interaction.response.send_message(embed=embed)

    @show_next_track.error
    async def handle_show_next_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="previousinfo", description="Shows information about the previous track.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_previous_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
        not await check_channel(self.guild_states, interaction) or\
        not await check_guild_state(self.guild_states, interaction, state="is_reading_history", msg="Track history is already being read, please wait.") or\
        not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return
        
        await update_guild_state(self.guild_states, interaction, True, "is_reading_history")
    
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        history = self.guild_states[interaction.guild.id]["queue_history"]
        
        previous = await get_previous(current_track, history)
        if isinstance(previous, Error):
            await update_guild_state(self.guild_states, interaction, False, "is_reading_history")
            
            await interaction.response.send_message(previous.msg)
            return
        
        embed = generate_yoink_embed(previous)
        await update_guild_state(self.guild_states, interaction, False, "is_reading_history")
        
        await interaction.response.send_message(embed=embed)

    @show_previous_track.error
    async def handle_show_previous_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False, "is_reading_history")

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="pause", description="Pauses track playback.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def pause_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return
        
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        can_update_status = self.guild_states[interaction.guild.id]["allow_voice_status_edit"]
        start_time = self.guild_states[interaction.guild.id]["start_time"]

        if voice_client.is_paused():
            await interaction.response.send_message("I'm already paused!")
            return

        await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")

        voice_client.pause()
        await update_guild_state(self.guild_states, interaction, int(get_time() - start_time), "elapsed_time")

        if can_update_status:
            await update_guild_state(self.guild_states, interaction, f"Listening to '{current_track['title']}' (paused)", "voice_status")
            await set_voice_status(self.guild_states, interaction)

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.response.send_message("Paused track playback.")

    @pause_track.error
    async def handle_pause_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="resume", description="Resumes track playback.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def resume_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return
        
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        can_update_status = self.guild_states[interaction.guild.id]["allow_voice_status_edit"]
        elapsed_time = self.guild_states[interaction.guild.id]["elapsed_time"]
        
        if not voice_client.is_paused():
            await interaction.response.send_message("I'm not paused!")
            return

        await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")

        voice_client.resume()
        await update_guild_state(self.guild_states, interaction, int(get_time() - elapsed_time), "start_time")

        if can_update_status:
            await update_guild_state(self.guild_states, interaction, f"Listening to '{current_track['title']}'", "voice_status")
            await set_voice_status(self.guild_states, interaction)

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.response.send_message("Resumed track playback.")

    @resume_track.error
    async def handle_resume_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="stop", description="Stops the current track and resets bot state.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def stop_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nWait for the other action first."):
            return

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        can_update_status = self.guild_states[interaction.guild.id]["allow_voice_status_edit"]

        await update_guild_states(self.guild_states, interaction, (True, True), ("voice_client_locked", "stop_flag"))
        voice_client.stop()

        if can_update_status:
            await update_guild_state(self.guild_states, interaction, None, "voice_status")
            await set_voice_status(self.guild_states, interaction)

        self.guild_states[interaction.guild.id] = await get_default_state(voice_client, interaction.channel)

        await interaction.response.send_message(f"Stopped track **{current_track['title']}** and reset bot state.")

    @stop_track.error
    async def handle_stop_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_states(self.guild_states, interaction, (False, False), ("voice_client_locked", "stop_flag"))

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="restart", description="Restarts the current track.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def restart_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        current_track = self.guild_states[interaction.guild.id]["current_track"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")
        if voice_client.is_playing() or voice_client.is_paused():
            await update_guild_state(self.guild_states, interaction, True, "stop_flag")
        
        await self.play_track(interaction, voice_client, current_track, state="restart")
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.followup.send(f"Restarted track **{current_track['title']}**.")

    @restart_track.error
    async def handle_restart_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False), ("voice_client_locked", "stop_flag"))

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="select", description="Selects a track from the queue and plays it. See entry in /help for more info.")
    @app_commands.describe(
        track_name="Name (or index, in case <by_index> is True) of the track to select.",
        by_index="Select track by its index."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def select_track(self, interaction: Interaction, track_name: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to select.") or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        queue = self.guild_states[interaction.guild.id]["queue"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        await update_guild_state(self.guild_states, interaction, True)

        found = await find_track(track_name, queue, by_index)
        if isinstance(found, Error):
            await update_guild_state(self.guild_states, interaction, False)

            await interaction.followup.send(found.msg)
            return
        
        track_dict = queue.pop(found[1])

        await update_guild_states(self.guild_states, interaction, (False, True), ("is_modifying", "voice_client_locked"))
        if voice_client.is_playing() or voice_client.is_paused():
            await update_guild_state(self.guild_states, interaction, True, "stop_flag")
        
        await self.play_track(interaction, voice_client, track_dict)
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.followup.send(f"Selected track **{track_dict['title']}**.")

    @select_track.error
    async def handle_select_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False, False), ("is_modifying", "voice_client_locked", "stop_flag"))

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send("An unknown error occurred.")

    @app_commands.command(name="select-random", description="Selects a random track from the queue and plays it. See entry in /help for more info.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def select_random_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to select.") or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return

        queue = self.guild_states[interaction.guild.id]["queue"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        await update_guild_states(self.guild_states, interaction, (True, True), ("is_modifying", "voice_client_locked"))

        random_track = queue.pop(queue.index(choice(queue)))

        if voice_client.is_playing() or voice_client.is_paused():
            await update_guild_state(self.guild_states, interaction, True, "stop_flag")
        
        await self.play_track(interaction, voice_client, random_track)
        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "voice_client_locked"))

        await interaction.response.send_message(f"Now playing: **{random_track['title']}**")

    @select_random_track.error
    async def handle_select_random_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False, False), ("is_modifying", "voice_client_locked", "stop_flag"))

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send("An unknown error occurred.")

    @app_commands.command(name="replace", description="Replaces a track with another one. See entry in /help for more info.")
    @app_commands.describe(
        track_name="Name (or index, in case <by_index> is True) of the track to replace.",
        new_track_query="URL or search query. Refer to help entry for valid URLs.",
        search_provider="The provider to use for search queries. URLs ignore this.",
        by_index="Replace a track by its index."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.choices(
        search_provider=[
            app_commands.Choice(name="SoundCloud search", value="soundcloud"),
            app_commands.Choice(name="YouTube search", value="youtube")
        ]
    )
    @app_commands.guild_only
    async def replace_track(self, interaction: Interaction, track_name: str, new_track_query: str, search_provider: app_commands.Choice[str]=None, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to replace.") or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status.") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        is_looping_queue = self.guild_states[interaction.guild.id]["is_looping_queue"]
        queue = self.guild_states[interaction.guild.id]["queue"]

        await update_guild_states(self.guild_states, interaction, (True, True), ("is_modifying", "is_extracting"))

        result = await replace_track_in_queue(self.guild_states, interaction, queue, track_name, new_track_query, by_index=by_index, provider=search_provider)
        if isinstance(result, Error):
            await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
            await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

            await interaction.followup.send(result.msg)
            return

        if is_looping_queue:
            await update_loop_queue_replace(self.guild_states, interaction, result[1], result[0])

        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        await interaction.followup.send(
            f"Replaced track **{result[1]['title']}** with **{result[0]['title']}**."
        )

        await check_users_in_channel(self.guild_states, interaction)

    @replace_track.error
    async def handle_replace_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send("An unknown error occurred.")

    @app_commands.command(name="loop", description="Loops the current or specified track. Functions as a toggle.")
    @app_commands.describe(
        track_name="The track to loop's name or index. (if <by_index> is True)",
        by_index="Whether or not to search for track by its index."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def loop_track(self, interaction: Interaction, track_name: str=None, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            (not track_name and not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!")) or\
            not await check_guild_state(self.guild_states, interaction, "voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return
        
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        queue = self.guild_states[interaction.guild.id]["queue"]

        if not is_looping:
            if track_name:

                if not await check_guild_state(self.guild_states, interaction) or\
                    not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to loop."):
                    return

                found_track = await find_track(track_name, queue, by_index)

                if isinstance(found_track, Error):
                    await interaction.response.send_message(found_track.msg)
                    return
                
                await update_guild_state(self.guild_states, interaction, found_track[0], "track_to_loop")
            else:
                await update_guild_state(self.guild_states, interaction, current_track, "track_to_loop")
            await update_guild_state(self.guild_states, interaction, True, "is_looping")
            
            await interaction.response.send_message(f"Loop enabled!\nWill loop '**{self.guild_states[interaction.guild.id]['track_to_loop']['title']}**'.")
        else:
            await update_guild_states(self.guild_states, interaction, (None, False), ("track_to_loop", "is_looping"))
            await interaction.response.send_message("Loop disabled!")

    @loop_track.error
    async def handle_loop_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="random", description="Randomizes track selection. Functions as a toggle.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def randomize_track_selection(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return

        is_random = self.guild_states[interaction.guild.id]["is_random"]

        if not is_random:
            await update_guild_state(self.guild_states, interaction, True, "is_random")
            await interaction.response.send_message("Track randomization enabled!\nWill choose a random track from the queue at next playback.")
        else:
            await update_guild_state(self.guild_states, interaction, False, "is_random")
            await interaction.response.send_message("Track randomization disabled!")

    @randomize_track_selection.error
    async def handle_randomize_track_selection_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return  
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="queueloop", description="Loops the queue. Functions as a toggle.")
    @app_commands.describe(
        include_current_track="Whether or not to keep the current track. Has no effect when disabling."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def loop_queue(self, interaction: Interaction, include_current_track: bool=True):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return

        queue = self.guild_states[interaction.guild.id]["queue"]
        is_looping_queue = self.guild_states[interaction.guild.id]["is_looping_queue"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]

        if not queue and not is_looping_queue:
            await interaction.response.send_message("Queue is empty, cannot enable queue loop!")
            return

        if not is_looping_queue:
            new_queue = deepcopy(queue)
            if current_track is not None and include_current_track:
                new_queue.insert(0, current_track)

            await update_guild_states(self.guild_states, interaction, (True, new_queue), ("is_looping_queue", "queue_to_loop"))
            
            await interaction.response.send_message(f"Queue loop enabled!\nWill loop **{len(new_queue)}** tracks at the end of the queue.")
        else:
            await update_guild_state(self.guild_states, interaction, False, "is_looping_queue")
            queue_to_loop.clear()
            
            await interaction.response.send_message("Queue loop disabled!")

    @loop_queue.error
    async def handle_loop_queue_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="clear", description="Removes every track from the queue.")
    @app_commands.describe(
        clear_history="Include track history in removal. (default False)",
        clear_loop_queue="Include the loop queue in removal. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def clear_queue(self, interaction: Interaction, clear_history: bool=False, clear_loop_queue: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return
        
        queue = self.guild_states[interaction.guild.id]["queue"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]
        track_history = self.guild_states[interaction.guild.id]["queue_history"]

        track_count = len(queue)
        track_history_count = len(track_history)

        await update_guild_state(self.guild_states, interaction, True)

        queue.clear()
        if clear_history:
            track_history.clear()
        if clear_loop_queue:
            queue_to_loop.clear()

        await update_guild_state(self.guild_states, interaction, False)

        await interaction.response.send_message(f"The queue is now empty.\n"
                                                f"Removed **{track_count}** items from queue{f' and **{track_history_count}** items from track history' if clear_history else ''}.")

    @clear_queue.error
    async def handle_clear_queue_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) and\
        self.guild_states.get(interaction.guild.id, None) is None:
            await interaction.response.send_message("Cannot clear queue.\nReason: No longer in voice channel.")
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False)

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="remove", description="Removes given tracks from the queue. See entry in /help for more info.")
    @app_commands.describe(
        track_names="A semicolon separated list of names (or indices, if <by_index> is True) of the tracks to remove.",
        by_index="Remove tracks by their index."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def remove_track(self, interaction: Interaction, track_names: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to remove.") or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return

        queue = self.guild_states[interaction.guild.id]["queue"]
        is_looping_queue = self.guild_states[interaction.guild.id]["is_looping_queue"]

        await update_guild_state(self.guild_states, interaction, True)

        found = await remove_track_from_queue(split(track_names), queue, by_index)
        if isinstance(found, Error):
            await update_guild_state(self.guild_states, interaction, False)
            
            await interaction.response.send_message(found.msg)
            return

        if is_looping_queue:
            await update_loop_queue_remove(self.guild_states, interaction, found)

        await update_guild_state(self.guild_states, interaction, False)

        embed = generate_removed_tracks_embed(found)
        await interaction.response.send_message(embed=embed)

    @remove_track.error
    async def handle_remove_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False)

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="reposition", description="Repositions a track from its original index to a new index. See entry in /help for more info.")
    @app_commands.describe(
        track_name="The name (or index, if <by_index> is True) of the track to reposition.",
        new_index="The new index of the track. Must be > 0 and <= maximum queue index.",
        by_index="Reposition a track by its index."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def reposition_track(self, interaction: Interaction, track_name: str, new_index: int, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to reposition.") or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return
        
        queue = self.guild_states[interaction.guild.id]["queue"]

        await update_guild_state(self.guild_states, interaction, True)

        result = await reposition_track_in_queue(track_name, new_index, queue, by_index)
        if isinstance(result, Error):
            await update_guild_state(self.guild_states, interaction, False)

            await interaction.response.send_message(result.msg)
            return

        await update_guild_state(self.guild_states, interaction, False)
        
        await interaction.response.send_message(f"Repositioned track **{result[0]['title']}** from index **{result[1]}** to **{result[2]}**.")

    @reposition_track.error
    async def handle_reposition_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False)

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="shuffle", description="Shuffles the queue randomly.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def shuffle_queue(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to shuffle.") or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return

        queue = self.guild_states[interaction.guild.id]["queue"]
        if len(queue) < 2:
            await interaction.response.send_message("There are not enough tracks to shuffle! (Need 2 atleast)")
            return

        await update_guild_state(self.guild_states, interaction, True)

        shuffle(queue)

        await update_guild_state(self.guild_states, interaction, False)

        await interaction.response.send_message("Queue shuffled successfully!")

    @shuffle_queue.error
    async def handle_shuffle_queue_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False)

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="seek", description="Seeks to specified position in current track. See entry in /help for more info.")
    @app_commands.describe(
        time="The time to seek to. Must be HH:MM:SS or shorter version (ex. 1:30)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def seek_to(self, interaction: Interaction, time: str):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        current_track = self.guild_states[interaction.guild.id]["current_track"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        # We may want to keep this as a fallback in case the 'current_track' state is not clean. (unlikely but possible)
        if not voice_client.is_playing() and\
            not voice_client.is_paused():
            await interaction.followup.send("No track is currently playing!")
            return

        position_seconds = format_to_seconds(time.strip())
        
        if position_seconds is None:
            await interaction.followup.send("Invalid time format. Be sure to format it to **HH:MM:SS**.\n**MM** and **SS** must not be > **59**.")
            return
        
        await update_guild_states(self.guild_states, interaction, (True, True), ("voice_client_locked", "stop_flag"))
        await self.play_track(interaction, voice_client, current_track, position_seconds, "seek")
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.followup.send(f"Set track (**{current_track['title']}**) position to **{format_to_minutes(position_seconds)}**.")

    @seek_to.error
    async def handle_seek_to_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False), ("voice_client_locked", "stop_flag"))

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send("An unknown error occurred.")

    @app_commands.command(name="rewind", description="Rewinds the track by the specified time. See entry in /help for more info.")
    @app_commands.describe(
        time="The amount of time to rewind by. Must be HH:MM:SS or shorter version (ex. 1:50)."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def rewind_track(self, interaction: Interaction, time: str):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]

        if not voice_client.is_playing() and\
            not voice_client.is_paused():
            await interaction.followup.send("No track is currently playing!")
            return

        time_seconds = format_to_seconds(time.strip())
        
        if time_seconds is None:
            await interaction.followup.send("Invalid time format. Be sure to format it to **HH:MM:SS**.\n**MM** and **SS** must not be > **59**.")
            return
        
        start_time = self.guild_states[interaction.guild.id]["start_time"]
        if not voice_client.is_paused():
            await update_guild_state(
                self.guild_states,
                interaction,
                min(int(get_time() - start_time), format_to_seconds(current_track["duration"])),
                "elapsed_time"
            )
        
        rewind_time = self.guild_states[interaction.guild.id]["elapsed_time"] - time_seconds

        await update_guild_states(self.guild_states, interaction, (True, True), ("voice_client_locked", "stop_flag"))        
        await self.play_track(interaction, voice_client, current_track, rewind_time, "rewind")
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        elapsed_time = self.guild_states[interaction.guild.id]["elapsed_time"]
        await interaction.followup.send(f"Rewound track (**{current_track['title']}**) by **{format_to_minutes(time_seconds)}**. Now at **{format_to_minutes(elapsed_time)}**")

    @rewind_track.error
    async def handle_rewind_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False), ("voice_client_locked", "stop_flag"))

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send("An unknown error occurred.")

    @app_commands.command(name="forward", description="Forwards the track by the specified time. See entry in /help for more info.")
    @app_commands.describe(
        time="The amount of time to forward by. Must be HH:MM:SS or shorter version (ex. 2:00)."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def forward_track(self, interaction: Interaction, time: str):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(thinking=True)

        current_track = self.guild_states[interaction.guild.id]["current_track"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        if not voice_client.is_playing() and\
            not voice_client.is_paused():
            await interaction.followup.send("I'm not playing anything!")
            return

        time_in_seconds = format_to_seconds(time.strip())
        
        if time_in_seconds is None:
            await interaction.followup.send("Invalid time format. Be sure to format it to **HH:MM:SS**.\n**MM** and **SS** must not be > **59**.")
            return
        
        start_time = self.guild_states[interaction.guild.id]["start_time"]
        if not voice_client.is_paused():
            await update_guild_state(
                self.guild_states,
                interaction,
                min(int(get_time() - start_time), format_to_seconds(current_track["duration"])),
                "elapsed_time"
            )

        position = self.guild_states[interaction.guild.id]["elapsed_time"] + time_in_seconds

        await update_guild_states(self.guild_states, interaction, (True, True), ("voice_client_locked", "stop_flag"))
        await self.play_track(interaction, voice_client, current_track, position, "forward")
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.followup.send(f"Forwarded track (**{current_track['title']}**) by **{format_to_minutes(time_in_seconds)}**. Now at **{format_to_minutes(position)}**.")

    @forward_track.error
    async def handle_forward_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False), ("voice_client_locked", "stop_flag"))

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send("An unknown error occurred.")

    @app_commands.command(name="queue", description="Shows tracks of a queue page.")
    @app_commands.describe(
        page="The queue page to view. Must be > 0."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_queue(self, interaction: Interaction, page: int):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue", [], "Queue is empty. Nothing to view.") or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_reading_queue", msg="I'm already reading the queue!"):
            return
        
        queue = self.guild_states[interaction.guild.id]["queue"]

        await update_guild_state(self.guild_states, interaction, True, "is_reading_queue")

        queue_pages = await asyncio.to_thread(get_pages, queue)

        page = max(1, min(page, len(queue_pages)))
        page -= 1

        embed = generate_queue_embed(queue_pages[page], page, len(queue_pages))

        await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")
        
        await interaction.response.send_message(embed=embed)

    @show_queue.error
    async def handle_show_queue_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="history", description="Shows tracks of a history page.")
    @app_commands.describe(
        page="The history page to view. Must be > 0."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_history(self, interaction: Interaction, page: int):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "queue_history", [], "Track history is empty. Nothing to view.") or\
            not await check_guild_state(self.guild_states, interaction, state="is_reading_history", msg="I'm already reading track history!"):
            return
        
        track_history = self.guild_states[interaction.guild.id]["queue_history"]
        
        await update_guild_state(self.guild_states, interaction, True, "is_reading_history")
        
        history_pages = await asyncio.to_thread(get_pages, track_history)

        page = max(1, min(page, len(history_pages)))
        page -= 1

        embed = generate_queue_embed(history_pages[page], page, len(history_pages), True)

        await update_guild_state(self.guild_states, interaction, False, "is_reading_history")

        await interaction.response.send_message(embed=embed)

    @show_history.error
    async def handle_show_history_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
            
        await update_guild_state(self.guild_states, interaction, False, "is_reading_history")

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="progress", description="Show info about the current extraction process.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_extraction(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "is_extracting", False, "I'm not extracting anything!"):
            return

        current_query = self.guild_states[interaction.guild.id]["current_query"]
        max_queries = self.guild_states[interaction.guild.id]["max_queries"]
        current_query_amount = self.guild_states[interaction.guild.id]["query_amount"]

        embed = generate_extraction_embed(current_query, max_queries, current_query_amount)

        await interaction.response.send_message(embed=embed)

    @show_extraction.error
    async def handle_show_extraction_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="epoch", description="Shows the elapsed time since the first track.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_start_time(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
        not await check_channel(self.guild_states, interaction):
            return
        
        start_time = self.guild_states[interaction.guild.id]["general_start_time"]
        join_time = self.guild_states[interaction.guild.id]["general_start_date"]

        if not start_time or not join_time:
            await interaction.response.send_message("Play a track first.")
            return
        
        formatted_start_time = format_to_minutes(int(get_time() - start_time))
        formatted_join_time = join_time.strftime("%d/%m/%Y @ %H:%M:%S")

        embed = generate_epoch_embed(formatted_join_time, formatted_start_time)

        await interaction.response.send_message(embed=embed)

    @show_start_time.error
    async def handle_show_start_time_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="yoink", description="DMs current track info to the user who invoked the command.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def dm_track_info(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return

        current_track = self.guild_states[interaction.guild.id]["current_track"]

        embed = generate_yoink_embed(current_track)
        
        await interaction.user.send(embed=embed)
        await interaction.response.send_message("Message sent!", ephemeral=True)

    @dm_track_info.error
    async def handle_dm_track_info_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, discord.errors.Forbidden):
            await interaction.response.send_message("I cannot send a message to you! Check your privacy settings and try again.", ephemeral=True)
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="nowplaying", description="Shows rich information about the current track.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_current_track_info(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return
        
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        info = self.guild_states[interaction.guild.id]["current_track"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]
        track_to_loop = self.guild_states[interaction.guild.id]["track_to_loop"]
        queue_state_being_modified = self.guild_states[interaction.guild.id]["is_reading_queue"] or self.guild_states[interaction.guild.id]["is_modifying"]
        
        if voice_client.is_playing():
            fixed_elapsed_time = min(int(get_time() - self.guild_states[interaction.guild.id]["start_time"]), format_to_seconds(info["duration"]))
            elapsed_time = format_to_minutes(fixed_elapsed_time)
        else:
            elapsed_time = format_to_minutes(int(self.guild_states[interaction.guild.id]["elapsed_time"]))
        
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        is_random = self.guild_states[interaction.guild.id]["is_random"]
        is_looping_queue = self.guild_states[interaction.guild.id]["is_looping_queue"]

        embed = generate_current_track_embed(
            info=info,
            queue=queue,
            queue_to_loop=queue_to_loop,
            track_to_loop=track_to_loop,
            elapsed_time=elapsed_time,
            looping=is_looping,
            random=is_random,
            queueloop=is_looping_queue,
            is_modifying_queue=queue_state_being_modified
        )
        await interaction.response.send_message(embed=embed)

    @show_current_track_info.error
    async def handle_show_current_track_info_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="allow-greetings", description="Enables/Disables the bot from greeting users that join the current voice channel.")
    @app_commands.describe(
        enable="New value of the flag."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    async def set_allow_greetings(self, interaction: Interaction, enable: bool):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="allow_greetings", condition=enable, msg=f"Setting is already {'enabled' if enable else 'disabled'}.") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked! Wait for the other action first."):
            return
        
        await update_guild_state(self.guild_states, interaction, enable, "allow_greetings")

        await interaction.response.send_message("Settings updated!")

    @set_allow_greetings.error
    async def handle_set_allow_greetings_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="allow-voice-status-edit", description="Enables/Disables the bot from changing the voice status to 'Listening to...'")
    @app_commands.describe(
        enable="New value of the flag."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    async def set_allow_voice_status_edit(self, interaction: Interaction, enable: bool):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="allow_voice_status_edit", condition=enable, msg=f"Setting is already {'enabled' if enable else 'disabled'}.") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked! Wait for the other action first."):
            return
        
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        voice_status = self.guild_states[interaction.guild.id]["voice_status"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        await update_guild_states(self.guild_states, interaction, (True, enable), ("voice_client_locked", "allow_voice_status_edit"))
        
        if not enable and voice_status is not None:
            await update_guild_state(self.guild_states, interaction, None, "voice_status")
            await set_voice_status(self.guild_states, interaction)
        elif current_track is not None and voice_status is None:
            status = f"Listening to '{current_track['title']}' {'(paused)' if voice_client.is_paused() else ''}"
            
            await update_guild_state(self.guild_states, interaction, status, "voice_status")
            await set_voice_status(self.guild_states, interaction)

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.response.send_message("Settings updated!")

    @set_allow_voice_status_edit.error
    async def handle_set_voice_status_edit_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    """ Playlist commands """

    @app_commands.command(name="playlist-view", description="Shows the tracks of a playlist page.")
    @app_commands.describe(
        playlist_name="The playlist to display's name.",
        page="The page to show. Must be > 0 and <= maximum playlist index."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_playlist(self, interaction: Interaction, playlist_name: str, page: int):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return

        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)

        result = await self.playlist.get_playlist(content, playlist_name)
        await unlock_playlist(locked, content, playlist_name)
        
        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
            return

        playlist_pages = await asyncio.to_thread(get_pages, result)

        page = max(1, min(page, len(playlist_pages)))
        page -= 1

        embed = generate_queue_embed(playlist_pages[page], page, len(playlist_pages), False, True)

        await interaction.followup.send(embed=embed)

        await check_users_in_channel(self.guild_states, interaction)

    @show_playlist.error
    async def handle_show_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-save", description="Creates or updates a playlist with the current queue. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The new playlist's name.",
        add_current_track="Whether or not to add the current track, if any. (default True)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def save_queue_in_playlist(self, interaction: Interaction, playlist_name: str, add_current_track: bool=True):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)

        queue = deepcopy(self.guild_states[interaction.guild.id]["queue"])
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        if not queue and not current_track:
            await unlock_playlist(locked, content, playlist_name)

            await interaction.followup.send("Queue is empty. Nothing to add.")
            return
        
        if current_track is not None and add_current_track:
            queue.insert(0, current_track)

        success = await self.playlist.add_queue(interaction, content, playlist_name, queue)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(success, Error):
            await interaction.followup.send(success.msg)
        elif isinstance(success, tuple):
            write_result = success[0]
            added = success[1]

            if not isinstance(write_result, Error):
                embed = generate_added_track_embed(added, True)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @save_queue_in_playlist.error
    async def handle_save_queue_in_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-save-current", description="Saves the current track to a playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to modify or create's name.",
        index="The index at which the track should be placed. Must be > 0. Ignore this field for last one."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def save_current_in_playlist(self, interaction: Interaction, playlist_name: str, index: int=None):
        if not await user_has_role(interaction) or\
        not await user_has_role(interaction, playlist=True) or\
        not await check_channel(self.guild_states, interaction) or\
        not await check_guild_state(self.guild_states, interaction, "current_track", None, "No track is currently playing!"):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]

        if await is_playlist_locked(locked):
            await interaction.followup.send("A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)

        success = await self.playlist.place(interaction, content, playlist_name, current_track, index)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(success, Error):
            await interaction.followup.send(success.msg)
        elif isinstance(success, tuple):
            write_result = success[0]
            added_track = success[1]
            index = success[2]

            if not isinstance(write_result, Error):
                await interaction.followup.send(f"Placed track **{added_track['title']}** at index **{index}** of playlist **{playlist_name}**.")
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @save_current_in_playlist.error
    async def handle_save_current_in_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-select", description="Selects tracks in a playlist and adds them to the queue. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The name of the playlist to select.",
        clear_current_queue="Whether or not to clear the current queue.",
        range_start="The range to start track selection from.",
        range_end="The range where track selection will stop."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def select_playlist(self, interaction: Interaction, playlist_name: str, clear_current_queue: bool=False, range_start: int=0, range_end: int=0):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status."):
            return
        
        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]

        if clear_current_queue:
            queue.clear()
            queue_to_loop.clear()

        is_queue_length_ok = await check_queue_length(interaction, self.max_track_limit, queue)
        if not is_queue_length_ok:
            return

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)

        await update_guild_states(self.guild_states, interaction, (True, True), ("is_modifying", "is_extracting"))

        success = await self.playlist.select(self.guild_states, self.max_track_limit, interaction, content, playlist_name, range_start, range_end)
        
        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await unlock_playlist(locked, content, playlist_name)
        
        if isinstance(success, list):
            if not voice_client.is_playing() and\
                not voice_client.is_paused():
                await self.play_next(interaction)

            embed = generate_added_track_embed(success)
            await interaction.followup.send(embed=embed)
        elif isinstance(success, Error):
            await interaction.followup.send(success.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @select_playlist.error
    async def handle_select_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-create", description="Creates a new empty playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The new playlist's name. Must be < 50 (default) characters."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def create_playlist(self, interaction: Interaction, playlist_name: str):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)

        success = await self.playlist.create(interaction, content, playlist_name)
        await unlock_playlist(locked, content, playlist_name)
            
        if isinstance(success, Error):
            await interaction.followup.send(success.msg)
        else:
            await interaction.followup.send(f"Playlist **{playlist_name}** has been created.")

        await check_users_in_channel(self.guild_states, interaction)

    @create_playlist.error
    async def handle_create_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-delete", description="Deletes a saved playlist or its contents. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to delete's name.",
        erase_contents_only="Whether or not to erase only the contents. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def delete_playlist(self, interaction: Interaction, playlist_name: str, erase_contents_only: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)

        success = await self.playlist.delete(interaction, content, playlist_name, erase_contents_only)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(success, Error):
            await interaction.followup.send(success.msg)
        elif isinstance(success, tuple):
            write_result = success[0]
            removed_tracks = success[1]
            removed_tracks_len = len(removed_tracks)

            if not isinstance(write_result, Error):
                await interaction.followup.send(f"**{removed_tracks_len}** tracks {'have' if removed_tracks_len > 1 else 'has'} been removed from playlist **{playlist_name}**.")
            else:
                await interaction.followup.send(write_result.msg)
        else:
            await interaction.followup.send(f"Playlist **{playlist_name}** has been deleted.")

        await check_users_in_channel(self.guild_states, interaction)

    @delete_playlist.error
    async def handle_delete_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-remove", description="Remove specified track(s) from a playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to remove tracks from's name.",
        track_names="A semicolon separated list of names (or indices, if <by_index> is True) of the tracks to remove.",
        by_index="Remove tracks by their index."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def remove_playlist_track(self, interaction: Interaction, playlist_name: str, track_names: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)

        success = await self.playlist.remove(interaction, content, playlist_name, track_names, by_index)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(success, Error):
            await interaction.followup.send(success.msg)
        elif isinstance(success, tuple):
            write_result = success[0]
            removed_tracks = success[1]

            if not isinstance(write_result, Error):
                embed = generate_removed_tracks_embed(removed_tracks, True)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @remove_playlist_track.error
    async def handle_remove_playlist_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-delete-all", description="Deletes all playlists saved in the current guild. See entry in /help for more info.")
    @app_commands.describe(
        rewrite="Rewrite the entire structure. Useful if it cannot be read anymore."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def delete_all_playlists(self, interaction: Interaction, rewrite: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)
        
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        content = await self.playlist.read(interaction)
        success = await self.playlist.delete_all(interaction, content, locked, rewrite)

        if isinstance(success, Error):
            await interaction.followup.send(success.msg)
        else:
            await interaction.followup.send(f'Deleted **{len(content)}** playlist(s).' if not rewrite else 'Structure rewritten successfully.')

        await check_users_in_channel(self.guild_states, interaction)

    @delete_all_playlists.error
    async def handle_delete_all_playlists_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-rename", description="Renames a playlist to a new specified name. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to rename's name.",
        new_playlist_name="New name to assign to the playlist. Must be < 50 (default) characters."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def rename_playlist(self, interaction: Interaction, playlist_name: str, new_playlist_name: str):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)
        
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)

        success = await self.playlist.rename(interaction, content, playlist_name, new_playlist_name)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(success, Error):
            await interaction.followup.send(success.msg)
        elif isinstance(success, tuple):
            write_result = success[0]
            old_name = success[1]
            new_name = success[2]

            if not isinstance(write_result, Error):
                await interaction.followup.send(f"Renamed playlist **{old_name}** to **{new_name}**.")
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @rename_playlist.error
    async def handle_rename_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-replace", description="Replaces a playlist track with a different one. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to modify's name.",
        old="The name (or index, if <by_index> is True) of the track to replace.",
        new="URL or search query. Refer to help entry for valid URLs.",
        search_provider="The provider used for search query. URLs ignore this.",
        by_index="Replace a track by its index."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.choices(
        search_provider=[
            app_commands.Choice(name="SoundCloud search", value="soundcloud"),
            app_commands.Choice(name="YouTube search", value="youtube")
        ]
    )
    @app_commands.guild_only
    async def replace_playlist_track(self, interaction: Interaction, playlist_name: str, old: str, new: str, search_provider: app_commands.Choice[str]=None, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status."):
            return

        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)

        await update_guild_state(self.guild_states, interaction, True, "is_extracting")

        success = await self.playlist.replace(self.guild_states, interaction, content, playlist_name, old, new, search_provider, by_index)
        
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(success, Error):
            await interaction.followup.send(success.msg)
        elif isinstance(success, tuple):
            write_result = success[0]
            old_track = success[1]
            new_track = success[2]

            if not isinstance(write_result, Error):
                await interaction.followup.send(f"Replaced track **{old_track['title']}** with track **{new_track['title']}**")
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @replace_playlist_track.error
    async def handle_replace_playlist_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
            
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-reposition", description="Repositions a playlist track to a new index. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to modify's name.",
        track_name="The name (or index, in case <by_index> is True) of the track to reposition.",
        new_index="The new index of the track. Must be > 0 and < maximum playlist index.",
        by_index="Reposition a track by its index."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def reposition_playlist_track(self, interaction: Interaction, playlist_name: str, track_name: str, new_index: int, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)

        success = await self.playlist.reposition(interaction, content, playlist_name, track_name, new_index, by_index)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(success, Error):
            await interaction.followup.send(success.msg)
        elif isinstance(success, tuple):
            write_result = success[0]
            track = success[1]
            old_index = success[2]
            new_index = success[3]

            if not isinstance(write_result, Error):
                await interaction.followup.send(f"Repositioned track **{track['title']}** from index **{old_index}** to **{new_index}**")
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @reposition_playlist_track.error
    async def handle_reposition_playlist_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-add", description="Adds specified tracks to a playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to modify's name.",
        queries="A semicolon separated list of URLs or search queries. Refer to help entry for valid URLs.",
        search_provider="The provider to use for search queries. URLs ignore this."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.choices(
        search_provider=[
            app_commands.Choice(name="SoundCloud search", value="soundcloud"),
            app_commands.Choice(name="YouTube search", value="youtube")
        ]
    )
    @app_commands.guild_only
    async def add_playlist_track(self, interaction: Interaction, playlist_name: str, queries: str, search_provider: app_commands.Choice[str]=None):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status."):
            return

        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)

        queries_split = await check_input_length(interaction, self.max_query_limit, split(queries))

        await update_guild_state(self.guild_states, interaction, True, "is_extracting")

        allowed_query_types = ("YouTube", "YouTube search", "SoundCloud", "SoundCloud search", "Bandcamp")
        success = await self.playlist.add(self.guild_states, interaction, content, playlist_name, queries_split, allowed_query_types=allowed_query_types, provider=search_provider)

        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(success, Error):
            await interaction.followup.send(success.msg)
        elif isinstance(success, tuple):
            write_result = success[0]
            added_tracks = success[1]
            
            if not isinstance(write_result, Error):
                embed = generate_added_track_embed(added_tracks, True)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @add_playlist_track.error
    async def handle_add_playlist_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-fetch-track", description="Adds tracks from a playlist to the queue. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to fetch tracks from's name.",
        track_names="A semicolon separated list of names (or indices, if <by_index> is True) of the tracks to fetch.",
        by_index="Fetch tracks by their index."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def fetch_playlist_track(self, interaction: Interaction, playlist_name: str, track_names: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status."):
            return

        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        queue = self.guild_states[interaction.guild.id]["queue"]

        queries_split = await check_input_length(interaction, self.max_query_limit, split(track_names))
        is_queue_length_ok = await check_queue_length(interaction, self.max_track_limit, queue)
        if not is_queue_length_ok:
            return

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)

        await update_guild_states(self.guild_states, interaction, (True, True), ("is_modifying", "is_extracting"))        

        success = await self.playlist.fetch(self.guild_states, self.max_track_limit, interaction, content, playlist_name, queries_split, by_index=by_index)

        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(success, Error):
            await interaction.followup.send(success.msg)
        elif isinstance(success, list):
            if not voice_client.is_playing() and\
            not voice_client.is_paused():
                await self.play_next(interaction)

            embed = generate_added_track_embed(success, False)
            await interaction.followup.send(embed=embed)

        await check_users_in_channel(self.guild_states, interaction)

    @fetch_playlist_track.error
    async def handle_fetch_playlist_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-fetch-random-track", description="Fetches random tracks from a specified playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to get tracks from's name.",
        amount="The amount of random tracks to fetch, must be <= 25 (default)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def choose_random_playlist_tracks(self, interaction: Interaction, playlist_name: str, amount: int=1):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status."):
            return
        
        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        queue = self.guild_states[interaction.guild.id]["queue"]

        amount = max(1, min(amount, 25))
        is_queue_length_ok = await check_queue_length(interaction, self.max_track_limit, queue)
        
        if not is_queue_length_ok:
            return

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)

        result = await self.playlist.get_playlist(content, playlist_name)
        if isinstance(result, Error):
            await unlock_playlist(locked, content, playlist_name)

            await interaction.followup.send(result.msg)
            return
        
        await update_guild_states(self.guild_states, interaction, (True, True), ("is_modifying", "is_extracting"))

        random_tracks = await get_random_tracks_from_playlist(result, amount)
        success = await self.playlist.fetch(self.guild_states, self.max_track_limit, interaction, content, playlist_name, random_tracks, True)

        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(success, Error):
            await interaction.followup.send(success.msg)
        elif isinstance(success, list):
            if not voice_client.is_playing() and\
            not voice_client.is_paused():
                await self.play_next(interaction)

            embed = generate_added_track_embed(success, False)
            await interaction.followup.send(embed=embed)

        await check_users_in_channel(self.guild_states, interaction)

    @choose_random_playlist_tracks.error
    async def handle_choose_random_playlist_tracks(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_states(self.guild_states, interaction, (False, False), ("is_modifying", "is_extracting"))
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-add-yt-playlist", description="Imports a playlist from YouTube. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to add the tracks to's name.",
        query="A YouTube playlist URL."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def add_playlist(self, interaction: Interaction, playlist_name: str, query: str):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status."):
            return
        
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)
        
        await update_guild_state(self.guild_states, interaction, True, "is_extracting")

        allowed_query_types = ("YouTube Playlist",)
        success = await self.playlist.add(self.guild_states, interaction, content, playlist_name, [query], allowed_query_types=allowed_query_types)

        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(success, Error):
            await interaction.followup.send(success.msg)
        elif isinstance(success, tuple):
            write_result = success[0]
            added_tracks = success[1]
            
            if not isinstance(write_result, Error):
                embed = generate_added_track_embed(added_tracks, True)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_result.msg)

        await check_users_in_channel(self.guild_states, interaction)

    @add_playlist.error
    async def handle_add_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-rename-track", description="Renames tracks to new names. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to modify's name.",
        old_track_names="A semicolon separated list of names (or indices, if <by_index> is True) of the tracks to rename.",
        new_track_names=f"A semicolon separated list of new names to assign to each old name.",
        by_index="Rename tracks by their index."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def rename_playlist_track(self, interaction: Interaction, playlist_name: str, old_track_names: str, new_track_names: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)
        
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.read(interaction)
            await lock_playlist(interaction, content, locked, playlist_name)

        success = await self.playlist.rename_item(interaction, content, playlist_name, old_track_names, new_track_names, by_index)
        await unlock_playlist(locked, content, playlist_name)

        if isinstance(success, Error):
            await interaction.followup.send(success.msg)
        elif isinstance(success, tuple):
            write_result = success[0]
            modified_tracks = success[1]

            if not isinstance(write_result, Error):
                embed = generate_edited_tracks_embed(modified_tracks)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(write_result.msg)
        
        await check_users_in_channel(self.guild_states, interaction)

    @rename_playlist_track.error
    async def handle_rename_playlist_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await unlock_all_playlists(self.guild_states[interaction.guild.id]["locked_playlists"])

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')

    @app_commands.command(name="playlist-get-saved", description="Shows saved playlists for this guild.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_saved_playlists(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await is_playlist_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return

        content = await self.playlist.read(interaction)

        result = await self.playlist.get_available(content)
        if isinstance(result, Error):
            await interaction.followup.send(result.msg)
            return

        playlists_string = "".join([f"- **{key}**\n" for key in result])
        remaining_slots = self.playlist.max_limit - len(result)

        await interaction.followup.send(f"Saved playlists\n{playlists_string}Remaining slots: **{remaining_slots}**.")

        await check_users_in_channel(self.guild_states, interaction)

    @show_saved_playlists.error
    async def handle_show_saved_playlists_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occurred.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occurred.')