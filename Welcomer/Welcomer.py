import json
import asyncio

import discord
from discord.ext import commands

from .models import apply_vars, SafeString


====
# Helpers

def default_invite():
    """
    Fallback value when the actual invite cannot be detected.
    """
    return SafeString("{unable to get invite}")


# Message Modal

class MessageModal(discord.ui.Modal):
    def __init__(
        self,
        cog,
        guild_id,
        channel,
        current_message=None
    ):
        super().__init__(title="Welcome Message")

        self.cog = cog
        self.guild_id = guild_id
        self.channel = channel

        self.message_input = discord.ui.TextInput(
            label="Welcome Message",
            placeholder=(
                "Welcome {member.mention} to {guild.name}!"
            ),
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000,
            default=current_message or ""
        )

        self.add_item(self.message_input)

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):
        message = self.message_input.value

        # Validate / format the message before saving.
        formatted = self.cog.format_message(
            interaction.user,
            message,
            default_invite()
        )

        if formatted is None:
            await interaction.response.send_message(
                "❌ Invalid welcome message.",
                ephemeral=True
            )
            return

        await self.cog.save_config(
            self.guild_id,
            self.channel,
            message,
            "message"
        )

        await interaction.response.send_message(
            f"✅ Welcome message saved for "
            f"{self.channel.mention}.",
            ephemeral=True
        )


# Embed JSON Modal

class EmbedModal(discord.ui.Modal):
    def __init__(
        self,
        cog,
        guild_id,
        channel,
        current_message=None
    ):
        super().__init__(title="Welcome Embed JSON")

        self.cog = cog
        self.guild_id = guild_id
        self.channel = channel

        self.embed_input = discord.ui.TextInput(
            label="Embed JSON",
            placeholder=(
                '{"embeds":[{"title":"Welcome!",'
                '"description":"Hello {member.mention}!"}]}'
            ),
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000,
            default=current_message or ""
        )

        self.add_item(self.embed_input)

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):
        raw_json = self.embed_input.value

        # Use the same parser as Test / Join.
        # This means the JSON accepted by the modal is
        # exactly the same JSON that the plugin can actually send.
        formatted = self.cog.format_message(
            interaction.user,
            raw_json,
            default_invite()
        )

        if formatted is None:
            await interaction.response.send_message(
                "❌ Invalid Embed JSON.\n\n"
                "Supported formats include:\n"
                "• Discord message JSON with `embeds: []`\n"
                "• A single embed object\n"
                "• `{ \"embed\": { ... } }`",
                ephemeral=True
            )
            return

        await self.cog.save_config(
            self.guild_id,
            self.channel,
            raw_json,
            "embed"
        )

        await interaction.response.send_message(
            f"✅ Welcome embed saved for "
            f"{self.channel.mention}.",
            ephemeral=True
        )


# Configuration View

class WelcomerView(discord.ui.View):

    def __init__(
        self,
        cog,
        author_id,
        guild_id,
        channel,
        config=None
    ):
        super().__init__(timeout=300)

        self.cog = cog
        self.author_id = author_id
        self.guild_id = guild_id
        self.channel = channel
        self.config = config

    # --------------------------------------------------------
    # Interaction Permission
    # --------------------------------------------------------

    async def interaction_check(
        self,
        interaction: discord.Interaction
    ):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the person who opened this "
                "configuration panel can use these buttons.",
                ephemeral=True
            )
            return False

        return True

    # --------------------------------------------------------
    # Message Button
    # --------------------------------------------------------

    @discord.ui.button(
        label="Message",
        style=discord.ButtonStyle.primary
    )
    async def message_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        current = None

        if (
            self.config
            and self.config.get("type") == "message"
        ):
            current = self.config.get("message")

        await interaction.response.send_modal(
            MessageModal(
                self.cog,
                self.guild_id,
                self.channel,
                current
            )
        )

    # --------------------------------------------------------
    # Embed JSON Button
    # --------------------------------------------------------

    @discord.ui.button(
        label="Embed JSON",
        style=discord.ButtonStyle.secondary
    )
    async def embed_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        current = None

        if (
            self.config
            and self.config.get("type") == "embed"
        ):
            current = self.config.get("message")

        await interaction.response.send_modal(
            EmbedModal(
                self.cog,
                self.guild_id,
                self.channel,
                current
            )
        )

    # --------------------------------------------------------
    # Test Button
    # --------------------------------------------------------

    @discord.ui.button(
        label="Test",
        style=discord.ButtonStyle.success
    )
    async def test_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        config = await self.cog.get_config(
            self.guild_id
        )

        if not config:
            await interaction.response.send_message(
                "❌ No Welcomer configuration exists yet.",
                ephemeral=True
            )
            return

        message = config.get("message")

        if not message:
            await interaction.response.send_message(
                "❌ No welcome message has been configured.",
                ephemeral=True
            )
            return

        # During Test, {member.*} refers to the user
        # who clicked the Test button.
        invite = default_invite()

        formatted = self.cog.format_message(
            interaction.user,
            message,
            invite
        )

        if formatted is None:
            await interaction.response.send_message(
                "❌ The saved welcome configuration "
                "is invalid.",
                ephemeral=True
            )
            return

        try:
            await self.channel.send(
                **formatted
            )

            await interaction.response.send_message(
                "✅ Test welcome message sent.",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to send messages "
                f"in {self.channel.mention}.",
                ephemeral=True
            )

        except discord.HTTPException as exc:
            await interaction.response.send_message(
                "❌ Discord rejected the message:\n"
                f"```text\n{exc}\n```",
                ephemeral=True
            )

    # --------------------------------------------------------
    # Disable Button
    # --------------------------------------------------------

    @discord.ui.button(
        label="Disable",
        style=discord.ButtonStyle.danger
    )
    async def disable_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.cog.disable_config(
            self.guild_id
        )

        embed = discord.Embed(
            title="Welcomer Disabled",
            description=(
                "The Welcomer has been disabled "
                f"for {self.channel.mention}."
            ),
            color=discord.Color.red()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=None
        )


