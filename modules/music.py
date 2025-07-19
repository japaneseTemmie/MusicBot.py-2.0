""" Simple music module for discord.py bot.\n
Includes a class with methods for managing a queue and track playback."""

from settings import *
from helpers import *
from handlers import *
from roles import *
from embedgenerator import *
from playlist import PlaylistManager
from bot import Bot

class MusicCog(commands.Cog):
    def __init__(self, client: Bot):
        self.client = client
        self.guild_states = {}
        self.max_track_limit = 100
        self.max_history_track_limit = 200
        self.max_query_limit = 25
        
        self.playlist = PlaylistManager(self.client)

    async def close_voice_clients(self):
        """ Close any leftover VCs and cleanup their open audio sources, if any. """
        
        VOICE_OPERATIONS_LOCKED_PERMANENTLY.set()
        log(f"Voice state permanently locked: {VOICE_OPERATIONS_LOCKED_PERMANENTLY.is_set()}")
        
        log("Closing voice clients..")
        
        async def _close(vc):
            log(f"Closing connection to channel ID {vc.channel.id}")
            
            await update_guild_state(self.guild_states, vc, True, "stop_flag")
            vc.stop()

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
        bot_voice_channel = member.guild.voice_client.channel if member.guild.voice_client is not None else None
        
        if member.id != self.client.user.id:
            if (bot_voice_channel is not None and before.channel == bot_voice_channel) and\
                (after.channel is None or after.channel is not None) and\
                member.guild.id in self.guild_states:
                """ User left, check member count in voice channel. """
                
                await check_users_in_channel(self.guild_states, self.playlist, member)
            elif (before.channel is None or before.channel is not None) and\
                (bot_voice_channel is not None and after.channel == bot_voice_channel) and\
                member.guild.id in self.guild_states:
                """ New user joined, why not greet them? """
                
                await greet_new_user_in_vc(self.guild_states, bot_voice_channel, member)
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
        VOICE_OPERATIONS_LOCKED_PERMANENTLY.is_set():
            return

        channel = interaction.user.voice.channel if interaction.user.voice else None
        current_channel = interaction.guild.voice_client.channel if interaction.guild.voice_client else None
        permissions = channel.permissions_for(interaction.guild.me) if channel is not None else None

        if channel is None:
            await interaction.response.send_message("Join a voice channel first.")
        elif channel.type == discord.ChannelType.stage_voice:
            await interaction.response.send_message(f"I can't join channel **{channel.name}**! Stage channels scare me!")
        elif channel is not None and\
            current_channel is not None and\
            channel == current_channel:
            await interaction.response.send_message("I'm already in your voice channel!")
        elif current_channel is not None:
            await interaction.response.send_message(f"I'm already in **{current_channel.name}**!")
        elif permissions is not None and\
        (not permissions.connect or not permissions.speak):
            await interaction.response.send_message(f"I don't have permission to join your channel!")
        else:
            log(f"[CONNECT] Requested to join channel ID {channel.id} in guild ID {channel.guild.id}")

            voice_client = await channel.connect()
            self.guild_states[interaction.guild.id] = await get_default_state(voice_client, interaction.channel)
            
            log(f"[GUILDSTATE] Allocated space for guild ID {interaction.guild.id} in guild states.")

            await interaction.response.send_message(f"Connected to **{channel.name}**!")

            await check_users_in_channel(self.guild_states, self.playlist, interaction) # awful fix to avoid users trapping the bot in a vc when using the join command

    @join_channel.error
    async def handle_join_error(self, interaction: Interaction, error):
        if isinstance(error, asyncio.TimeoutError):
            await interaction.response.send_message("Connection timed out.", ephemeral=True)
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)

    @app_commands.command(name="leave", description="Makes the bot leave your voice channel.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def leave_channel(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use /progress to see the status.") or\
            VOICE_OPERATIONS_LOCKED_PERMANENTLY.is_set():
            return

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        if await self.playlist.is_locked(locked):
            await interaction.response.send_message(f"A playlist is currently locked, please wait.")
            return

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        if voice_client.is_connected():
            log(f"[DISCONNECT] Requested to leave channel ID {voice_client.channel.id} in guild ID {interaction.guild.id}")

            if voice_client.is_playing() or voice_client.is_paused():
                await update_guild_state(self.guild_states, interaction, True, "stop_flag")
                voice_client.stop()

            await voice_client.disconnect()
            await interaction.response.send_message(f"Disconnected from **{voice_client.channel.name}**.")

    @leave_channel.error
    async def handle_leave_error(self, interaction: Interaction, error):
        if isinstance(error, asyncio.TimeoutError):
            await interaction.response.send_message("Connection timed out.", ephemeral=True)
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)

    @app_commands.command(name="add", description="Adds a track to the queue. See entry in /help for more info.")
    @app_commands.describe(
        queries="A semicolon separated list of YT, NG, SC, BC URLs or YT search queries.",
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def add_track(self, interaction: Interaction, queries: str):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status."):
            return

        await update_guild_state(self.guild_states, interaction, True)
        await update_guild_state(self.guild_states, interaction, True, "is_extracting")

        await interaction.response.defer(thinking=True)
        
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        is_looping_queue = self.guild_states[interaction.guild.id]["is_looping_queue"]

        queries_split = await check_input_length(interaction, self.max_query_limit, split(queries))

        is_queue_too_long = await check_queue_length(interaction, self.max_track_limit, queue) == RETURN_CODES["QUEUE_TOO_LONG"]
        if is_queue_too_long:
            await update_guild_state(self.guild_states, interaction, False)
            await update_guild_state(self.guild_states, interaction, False, "is_extracting")
            return

        found = await fetch_queries(self.guild_states, interaction, queries_split)

        await update_guild_state(self.guild_states, interaction, False)
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        if isinstance(found, list):
            await add_results_to_queue(interaction, found, queue, self.max_track_limit)
            
            if is_looping_queue:
                await update_loop_queue_add(self.guild_states, interaction)

            if not voice_client.is_playing() and\
                not voice_client.is_paused():
                await self.play_next(interaction)
            
            embed = generate_added_track_embed(results=found)

            await interaction.channel.send(embed=embed) if interaction.is_expired()\
            else await interaction.followup.send(embed=embed)
        elif isinstance(found, tuple):
            await handle_generic_extraction_errors(interaction, found)
            await check_users_in_channel(self.guild_states, self.playlist, interaction)

    @add_track.error
    async def handle_add_error(self, interaction: Interaction, error):
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

        await update_guild_state(self.guild_states, interaction, False)
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.followup.send("An unknown error occured.") if interaction.response.is_done() else\
        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    async def play_track(self, interaction: Interaction, voice_client: discord.VoiceClient, track: dict, position: int=0, state: str | None=None):
        if not voice_client or not voice_client.is_connected() or track is None:
            return
        
        position = max(0, min(position, format_minutes(track["duration"])))
        options = await get_ffmpeg_options(position)
        
        source = await discord.FFmpegOpusAudio.from_probe(track["url"], **options)

        try:
            voice_client.stop()
            voice_client.play(source, after=lambda _:self.client.loop.create_task(self.play_next(interaction)))
        except Exception as e:
            if CAN_LOG and LOGGER is not None:
                LOGGER.exception(e)
            
            await interaction.followup.send("An error occured while reading audio stream.")
            return

        history = self.guild_states[interaction.guild.id]["queue_history"]
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        track_to_loop = self.guild_states[interaction.guild.id]["track_to_loop"]
        general_start_time, general_start_date = self.guild_states[interaction.guild.id]["general_start_time"], self.guild_states[interaction.guild.id]["general_start_date"]

        if not general_start_time or not general_start_date:
            await update_guild_state(self.guild_states, interaction, get_time(), "general_start_time")
            await update_guild_state(self.guild_states, interaction, datetime.now(), "general_start_date")

        await update_guild_state(self.guild_states, interaction, get_time() - position, "start_time")
        await update_guild_state(self.guild_states, interaction, position, "elapsed_time")
        
        """Update track to loop if looping is enabled
        Cases in which this is useful:
        We already have a track set to loop, we use /playnow or something that overrides this, now we need to update the track to loop."""

        if is_looping and track_to_loop != track:
            await update_guild_state(self.guild_states, interaction, track, "track_to_loop")

        await update_guild_state(self.guild_states, interaction, track, "current_track")
        
        """ Only append if the maximum amount of tracks in the track history is not reached, if
            the position is less or equal to 0, if it's not looping the current track, and we're not
            altering the current track with commands like restart, seek, etc. """
        
        if len(history) >= self.max_history_track_limit:
            history.clear()

        if not position > 0 and\
            not is_looping and\
            state is None:

            history.append(track)

    async def play_next(self, interaction: Interaction):
        if self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif self.guild_states[interaction.guild.id]["stop_flag"]:
            await update_guild_state(self.guild_states, interaction, False, "stop_flag")
            return
        elif self.guild_states[interaction.guild.id]["voice_client_locked"]:
            return

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        is_random = self.guild_states[interaction.guild.id]["is_random"]
        track_to_loop = self.guild_states[interaction.guild.id]["track_to_loop"]

        if await check_users_in_channel(self.guild_states, self.playlist, interaction):
            return

        await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")
        
        if not queue and not\
            is_looping and not\
            queue_to_loop:
            
            await update_guild_state(self.guild_states, interaction, None, "current_track")
            await update_guild_state(self.guild_states, interaction, 0, "start_time")
            await update_guild_state(self.guild_states, interaction, 0, "elapsed_time")
            await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

            await interaction.channel.send("Queue is empty.") if interaction.is_expired()\
            else await interaction.followup.send("Queue is empty.")
            return
        
        if not queue and queue_to_loop:
            queue = deepcopy(queue_to_loop)
            await update_guild_state(self.guild_states, interaction, queue, "queue")

        if track_to_loop and is_looping:
            track = track_to_loop
        elif is_random:
            track = queue.pop(queue.index(choice(queue)))
        else:
            track = queue.pop(0)

        if track and voice_client:
            await self.play_track(interaction, voice_client, track)

            if not is_looping:
                try:
                    await interaction.channel.send(f"Now playing: **{track['title']}**") if interaction.is_expired()\
                    else await interaction.followup.send(f"Now playing: **{track['title']}**")
                except Exception:
                    pass
        else:
            await interaction.channel.send("An error occured while getting track from the queue.") if interaction.is_expired()\
            else await interaction.followup.send("An error occured while getting track from the queue.")

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

    @app_commands.command(name="playnow", description="Plays the given query without saving it to the queue first. See entry in /help for more info.")
    @app_commands.describe(
        query="YouTube (video), Newgrounds, SoundCloud, Bandcamp URL or YouTube search query.",
        keep_current_track="Whether or not to keep the current track (if any) in the queue."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def play_track_now(self, interaction: Interaction, query: str, keep_current_track: bool=True):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status.") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nPlease wait for the current action first."):
            return
        
        if keep_current_track:
            if await check_queue_length(interaction, self.max_track_limit, self.guild_states[interaction.guild.id]["queue"]) == RETURN_CODES["QUEUE_TOO_LONG"] or\
            not await check_guild_state(self.guild_states, interaction):
                return

        await update_guild_state(self.guild_states, interaction, True, "is_extracting")
        await update_guild_state(self.guild_states, interaction, True)

        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        
        extracted_track = await fetch_query(self.guild_states, interaction, query, 1, 1, None, "YouTube Playlist")

        await update_guild_state(self.guild_states, interaction, False)
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        if isinstance(extracted_track, dict):
            if current_track is not None and keep_current_track:
                queue.insert(0, current_track)

            await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")
            if voice_client.is_playing() or voice_client.is_paused():
                await update_guild_state(self.guild_states, interaction, True, "stop_flag")
            
            await self.play_track(interaction, voice_client, extracted_track)

            await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

            await interaction.followup.send(f"Now playing: **{extracted_track["title"]}**")
        elif isinstance(extracted_track, int):
            await handle_generic_extraction_errors(interaction, extracted_track)
            await check_users_in_channel(self.guild_states, self.playlist, interaction)

    @play_track_now.error
    async def handle_playnow_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) and\
              self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")
        await update_guild_state(self.guild_states, interaction, False)
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.followup.send("An unknown error occurred.", ephemeral=True) if interaction.response.is_done() else\
        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="skip", description="Skips to next track in the queue.")
    @app_commands.describe(
        amount="The amount of tracks to skip. Starts from the current track. Must be <= 25"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def skip_track(self, interaction: Interaction, amount: int=1):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nWait for the other action first."):
            return

        queue = self.guild_states[interaction.guild.id]["queue"]
        is_random = self.guild_states[interaction.guild.id]["is_random"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]

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

        if skipped:
            embed = generate_skipped_tracks_embed(skipped)
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(f"Skipped track **{current_track['title']}**.")

    @skip_track.error
    async def handle_skip_error(self, interaction: Interaction, error):
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

    @app_commands.command(name="nextinfo", description="Shows information about the next track.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_next_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
        not await check_channel(self.guild_states, interaction) or\
        not await check_guild_state(self.guild_states, interaction) or\
        not await check_guild_state(self.guild_states, interaction, state="is_reading_queue", msg="Queue is already being read, please wait.") or\
        not await check_guild_state(self.guild_states, interaction) or\
        not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked! Wait for the other action first."):
            return
        
        await update_guild_state(self.guild_states, interaction, True, "is_reading_queue")
        
        is_random = self.guild_states[interaction.guild.id]["is_random"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        if is_random:
            await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")

            await interaction.response.send_message("Next track will be random.")
            return

        if queue:
            next_track = queue[0]
        elif queue_to_loop:
            next_track = queue_to_loop[0]
        else:
            await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")

            await interaction.response.send_message("Queue is empty. Nothing to preview.")
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
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")

        await interaction.response.send_message("An unknown error occured.", ephemeral=True)

    @app_commands.command(name="previousinfo", description="Shows information about the previous track.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_previous_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
        not await check_channel(self.guild_states, interaction) or\
        not await check_guild_state(self.guild_states, interaction, state="is_reading_history", msg="Track history is already being read, please wait.") or\
        not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked! Wait for the other action first."):
            return
        
        await update_guild_state(self.guild_states, interaction, True, "is_reading_history")
    
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        history = self.guild_states[interaction.guild.id]["queue_history"]
        
        previous = await get_previous(current_track, history)
        if isinstance(previous, int):
            await update_guild_state(self.guild_states, interaction, False, "is_reading_history")
            
            await handle_get_previous_error(interaction, previous)
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
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)
        
        await update_guild_state(self.guild_states, interaction, False, "is_reading_history")

        await interaction.response.send_message("An unknown error occured.", ephemeral=True)

    @app_commands.command(name="pause", description="Pauses track playback.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def pause_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_current_track(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return
        
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        if voice_client.is_paused():
            await interaction.response.send_message("I'm already paused!")
            return

        voice_client.pause()
        self.guild_states[interaction.guild.id]["elapsed_time"] = int(get_time() - self.guild_states[interaction.guild.id]["start_time"])

        await interaction.response.send_message("Paused track playback.")

    @pause_track.error
    async def handle_pause_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="resume", description="Resumes track playback.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def resume_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_current_track(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return
        
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        
        if not voice_client.is_paused():
            await interaction.response.send_message("I'm not paused!")
            return

        voice_client.resume()
        self.guild_states[interaction.guild.id]["start_time"] = int(get_time() - self.guild_states[interaction.guild.id]["elapsed_time"])

        await interaction.response.send_message("Resumed track playback.")

    @resume_track.error
    async def handle_resume_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="stop", description="Stops the current track and resets bot state.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def stop_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_current_track(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nWait for the other action first."):
            return

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]

        await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")

        self.guild_states[interaction.guild.id] = await get_default_state(voice_client, interaction.channel)
        
        await update_guild_state(self.guild_states, interaction, True, "stop_flag")
        voice_client.stop()

        await interaction.response.send_message(f"Stopped track **{current_track['title']}** and reset bot state.")

    @stop_track.error
    async def handle_stop_error(self, interaction: Interaction, error):
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

    @app_commands.command(name="restart", description="Restarts the current track.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def restart_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_current_track(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nWait for the other action first."):
            return
        
        await interaction.response.defer(thinking=True)

        await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")

        current_track = self.guild_states[interaction.guild.id]["current_track"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        
        await update_guild_state(self.guild_states, interaction, True, "stop_flag")
        await self.play_track(interaction, voice_client, current_track, state="restart")
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.followup.send(f"Restarted track **{current_track['title']}**.")

    @restart_track.error
    async def handle_restart_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="select", description="Selects a track from the queue and plays it. See entry in /help for more info.")
    @app_commands.describe(
        track_name="The name of the track to select.",
        by_index="Select track by its index. <track_name> must be a number."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def select_track(self, interaction: Interaction, track_name: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_queue(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nWait for the other action first."):
            return
        
        await update_guild_state(self.guild_states, interaction, True)

        queue = self.guild_states[interaction.guild.id]["queue"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        found = await find_track(track_name, queue, by_index)
        if isinstance(found, int):
            await update_guild_state(self.guild_states, interaction, False)

            await handle_not_found_error(interaction, found)
            return
        
        track_dict = queue.pop(found[1])

        await update_guild_state(self.guild_states, interaction, False)
        await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")

        if voice_client.is_playing() or voice_client.is_paused():
            await update_guild_state(self.guild_states, interaction, True, "stop_flag")
        await self.play_track(interaction, voice_client, track_dict)

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.response.send_message(f"Selected track **{found[0]['title']}**.")

    @select_track.error
    async def handle_select_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False)
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="replace", description="Replaces a track with another one. See entry in /help for more info.")
    @app_commands.describe(
        track_name="Name of the track to replace.",
        new_track_query="YouTube (video), Newgrounds, SoundCloud, Bandcamp URL or YouTube search query.",
        by_index="Replace a track by its index. <track_name> must be a number."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def replace_track(self, interaction: Interaction, track_name: str, new_track_query: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_queue(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status.") or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return
        
        await update_guild_state(self.guild_states, interaction, True)
        await update_guild_state(self.guild_states, interaction, True, "is_extracting")

        await interaction.response.defer(thinking=True)

        result = await replace_track_in_queue(self.guild_states, interaction, track_name, new_track_query, by_index=by_index)
        if isinstance(result, int):
            await update_guild_state(self.guild_states, interaction, False)
            await update_guild_state(self.guild_states, interaction, False, "is_extracting")
            await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

            await handle_not_found_error(interaction, result)
            await handle_generic_extraction_errors(interaction, result)
            
            return

        await update_guild_state(self.guild_states, interaction, False)
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        await interaction.followup.send(
            f"Replaced track **{result[1]["title"]}** with **{result[0]["title"]}**."
        )

        await check_users_in_channel(self.guild_states, self.playlist, interaction)

    @replace_track.error
    async def handle_replace_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False)
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.followup.send("An unknown error occurred.") if interaction.response.is_done() else\
        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="loop", description="Loops the current track. Functions as a toggle.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def loop_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_current_track(self.guild_states, interaction):
            return
        
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]

        if not is_looping:
            self.guild_states[interaction.guild.id]["track_to_loop"] = self.guild_states[interaction.guild.id]["current_track"]
            self.guild_states[interaction.guild.id]["is_looping"] = True
            
            await interaction.response.send_message(f"Loop enabled!\nWill loop track: **{self.guild_states[interaction.guild.id]['track_to_loop']['title']}**")
        else:
            self.guild_states[interaction.guild.id]["track_to_loop"] = None
            self.guild_states[interaction.guild.id]["is_looping"] = False

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
    async def randomize_track(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction):
            return

        is_random = self.guild_states[interaction.guild.id]["is_random"]

        if not is_random:
            self.guild_states[interaction.guild.id]["is_random"] = True
            await interaction.response.send_message("Track randomization enabled!\nWill choose a random track from the queue at next playback.")
        else:
            self.guild_states[interaction.guild.id]["is_random"] = False
            await interaction.response.send_message("Track randomization disabled!")

    @randomize_track.error
    async def handle_randomize_track_error(self, interaction: Interaction, error):
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
            not await check_guild_state(self.guild_states, interaction):
            return

        queue = self.guild_states[interaction.guild.id]["queue"]
        looping_queue = self.guild_states[interaction.guild.id]["is_looping_queue"]

        if not queue and not looping_queue:
            await interaction.response.send_message("Queue is empty, cannot enable queue loop!")
            return

        if not looping_queue:
            self.guild_states[interaction.guild.id]["is_looping_queue"] = True

            queue = self.guild_states[interaction.guild.id]["queue"]
            current_track = self.guild_states[interaction.guild.id]["current_track"]

            self.guild_states[interaction.guild.id]["queue_to_loop"] = deepcopy(queue)
            if current_track is not None and include_current_track:
                self.guild_states[interaction.guild.id]["queue_to_loop"].insert(0, current_track)
            
            await interaction.response.send_message("Queue loop enabled!")
        else:
            self.guild_states[interaction.guild.id]["is_looping_queue"] = False
            self.guild_states[interaction.guild.id]["queue_to_loop"].clear()
            
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

    @app_commands.command(name="clear", description="Removes every track from the queue (and/or history or loop queue).")
    @app_commands.describe(
        clear_history="Include track history in deletion.",
        clear_loop_queue="Include the loop queue in deletion."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def clear_queue(self, interaction: Interaction, clear_history: bool=False, clear_loop_queue: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return
        
        track_count = len(self.guild_states[interaction.guild.id]["queue"])
        history_track_count = len(self.guild_states[interaction.guild.id]["queue_history"])

        self.guild_states[interaction.guild.id]["queue"].clear()
        if clear_history:
            self.guild_states[interaction.guild.id]["queue_history"].clear()
        if clear_loop_queue:
            self.guild_states[interaction.guild.id]["queue_to_loop"].clear()

        await interaction.response.send_message(f"The queue is now empty.\nRemoved **{track_count}** items from queue{f' and **{history_track_count}** items from track history' if clear_history else ''}.")

    @clear_queue.error
    async def handle_clear_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) and\
        self.guild_states.get(interaction.guild.id, None) is None:
            await interaction.response.send_message("Cannot clear queue.\nReason: No longer in voice channel.")
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="remove", description="Removes user-given tracks from the queue. See entry in /help for more info.")
    @app_commands.describe(
        track_names="A semicolon separated list of name(s) of the track(s) to remove.",
        by_index="Remove tracks by their index. <track_names> must be a semicolon separated list of indices."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def remove_track(self, interaction: Interaction, track_names: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_queue(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return

        await update_guild_state(self.guild_states, interaction, True)

        queue = self.guild_states[interaction.guild.id]["queue"]
        is_looping_queue = self.guild_states[interaction.guild.id]["is_looping_queue"]

        tracks = split(track_names)
        found = await remove_track_from_queue(tracks, queue, by_index)

        if isinstance(found, int):
            await update_guild_state(self.guild_states, interaction, False)
            await handle_not_found_error(interaction, found)

            return

        if is_looping_queue:
            await update_loop_queue_remove(self.guild_states, interaction, found)

        await update_guild_state(self.guild_states, interaction, False)

        embed = generate_removed_tracks_embed(found)
        await interaction.response.send_message(embed=embed)

    @remove_track.error
    async def handle_remove_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="reposition", description="Repositions a track from its original position to a new index. See entry in /help for more info.")
    @app_commands.describe(
        track_name="The name of the track to reposition.",
        new_index="The new index of the track. Must be > 0 and <= maximum queue index.",
        by_index="Reposition a track by its index. <track_name> must be a number."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def reposition_track(self, interaction: Interaction, track_name: str, new_index: int, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_queue(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return
        
        await update_guild_state(self.guild_states, interaction, True)
    
        queue = self.guild_states[interaction.guild.id]["queue"]

        new_index -= 1
        new_index = max(0, min(new_index, len(queue) - 1))

        result = await reposition_track_in_queue(track_name, new_index, queue, by_index)
        if isinstance(result, int):
            await update_guild_state(self.guild_states, interaction, False)

            await handle_reposition_error(interaction, result)
            await handle_not_found_error(interaction, result)
            return

        await update_guild_state(self.guild_states, interaction, False)
        
        await interaction.response.send_message(f"Repositioned track **{result[0]['title']}**\nFrom index **{result[1][1] + 1}** to **{new_index + 1}**.")

    @reposition_track.error
    async def handle_reposition_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="shuffle", description="Shuffles the queue randomly.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def shuffle_queue(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_queue(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return

        await update_guild_state(self.guild_states, interaction, True)

        queue = self.guild_states[interaction.guild.id]["queue"]
        if len(queue) < 2:
            await interaction.response.send_message("There are not enough tracks to shuffle! (Need 2 atleast)")
            return

        shuffle(queue)

        await update_guild_state(self.guild_states, interaction, False)

        await interaction.response.send_message("Queue shuffled successfully!")

    @shuffle_queue.error
    async def handle_shuffle_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="seek", description="Seeks to another position in current track. See entry in /help for more info.")
    @app_commands.describe(
        time="The time to seek to. Must be HH:MM:SS or shorter version (ex. 1:30)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def seek_to(self, interaction: Interaction, time: str):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_current_track(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nWait for the other action first."):
            return

        current_track = self.guild_states[interaction.guild.id]["current_track"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        await interaction.response.defer(thinking=True) # If the connection is too slow, responding takes goddamn ages, so we need to defer and followup.

        if not voice_client.is_playing() and\
        not voice_client.is_paused():
            await interaction.followup.send("I'm not playing anything!")
            return

        position_seconds = format_minutes(time.strip())
        
        if position_seconds is None:
            await interaction.followup.send("Invalid time format. Be sure to format it to **HH:MM:SS**.\n**MM** and **SS** must not be > **59**.")
            return
        
        await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")
        await update_guild_state(self.guild_states, interaction, True, "stop_flag")

        await self.play_track(interaction, voice_client, current_track, position_seconds, "seek")

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.followup.send(f"Set track (**{current_track['title']}**) position to **{format_seconds(position_seconds)}**.")

    @seek_to.error
    async def handle_seek_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

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
            not await check_current_track(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nWait for the other action first."):
            return

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        current_track = self.guild_states[interaction.guild.id]["current_track"]

        await interaction.response.defer(thinking=True)

        if not voice_client.is_playing() and\
        not voice_client.is_paused():
            await interaction.followup.send("I'm not playing anything!")
            return

        time_seconds = format_minutes(time.strip())
        
        if time_seconds is None:
            await interaction.followup.send("Invalid time format. Be sure to format it to **HH:MM:SS**.\n**MM** and **SS** must not be > **59**.")
            return
        
        if not voice_client.is_paused():
            self.guild_states[interaction.guild.id]["elapsed_time"] = min(int(get_time() - self.guild_states[interaction.guild.id]["start_time"]), format_minutes(current_track["duration"]))
        
        rewind_time = self.guild_states[interaction.guild.id]["elapsed_time"] - time_seconds

        await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")
        await update_guild_state(self.guild_states, interaction, True, "stop_flag")
        
        await self.play_track(interaction, voice_client, current_track, rewind_time, "rewind")

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        elapsed_time = self.guild_states[interaction.guild.id]["elapsed_time"]
        await interaction.followup.send(f"Rewound track (**{current_track['title']}**) by **{format_seconds(time_seconds)}**. Now at **{format_seconds(elapsed_time)}**")

    @rewind_track.error
    async def handle_rewind_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

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
            not await check_current_track(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state is currently locked!\nWait for the other action first."):
            return

        current_track = self.guild_states[interaction.guild.id]["current_track"]
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]

        await interaction.response.defer(thinking=True)

        if not voice_client.is_playing() and\
        not voice_client.is_paused():
            await interaction.followup.send("I'm not playing anything!")
            return

        time_in_seconds = format_minutes(time.strip())
        
        if time_in_seconds is None:
            await interaction.followup.send("Invalid time format. Be sure to format it to **HH:MM:SS**.\n**MM** and **SS** must not be > **59**.")
            return
        
        start_time = self.guild_states[interaction.guild.id]["start_time"]
        if not voice_client.is_paused():
            self.guild_states[interaction.guild.id]["elapsed_time"] = min(int(get_time() - start_time), format_minutes(current_track["duration"]))

        position = self.guild_states[interaction.guild.id]["elapsed_time"] + time_in_seconds

        await update_guild_state(self.guild_states, interaction, True, "voice_client_locked")
        await update_guild_state(self.guild_states, interaction, True, "stop_flag")

        await self.play_track(interaction, voice_client, current_track, position, "forward")
        
        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        await interaction.followup.send(f"Forwarded track (**{current_track['title']}**) by **{format_seconds(time_in_seconds)}**. Now at **{format_seconds(position)}**.")

    @forward_track.error
    async def handle_forward_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False, "voice_client_locked")

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send("An unknown error occurred.")

    @app_commands.command(name="queue", description="Shows the tracks in the queue.")
    @app_commands.describe(
        page="The queue page to view. Must be > 0."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_queue(self, interaction: Interaction, page: int):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_queue(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_reading_queue", msg="I'm already reading the queue!"):
            return
        
        await update_guild_state(self.guild_states, interaction, True, "is_reading_queue")
        await asyncio.to_thread(update_queue_pages, self.guild_states, interaction)

        queue_pages = self.guild_states[interaction.guild.id]["queue_pages"]

        page -= 1
        fixed_page = max(0, min(page, len(queue_pages) - 1))

        embed = generate_queue_embed(queue_pages[fixed_page], fixed_page, len(queue_pages))
        queue_pages.clear()

        await update_guild_state(self.guild_states, interaction, False, "is_reading_queue")
        await interaction.response.send_message(embed=embed)

    @show_queue.error
    async def handle_queue_error(self, interaction: Interaction, error):
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

    @app_commands.command(name="history", description="Shows history of played tracks.")
    @app_commands.describe(
        page="The history page to view. Must be > 0."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_history(self, interaction: Interaction, page: int):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_history(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_reading_history", msg="I'm already reading track history!"):
            return
        
        await update_guild_state(self.guild_states, interaction, True, "is_reading_history")
        await asyncio.to_thread(update_history_pages, self.guild_states, interaction)

        history_pages = self.guild_states[interaction.guild.id]["history_pages"]

        page -= 1
        fixed_page = max(0, min(page, len(history_pages) - 1))
        embed = generate_queue_embed(history_pages[fixed_page], fixed_page, len(history_pages), True)

        history_pages.clear()

        await update_guild_state(self.guild_states, interaction, False, "is_reading_history")
        await interaction.response.send_message(embed=embed)

    @show_history.error
    async def handle_history_error(self, interaction: Interaction, error):
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

        if current_query is None and\
        max_queries == 0 and\
        current_query_amount == 0:
            await interaction.response.send_message("Failed to read values.")
            return

        embed = generate_extraction_embed(current_query, max_queries, current_query_amount)

        await interaction.response.send_message(embed=embed)

    @show_extraction.error
    async def handle_show_extract_error(self, interaction: Interaction, error):
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
        
        formatted_start_time = format_seconds(int(get_time() - start_time))
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

    @app_commands.command(name="yoink", description="DMs current track info to the user who ran the command.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def dm_track_info(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_current_track(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return

        await interaction.response.defer(ephemeral=True)

        current_track = self.guild_states[interaction.guild.id]["current_track"]
        user = interaction.user
        
        embed = generate_yoink_embed(current_track)
        
        await user.send(embed=embed)
        await interaction.followup.send("Message sent!")

    @dm_track_info.error
    async def handle_dm_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, discord.errors.Forbidden):
            await interaction.followup.send("I cannot send a message to you! Check your privacy settings and try again.")
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="nowplaying", description="Show information about the current track.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_current_track_info(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_current_track(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="voice_client_locked", msg="Voice state currently locked!\nWait for the other action first."):
            return
        
        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        info = self.guild_states[interaction.guild.id]["current_track"]
        queue = self.guild_states[interaction.guild.id]["queue"]
        queue_to_loop = self.guild_states[interaction.guild.id]["queue_to_loop"]
        queue_state_being_modified = self.guild_states[interaction.guild.id]["is_reading_queue"] or self.guild_states[interaction.guild.id]["is_modifying"]
        
        if voice_client.is_playing():
            fixed_elapsed_time = min(int(get_time() - self.guild_states[interaction.guild.id]["start_time"]), format_minutes(info["duration"]))
            elapsed_time = format_seconds(fixed_elapsed_time)
        else:
            elapsed_time = format_seconds(int(self.guild_states[interaction.guild.id]["elapsed_time"]))
        
        is_looping = self.guild_states[interaction.guild.id]["is_looping"]
        is_random = self.guild_states[interaction.guild.id]["is_random"]
        is_looping_queue = self.guild_states[interaction.guild.id]["is_looping_queue"]

        embed = generate_current_track_embed(
                                        info=info,
                                        queue=queue,
                                        queue_to_loop=queue_to_loop,
                                        elapsed_time=elapsed_time,
                                        looping=is_looping,
                                        random=is_random,
                                        queueloop=is_looping_queue,
                                        is_modifying_queue=queue_state_being_modified
                                    )
        await interaction.response.send_message(embed=embed)

    @show_current_track_info.error
    async def handle_show_track_info_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await interaction.response.send_message("An unknown error occurred.", ephemeral=True)

    """ Playlist commands """

    @app_commands.command(name="playlist-view", description="Shows the tracks in a playlist.")
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

        if await self.playlist.is_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)

        result = await self.playlist.read(content, playlist_name)
        if isinstance(result, int):
            await self.playlist.unlock(locked, content, playlist_name)

            await handle_generic_playlist_errors(interaction, result, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)
            return

        await asyncio.to_thread(update_playlist_pages, self.guild_states, interaction, result, playlist_name)

        playlist_pages = self.guild_states[interaction.guild.id]["playlist_pages"][playlist_name]

        page -= 1
        page = max(0, min(page, len(playlist_pages) - 1))
        embed = generate_queue_embed(playlist_pages[page], page, len(playlist_pages), False, True)
        playlist_pages.clear()

        await self.playlist.unlock(locked, content, playlist_name)
        await interaction.followup.send(embed=embed)

    @show_playlist.error
    async def handle_show_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="playlist-save", description="Creates a new playlist with the current queue. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The new playlist's name.",
        add_current_track="Whether or not to add the currently playing track."
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

        if await self.playlist.is_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)

        queue = deepcopy(self.guild_states[interaction.guild.id]["queue"])
        current_track = self.guild_states[interaction.guild.id]["current_track"]
        if not queue and not current_track:
            await self.playlist.unlock(locked, content, playlist_name)

            await interaction.followup.send("Queue is empty. Nothing to add.")
            return
        
        if current_track and add_current_track:
            queue.insert(0, current_track)

        success = await self.playlist.add_queue(interaction, content, playlist_name, queue, True)
        await self.playlist.unlock(locked, content, playlist_name)

        if isinstance(success, tuple):
            if success[0] == RETURN_CODES["WRITE_SUCCESS"]:
                if success[2]:
                    await interaction.followup.send(f"Maximum playlist track limit of **{self.playlist.max_item_limit}** tracks reached. Cannot add other track(s).")

                embed = generate_added_track_embed(success[1], True)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("Failed to update playlist contents.")
        elif isinstance(success, int):
            await handle_generic_playlist_errors(interaction, success, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)
            await handle_rename_error(interaction, success, playlist_name, self.playlist.max_name_length)

    @save_queue_in_playlist.error
    async def handle_save_queue_in_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="playlist-save-current", description="Saves the current track to a playlist. See entry in /help for more info.")
    @app_commands.describe(
        index="The index at which the track should be placed. Must be > 0. Ignore this field for last one.",
        playlist_name="The playlist to modify's name."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def save_current_in_playlist(self, interaction: Interaction, playlist_name: str, index: int=None):
        if not await user_has_role(interaction) or\
        not await user_has_role(interaction, playlist=True) or\
        not await check_channel(self.guild_states, interaction) or\
        not await check_current_track(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await self.playlist.is_locked(locked):
            await interaction.followup.send("A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)

        current_track = self.guild_states[interaction.guild.id]["current_track"]

        success = await self.playlist.place(interaction, content, playlist_name, current_track, index)
        await self.playlist.unlock(locked, content, playlist_name)

        if isinstance(success, tuple):
            if success[0] == RETURN_CODES["WRITE_SUCCESS"]:
                await interaction.followup.send(f"Placed track **{success[1]['title']}** at index **{success[2]}** of playlist **{playlist_name}**.")
            else:
                await interaction.followup.send("Failed to update playlist contents.")
        elif isinstance(success, int):
            await handle_generic_playlist_errors(interaction, success, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)
            await handle_rename_error(interaction, success, playlist_name, self.playlist.max_name_length)

    @save_current_in_playlist.error
    async def handle_save_current_in_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

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

        is_queue_too_long = await check_queue_length(interaction, self.max_track_limit, queue) == RETURN_CODES["QUEUE_TOO_LONG"]
        if is_queue_too_long:
            return

        if await self.playlist.is_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)

        await update_guild_state(self.guild_states, interaction, True, "is_modifying")
        await update_guild_state(self.guild_states, interaction, True, "is_extracting")

        success = await self.playlist.select(self.guild_states, self.max_track_limit, interaction, content, playlist_name, range_start, range_end)
        
        await update_guild_state(self.guild_states, interaction, False)
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await self.playlist.unlock(locked, content, playlist_name)
        
        if isinstance(success, list):
            if not voice_client.is_playing() and\
            not voice_client.is_paused():
                await self.play_next(interaction)

            embed = generate_added_track_embed(success)
            await interaction.followup.send(embed=embed)
        elif isinstance(success, tuple):
            await handle_generic_extraction_errors(interaction, success)
        elif isinstance(success, int):
            await handle_generic_playlist_errors(interaction, success, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)

    @select_playlist.error
    async def handle_select_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False)
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="playlist-create", description="Creates a new empty playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The new playlist's name. Muse be under 100 (default) characters."
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
        if await self.playlist.is_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)

        code = await self.playlist.create(interaction, content, playlist_name)
        await self.playlist.unlock(locked, content, playlist_name)

        if code == RETURN_CODES["NAME_TOO_LONG"]:
            success = await handle_rename_error(interaction, code, playlist_name, self.playlist.max_name_length)
        else:
            success = await handle_generic_playlist_errors(interaction, code, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)
            
        if success:
            await interaction.followup.send(f"Playlist **{playlist_name}** has been created.")

    @create_playlist.error
    async def handle_create_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="playlist-delete", description="Deletes a saved playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to delete's name."
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

        if await self.playlist.is_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)

        code = await self.playlist.delete(interaction, content, playlist_name, erase_contents_only)
        await self.playlist.unlock(locked, content, playlist_name)

        success = await handle_generic_playlist_errors(interaction, code, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)

        if success:
            msg = f'Playlist **{playlist_name}** has been deleted.' if not erase_contents_only else\
            f'**{len(code[1])}** tracks have been deleted from playlist **{playlist_name}**.'

            await interaction.followup.send(msg)

    @delete_playlist.error
    async def handle_delete_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="playlist-remove", description="Remove specified track(s) from a playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to remove tracks from's name.",
        track_names="A semicolon separated list of name(s) of the track(s) to remove.",
        by_index="Remove tracks by their index. <track_names> must be a semicolon separated list of indices."
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

        if await self.playlist.is_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)

        success = await self.playlist.remove(interaction, content, playlist_name, track_names, by_index)
        await self.playlist.unlock(locked, content, playlist_name)

        if isinstance(success, list):
            embed = generate_removed_tracks_embed(success, True)
            await interaction.followup.send(embed=embed)
        elif isinstance(success, int):
            await handle_generic_playlist_errors(interaction, success, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)

    @remove_playlist_track.error
    async def handle_remove_playlist_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

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

        if await self.playlist.is_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        
        content = await self.playlist.get_content(interaction) if not rewrite else {}

        code = await self.playlist.delete_all(interaction, content, locked, rewrite)

        success = await handle_generic_playlist_errors(interaction, code, playlist_limit=self.playlist.max_limit, playlist_item_limit=self.playlist.max_item_limit)
        if success:
            msg = f'Deleted **{len(content)}** playlist(s).' if not rewrite else 'Structure rewritten successfully.'

            await interaction.followup.send(msg)

    @delete_all_playlists.error
    async def handle_delete_all_playlists_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="playlist-rename", description="Renames a playlist to a new user-specified name. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to rename's name.",
        new_playlist_name="New name to assign to the playlist."
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

        if await self.playlist.is_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)

        success = await self.playlist.rename(interaction, content, playlist_name, new_playlist_name)
        await self.playlist.unlock(locked, content, playlist_name)

        if isinstance(success, tuple):
            if success[0] == RETURN_CODES["WRITE_SUCCESS"]:
                await interaction.followup.send(f"Renamed playlist **{success[1]}** to **{success[2]}**")
            else:
                await interaction.followup.send("Failed to update playlist contents.")
        elif isinstance(success, int):
            await handle_generic_playlist_errors(interaction, success, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)
            await handle_rename_error(interaction, success, new_playlist_name, self.playlist.max_name_length)

    @rename_playlist.error
    async def handle_rename_playlist_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="playlist-replace", description="Replaces a track with a new one in a playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to modify's name.",
        old="The track name of the track to replace.",
        new="YouTube (video only), Newgrounds, Soundcloud, Bandcamp URL or a YouTube search query.",
        by_index="Replace a track by its index. <old> must be a number."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def replace_playlist_track(self, interaction: Interaction, playlist_name: str, old: str, new: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status."):
            return

        await update_guild_state(self.guild_states, interaction, True, "is_extracting")
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await self.playlist.is_locked(locked):
            await update_guild_state(self.guild_states, interaction, False, "is_extracting")

            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)
        
        success = await self.playlist.replace(self.guild_states, interaction, content, playlist_name, old, new, by_index)
        
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await self.playlist.unlock(locked, content, playlist_name)

        if isinstance(success, tuple):
            if success[0] == RETURN_CODES["WRITE_SUCCESS"]:
                await interaction.followup.send(f"Replaced track **{success[1]["title"]}** with track **{success[2]["title"]}**")
            else:
                await interaction.followup.send("Failed to update playlist contents.")
        elif isinstance(success, int):
            await handle_generic_playlist_errors(interaction, success, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)
            await handle_generic_extraction_errors(interaction, success)

        await check_users_in_channel(self.guild_states, self.playlist, interaction)

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
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="playlist-reposition", description="Repositions a playlist track to a new index. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to modify's name.",
        track_name="The track name of the track to reposition.",
        new_index="The new index of the track.",
        by_index="Reposition a track by its index. <track_name> must be a number."
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

        if await self.playlist.is_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)

        success = await self.playlist.reposition(interaction, content, playlist_name, track_name, new_index, by_index)
        await self.playlist.unlock(locked, content, playlist_name)

        if isinstance(success, tuple):
            if success[0] == RETURN_CODES["WRITE_SUCCESS"]:
                await interaction.followup.send(f"Repositioned track **{success[1]["title"]}** from index **{success[2]}** to **{success[3]}**")
            else:
                await interaction.followup.send("Failed to update playlist contents.")
        elif isinstance(success, int):
            await handle_generic_playlist_errors(interaction, success, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)
            await handle_reposition_error(interaction, success)

    @reposition_playlist_track.error
    async def handle_reposition_playlist_track(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="playlist-add", description="Adds track(s) to the specified playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to modify's name.",
        queries="A semicolon separated list of YouTube, Newgrounds, SoundCloud, Bandcamp URLs or YouTube search queries."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def add_playlist_track(self, interaction: Interaction, playlist_name: str, queries: str):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status."):
            return

        await update_guild_state(self.guild_states, interaction, True, "is_extracting")
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await self.playlist.is_locked(locked):
            await update_guild_state(self.guild_states, interaction, False, "is_extracting")

            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)

        queries_split = await check_input_length(interaction, self.max_query_limit, split(queries))
        success = await self.playlist.add(self.guild_states, interaction, content, playlist_name, queries_split, False, "YouTube Playlist")

        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await self.playlist.unlock(locked, content, playlist_name)

        if isinstance(success, tuple):
            is_not_extraction_error = await handle_generic_extraction_errors(interaction, success)
            if not is_not_extraction_error:
                return

            if success[0] == RETURN_CODES["WRITE_SUCCESS"]:
                if success[2]:
                    await interaction.followup.send(f"Maximum playlist track limit of **{self.playlist.max_item_limit}** tracks reached. Cannot add other track(s).")
            
                embed = generate_added_track_embed(success[1], True)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("Failed to update playlist contents.")
        elif isinstance(success, int):
            await handle_generic_playlist_errors(interaction, success, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)
            await handle_rename_error(interaction, success, playlist_name, self.playlist.max_name_length)

        await check_users_in_channel(self.guild_states, self.playlist, interaction)

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
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="playlist-fetch-track", description="Adds a track from a playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to fetch track(s) from's name.",
        tracks="The name(s) of the track(s) to fetch in a semicolon separated list.",
        by_index="Fetch tracks by their index. <tracks> must be a semicolon separated list of indices."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def fetch_playlist_track(self, interaction: Interaction, playlist_name: str, tracks: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status."):
            return
        
        await update_guild_state(self.guild_states, interaction, True, "is_extracting")
        await update_guild_state(self.guild_states, interaction, True)

        await interaction.response.defer(thinking=True)

        voice_client = self.guild_states[interaction.guild.id]["voice_client"]
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]
        queue = self.guild_states[interaction.guild.id]["queue"]

        queries_split = await check_input_length(interaction, self.max_query_limit, split(tracks))
        is_queue_too_long = await check_queue_length(interaction, self.max_track_limit, queue) == RETURN_CODES["QUEUE_TOO_LONG"]
        if is_queue_too_long:
            await update_guild_state(self.guild_states, interaction, False, "is_extracting")
            await update_guild_state(self.guild_states, interaction, False)
            return

        if await self.playlist.is_locked(locked):
            await update_guild_state(self.guild_states, interaction, False, "is_extracting")
            await update_guild_state(self.guild_states, interaction, False)
            
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)

        success = await self.playlist.fetch(self.guild_states, self.max_track_limit, interaction, content, playlist_name, queries_split, by_index=by_index)

        await update_guild_state(self.guild_states, interaction, False)
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await self.playlist.unlock(locked, content, playlist_name)

        if isinstance(success, list):
            if not voice_client.is_playing() and\
            not voice_client.is_paused():
                await self.play_next(interaction)

            embed = generate_added_track_embed(success, False)
            await interaction.followup.send(embed=embed)
        elif isinstance(success, int):
            await handle_generic_playlist_errors(interaction, success, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)
        elif isinstance(success, tuple):
            await handle_generic_extraction_errors(interaction, success)

    @fetch_playlist_track.error
    async def handle_fetch_playlist_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        
        await update_guild_state(self.guild_states, interaction, False)
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="playlist-fetch-random-track", description="Fetches random track(s) from specified playlist. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The name of the playlist to search in.",
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
        is_queue_too_long = await check_queue_length(interaction, self.max_track_limit, queue) == RETURN_CODES["QUEUE_TOO_LONG"]
        
        if is_queue_too_long:
            return

        await update_guild_state(self.guild_states, interaction, True)
        await update_guild_state(self.guild_states, interaction, True, "is_extracting")

        if await self.playlist.is_locked(locked):
            await update_guild_state(self.guild_states, interaction, False)
            await update_guild_state(self.guild_states, interaction, False, "is_extracting")

            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)

        result = await self.playlist.read(content, playlist_name)
        if isinstance(result, int):
            await update_guild_state(self.guild_states, interaction, False)
            await update_guild_state(self.guild_states, interaction, False, "is_extracting")
            await self.playlist.unlock(locked, content, playlist_name)

            await handle_generic_playlist_errors(interaction, result, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)
            return
        
        random_tracks = await get_random_tracks_from_playlist(result, amount)
        success = await self.playlist.fetch(self.guild_states, self.max_track_limit, interaction, content, playlist_name, random_tracks, True)

        await update_guild_state(self.guild_states, interaction, False)
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await self.playlist.unlock(locked, content, playlist_name)

        if isinstance(success, list):
            if not voice_client.is_playing() and\
            not voice_client.is_paused():
                await self.play_next(interaction)

            embed = generate_added_track_embed(success, False)
            await interaction.followup.send(embed=embed)
        elif isinstance(success, tuple):
            await handle_generic_extraction_errors(interaction, success)

    @choose_random_playlist_tracks.error
    async def handle_choose_random_playlist_tracks(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await update_guild_state(self.guild_states, interaction, False)
        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="playlist-add-yt-playlist", description="Adds a YouTube playlist to a playlist. See entry in /help for more info.")
    @app_commands.describe(
        query="A YouTube playlist URL.",
        playlist_name="The playlist to add the tracks to's name."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["EXTRACTOR_MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def add_playlist(self, interaction: Interaction, playlist_name: str, query: str):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction) or\
            not await check_guild_state(self.guild_states, interaction, state="is_extracting", msg="Please wait for the current extraction process to finish. Use `/progress` to see the status."):
            return
        
        await update_guild_state(self.guild_states, interaction, True, "is_extracting")
        await interaction.response.defer(thinking=True)

        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await self.playlist.is_locked(locked):
            await update_guild_state(self.guild_states, interaction, False, "is_extracting")
            
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)

        success = await self.playlist.add(self.guild_states, interaction, content, playlist_name, [query], False, None, "YouTube Playlist")

        await update_guild_state(self.guild_states, interaction, False, "is_extracting")
        await update_query_extraction_state(self.guild_states, interaction, 0, 0, None)
        await self.playlist.unlock(locked, content, playlist_name)

        if isinstance(success, tuple):
            is_not_extraction_error = await handle_generic_extraction_errors(interaction, success)
            if not is_not_extraction_error:
                return

            if success[0] == RETURN_CODES["WRITE_SUCCESS"]:
                if success[2]:
                    await interaction.followup.send(f"Maximum playlist track limit of **{self.playlist.max_item_limit}** tracks reached. Cannot add other track(s).")
                
                embed = generate_added_track_embed(success[1], True)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("Failed to update playlist contents.")
        elif isinstance(success, int):
            await handle_generic_playlist_errors(interaction, success, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)
            await handle_rename_error(interaction, success, playlist_name, self.playlist.max_name_length)

        await check_users_in_channel(self.guild_states, self.playlist, interaction)

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
        
        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="playlist-edit-track", description="Modifies the specified track's name. See entry in /help for more info.")
    @app_commands.describe(
        playlist_name="The playlist to modify's name.",
        old_track_names="A semicolon separated list of the tracks to rename.",
        new_track_names=f"A semicolon separated list of new names.",
        by_index="Rename tracks by their index. <old_track_names> must be a semicolon separated list of indices."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def edit_playlist_track(self, interaction: Interaction, playlist_name: str, old_track_names: str, new_track_names: str, by_index: bool=False):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)
        
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await self.playlist.is_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return
        else:
            content = await self.playlist.get_content(interaction)
            await self.playlist.lock(interaction, content, locked, playlist_name)

        success = await self.playlist.edit(interaction, content, playlist_name, old_track_names, new_track_names, by_index)
        await self.playlist.unlock(locked, content, playlist_name)

        if isinstance(success, tuple):
            if success[0] == RETURN_CODES["WRITE_SUCCESS"]:
                embed = generate_edited_tracks_embed(success[1])
                await interaction.followup.send(embed=embed)
        elif isinstance(success, int):
            await handle_generic_playlist_errors(interaction, success, playlist_name, self.playlist.max_limit, self.playlist.max_item_limit)

    @edit_playlist_track.error
    async def handle_edit_playlist_track_error(self, interaction: Interaction, error):
        if isinstance(error, KeyError) or\
            self.guild_states.get(interaction.guild.id, None) is None:
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        if CAN_LOG and LOGGER is not None:
            LOGGER.exception(error)

        await self.playlist.unlock_all(self.guild_states, interaction, self.guild_states[interaction.guild.id]["locked_playlists"])

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')

    @app_commands.command(name="playlist-get-saved", description="Shows the saved playlists for this guild.")
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MUSIC_COMMANDS_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.guild_only
    async def show_saved_playlists(self, interaction: Interaction):
        if not await user_has_role(interaction) or\
            not await user_has_role(interaction, playlist=True) or\
            not await check_channel(self.guild_states, interaction):
            return
        
        await interaction.response.defer(thinking=True)
        locked = self.guild_states[interaction.guild.id]["locked_playlists"]

        if await self.playlist.is_locked(locked):
            await interaction.followup.send(f"A playlist is currently locked, please wait.")
            return

        content = await self.playlist.get_content(interaction)

        result = await self.playlist.get_available(content)
        if isinstance(result, int):
            await handle_generic_playlist_errors(interaction, result, playlist_limit=self.playlist.max_limit, playlist_item_limit=self.playlist.max_item_limit)
            return

        playlists_string = ", ".join([f"`{key}`" for key in result])
        remaining_slots = self.playlist.max_limit - len(result)

        await interaction.followup.send(f"Saved playlists: {playlists_string}.\nRemaining slots: **{remaining_slots}**.")

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

        await interaction.response.send_message('An unknown error occured.', ephemeral=True) if not interaction.response.is_done() else\
        await interaction.followup.send('An unknown error occured.')