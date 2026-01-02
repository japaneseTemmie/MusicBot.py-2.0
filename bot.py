""" Bot subclass setup module for discord.py bot """

from settings import (
    ACTIVITY_DATA, ACTIVITY, STATUS,
    ROLE_LOCKS, PLAYLIST_LOCKS, 
    LOGGER, CAN_LOG, CONFIG
)
from init.constants import MAX_IO_SYNC_WAIT_TIME, STREAM_VALIDATION_TIMEOUT
from loader import ModuleLoader
from init.config import correct_type
from helpers.lockhelpers import set_global_locks, get_file_lock, get_vc_lock
from init.logutils import log, separator, log_to_discord_log
from guildchecks import ensure_guild_data, check_guild_data

import asyncio
from aiohttp import ClientSession, ClientTimeout
from discord.ext import commands
from discord.app_commands import AppCommand
from time import monotonic
from random import randint

class Bot(commands.Bot):
    """ Custom bot object with special methods for modularity and safer cleanups. """
    
    def __init__(self, command_prefix: str, **options) -> None:
        super().__init__(command_prefix=command_prefix, help_command=None, **options)
        
        self.on_ready_lock = asyncio.Lock()
        
        self.has_finished_on_ready = False # Avoid re-running on_ready() in case of disconnects and reconnects, since it contains code that blocks the bot
        self.is_sharded = False

        self.loaded_cogs = []
        self.synced_commands = []
        self.guild_states = {}

        self.max_track_limit = correct_type(CONFIG.get("max_queue_track_limit", 100), int, 100)
        self.max_history_track_limit = correct_type(CONFIG.get("max_history_track_limit", 200), int, 200)
        self.max_query_limit = correct_type(CONFIG.get("max_query_limit", 25), int, 25)

        self.max_playlist_limit = correct_type(CONFIG.get("max_playlist_limit", 10), int, 10)
        self.max_playlist_item_limit = correct_type(CONFIG.get("max_playlist_track_limit", 100), int, 100)
        self.max_playlist_name_length = correct_type(CONFIG.get("max_playlist_name_length", 50), int, 50)

        self.max_channel_name_length = 100
        self.max_topic_length = 1024
        self.max_slowmode = 21600
        self.max_bitrate = 96000
        self.max_stage_bitrate = 64000
        self.max_user_limit = 99
        self.max_announcement_length = 2000
        self.max_purge_limit = 500

    async def setup_hook(self) -> None:
        self.stream_url_check_session = ClientSession(timeout=ClientTimeout(STREAM_VALIDATION_TIMEOUT))
        log("Set up a ClientSession for stream URL checks")
        separator()

    async def get_cogs(self) -> list[type[commands.Cog]]:
        """ Get cogs from all modules and their respective enable value from config.json """
        
        loader = ModuleLoader("modules")
        classes = loader.get_classes()
        values = loader.get_enable_values_from_config(CONFIG, [obj.__name__ for obj in classes])
        cogs = []

        for (_, value), cog in zip(values, classes):
            if value:
                cogs.append(cog)
            else:
                log(f"Ignoring cog {cog.__name__} because blacklisted in config.json")

        return cogs

    async def load_cog(self, cog: commands.Cog) -> bool:
        """ Wrapper function for client.add_cog() with error handling. """
        
        try:
            await self.add_cog(cog)
        except Exception as e:
            log_to_discord_log(e, can_log=CAN_LOG, logger=LOGGER)

            log(f"An error occurred while loading {cog.__class__.__name__}\nErr: {e}")
            return False
        
        log(f"Successfully loaded cog {cog.__class__.__name__}")
        return True

    async def load_cogs(self) -> list[commands.Cog]:
        """ Loads all available cogs from the `modules` folder based on their enable_* value from the config file. 
        
        Returns loaded cogs. """
        
        log(f"Loading cogs..")

        self.loaded_cogs.clear()
        cogs = await self.get_cogs()

        for cog in cogs:
            obj = cog(self)
            is_loaded = await self.load_cog(obj)

            if is_loaded:
                self.loaded_cogs.append(obj)

        if cogs and not self.loaded_cogs:
            log(f"All cogs failed to load. Check log file if present.")
            await asyncio.sleep(5)

        log("done")
        separator()

        return self.loaded_cogs

    async def set_activity(self) -> None:
        """ Set up an activity, if configured. """
        
        if ACTIVITY:
            log(f"Setting activity name to '{ACTIVITY_DATA["activity_name"]}'")
            log(f"Setting activity type to '{ACTIVITY_DATA["activity_type"]}'")
            
            if ACTIVITY_DATA["activity_type"] in ("listening", "playing"):
                log(f"Setting activity state to '{ACTIVITY_DATA["activity_state"]}'")

        if STATUS:
            log(f"Setting {'(random)' if ACTIVITY_DATA["status_type"] is None else ''} status to '{STATUS.name}'")

        await self.change_presence(activity=ACTIVITY, status=STATUS)

        log("done")
        separator()

    async def sync_commands(self) -> list[AppCommand]:
        """ Sync application commands to Discord. 
        
        Return synced commands. """

        log(f"Syncing app commands..")
        
        self.synced_commands.clear()

        try:
            synced_commands = await self.tree.sync()
            self.synced_commands.extend(synced_commands)
            
            log(f"Successfully synced {len(synced_commands)} application commands with the Discord API.")
        except Exception as e:
            log_to_discord_log(e, can_log=CAN_LOG, logger=LOGGER)
            log(f"An error occurred while syncing app commands to Discord.\nErr: {e}")
        
        log("done")
        separator()

        return self.synced_commands

    async def post_login_tasks(self) -> None:
        """ Handle any post-login tasks like checking guild directories, loading cogs, and syncing commands with the Discord API. """
        
        log("Running post-login tasks..")
        separator()
        await asyncio.sleep(0.3)

        guild_data_exists = await ensure_guild_data()
        if not guild_data_exists:
            await self.close()
        
        guild_data_is_ok = await check_guild_data(self.user.name, self.guilds, self.is_sharded)
        if not guild_data_is_ok:
            log("Failed check: Guild data")

        await asyncio.sleep(0.3)

        loaded_cogs = await self.load_cogs()
        if not loaded_cogs:
            await self.close()
        await asyncio.sleep(0.3)

        synced_commands = await self.sync_commands()
        if not synced_commands:
            await self.close()
        await asyncio.sleep(0.3)

        await self.set_activity()
        await asyncio.sleep(0.3)

    async def on_ready(self) -> None:
        if self.has_finished_on_ready:
            log(f"[reconnect?] on_ready() function triggered after first initialization. Ignoring.")
            return
        
        async with self.on_ready_lock:
            log("Starting setup in locked mode")
            separator()

            await set_global_locks(True, True)

            log(f"Logged in as {self.user.name}")
            separator()
            log(f"Command prefix is '{self.command_prefix}'")
            separator()

            await self.post_login_tasks()

            log(f"Running in {'sharded' if self.is_sharded else 'non-sharded'} mode.")
            separator()

            log(f"Ready with {len(self.loaded_cogs)} modules and {len(self.synced_commands)} commands :{'3' * randint(1, 10)}")
            separator()
            
            self.has_finished_on_ready = True

            await set_global_locks(False, False)

    async def on_shard_ready(self, shard_id: int) -> None:
        log(f"Shard {shard_id} is ready.")

    async def wait_for_read_write_sync(self) -> None:
        """ Wait for any write/reads to finish before closing to keep data safe. """

        log("Waiting for read/write sync..")

        start_time = monotonic() # Track elapsed time and continue anyways if it times out.

        while (any(playlist_lock.locked() for playlist_lock in PLAYLIST_LOCKS.values()) or\
            any(role_lock.locked() for role_lock in ROLE_LOCKS.values())) and (monotonic() - start_time < MAX_IO_SYNC_WAIT_TIME):
            
            await asyncio.sleep(0.1)

        log("done")
        separator()

    async def close(self) -> None:
        """ Attempt to cleanly exit the program. Called when SIGINT is recieved. (either by user or runner script) """
        
        separator()
        log("Requested to terminate program.")
        log("Attempting a cleanup..")
        separator()

        await set_global_locks(True, True)

        log(f"File operations locked permanently: {await get_file_lock()}")
        log(f"Voice state permanently locked: {await get_vc_lock()}")
        separator()
        
        await self.wait_for_read_write_sync()

        await super().close()

        if hasattr(self, "stream_url_check_session"):
            await self.stream_url_check_session.close()
            log("Closed ClientSession for stream URL checks")

        separator()
        log(f"Bai bai :{'3' * randint(1, 10)}")

        log_to_discord_log("Connection closed by host.\nEnd of log.", can_log=CAN_LOG, logger=LOGGER)

class ShardedBot(commands.AutoShardedBot, Bot):
    """ `Bot` class with sharding. """

    def __init__(self, command_prefix: str, **options):
        super().__init__(command_prefix, **options)
        self.is_sharded = True