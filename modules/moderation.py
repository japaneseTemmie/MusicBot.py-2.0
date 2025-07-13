""" A complete, simple moderation module for discord.py bot.\n 
Includes a class with a few methods for managing
a Discord guild and its users. """

from settings import *
from handlers import handle_moderation_command_error
from modules.utils import format_minutes_extended
from helpers import *
from bot import Bot

class ModerationCog(commands.Cog):
    def __init__(self, client: Bot):
        self.client = client

    @app_commands.command(name="purge", description="Bulk removes selected amount of text messages in a channel.")
    @app_commands.describe(
        channel="The channel to purge. Leave empty for current.",
        amount="The amount of messages to delete (default 100). Must be > 0 and <= 1000.",
        user="Delete only messages sent by this user.",
        word="Delete only messages that have this word.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["PURGE_CHANNEL_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    @app_commands.guild_only
    async def purge_channel(self, interaction: Interaction, channel: discord.TextChannel=None, amount: int=100, user: discord.Member=None, word: str=None, show: bool=False):
        await interaction.response.defer(ephemeral=True) # This will take ages so we need to defer

        channel = interaction.channel if channel is None else channel
        amount = max(1, min(1000, amount))

        deleted = await channel.purge(limit=amount, check=await get_purge_check(user, word))
        message_amount = len(deleted)

        if message_amount < 1:
            await interaction.followup.send("No messages deleted.")
            if show:
                await interaction.channel.send("No messages deleted.")
            return
        
        await interaction.followup.send(f"Deleted **{message_amount}** {'messages' if message_amount > 1 else 'message'} from channel **{channel.name} ({channel.id})**.") if not show else\
        await interaction.followup.send(f"Finished with **{message_amount}** {'messages' if message_amount > 1 else 'message'}.")
        
        if show:
            await interaction.channel.send(f"Deleted **{message_amount}** {'messages' if message_amount > 1 else 'message'} from channel **{channel.name} ({channel.id})**.")       

    @purge_channel.error
    async def handle_purge_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="kick", description="Kicks a member from the guild.")
    @app_commands.describe(
        member="The member to kick.",
        reason="Reason for kick.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["KICK_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    @app_commands.guild_only
    async def kick_member(self, interaction: Interaction, member: discord.Member, reason: str="None", show: bool=False):
        bot_top_role = interaction.guild.me.top_role
        target_member_top_role = member.top_role
        member_top_role = interaction.user.top_role

        if member in (interaction.user, interaction.guild.me):
            await interaction.response.send_message(f"Member cannot be yourself or me.", ephemeral=True)
            return
        elif bot_top_role <= target_member_top_role:
            await interaction.response.send_message(f"My role is not high enough to kick member **{member.name}**.", ephemeral=True)
            return
        elif member_top_role <= target_member_top_role:
            await interaction.response.send_message(f"Your role is not high enough to kick member **{member.name}**.", ephemeral=True)
            return
        
        await interaction.guild.kick(member, reason=reason)
        
        await interaction.response.send_message(f"Member **{member.name}** has been kicked from the guild{f' by **{interaction.user.display_name}**' if show else ''}.", ephemeral=not show)

    @kick_member.error
    async def handle_kick_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="ban", description="Bans a member from the guild.")
    @app_commands.describe(
        member="The member to ban.",
        reason="Ban reason.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["BAN_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    @app_commands.guild_only
    async def ban_member(self, interaction: Interaction, member: discord.Member, reason: str="None", show: bool=False):
        bot_top_role = interaction.guild.me.top_role
        target_member_top_role = member.top_role
        member_top_role = interaction.user.top_role
        
        if member in (interaction.user, interaction.guild.me):
            await interaction.response.send_message(f"Member cannot be yourself or me.", ephemeral=True)
            return
        elif bot_top_role <= target_member_top_role:
            await interaction.response.send_message(f"My role is not high enough to ban member **{member.name}**.", ephemeral=True)
            return
        elif member_top_role <= target_member_top_role:
            await interaction.response.send_message(f"Your role is not high enough to ban member **{member.name}**.", ephemeral=True)
            return

        await interaction.guild.ban(member, reason=reason)

        await interaction.response.send_message(f"Member **{member.name}** has been banned from the guild"
                                                f"{f' by **{interaction.user.display_name}**' if show else ''}.", ephemeral=not show)

    @ban_member.error
    async def handle_ban_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="unban", description="Unbans a member from the guild.")
    @app_commands.describe(
        member="The member to unban's username or ID",
        show="Whether or not to broadcast the action in the current channel.",
        reason="The unban reason.",
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["UNBAN_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    @app_commands.guild_only
    async def unban_member(self, interaction: Interaction, member: str, reason: str="None", show: bool=False):
        ban_entries = await get_ban_entries(interaction.guild)
        if not ban_entries:
            await interaction.response.send_message("Ban entries are empty.", ephemeral=True)
            return

        member_to_unban = await get_user_to_unban(ban_entries, member.strip())
        if member_to_unban is None:
            await interaction.response.send_message(f"Could not find member **{member}** in ban entries.", ephemeral=True)
            return
        elif member_to_unban in (interaction.user, interaction.guild.me):
            await interaction.response.send_message(f"Member cannot be yourself or me.", ephemeral=True)
            return

        await interaction.guild.unban(member_to_unban, reason=reason.strip())
        await interaction.response.send_message(f"Member **{member_to_unban.name}** has been unbanned"
                                                f"{f' by **{interaction.user.display_name}**' if show else ''}.", ephemeral=not show)

    @unban_member.error
    async def handle_unban_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="timeout", description="Times out a member.")
    @app_commands.describe(
        duration="For how long the user should remain timed out. Must be DD:HH:MM:SS",
        member="The member to timeout.",
        reason="Reason for timeout.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["TIMEOUT_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    @app_commands.guild_only
    async def time_out_member(self, interaction: Interaction, duration: str, member: discord.Member, reason: str="None", show: bool=False):
        target_member_top_role = member.top_role
        member_top_role = interaction.user.top_role
        bot_top_role = interaction.guild.me.top_role

        duration_in_seconds = format_minutes_extended(duration.strip())
        current_time = get_time()

        if duration_in_seconds is None:
            await interaction.response.send_message("Invalid duration, must be **DD:HH:MM:SS**.\nExample: /timeout duration:**00:03:00:00**", ephemeral=True)
            return
        elif member in (interaction.user, interaction.guild.me):
            await interaction.response.send_message("Member cannot be yourself or me.", ephemeral=True)
            return
        elif member.is_timed_out():
            await interaction.response.send_message(f"Member **{member.name}** is already timed out!", ephemeral=True)
            return
        elif bot_top_role <= target_member_top_role:
            await interaction.response.send_message(f"My role is not high enough to time out member **{member.name}**.", ephemeral=True)
            return
        elif member_top_role <= target_member_top_role:
            await interaction.response.send_message(f"Your role is not high enough to time out member **{member.name}**.", ephemeral=True)
            return

        until_time = int(current_time + duration_in_seconds)
        timestamp = datetime.fromtimestamp(until_time).astimezone()

        await member.timeout(timestamp, reason=reason)
        await interaction.response.send_message(
            f"User **{member.name}** has been timed out{f' by **{interaction.user.display_name}**' if show else ''}.\n"
            f"Timeout will expire on **{timestamp.strftime("%Y/%m/%d @ %H:%M:%S")}**.",
            ephemeral=not show
        )

    @time_out_member.error
    async def handle_time_out_member_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="deltimeout", description="Removes a timeout from a user.")
    @app_commands.describe(
        member="The member to remove the timeout from.",
        reason="Reason for removing the timeout.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["REMOVE_TIMEOUT_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    @app_commands.guild_only
    async def remove_timeout_from_member(self, interaction: Interaction, member: discord.Member, reason: str="None", show: bool=False):
        if member in (interaction.user, interaction.guild.me):
            await interaction.response.send_message(f"Member cannot be yourself or me.", ephemeral=True)
            return
        elif not member.is_timed_out():
            await interaction.response.send_message(f"Member **{member.name}** is not timed out!", ephemeral=True)
            return
        
        await member.timeout(None, reason=reason)
        await interaction.response.send_message(f"{f'**{interaction.user.display_name}** has ' if show else ''}"
                                                f"{'R' if not show else 'r'}emoved timeout from member **{member.name}**.", ephemeral=not show)

    @remove_timeout_from_member.error
    async def handle_remove_timeout_from_member_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="add-role", description="Adds a role to a member.")
    @app_commands.describe(
        role="Role to add.",
        member="The member to add the role to.",
        reason="The reason for adding the role.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ADD_ROLE_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    @app_commands.guild_only
    async def add_role(self, interaction: Interaction, role: discord.Role, member: discord.Member, reason: str="None", show: bool=False):
        member_top_role = interaction.user.top_role
        bot_top_role = interaction.guild.me.top_role
        
        if role in member.roles:
            await interaction.response.send_message(f"Member **{member.name}** already has **{role.name}** role!", ephemeral=True)
            return
        elif bot_top_role < role:
            await interaction.response.send_message(f"My role is not high enough to add role **{role.name}** to member **{member.name}**.", ephemeral=True)
            return
        elif member_top_role < role:
            await interaction.response.send_message(f"Your role is not high enough to add role **{role.name}** to member **{member.name}**.", ephemeral=True)
            return

        await member.add_roles(role, reason=reason)
        await interaction.response.send_message(f"{f'**{interaction.user.display_name}** has ' if show else ''}"
                                                f"{'A' if not show else 'a'}dded role **{role.name}** to member **{member.name}**!", ephemeral=not show)

    @add_role.error
    async def handle_add_role_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="remove-role", description="Removes a role from a member.")
    @app_commands.describe(
        role="Role to remove.",
        member="The member to remove the role from.",
        reason="The reason for removing the role.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["REMOVE_ROLE_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    @app_commands.guild_only
    async def remove_role(self, interaction: Interaction, role: discord.Role, member: discord.Member, reason: str="None", show: bool=False):
        member_top_role = interaction.user.top_role
        bot_top_role = interaction.guild.me.top_role
        
        if role not in member.roles:
            await interaction.response.send_message(f"Member **{member.name}** doesn't have **{role.name}** role!", ephemeral=True)
            return
        elif member_top_role < role:
            await interaction.response.send_message(f"Your role is not high enough to remove role **{role.name}** from member **{member.name}**", ephemeral=True)
            return
        elif bot_top_role < role:
            await interaction.response.send_message(f"My role is not high enough to remove role **{role.name}** from member **{member.name}**", ephemeral=True)
            return

        await member.remove_roles(role, reason=reason)
        await interaction.response.send_message(f"{f'**{interaction.user.display_name}** has ' if show else ''}"
                                                f"{'R' if not show else 'r'}emoved role **{role.name}** from member **{member.name}**!", ephemeral=not show)

    @remove_role.error
    async def handle_remove_role_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="delchannel", description="Deletes a channel from the current guild.")
    @app_commands.describe(
        channel="The channel to delete.",
        type="The channel type. Can be text, voice, news, forum, category or stage.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["DELETE_CHANNEL_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only
    async def delete_channel(self, interaction: Interaction, channel: str, type: discord.ChannelType, show: bool=False):
        if len(channel) > 100:
            await interaction.response.send_message(f"`channel` field is too long! Must be < **100** characters.", ephemeral=True)
            return
        
        channel_to_delete = await get_channel(interaction.guild.channels, channel, type)
        
        if channel_to_delete is None:
            await interaction.response.send_message(f"Could not find channel **{channel}** that matches type **{type}**.", ephemeral=True)
            return
        
        await channel_to_delete.delete()
        await interaction.response.send_message(f"Deleted channel **{channel_to_delete.name}** (**{channel_to_delete.id}**) of type **{channel_to_delete.type.name}**", ephemeral=not show)

    @delete_channel.error
    async def handle_delete_channel_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="make-text-channel", description="Creates a text channel.")
    @app_commands.describe(
        name="The new channel's name.",
        topic="The new channel's topic.",
        category="The category name to apply the channel to.",
        announcement="Whether or not the channel is an announcement channel.",
        slowmode_delay="The slowmode delay to apply to the channel, must be in seconds.",
        nsfw="Whether or not the channel is NSFW.",
        position="The new channel's position relative to all channels. See entry in /help for more info.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["CREATE_CHANNEL_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only
    async def create_text_channel(self,
        interaction: Interaction,
        name: str,
        topic: str="",
        category: discord.CategoryChannel=None,
        announcement: bool=False,
        slowmode_delay: int=0,
        nsfw: bool=False,
        position: int=0,
        show: bool=False
        ):
        
        guild_features = interaction.guild.features
        topic = topic.strip()
        name = name.strip()
        if len(name) > 100:
            await interaction.response.send_message("`name` field is too long! Must be < **100** characters.", ephemeral=True)
            return

        if len(topic) > 1024:
            await interaction.response.send_message("`topic` field is too long! Must be < **1024** characters.", ephemeral=True)
            return

        position = max(0, min(position, len(interaction.guild.channels)))
        slowmode_delay = max(0, min(slowmode_delay, 21600))

        channel = await get_channel(interaction.guild.channels, name)
        if channel is not None:
            await interaction.response.send_message(f"A channel named **{channel.name}** of type **{channel.type.name}** already exists!", ephemeral=True)
            return
        elif announcement and "NEWS" not in guild_features:
            await interaction.response.send_message(f"News channels require a community-enabled guild.", ephemeral=True)
            return

        created_channel = await interaction.guild.create_text_channel(name, category=category, news=announcement, slowmode_delay=slowmode_delay, nsfw=nsfw, position=position, topic=topic)

        await interaction.response.send_message(f"Created channel **{created_channel.name}** of type **{created_channel.type.name}** with parameters:\n"
                                                f"Category: **{created_channel.category.name if created_channel.category is not None else 'None'}**\n"
                                                f"News: **{created_channel.is_news()}**\n"
                                                f"Slowmode delay: **{created_channel.slowmode_delay}** seconds\n"
                                                f"NSFW: **{created_channel.is_nsfw()}**\n"
                                                f"Position: **{created_channel.position}**\n"
                                                f"Topic: **{created_channel.topic if created_channel.topic else 'None'}**.", ephemeral=not show)

    @create_text_channel.error
    async def handle_create_channel_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="make-voice-channel", description="Creates a voice channel.")
    @app_commands.describe(
        name="The name of the new channel.",
        category="The category to apply the new channel to. Leave empty for none.",
        position="The position of the channel relative to all channels. See entry in /help for more info.",
        bitrate="The bitrate of the new channel, must be >= 8000 and <= 96000.",
        user_limit="The new channel's user limit. Must be >= 0 and <= 99.",
        video_quality_mode="The new channel's video quality mode, if unsure, leave empty (auto).",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["CREATE_CHANNEL_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only
    async def create_voice_channel(self,
        interaction: Interaction,
        name: str,
        category: discord.CategoryChannel=None,
        position: int=0,
        bitrate: int=64000,
        user_limit: int=0,
        video_quality_mode: discord.VideoQualityMode=discord.VideoQualityMode.auto,
        show: bool=False
        ):
        
        position = max(0, min(position, len(interaction.guild.channels)))
        bitrate = max(8000, min(bitrate, 96000))
        user_limit = max(0, min(99, user_limit))
        name = name.strip()

        if len(name) > 100:
            await interaction.response.send_message("`name` field is too long! Must be < **100** characters.", ephemeral=True)
            return

        channel = await get_channel(interaction.guild.channels, name, discord.ChannelType.voice)
        if channel is not None:
            await interaction.response.send_message(f"Channel **{channel.name}** matching type **{channel.type.name}** already exists.", ephemeral=True)
            return
        
        created_channel = await interaction.guild.create_voice_channel(name, category=category, position=position, bitrate=bitrate, user_limit=user_limit, video_quality_mode=video_quality_mode)

        await interaction.response.send_message(f"Created channel **{created_channel.name}** of type **{created_channel.type.name}** with parameters:\n"
                                                f"Category: **{created_channel.category.name if created_channel.category is not None else 'None'}**\n"
                                                f"Position: **{created_channel.position}**\n"
                                                f"Bitrate: **{created_channel.bitrate}**kbps\n"
                                                f"User limit: **{created_channel.user_limit}**\n"
                                                f"Video quality: **{created_channel.video_quality_mode.name}**.", ephemeral=not show)

    @create_voice_channel.error
    async def handle_create_voice_channel_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="make-category", description="Creates a category.")
    @app_commands.describe(
        name="The new category's name.",
        position="The new category's position relative to all categories. See entry in /help for more info.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["CREATE_CHANNEL_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only
    async def create_category(self, interaction: Interaction, name: str, position: int=0, show: bool=False):
        position = max(0, min(position, len(interaction.guild.channels)))
        name = name.strip()

        category = await get_channel(interaction.guild.channels, name, discord.ChannelType.category)
        if category is not None:
            await interaction.response.send_message(f"A category named **{category.name}** already exists.", ephemeral=True)
            return
        elif len(name) > 100:
            await interaction.response.send_message("`name` field is too long! Must be < **100** characters.", ephemeral=True)
            return

        created_category = await interaction.guild.create_category(name=name, position=position)

        await interaction.response.send_message(f"Created category named **{created_category.name}** with position **{created_category.position}**", ephemeral=not show)

    @create_category.error
    async def handle_create_category_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="make-forum", description="Creates a forum channel.")
    @app_commands.describe(
        name="The new forum's name.",
        post_guidelines="The new forum's post guidelines. Must be < 1024 characters.",
        position="The new forum's position relative to all channels. See /help command:makeforum.",
        category="The new forum's category, leave empty for none.",
        slowmode_delay="The slowmode delay to apply to the new forum in seconds, default is 0 and max is 21600.",
        nsfw="Whether or not the new forum should be marked as NSFW.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["CREATE_CHANNEL_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only
    async def create_forum_channel(self,
        interaction: Interaction,
        name: str,
        post_guidelines: str="",
        position: int=0,
        category: discord.CategoryChannel=None,
        slowmode_delay: int=0,
        nsfw: bool=False,
        show: bool=False
        ):

        guild_features = interaction.guild.features
        position = max(0, min(len(interaction.guild.channels), position))
        slowmode_delay = max(0, min(slowmode_delay, 21600))
        name = name.strip()
        post_guidelines = post_guidelines.strip()

        if len(name) > 100:
            await interaction.response.send_message("`name` field is too long! Must be < **100** characters.", ephemeral=True)
            return
        if len(post_guidelines) > 1024:
            await interaction.response.send_message("`post_guidelines` field is too long! Must be < **1024** characters.", ephemeral=True)
            return

        channel = await get_channel(interaction.guild.channels, name, discord.ChannelType.forum)
        if channel is not None:
            await interaction.response.send_message(f"Channel named **{channel.name}** that matches type {channel.type.name} already exists.", ephemeral=True)
            return
        elif "COMMUNITY" not in guild_features:
            await interaction.response.send_message("Forum channels require a community-enabled guild.", ephemeral=True)
            return

        created_channel = await interaction.guild.create_forum(name=name, topic=post_guidelines, position=position, category=category, slowmode_delay=slowmode_delay, nsfw=nsfw)
        await interaction.response.send_message(f"Created channel **{created_channel.name}** of type **{created_channel.type.name}** with parameters:\n"
                                                f"Topic: **{created_channel.topic if created_channel.topic else 'None'}**\n"
                                                f"Position: **{created_channel.position}**\n"
                                                f"Category: **{created_channel.category.name if created_channel.category is not None else 'None'}**\n"
                                                f"Slowmode delay: **{created_channel.slowmode_delay}**\n"
                                                f"NSFW: **{created_channel.is_nsfw()}**", ephemeral=not show)

    @create_forum_channel.error
    async def handle_create_forum_channel_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="make-stage", description="Creates a stage channel.")
    @app_commands.describe(
        name="The new stage channel's name.",
        category="The category to apply the new stage channel to. Leave empty for none.",
        position="The position of the new channel relative to all channels. See entry in /help for more info.",
        bitrate="The new stage channel's bitrate. Must be >= 8000 and <= 64000. Defaults to 64000.",
        video_quality_mode="The new stage channel's video quality mode, if unsure, leave the default (auto).",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["CREATE_CHANNEL_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only
    async def create_stage_channel(self,
            interaction: Interaction,
            name: str,
            category: discord.CategoryChannel=None,
            position: int=0,
            bitrate: int=64000,
            video_quality_mode: discord.VideoQualityMode=discord.VideoQualityMode.auto,
            show: bool=False
        ):
        
        guild_features = interaction.guild.features
        position = max(0, min(len(interaction.guild.channels), position))
        bitrate = max(8000, min(64000, bitrate))
        name = name.strip()

        channel = await get_channel(interaction.guild.channels, name, discord.ChannelType.stage_voice)
        if channel is not None:
            await interaction.response.send_message(f"Channel named **{channel.name}** that matches type **{channel.type.name}** already exists.", ephemeral=True)
            return
        elif "COMMUNITY" not in guild_features:
            await interaction.response.send_message("Stage channels require a community-enabled guild.", ephemeral=True)
            return
        elif len(name) > 100:
            await interaction.response.send_message("`name` field is too long! Must be < **100** characters.", ephemeral=True)
            return

        created_channel = await interaction.guild.create_stage_channel(name=name, category=category, position=position, bitrate=bitrate, video_quality_mode=video_quality_mode)
        await interaction.response.send_message(f"Created channel named **{created_channel.name}** of type **{created_channel.type.name}** with parameters:\n"
                                                f"Category: **{created_channel.category.name if created_channel.category is not None else 'None'}**\n"
                                                f"Position: **{created_channel.position}**\n"
                                                f"Bitrate: **{created_channel.bitrate}**kbps\n"
                                                f"Video quality mode: **{created_channel.video_quality_mode.name}**", ephemeral=not show)
    
    @create_stage_channel.error
    async def handle_create_stage_channel_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="slowmode", description="Change slowmode of current or specified channel.")
    @app_commands.describe(
        channel="The channel to modify. Defaults to current one.",
        slowmode_delay="The new slowmode delay in seconds to set. 0 for none, maximum is 21600.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["CHANGE_SLOWMODE_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only
    async def change_slowmode(self, interaction: Interaction, slowmode_delay: int, channel: discord.TextChannel=None, show: bool=False):
        channel = interaction.channel if channel is None else channel
        slowmode_delay = max(0, min(slowmode_delay, 21600))
        old_delay = int(channel.slowmode_delay) # Make a copy of the integer

        await channel.edit(slowmode_delay=slowmode_delay)

        await interaction.response.send_message(f"New slowmode delay applied for channel **{channel.name}**!\n"
                                                f"Old: **{old_delay}** seconds; New: **{channel.slowmode_delay}** seconds",
                                                ephemeral=not show)

    @change_slowmode.error
    async def handle_change_slowmode_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="announce", description="Announce a message in the current/specified channel.")
    @app_commands.describe(
        channel="The channel to announce the message in. Leave empty for current one.",
        message="The message to announce. Must be < 2000 characters long.",
        no_markdown="Whether or not to ignore markdown text formatting.",
        no_mentions="Whether or not to ignore formatting of mentions."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["ANNOUNCE_MESSAGE_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(send_messages=True)
    @app_commands.guild_only
    async def announce_message(self, interaction: Interaction, message: str, channel: discord.TextChannel=None, no_markdown: bool=False, no_mentions: bool=False):
        channel = interaction.channel if channel is None else channel
        message = message.strip()

        if len(message) > 2000:
            await interaction.response.send_message("Message exceeds **2000** characters.", ephemeral=True)
            return
        
        if no_markdown or no_mentions:
            message = await remove_markdown_or_mentions(message, no_markdown, no_mentions)

        await channel.send(message)
        await interaction.response.send_message(f"Message announced in channel **{interaction.channel.name}**.", ephemeral=True)

    @announce_message.error
    async def handle_announce_message_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="vckick", description="Kicks a user from a voice channel.")
    @app_commands.describe(
        member="The member to kick.",
        reason="The reason for kicking the user from its voice channel.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["VC_KICK_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(move_members=True)
    @app_commands.checks.bot_has_permissions(move_members=True)
    @app_commands.guild_only
    async def kick_user_from_vc(self, interaction: Interaction, member: discord.Member, reason: str="None", show: bool=False):
        target_member_top_role = member.top_role
        member_top_role = interaction.user.top_role
        bot_top_role = interaction.guild.me.top_role
        target_member_vc = member.voice.channel if member.voice is not None else None
        
        if not member.voice:
            await interaction.response.send_message(f"Member **{member.name}** is not in a voice channel.", ephemeral=True)
            return
        elif member in (interaction.user, interaction.guild.me):
            await interaction.response.send_message(f"Member cannot be yourself or me.", ephemeral=True)
            return
        elif member_top_role <= target_member_top_role:
            await interaction.response.send_message(f"Your role is not high enough to kick **{member.name}** from **{target_member_vc}**.", ephemeral=True)
            return
        elif bot_top_role <= target_member_top_role:
            await interaction.response.send_message(f"My role is not high enough to kick **{member.name}** from **{target_member_vc}**.", ephemeral=True)
            return
        
        channel = member.voice.channel
        await member.move_to(None, reason=reason.strip())

        await interaction.response.send_message(f"Member **{member.name}** has been kicked from voice channel "
                                                f"**{channel.name}**"
                                                f"{f' by **{interaction.user.display_name}**' if show else ''}.", ephemeral=not show)

    @kick_user_from_vc.error
    async def handle_kick_user_from_vc_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="vcmove", description="Moves member to target voice channel.")
    @app_commands.describe(
        member="The member to move to the new target voice channel.",
        target_voice_channel="The target voice channel to move the member to.",
        reason="Reason for moving member to target channel.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["MOVE_USER_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(move_members=True)
    @app_commands.checks.bot_has_permissions(move_members=True)
    @app_commands.guild_only
    async def move_user_to_vc(self, interaction: Interaction, member: discord.Member, target_voice_channel: discord.VoiceChannel, reason: str="None", show: bool=False):
        target_member_top_role = member.top_role
        member_top_role = interaction.user.top_role
        bot_top_role = interaction.guild.me.top_role

        if not member.voice:
            await interaction.response.send_message(f"Member **{member.name}** is not in a voice channel.", ephemeral=True)
            return
        elif member.voice.channel == target_voice_channel:
            await interaction.response.send_message(f"Member **{member.name}** is already in **{target_voice_channel.name}**.", ephemeral=True)
            return
        elif member in (interaction.user, interaction.guild.me):
            await interaction.response.send_message(f"Member cannot be yourself or me.", ephemeral=True)
            return
        elif member_top_role <= target_member_top_role:
            await interaction.response.send_message(f"Your role is not high enough to move **{member.name}** to **{target_voice_channel.name}**.", ephemeral=True)
            return
        elif bot_top_role <= target_member_top_role:
            await interaction.response.send_message(f"My role is not high enough to move **{member.name}** to **{target_voice_channel.name}**.", ephemeral=True)
            return
        
        current_channel = member.voice.channel
        await member.move_to(target_voice_channel, reason=reason.strip())

        await interaction.response.send_message(f"Member **{member.name}** has been moved from voice channel "
                                                f"**{current_channel.name}** to **{target_voice_channel.name}**"
                                                f"{f' by **{interaction.user.display_name}**' if show else ''}.", ephemeral=not show)
    
    @move_user_to_vc.error
    async def handle_move_user_to_vc(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)

    @app_commands.command(name="vcmute", description="Mutes/deafens a member in voice channel.")
    @app_commands.describe(
        member="The member to mute.",
        mute="Whether to mute or unmute the member. False to unmute, True to mute (default).",
        reason="Reason for mute.",
        show="Whether or not to broadcast the action in the current channel."
    )
    @app_commands.checks.cooldown(rate=1, per=COOLDOWNS["VC_MUTE_COMMAND_COOLDOWN"], key=lambda i: i.guild.id)
    @app_commands.checks.has_permissions(mute_members=True)
    @app_commands.checks.bot_has_permissions(mute_members=True)
    @app_commands.guild_only
    async def vc_mute_member(self, interaction: Interaction, member: discord.Member, mute: bool=True, reason: str="None", show: bool=False):
        target_member_top_role = member.top_role
        member_top_role = interaction.user.top_role
        bot_top_role = interaction.guild.me.top_role
        
        if not member.voice:
            await interaction.response.send_message(f"Member **{member.name}** is not in a voice channel.", ephemeral=True)
            return
        elif member.voice.mute == mute:
            await interaction.response.send_message(f"Member **{member.name}** is already **{"muted" if mute else "unmuted"}**.", ephemeral=True)
            return
        elif member in (interaction.user, interaction.guild.me):
            await interaction.response.send_message(f"Member cannot be yourself or me.", ephemeral=True)
            return
        elif member_top_role <= target_member_top_role:
            await interaction.response.send_message(f"Your role is not high enough to mute **{member.name}**.", ephemeral=True)
            return
        elif bot_top_role <= target_member_top_role:
            await interaction.response.send_message(f"My role is not high enough to mute **{member.name}**.", ephemeral=True)
            return

        await member.edit(mute=mute, reason=reason.strip())

        await interaction.response.send_message(f"Member **{member.name}** has been **{"muted" if mute else "unmuted"}**"
                                                f"{f' by **{interaction.user.display_name}**' if show else ''}.", ephemeral=not show)
        
    @vc_mute_member.error
    async def handle_vc_mute_member_error(self, interaction: Interaction, error):
        await handle_moderation_command_error(interaction, error)
