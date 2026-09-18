import json

import discord
from box import Box
from discord.ext import commands

from .models import apply_vars, SafeString

# Helpers
def default_invite():
    return SafeString("{unable to get invite}")

# Message Modal

class MessageModal(discord.ui.Modal):
    def __init__(self, cog, guild_id, channel, current_message=None):
        super().__init__(title="Welcome Message")

        self.cog = cog
        self.guild_id = guild_id
        self.channel = channel

        self.message_input = discord.ui.TextInput(
            label="Welcome Message",
            placeholder="Welcome {member.mention} to {guild.name}!",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000,
            default=current_message or ""
        )

        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        message = self.message_input.value

        # Test whether the message can be formatted.
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
            f"✅ Welcome message saved for {self.channel.mention}.",
            ephemeral=True
        )


# ============================================================
# Embed JSON Modal
# ============================================================

class EmbedModal(discord.ui.Modal):
    def __init__(self, cog, guild_id, channel, current_message=None):
        super().__init__(title="Welcome Embed JSON")

        self.cog = cog
        self.guild_id = guild_id
        self.channel = channel

        self.embed_input = discord.ui.TextInput(
            label="Embed JSON",
            placeholder='{"title":"Welcome!","description":"Hello {member.mention}!"}',
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000,
            default=current_message or ""
        )

        self.add_item(self.embed_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_json = self.embed_input.value

        try:
            data = json.loads(raw_json)

            if not isinstance(data, dict):
                raise ValueError(
                    "Embed JSON must be an object."
                )

            discord.Embed.from_dict(data)

        except (json.JSONDecodeError, ValueError, TypeError):
            await interaction.response.send_message(
                "❌ Invalid Embed JSON.\n\n"
                "Make sure you are using valid Discord Embed JSON.",
                ephemeral=True
            )
            return

        formatted = self.cog.format_message(
            interaction.user,
            raw_json,
            default_invite()
        )

        if formatted is None:
            await interaction.response.send_message(
                "❌ Invalid Embed JSON.",
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
            f"✅ Welcome embed saved for {self.channel.mention}.",
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

    async def interaction_check(
        self,
        interaction: discord.Interaction
    ):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the person who opened this configuration "
                "panel can use these buttons.",
                ephemeral=True
            )
            return False

        return True

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

        invite = default_invite()

        formatted = self.cog.format_message(
            interaction.user,
            config["message"],
            invite
        )

        if formatted is None:
            await interaction.response.send_message(
                "❌ The saved welcome configuration is invalid.",
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

        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"❌ Discord rejected the message:\n```text\n{exc}\n```",
                ephemeral=True
            )

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

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Welcomer Disabled",
                description=(
                    "The Welcomer has been disabled "
                    f"for {self.channel.mention}."
                ),
                color=discord.Color.red()
            ),
            view=None
        )


# Welcomer Cog

