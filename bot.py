""" Bot subclass setup module for discord.py bot """

from settings import *
from guild import check_guilds
from handlers import handle_sync_error, handle_load_error
from loader import Loader

class Bot(commands.Bot):
    """ Custom bot object with special methods for modularity and safer cleanups. """
    
    def __init__(self, command_prefix: str, **options) -> None:
        super().__init__(command_prefix=command_prefix, help_command=None, **options)
        self.has_finished_on_ready = False # Avoid re-running on_ready() in case of disconnects and reconnects, since it contains code that blocks the bot
        self.cog_objs = {}

    async def get_cogs(self) -> list[commands.Cog]:
        """ Get cogs from all modules and their respective enable value from config.json """
        loader = Loader("modules")
        classes = loader.get_classes()
        values = loader.get_enable_values_from_config([obj.__name__ for obj in classes])
        cogs = []

        for (_, value), cog in zip(values, classes):
            if value:
                cogs.append(cog)
            else:
                log(f"Ignoring cog {cog.__name__} because blacklisted in config.json")

        return cogs

    async def load_cog(self, cog: commands.Cog) -> bool | tuple[bool, Exception]:
        try:
            await self.add_cog(cog)
            self.cog_objs[cog.__class__.__name__] = cog
        except Exception as e:
            return (False, e)
        
        log(f"Successfully loaded cog {cog.__class__.__name__}")
        return True

    async def load_cogs(self) -> None:
        log(f"Loading cogs..")
        cogs = await self.get_cogs()

        for cog in cogs:
            obj = cog(self)
            result = await self.load_cog(obj)
        
            if isinstance(result, tuple):
                await handle_load_error(obj, result[1])

    async def set_activity(self) -> None:
        """ Set up an activity, if configured. """
        
        if ACTIVITY:
            log(f"Setting activity name to '{ACTIVITY.name}'")
            log(f"Setting activity type to '{ACTIVITY.type.name}'")

        if STATUS:
            log(f"Setting{' (random) ' if STATUS_TYPE is None else ''}status to '{STATUS.name}'")

        await self.change_presence(activity=ACTIVITY, status=STATUS)

    async def sync_commands(self) -> None:
        """ Sync application commands to Discord. """

        try:
            synced_commands = await self.tree.sync()
            log(f"Successfully synced {len(synced_commands)} application commands with the Discord API.")
        except Exception as e:
            await handle_sync_error(e)

    async def post_login_tasks(self) -> None:
        """ Handle any post-login tasks.\n
        Checking guilds, loading cogs, and syncing commands with the Discord API. """
        
        log("Running post-login tasks")
        separator()
        await asyncio.sleep(0.3)

        await check_guilds(bot_user=self.user.name, guilds=self.guilds)
        separator()

        await self.load_cogs()
        await asyncio.sleep(0.3)

        log("done")
        separator()

        log(f"Syncing app commands..")
        await self.sync_commands()
        await asyncio.sleep(0.3)

        log("done")
        separator()

        await self.set_activity()
        separator()

    async def on_ready(self) -> None:
        if self.has_finished_on_ready:
            log(f"[reconnect?] on_ready() function triggered after first initialization. Ignoring.")
            return

        log(f"Logged in as {self.user}")
        separator()
        await self.post_login_tasks()

        log(f"Ready :{'3' * randint(1, 10)}")
        separator()

        self.has_finished_on_ready = True

    async def wait_for_read_write_sync(self) -> None:
        """ Wait for any write/reads to finish before closing to keep data safe. """
        
        FILE_OPERATIONS_LOCKED_PERMANENTLY.set()
        log(f"File operations locked permanently: {FILE_OPERATIONS_LOCKED_PERMANENTLY.is_set()}")

        log("Waiting for read/write sync..")

        start_time = get_time() # Track elapsed time and continue anyways if it times out.

        while (any(playlist_lock.locked() for playlist_lock in PLAYLIST_LOCKS.values()) or\
            any(role_lock.locked() for role_lock in ROLE_LOCKS.values())) and (get_time() - start_time < MAX_IO_WAIT_TIME):
            
            await asyncio.sleep(0.1)

        log("done")

    async def close(self) -> None:
        """ Attempt to cleanly exit the program. Called when CTRL + C is pressed. """
        
        log("Requested to terminate program.")
        log("Attempting a cleanup..")
        
        await self.wait_for_read_write_sync()

        await super().close()

        separator()
        log(f"Bai bai :{'3' * randint(1, 10)}")

        if CAN_LOG and LOGGER is not None:
            LOGGER.info(f"Connection closed by host.\nEnd of log.")
