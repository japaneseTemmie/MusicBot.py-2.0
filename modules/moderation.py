""" A complete, simple moderation module for discord.py bot.

Includes a class with a few methods for managing
a Discord guild and its users. """

from settings import CAN_LOG, LOGGER
from init.constants import (
    COOLDOWNS,
    MAX_CHANNEL_NAME_LENGTH, MAX_TOPIC_LENGTH, MAX_SLOWMODE, MAX_STAGE_BITRATE,
    MAX_USER_LIMIT, MAX_ANNOUNCEMENT_LENGTH_LIMIT, MAX_PURGE_LIMIT, MAX_FORUM_TOPIC_LENGTH
)
from init.logutils import log_to_discord_log
from bot import Bot, ShardedBot
from helpers.moderationhelpers import get_purge_check, remove_markdown_or_mentions
from helpers.timehelpers import format_to_seconds_extended

import discord
from discord import app_commands
from discord.ext import commands
from discord.interactions import Interaction
from datetime import datetime, timedelta, timezone

class ModerationCog(commands.Cog):
    def __init__(self, client: Bot | ShardedBot):
        self.client = client

    async def handle_command_error(self, interaction: Interaction, error: Exception):
        """ AIO error handler for moderation commands.
        
        Currently handles:
         
        - BotMissingPermissions
        - MissingPermissions (user)
        - CommandOnCooldown
        - Forbidden
        - HTTPException """
        
        send_func = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        
        if isinstance(error, app_commands.errors.BotMissingPermissions):
            await send_func("I don't have the necessary permissions to perform that operation!", ephemeral=True)
            return
        elif isinstance(error, app_commands.errors.MissingPermissions):
            await send_func("You don't have the necessary permissions to perform that operation!", ephemeral=True)
            return
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            await send_func(str(error), ephemeral=True)
            return
        
        if isinstance(error, app_commands.errors.CommandInvokeError):
            if isinstance(error.original, discord.errors.Forbidden):
                await send_func("I'm unable to do that! Please check my permissions. (Including channel overrides)", ephemeral=True)
                return
            elif isinstance(error.original, discord.errors.HTTPException):
                await send_func("Something went wrong while requesting changes. Try again later.", ephemeral=True)
                return
            
            log_to_discord_log(error.original, can_log=CAN_LOG, logger=LOGGER)
            return

        log_to_discord_log(error, can_log=CAN_LOG, logger=LOGGER)

        await send_func("An unknown error occurred.", ephemeral=True)

    @app_commands.command(name="purge", description="Bulk removes selected amount of text messages in a channel. See entry in /help for more info.")
    @app_commands.describe(
        channel="The channel to purge. (defaults to the current channel)",
        amount="The amount of messages to delete. Must be > 0 and <= 500. (defaults to 100)",
        user="Delete only messages sent by this user. (defaults to none)",
        word="Delete only messages that have this word. (defaults to none)",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PURGE_CHANNEL_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    @app_commands.guild_only
    async def purge_channel(self, interaction: Interaction, channel: discord.TextChannel=None, amount: int=100, user: discord.Member=None, word: str=None, show: bool=False):
        if amount < 1 or amount > MAX_PURGE_LIMIT:
            await interaction.response.send_message(f"Amount must be >= **1** and <= **{MAX_PURGE_LIMIT}**", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True) # This will take ages so we need to defer

        channel = interaction.channel if channel is None else channel
        after = datetime.now(timezone.utc) - timedelta(days=13, hours=50)

        deleted_messages = await channel.purge(limit=amount, check=get_purge_check(user, word), after=after)
        deleted_message_amount = len(deleted_messages)

        if deleted_message_amount < 1:
            await interaction.followup.send("No messages deleted.\nNote: Due to performance concerns and Discord limitations, I'm only able to delete messages not older than 14 days.")
            return
        
        if show:
            await interaction.followup.send(f"Finished with **{deleted_message_amount}** {'messages' if deleted_message_amount > 1 else 'message'}.")
            await interaction.channel.send(f"Deleted **{deleted_message_amount}** {'messages' if deleted_message_amount > 1 else 'message'} from channel **{channel.name} ({channel.id})**.")       
        else:
            await interaction.followup.send(f"Deleted **{deleted_message_amount}** {'messages' if deleted_message_amount > 1 else 'message'} from channel **{channel.name} ({channel.id})**.")

    @purge_channel.error
    async def handle_purge_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="kick", description="Kicks a member from the guild.")
    @app_commands.describe(
        member="The member to kick.",
        reason="Reason for kick. (defaults to 'None')",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["KICK_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    @app_commands.guild_only
    async def kick_member(self, interaction: Interaction, member: discord.Member, reason: str="None", show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        bot_top_role = interaction.guild.me.top_role
        target_member_top_role = member.top_role
        member_top_role = interaction.user.top_role

        if member in (interaction.user, interaction.guild.me):
            await interaction.followup.send(f"Member cannot be yourself or me.")
            return
        elif bot_top_role < target_member_top_role:
            await interaction.followup.send(f"My role (**{bot_top_role.name}**) is not high enough to kick member **{member.name}**.")
            return
        elif member_top_role < target_member_top_role:
            await interaction.followup.send(f"Your role (**{member_top_role.name}**) is not high enough to kick member **{member.name}**.")
            return
        
        await interaction.guild.kick(member, reason=reason)
        
        await interaction.followup.send(f"Member **{member.name}** has been kicked from the guild{f' by **{interaction.user.display_name}**' if show else ''}.")

    @kick_member.error
    async def handle_kick_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="ban", description="Bans a member from the guild.")
    @app_commands.describe(
        member="The member to ban.",
        reason="The ban reason. (defaults to 'None')",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["BAN_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    @app_commands.guild_only
    async def ban_member(self, interaction: Interaction, member: discord.Member, reason: str="None", show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        bot_top_role = interaction.guild.me.top_role
        target_member_top_role = member.top_role
        member_top_role = interaction.user.top_role
        
        if member in (interaction.user, interaction.guild.me):
            await interaction.followup.send(f"Member cannot be yourself or me.")
            return
        elif bot_top_role < target_member_top_role:
            await interaction.followup.send(f"My role (**{bot_top_role.name}**) is not high enough to ban member **{member.name}**.")
            return
        elif member_top_role < target_member_top_role:
            await interaction.followup.send(f"Your role (**{member_top_role.name}**) is not high enough to ban member **{member.name}**.")
            return

        await interaction.guild.ban(member, reason=reason)

        await interaction.followup.send(
            f"Member **{member.name}** has been banned from the guild"
            f"{f' by **{interaction.user.display_name}**' if show else ''}."
        )

    @ban_member.error
    async def handle_ban_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="unban", description="Unbans a member from the guild. See entry in /help for more info.")
    @app_commands.describe(
        member_id="The member to unban's ID",
        reason="The unban reason. (defaults to 'None')",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["UNBAN_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    @app_commands.guild_only
    async def unban_member(self, interaction: Interaction, member_id: str, reason: str="None", show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        if not member_id.isdigit():
            await interaction.followup.send("Member ID must be a numeric string.")
            return

        try:
            entry = await interaction.guild.fetch_ban(discord.Object(int(member_id)))
            member_to_unban = entry.user
        except discord.errors.NotFound:
            member_to_unban = None

        if member_to_unban is None:
            await interaction.followup.send(f"Could not find member of ID **{member_id}** in ban entries.")
            return
        elif member_to_unban in (interaction.user, interaction.guild.me):
            await interaction.followup.send(f"Member cannot be yourself or me.")
            return

        await interaction.guild.unban(member_to_unban, reason=reason.strip())
        await interaction.followup.send(
            f"Member **{member_to_unban.name}** has been unbanned"
            f"{f' by **{interaction.user.display_name}**' if show else ''}."
        )

    @unban_member.error
    async def handle_unban_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="timeout", description="Times out a member.")
    @app_commands.describe(
        duration="For how long the user should remain timed out. Must be DD:HH:MM:SS.",
        member="The member to timeout.",
        reason="Reason for timeout. (defaults to 'None')",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["TIMEOUT_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    @app_commands.guild_only
    async def time_out_member(self, interaction: Interaction, duration: str, member: discord.Member, reason: str="None", show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        target_member_top_role = member.top_role
        member_top_role = interaction.user.top_role
        bot_top_role = interaction.guild.me.top_role

        duration_in_seconds = format_to_seconds_extended(duration.strip())

        if duration_in_seconds is None:
            await interaction.followup.send(
                "Invalid duration. Be sure to format it to **DD:HH:MM:SS**.\n"+
                "Example: **00:03:00:00**.\n"+
                "Additionally, **DD** must not be > **28** and **HH** and **MM** must not be > **59**."
            )
            return
        elif member in (interaction.user, interaction.guild.me):
            await interaction.followup.send("Member cannot be yourself or me.")
            return
        elif member.is_timed_out():
            await interaction.followup.send(f"Member **{member.name}** is already timed out!")
            return
        elif bot_top_role < target_member_top_role:
            await interaction.followup.send(f"My role (**{bot_top_role.name}**) is not high enough to time out member **{member.name}**.")
            return
        elif member_top_role < target_member_top_role:
            await interaction.followup.send(f"Your role (**{member_top_role.name}**) is not high enough to time out member **{member.name}**.")
            return

        until = datetime.now(timezone.utc) + timedelta(seconds=duration_in_seconds)

        await member.timeout(until, reason=reason)
        await interaction.followup.send(
            f"User **{member.name}** has been timed out{f' by **{interaction.user.display_name}**' if show else ''}.\n"
            f"Timeout will expire on **{until.strftime('%Y/%m/%d @ %H:%M:%S')}**."
        )

    @time_out_member.error
    async def handle_time_out_member_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="remove-timeout", description="Removes a timeout from a member.")
    @app_commands.describe(
        member="The member to remove the timeout from.",
        reason="Reason for removing the timeout. (defaults to 'None')",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["REMOVE_TIMEOUT_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    @app_commands.guild_only
    async def remove_timeout_from_member(self, interaction: Interaction, member: discord.Member, reason: str="None", show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        if member in (interaction.user, interaction.guild.me):
            await interaction.followup.send(f"Member cannot be yourself or me.")
            return
        elif not member.is_timed_out():
            await interaction.followup.send(f"Member **{member.name}** is not timed out!")
            return
        
        await member.timeout(None, reason=reason)
        await interaction.followup.send(
            f"{f'**{interaction.user.display_name}** has ' if show else ''}"
            f"{'R' if not show else 'r'}emoved timeout from member **{member.name}**."
        )

    @remove_timeout_from_member.error
    async def handle_remove_timeout_from_member_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="add-role", description="Adds a role to a member.")
    @app_commands.describe(
        role="The role to add to member.",
        member="The member to add the role to.",
        reason="The reason for adding the role. (defaults to 'None')",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ADD_ROLE_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    @app_commands.guild_only
    async def add_role(self, interaction: Interaction, role: discord.Role, member: discord.Member, reason: str="None", show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        member_top_role = interaction.user.top_role
        bot_top_role = interaction.guild.me.top_role
        
        if role in member.roles:
            await interaction.followup.send(f"Member **{member.name}** already has **{role.name}** role!")
            return
        elif bot_top_role < role:
            await interaction.followup.send(f"My role (**{bot_top_role.name}**) is not high enough to add role **{role.name}** to member **{member.name}**.")
            return
        elif member_top_role < role:
            await interaction.followup.send(f"Your role (**{member_top_role.name}**) is not high enough to add role **{role.name}** to member **{member.name}**.")
            return

        await member.add_roles(role, reason=reason)
        await interaction.followup.send(
            f"{f'**{interaction.user.display_name}** has ' if show else ''}"
            f"{'A' if not show else 'a'}dded role **{role.name}** to member **{member.name}**!"
        )

    @add_role.error
    async def handle_add_role_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="remove-role", description="Removes a role from a member.")
    @app_commands.describe(
        role="The role to remove from member.",
        member="The member to remove the role from.",
        reason="The reason for removing the role. (defaults to 'None')",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["REMOVE_ROLE_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    @app_commands.guild_only
    async def remove_role(self, interaction: Interaction, role: discord.Role, member: discord.Member, reason: str="None", show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        member_top_role = interaction.user.top_role
        bot_top_role = interaction.guild.me.top_role
        
        if role not in member.roles:
            await interaction.followup.send(f"Member **{member.name}** doesn't have **{role.name}** role!")
            return
        elif member_top_role < role:
            await interaction.followup.send(f"Your role (**{member_top_role.name}**) is not high enough to remove role **{role.name}** from member **{member.name}**")
            return
        elif bot_top_role < role:
            await interaction.followup.send(f"My role (**{bot_top_role.name}**) is not high enough to remove role **{role.name}** from member **{member.name}**")
            return

        await member.remove_roles(role, reason=reason)
        await interaction.followup.send(
            f"{f'**{interaction.user.display_name}** has ' if show else ''}"
            f"{'R' if not show else 'r'}emoved role **{role.name}** from member **{member.name}**!"
        )

    @remove_role.error
    async def handle_remove_role_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="remove-channel", description="Removes a channel from the current guild.")
    @app_commands.describe(
        channel="The channel to delete.",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["DELETE_CHANNEL_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only
    async def delete_channel(self, interaction: Interaction, channel: discord.abc.GuildChannel, show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        await channel.delete()
        await interaction.followup.send(f"Deleted channel **{channel.name}** (**{channel.id}**) of type **{channel.type.name}**.")

    @delete_channel.error
    async def handle_delete_channel_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="make-text-channel", description="Creates a text channel. See entry in /help for more info.")
    @app_commands.describe(
        name="The new channel's name.",
        topic="The new channel's topic. (default none)",
        category="The category name to apply the channel to. (defaults to no category)",
        announcement="Whether or not the channel is an announcement channel. (default False)",
        slowmode_delay="The slowmode delay to apply to the channel, must be in seconds. (defaults to 0)",
        nsfw="Whether or not the channel is NSFW. (default False)",
        position="The new channel's position relative to all channels. (defaults to 1)",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["CREATE_CHANNEL_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only
    async def create_text_channel(
            self,
            interaction: Interaction,
            name: str,
            topic: str="",
            category: discord.CategoryChannel=None,
            announcement: bool=False,
            slowmode_delay: int=0,
            nsfw: bool=False,
            position: int=1,
            show: bool=False
        ):
        await interaction.response.defer(ephemeral=not show)

        guild_features = interaction.guild.features

        topic = topic.strip()
        name = name.strip()
        channel_amount = len(interaction.guild.channels)
        
        if len(name) > MAX_CHANNEL_NAME_LENGTH:
            await interaction.followup.send(f"Name field is too long! Must be <= **{MAX_CHANNEL_NAME_LENGTH}** characters.")
            return
        elif len(topic) > MAX_TOPIC_LENGTH:
            await interaction.followup.send(f"Topic field is too long! Must be <= **{MAX_TOPIC_LENGTH}** characters.")
            return
        elif position < 1 or position > channel_amount:
            await interaction.followup.send(f"Position must be >= **1** or <= **{channel_amount}**.")
            return
        elif slowmode_delay < 0 or slowmode_delay > MAX_SLOWMODE:
            await interaction.followup.send(f"Slowmode delay must be >= **0** and <= **{MAX_SLOWMODE}**.")
            return
        elif announcement and "NEWS" not in guild_features:
            await interaction.followup.send(f"Announcement channels require a community-enabled guild.")
            return
        
        position -= 1

        created_channel = await interaction.guild.create_text_channel(name, category=category, news=announcement, slowmode_delay=slowmode_delay, nsfw=nsfw, position=position, topic=topic)
        await created_channel.edit(position=created_channel.position) # ??? discord wtf

        await interaction.followup.send(
            f"Created channel **{created_channel.name}** of type **{created_channel.type.name}** with parameters:\n"
            f"Category: **{created_channel.category.name if created_channel.category is not None else 'None'}**\n"
            f"Announcement channel: **{created_channel.is_news()}**\n"
            f"Slowmode delay: **{created_channel.slowmode_delay}** seconds\n"
            f"NSFW: **{created_channel.is_nsfw()}**\n"
            f"Position: **{created_channel.position + 1}**\n"
            f"Topic: **{created_channel.topic if created_channel.topic else 'None'}**."
        )

    @create_text_channel.error
    async def handle_create_channel_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="make-voice-channel", description="Creates a voice channel. See entry in /help for more info.")
    @app_commands.describe(
        name="The name of the new channel.",
        category="The category to apply the new channel to. (defaults to no category)",
        position="The position of the channel relative to all channels. (defaults to 1)",
        bitrate="The bitrate of the new channel. (defaults to 64000)",
        user_limit="The new channel's user limit. (defaults to infinite)",
        video_quality_mode="The new channel's video quality mode, if unsure, leave empty (auto).",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["CREATE_CHANNEL_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only
    async def create_voice_channel(
            self,
            interaction: Interaction,
            name: str,
            category: discord.CategoryChannel=None,
            position: int=1,
            bitrate: int=64000,
            user_limit: int=0,
            video_quality_mode: discord.VideoQualityMode=discord.VideoQualityMode.auto,
            show: bool=False
        ):
        await interaction.response.defer(ephemeral=not show)

        max_bitrate = interaction.guild.bitrate_limit
        channel_amount = len(interaction.guild.channels)
        name = name.strip()

        if len(name) > MAX_CHANNEL_NAME_LENGTH:
            await interaction.followup.send(f"Name field is too long! Must be <= **{MAX_CHANNEL_NAME_LENGTH}** characters.")
            return
        elif user_limit < 0 or user_limit > MAX_USER_LIMIT:
            await interaction.followup.send(f"User limit must be >= **1** and <= **{MAX_USER_LIMIT}**.")
            return
        elif bitrate < 8000 or bitrate > max_bitrate:
            await interaction.followup.send(f"Bitrate must be >= **8000** and <= **{max_bitrate}**.")
            return
        elif position < 1 or position > channel_amount:
            await interaction.followup.send(f"Position should be >= **1** and <= **{channel_amount}**")
            return

        position -= 1

        created_channel = await interaction.guild.create_voice_channel(name, category=category, position=position, bitrate=bitrate, user_limit=user_limit, video_quality_mode=video_quality_mode)
        await created_channel.edit(position=created_channel.position)

        await interaction.followup.send(
            f"Created channel **{created_channel.name}** of type **{created_channel.type.name}** with parameters:\n"
            f"Category: **{created_channel.category.name if created_channel.category is not None else 'None'}**\n"
            f"Position: **{created_channel.position + 1}**\n"
            f"Bitrate: **{created_channel.bitrate}**kbps\n"
            f"User limit: **{created_channel.user_limit}**\n"
            f"Video quality: **{created_channel.video_quality_mode.name}**."
        )

    @create_voice_channel.error
    async def handle_create_voice_channel_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="make-category", description="Creates a category. See entry in /help for more info.")
    @app_commands.describe(
        name="The new category's name.",
        position="The new category's position relative to all channels. (defaults to 1)",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["CREATE_CHANNEL_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only
    async def create_category(self, interaction: Interaction, name: str, position: int=1, show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        name = name.strip()
        channel_amount = len(interaction.guild.channels)

        if len(name) > MAX_CHANNEL_NAME_LENGTH:
            await interaction.followup.send(f"Name field is too long! Must be <= **{MAX_CHANNEL_NAME_LENGTH}** characters.")
            return
        elif position < 1 or position > channel_amount:
            await interaction.followup.send(f"Position must be >= **1** and <= **{channel_amount}**.")
            return

        position -= 1

        created_category = await interaction.guild.create_category(name=name, position=position)
        await created_category.edit(position=created_category.position)

        await interaction.followup.send(f"Created category named **{created_category.name}** at position **{created_category.position + 1}**")

    @create_category.error
    async def handle_create_category_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="make-forum", description="Creates a forum channel. See entry in /help for more info.")
    @app_commands.describe(
        name="The new forum's name.",
        post_guidelines="The new forum's post guidelines. (default none)",
        position="The new forum's position relative to all channels. (defaults to 1)",
        category="The new forum's category. (defaults to no category)",
        slowmode_delay="The slowmode delay to apply to the new forum in seconds. (defaults to 0)",
        nsfw="Whether or not the new forum should be marked as NSFW. (default False)",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["CREATE_CHANNEL_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only
    async def create_forum_channel(
            self,
            interaction: Interaction,
            name: str,
            post_guidelines: str="",
            position: int=1,
            category: discord.CategoryChannel=None,
            slowmode_delay: int=0,
            nsfw: bool=False,
            show: bool=False
        ):
        await interaction.response.defer(ephemeral=not show)

        guild_features = interaction.guild.features

        name = name.strip()
        post_guidelines = post_guidelines.strip()
        channel_amount = len(interaction.guild.channels)

        if len(name) > MAX_CHANNEL_NAME_LENGTH:
            await interaction.followup.send(f"Name field is too long! Must be <= **{MAX_CHANNEL_NAME_LENGTH}** characters.")
            return
        elif len(post_guidelines) > MAX_FORUM_TOPIC_LENGTH:
            await interaction.followup.send(f"Post guidelines field is too long! Must be <= **{MAX_FORUM_TOPIC_LENGTH}** characters.")
            return
        elif position < 1 or position > channel_amount:
            await interaction.followup.send(f"Position must be >= **1** and <= **{channel_amount}**.")
            return
        elif slowmode_delay < 0 or slowmode_delay > MAX_SLOWMODE:
            await interaction.followup.send(f"Slowmode delay must be >= **0** and <= **{MAX_SLOWMODE}**.")
            return
        elif "COMMUNITY" not in guild_features:
            await interaction.followup.send("Forum channels require a community-enabled guild.")
            return

        position -= 1

        created_channel = await interaction.guild.create_forum(name=name, topic=post_guidelines, position=position, category=category, slowmode_delay=slowmode_delay, nsfw=nsfw)
        await created_channel.edit(position=created_channel.position)

        await interaction.followup.send(
            f"Created channel **{created_channel.name}** of type **{created_channel.type.name}** with parameters:\n"
            f"Post guidelines: **{created_channel.topic[:1024] if created_channel.topic else 'None'}**\n"
            f"Position: **{created_channel.position + 1}**\n"
            f"Category: **{created_channel.category.name if created_channel.category is not None else 'None'}**\n"
            f"Slowmode delay: **{created_channel.slowmode_delay}**s\n"
            f"NSFW: **{created_channel.is_nsfw()}**"
        )

    @create_forum_channel.error
    async def handle_create_forum_channel_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="make-stage", description="Creates a stage channel. See entry in /help for more info.")
    @app_commands.describe(
        name="The new stage channel's name.",
        category="The category to apply the new stage channel to. (defaults to no category)",
        position="The position of the new channel relative to all channels. (defaults to 1)",
        bitrate="The new stage channel's bitrate. (defaults to 64000).",
        video_quality_mode="The new stage channel's video quality mode, if unsure, leave the default (auto).",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["CREATE_CHANNEL_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only
    async def create_stage_channel(
            self,
            interaction: Interaction,
            name: str,
            category: discord.CategoryChannel=None,
            position: int=1,
            bitrate: int=64000,
            video_quality_mode: discord.VideoQualityMode=discord.VideoQualityMode.auto,
            show: bool=False
        ):
        await interaction.response.defer(ephemeral=not show)
        
        guild_features = interaction.guild.features

        name = name.strip()
        channel_amount = len(interaction.guild.channels)

        if len(name) > MAX_CHANNEL_NAME_LENGTH:
            await interaction.followup.send(f"Name field is too long! Must be <= **{MAX_CHANNEL_NAME_LENGTH}** characters.")
            return
        elif position < 1 or position > channel_amount:
            await interaction.followup.send(f"Position must be >= **1** and <= **{channel_amount}**.")
            return
        elif bitrate < 8000 or bitrate > MAX_STAGE_BITRATE:
            await interaction.followup.send(f"Bitrate must be >= **8000** or <= **{MAX_STAGE_BITRATE}**.")
            return
        elif "COMMUNITY" not in guild_features:
            await interaction.followup.send("Stage channels require a community-enabled guild.")
            return

        position -= 1

        created_channel = await interaction.guild.create_stage_channel(name=name, category=category, position=position, bitrate=bitrate, video_quality_mode=video_quality_mode)
        await created_channel.edit(position=created_channel.position)

        await interaction.followup.send(
            f"Created channel named **{created_channel.name}** of type **{created_channel.type.name}** with parameters:\n"
            f"Category: **{created_channel.category.name if created_channel.category is not None else 'None'}**\n"
            f"Position: **{created_channel.position + 1}**\n"
            f"Bitrate: **{created_channel.bitrate}**kbps\n"
            f"Video quality mode: **{created_channel.video_quality_mode.name}**"
        )
    
    @create_stage_channel.error
    async def handle_create_stage_channel_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="slowmode", description="Change slowmode of current or specified channel. See entry in /help for more info.")
    @app_commands.describe(
        channel="The channel to modify. Defaults to current one.",
        slowmode_delay="The new slowmode delay in seconds to set.",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["CHANGE_SLOWMODE_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only
    async def change_slowmode(self, interaction: Interaction, slowmode_delay: int, channel: discord.TextChannel=None, show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        if slowmode_delay < 0 or slowmode_delay > MAX_SLOWMODE:
            await interaction.followup.send(f"`slowmode_delay` must be >= **0** and <= **{MAX_SLOWMODE}**.")
            return

        channel = interaction.channel if channel is None else channel
        old_delay = channel.slowmode_delay
        
        if slowmode_delay == old_delay:
            await interaction.followup.send(f"Slowmode delay is already set to **{slowmode_delay}** seconds.")
            return

        new_channel = await channel.edit(slowmode_delay=slowmode_delay)

        await interaction.followup.send(
            f"New slowmode delay applied for channel **{channel.name}**!\n"
            f"Old: **{old_delay}** seconds; New: **{new_channel.slowmode_delay}** seconds"
        )

    @change_slowmode.error
    async def handle_change_slowmode_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="announce", description="Announce a message in the current/specified channel. See entry in /help for more info.")
    @app_commands.describe(
        channel="The channel to announce the message in. Leave empty for current one.",
        message="The message to announce. Must be <= 2000 characters long.",
        no_markdown="Whether or not to ignore markdown text formatting. (default False)",
        no_mentions="Whether or not to ignore formatting of mentions. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ANNOUNCE_MESSAGE_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(send_messages=True)
    @app_commands.guild_only
    async def announce_message(self, interaction: Interaction, message: str, channel: discord.TextChannel=None, no_markdown: bool=False, no_mentions: bool=False):
        await interaction.response.defer(ephemeral=True)
        
        channel = interaction.channel if channel is None else channel
        message = message.strip()

        if len(message) > MAX_ANNOUNCEMENT_LENGTH_LIMIT:
            await interaction.followup.send(f"Message exceeds **{MAX_ANNOUNCEMENT_LENGTH_LIMIT}** characters.")
            return
        
        if no_markdown or no_mentions:
            message = remove_markdown_or_mentions(message, no_markdown, no_mentions)

        await channel.send(message)
        await interaction.followup.send(f"Message announced in channel **{channel.name}**.")

    @announce_message.error
    async def handle_announce_message_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="vckick", description="Kicks a user from a voice channel. See entry in /help for more info.")
    @app_commands.describe(
        member="The member to kick.",
        reason="The reason for kicking the user from its voice channel. (defaults to 'None')",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["VC_KICK_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(move_members=True)
    @app_commands.checks.bot_has_permissions(move_members=True)
    @app_commands.guild_only
    async def kick_user_from_vc(self, interaction: Interaction, member: discord.Member, reason: str="None", show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        target_member_top_role = member.top_role
        member_top_role = interaction.user.top_role
        bot_top_role = interaction.guild.me.top_role
        target_member_vc = member.voice.channel if member.voice is not None else None
        
        if not member.voice:
            await interaction.followup.send(f"Member **{member.name}** is not in a voice channel.")
            return
        elif member_top_role < target_member_top_role:
            await interaction.followup.send(f"Your role (**{member_top_role.name}**) is not high enough to kick **{member.name}** from **{target_member_vc}**.")
            return
        elif bot_top_role < target_member_top_role:
            await interaction.followup.send(f"My role (**{bot_top_role.name}**) is not high enough to kick **{member.name}** from **{target_member_vc}**.")
            return
        
        channel = member.voice.channel
        await member.move_to(None, reason=reason.strip())

        await interaction.followup.send(
            f"Member **{member.name}** has been kicked from voice channel "
            f"**{channel.name}**"
            f"{f' by **{interaction.user.display_name}**' if show else ''}.", ephemeral=not show
        )

    @kick_user_from_vc.error
    async def handle_kick_user_from_vc_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="vcmove", description="Moves member to target voice channel. See entry in /help for more info.")
    @app_commands.describe(
        member="The member to move to target voice channel.",
        target_voice_channel="The target voice channel to move the member to.",
        reason="Reason for moving member to target channel. (defaults to 'None')",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MOVE_USER_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(move_members=True)
    @app_commands.checks.bot_has_permissions(move_members=True)
    @app_commands.guild_only
    async def move_user_to_vc(self, interaction: Interaction, member: discord.Member, target_voice_channel: discord.VoiceChannel, reason: str="None", show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        target_member_top_role = member.top_role
        member_top_role = interaction.user.top_role
        bot_top_role = interaction.guild.me.top_role

        if not member.voice:
            await interaction.followup.send(f"Member **{member.name}** is not in a voice channel.")
            return
        elif member.voice.channel == target_voice_channel:
            await interaction.followup.send(f"Member **{member.name}** is already in **{target_voice_channel.name}**.")
            return
        elif member_top_role < target_member_top_role:
            await interaction.followup.send(f"Your role (**{member_top_role.name}**) is not high enough to move **{member.name}** to **{target_voice_channel.name}**.")
            return
        elif bot_top_role < target_member_top_role:
            await interaction.followup.send(f"My role (**{bot_top_role.name}**) is not high enough to move **{member.name}** to **{target_voice_channel.name}**.")
            return
        
        current_channel = member.voice.channel
        await member.move_to(target_voice_channel, reason=reason.strip())

        await interaction.followup.send(
            f"Member **{member.name}** has been moved from voice channel "
            f"**{current_channel.name}** to **{target_voice_channel.name}**"
            f"{f' by **{interaction.user.display_name}**' if show else ''}."
        )
    
    @move_user_to_vc.error
    async def handle_move_user_to_vc(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)

    @app_commands.command(name="vcmute", description="Mutes a member in voice channel. See entry in /help for more info.")
    @app_commands.describe(
        member="The member to mute.",
        mute="Whether to mute or unmute the member. False will unmute member. (default True)",
        reason="Reason for mute. (defaults to 'None')",
        show="Whether or not to broadcast the action in the current channel. (default False)"
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["VC_MUTE_COMMAND_COOLDOWN"], key=lambda i: i.user.id)
    @app_commands.checks.has_permissions(mute_members=True)
    @app_commands.checks.bot_has_permissions(mute_members=True)
    @app_commands.guild_only
    async def vc_mute_member(self, interaction: Interaction, member: discord.Member, mute: bool=True, reason: str="None", show: bool=False):
        await interaction.response.defer(ephemeral=not show)
        
        target_member_top_role = member.top_role
        member_top_role = interaction.user.top_role
        bot_top_role = interaction.guild.me.top_role
        
        if not member.voice:
            await interaction.followup.send(f"Member **{member.name}** is not in a voice channel.")
            return
        elif member.voice.mute == mute:
            await interaction.followup.send(f"Member **{member.name}** is already **{"muted" if mute else "unmuted"}**.")
            return
        elif member in (interaction.user, interaction.guild.me):
            await interaction.followup.send(f"Member cannot be yourself or me.")
            return
        elif member_top_role < target_member_top_role:
            await interaction.followup.send(f"Your role (**{member_top_role.name}**) is not high enough to mute **{member.name}**.")
            return
        elif bot_top_role < target_member_top_role:
            await interaction.followup.send(f"My role (**{bot_top_role.name}**) is not high enough to mute **{member.name}**.")
            return

        await member.edit(mute=mute, reason=reason.strip())

        await interaction.followup.send(
            f"Member **{member.name}** has been **{'muted' if mute else 'unmuted'}**"
            f"{f' by **{interaction.user.display_name}**' if show else ''}."
        )
        
    @vc_mute_member.error
    async def handle_vc_mute_member_error(self, interaction: Interaction, error: Exception):
        await self.handle_command_error(interaction, error)