class Welcomer(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

        # Modmail plugin database
        self.db = bot.plugin_db.get_partition(self)

        # Guild ID -> invite set
        self.invite_cache = {}

        # Start invite cache task
        bot.loop.create_task(
            self.populate_invite_cache()
        )

    # Invite Cache
    
    async def populate_invite_cache(self):
        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            try:
                invites = await guild.invites()

                self.invite_cache[guild.id] = {
                    invite for invite in invites
                }

            except discord.Forbidden:
                self.invite_cache[guild.id] = set()

    async def get_used_invite(self, guild):

        try:
            old_invites = self.invite_cache.get(
                guild.id,
                set()
            )

            new_invites = {
                invite
                for invite in await guild.invites()
            }

        except discord.Forbidden:
            return default_invite()

        # Check invite usage.
        for old_invite in old_invites:

            for new_invite in new_invites:

                if new_invite.id != old_invite.id:
                    continue

                old_uses = old_invite.uses or 0
                new_uses = new_invite.uses or 0

                if new_uses > old_uses:

                    self.invite_cache[guild.id] = (
                        new_invites
                    )

                    return new_invite

        # Check deleted invites.
        old_ids = {
            invite.id
            for invite in old_invites
        }

        new_ids = {
            invite.id
            for invite in new_invites
        }

        if old_ids - new_ids:

            self.invite_cache[guild.id] = (
                new_invites
            )

            return default_invite()

        self.invite_cache[guild.id] = new_invites

        return default_invite()

    # Database
    
    async def get_config(self, guild_id):

        document = await self.db.find_one(
            {
                "_id": str(guild_id)
            }
        )

        if not document:
            return None

        return document.get("welcomer")

    async def save_config(
        self,
        guild_id,
        channel,
        message,
        message_type
    ):

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

    async def disable_config(self, guild_id):

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

    # Variables
   
    def apply_vars_dict(
        self,
        member,
        message,
        invite
    ):

        for key, value in message.items():

            if isinstance(value, dict):

                message[key] = self.apply_vars_dict(
                    member,
                    value,
                    invite
                )

            elif isinstance(value, str):

                message[key] = apply_vars(
                    self,
                    member,
                    value,
                    invite
                )

            elif isinstance(value, list):

                new_list = []

                for item in value:

                    if isinstance(item, dict):
                        new_list.append(
                            self.apply_vars_dict(
                                member,
                                item,
                                invite
                            )
                        )
                    elif isinstance(item, str):
                        new_list.append(
                            apply_vars(
                                self,
                                member,
                                item,
                                invite
                            )
                        )
                    else:
                        new_list.append(item)

                message[key] = new_list

            # Discord timestamp JSON sometimes ends with Z.
            if (
                key == "timestamp"
                and isinstance(value, str)
                and value.endswith("Z")
            ):
                message[key] = value[:-1]

        return message

    # Message Formatting
    
    def format_message(
        self,
        member,
        message,
        invite
    ):

        try:
            data = json.loads(message)

        except json.JSONDecodeError:

            # Plain message.
            content = apply_vars(
                self,
                member,
                message,
                invite
            )

            return {
                "content": content
            }

        # JSON message.
        if not isinstance(data, dict):
            return None

        data = self.apply_vars_dict(
            member,
            data,
            invite
        )

        try:

            # Support both:
            #
            # {
            #   "title": "Welcome"
            # }
            #
            # and:
            #
            # {
            #   "embed": {
            #       "title": "Welcome"
            #   }
            # }

            if "embed" in data:

                embed_data = data["embed"]

                if not isinstance(embed_data, dict):
                    return None

                embed = discord.Embed.from_dict(
                    embed_data
                )

                result = {
                    "embed": embed
                }

                if "content" in data:
                    result["content"] = data["content"]

                return result

            # Direct Embed JSON.
            embed = discord.Embed.from_dict(
                data
            )

            return {
                "embed": embed
            }

        except (ValueError, TypeError):
            return None

    # Configuration Command
    
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
        """

        config = await self.get_config(
            ctx.guild.id
        )

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

            embed.add_field(
                name="Current Configuration",
                value=(
                    f"**Channel:** {channel.mention}\n"
                    f"**Type:** `{message_type}`\n"
                    f"**Status:** `{status}`"
                ),
                inline=False
            )

        else:

            embed.add_field(
                name="Current Configuration",
                value="No Welcomer has been configured yet.",
                inline=False
            )

        embed.add_field(
            name="Message",
            value=(
                "Configure a normal text welcome message."
            ),
            inline=False
        )

        embed.add_field(
            name="Embed JSON",
            value=(
                "Configure a Discord embed using JSON."
            ),
            inline=False
        )

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
    async def on_member_join(self, member):

        config = await self.get_config(
            member.guild.id
        )

        if not config:
            return

        if not config.get(
            "enabled",
            True
        ):
            return

        channel_id = config.get(
            "channel"
        )

        if not channel_id:
            return

        try:
            channel = member.guild.get_channel(
                int(channel_id)
            )
        except (TypeError, ValueError):
            return

        if not channel:
            return

        invite = await self.get_used_invite(
            member.guild
        )

        message = config.get(
            "message"
        )

        if not message:
            return

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
                f"Welcomer: Discord error: {exc}"
            )


# Modmail Plugin Entry Point

def setup(bot):
    bot.add_cog(
        Welcomer(bot)
    )