# Welcomer Cog

class Welcomer(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

        # ----------------------------------------------------
        # Modmail Plugin Database
        #
        # Support both newer and older Modmail database APIs.
        # ----------------------------------------------------

        if hasattr(bot, "api") and hasattr(
            bot.api,
            "get_plugin_partition"
        ):
            self.db = bot.api.get_plugin_partition(self)

        elif hasattr(bot, "plugin_db") and hasattr(
            bot.plugin_db,
            "get_partition"
        ):
            self.db = bot.plugin_db.get_partition(self)

        else:
            raise RuntimeError(
                "Unable to find a compatible Modmail "
                "plugin database API."
            )

        # ----------------------------------------------------
        # Invite Cache
        #
        # guild_id -> {
        #     invite_id: uses
        # }
        # ----------------------------------------------------

        self.invite_cache = {}

        # Start invite cache task.
        self.invite_cache_task = (
            bot.loop.create_task(
                self.populate_invite_cache()
            )
        )

    # Cog Unload
    
    def cog_unload(self):
        if (
            hasattr(self, "invite_cache_task")
            and self.invite_cache_task
        ):
            self.invite_cache_task.cancel()

    # Invite Cache
    
    async def populate_invite_cache(self):
        """
        Populate invite usage cache for every guild.
        """

        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            await self.update_invite_cache(guild)

    async def update_invite_cache(self, guild):
        """
        Refresh the invite cache for one guild.
        """

        try:
            invites = await guild.invites()

        except discord.Forbidden:
            self.invite_cache[guild.id] = {}
            return

        except discord.HTTPException:
            self.invite_cache[guild.id] = {}
            return

        self.invite_cache[guild.id] = {
            invite.id: (
                invite.uses or 0
            )
            for invite in invites
        }

    async def get_used_invite(self, guild):
        """
        Try to detect which invite was used.

        Returns:
            discord.Invite
            or
            default_invite()
        """

        old_cache = self.invite_cache.get(
            guild.id,
            {}
        )

        try:
            invites = await guild.invites()

        except discord.Forbidden:
            return default_invite()

        except discord.HTTPException:
            return default_invite()

        new_cache = {
            invite.id: (
                invite.uses or 0
            )
            for invite in invites
        }

        for invite in invites:

            old_uses = old_cache.get(
                invite.id,
                0
            )

            new_uses = invite.uses or 0

            if new_uses > old_uses:
                self.invite_cache[guild.id] = new_cache

                return invite

        # Update cache even if we didn't find the invite.

        self.invite_cache[guild.id] = new_cache

        return default_invite()

    # Database
    
    async def get_config(self, guild_id):
        """
        Get Welcomer configuration for a guild.
        """

        document = await self.db.find_one(
            {
                "_id": str(guild_id)
            }
        )

        if not document:
            return None

        return document.get(
            "welcomer"
        )

    async def save_config(
        self,
        guild_id,
        channel,
        message,
        message_type
    ):
        """
        Save Welcomer configuration.
        """

        await self.db.find_one_and_update(
            {
                "_id": str(guild_id)
            },
            {
                "$set": {
                    "welcomer": {
                        "channel": str(channel.id),
                        "message": message,
                        "type": message_type,
                        "enabled": True
                    }
                }
            },
            upsert=True
        )

    async def disable_config(
        self,
        guild_id
    ):
        """
        Disable Welcomer for a guild.
        """

        await self.db.find_one_and_update(
            {
                "_id": str(guild_id)
            },
            {
                "$set": {
                    "welcomer.enabled": False
                }
            },
            upsert=True
        )

    # Variable Replacement
    
    def apply_vars_dict(
        self,
        member,
        message,
        invite
    ):
        """
        Recursively replace variables inside JSON.

        Supports variables in:
        - strings
        - dictionaries
        - lists
        """

        if isinstance(message, dict):

            result = {}

            for key, value in message.items():

                result[key] = self.apply_vars_dict(
                    member,
                    value,
                    invite
                )

            return result

        if isinstance(message, list):

            return [
                self.apply_vars_dict(
                    member,
                    item,
                    invite
                )
                for item in message
            ]

        if isinstance(message, str):

            return apply_vars(
                self,
                member,
                message,
                invite
            )

        return message

    # Message Formatting
    
    def format_message(
        self,
        member,
        message,
        invite
    ):
        """
        Convert saved configuration into kwargs
        accepted by discord.py's channel.send().

        Supported:

        1. Plain text

            Hello {member.mention}

        2. Direct Embed JSON

            {
                "title": "Welcome!",
                "description": "Hello!"
            }

        3. Wrapped Embed JSON

            {
                "embed": {
                    "title": "Welcome!"
                }
            }

        4. Full Discord message JSON

            {
                "content": "Hello!",
                "embeds": [
                    {
                        "title": "Welcome!"
                    }
                ],
                "components": []
            }
        """

        if not isinstance(
            message,
            str
        ):
            return None

        # ----------------------------------------------------
        # Try JSON first.
        # ----------------------------------------------------

        try:
            data = json.loads(message)

        except json.JSONDecodeError:

            # Not JSON -> normal text message.
            content = apply_vars(
                self,
                member,
                message,
                invite
            )

            return {
                "content": content
            }

        # ----------------------------------------------------
        # JSON must be an object.
        # ----------------------------------------------------

        if not isinstance(
            data,
            dict
        ):
            return None

        # ----------------------------------------------------
        # Replace variables recursively.
        # ----------------------------------------------------

        data = self.apply_vars_dict(
            member,
            data,
            invite
        )

        # ----------------------------------------------------
        # Build Discord message.
        # ----------------------------------------------------

        try:

            result = {}

            # =================================================
            # Content
            # =================================================

            if "content" in data:

                content = data["content"]

                if content is not None:

                    if not isinstance(
                        content,
                        str
                    ):
                        return None

                    result["content"] = content

            # =================================================
            # Full Discord JSON:
            #
            # "embeds": [...]
            # =================================================

            if "embeds" in data:

                embeds_data = data["embeds"]

                if not isinstance(
                    embeds_data,
                    list
                ):
                    return None

                embeds = []

                for embed_data in embeds_data:

                    if not isinstance(
                        embed_data,
                        dict
                    ):
                        return None

                    embed = discord.Embed.from_dict(
                        embed_data
                    )

                    embeds.append(embed)

                result["embeds"] = embeds

            # =================================================
            # Wrapped format:
            #
            # "embed": {...}
            # =================================================

            elif "embed" in data:

                embed_data = data["embed"]

                if not isinstance(
                    embed_data,
                    dict
                ):
                    return None

                embed = discord.Embed.from_dict(
                    embed_data
                )

                result["embed"] = embed

            # =================================================
            # Direct Embed JSON:
            #
            # {
            #   "title": "...",
            #   "description": "..."
            # }
            #
            # Do not treat arbitrary Discord message keys
            # as embed keys.
            # =================================================

            elif any(
                key in data
                for key in (
                    "title",
                    "description",
                    "fields",
                    "color",
                    "footer",
                    "author",
                    "thumbnail",
                    "image",
                    "timestamp",
                    "url"
                )
            ):

                embed = discord.Embed.from_dict(
                    data
                )

                result["embed"] = embed

            # =================================================
            # Components
            #
            # Your JSON may contain:
            #
            # "components": []
            #
            # Welcomer currently does not build interactive
            # Discord components from arbitrary JSON.
            #
            # Empty components are therefore ignored.
            # =================================================

            if "components" in data:

                components = data["components"]

                if (
                    components
                    and not isinstance(
                        components,
                        list
                    )
                ):
                    return None

                # Currently intentionally ignored.

            # ------------------------------------------------
            # Nothing usable.
            # ------------------------------------------------

            if not result:
                return None

            return result

        except (
            ValueError,
            TypeError,
            KeyError
        ):
            return None

    # Configuration Command
    
    @commands.guild_only()
    @commands.has_permissions(
        manage_guild=True
    )
    @commands.command()
    async def welcomer(
        self,
        ctx,
        channel: discord.TextChannel
    ):
        """
        Configure the Welcomer.

        Usage:
            <prefix>welcomer #channel

        The actual prefix is automatically taken from
        Modmail's configured command prefix.
        """

        config = await self.get_config(
            ctx.guild.id
        )

        # Configuration Embed
        
        embed = discord.Embed(
            title="Welcomer Configuration",
            color=discord.Color.blurple()
        )

        embed.description = (
            f"Configure the welcome message for "
            f"{channel.mention}.\n\n"
            "Choose how you want your welcome message "
            "to be configured."
        )

        # Existing Configuration
        
        if config:

            enabled = config.get(
                "enabled",
                True
            )

            message_type = config.get(
                "type",
                "unknown"
            )

            status = (
                "Enabled"
                if enabled
                else "Disabled"
            )

            configured_channel_id = config.get(
                "channel"
            )

            configured_channel = (
                self.bot.get_channel(
                    int(configured_channel_id)
                )
                if configured_channel_id
                and str(configured_channel_id).isdigit()
                else None
            )

            configured_channel_text = (
                configured_channel.mention
                if configured_channel
                else f"<#{configured_channel_id}>"
                if configured_channel_id
                else "Unknown"
            )

            embed.add_field(
                name="Current Configuration",
                value=(
                    f"**Channel:** "
                    f"{configured_channel_text}\n"
                    f"**Type:** `{message_type}`\n"
                    f"**Status:** `{status}`"
                ),
                inline=False
            )

        else:

            embed.add_field(
                name="Current Configuration",
                value=(
                    "No Welcomer has been configured yet."
                ),
                inline=False
            )

        # Message Information
        
        embed.add_field(
            name="Message",
            value=(
                "Configure a normal text welcome message."
            ),
            inline=False
        )

        # Embed Information
        
        embed.add_field(
            name="Embed JSON",
            value=(
                "Configure a Discord embed using JSON.\n"
                "You can also use Discord's full JSON format "
                "with `embeds` and `content`."
            ),
            inline=False
        )

        # Variables
        
        embed.add_field(
            name="Variables",
            value=(
                "`{member.mention}`\n"
                "`{member.name}`\n"
                "`{guild.name}`\n"
                "`{invite}`"
            ),
            inline=False
        )

        # View
        
        view = WelcomerView(
            cog=self,
            author_id=ctx.author.id,
            guild_id=ctx.guild.id,
            channel=channel,
            config=config
        )

        await ctx.send(
            embed=embed,
            view=view
        )

    # Member Join
    
    @commands.Cog.listener()
    async def on_member_join(
        self,
        member
    ):
        """
        Send the configured welcome message when
        a new member joins.
        """

        config = await self.get_config(
            member.guild.id
        )

        # No configuration.
        
        if not config:
            return

        # Disabled.
        
        if not config.get(
            "enabled",
            True
        ):
            return

        # Channel.
        
        channel_id = config.get(
            "channel"
        )

        if not channel_id:
            return

        try:

            channel = member.guild.get_channel(
                int(channel_id)
            )

        except (
            TypeError,
            ValueError
        ):
            return

        if not channel:
            return

        # Get used invite.

        invite = await self.get_used_invite(
            member.guild
        )

        # Message.
        
        message = config.get(
            "message"
        )

        if not message:
            return

        # Format.
        
        formatted = self.format_message(
            member,
            message,
            invite
        )

        if formatted is None:

            print(
                "Welcomer: Invalid saved configuration "
                f"for guild {member.guild.id}"
            )

            return

        # Send.
        
        try:

            await channel.send(
                **formatted
            )

        except discord.Forbidden:

            print(
                "Welcomer: Missing permissions in "
                f"{channel} ({channel.id})"
            )

        except discord.HTTPException as exc:

            print(
                "Welcomer: Discord error: "
                f"{exc}"
            )


# Modmail Plugin Entry Point

async def setup(bot):
    await bot.add_cog(
        Welcomer(bot)
    )
