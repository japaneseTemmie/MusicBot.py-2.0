from settings import CAN_LOG, LOGGER, COOLDOWNS, VOICE_OPERATIONS_LOCKED, FILE_OPERATIONS_LOCKED
from init.logutils import log, log_to_discord_log
from bot import Bot, ShardedBot

from discord.ext import commands
from time import monotonic

class DevCog(commands.Cog):
    def __init__(self, client: Bot | ShardedBot):
        self.client = client
        self.guild_states = self.client.guild_states
        self.reloading_cogs = False

    @commands.command("reload-cogs")
    @commands.cooldown(rate=1, per=COOLDOWNS["DEV_COMMAND_COOLDOWN"], type=commands.BucketType.user)
    @commands.guild_only()
    async def reload_cogs(self, ctx: commands.Context):
        if not await self.client.is_owner(ctx.author) or\
            self.reloading_cogs or\
            not self.client.has_finished_on_ready:
            return
        
        self.reloading_cogs = True
        start_time = monotonic()

        log("===== RELOADING COGS =====")
        
        VOICE_OPERATIONS_LOCKED.set()
        FILE_OPERATIONS_LOCKED.set()

        cog_names = list(self.client.cogs)
        for name in cog_names:
            await self.client.remove_cog(name)

        await self.client.load_cogs()
        await self.client.sync_commands()

        VOICE_OPERATIONS_LOCKED.clear()
        FILE_OPERATIONS_LOCKED.clear()

        self.reloading_cogs = False

        current_cog_names = list(self.client.cogs)
        await ctx.send(f"Reloaded **{len(current_cog_names)}** out of **{len(cog_names)}** cogs in **{round(monotonic() - start_time, 2)}**s\n"+
                       f"Currently active cogs:\n{"".join([f"- **{name}**\n" for name in current_cog_names])}")

    @reload_cogs.error
    async def handle_reload_cogs_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.MissingRequiredArgument) or\
            isinstance(error, commands.NoPrivateMessage) or\
            isinstance(error, commands.CommandOnCooldown):
            return

        log("An error occured while reloading cogs")
        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)