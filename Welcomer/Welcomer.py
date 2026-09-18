import json

import discord
from box import Box
from discord.ext import commands

from .models import apply_vars, SafeString


class MessageModal(discord.ui.Modal, title="Set Welcome Message"):
    message = discord.ui.TextInput(
        label="Welcome Message",
        placeholder="Welcome {member.mention} to {guild.name}!",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
    )

    def __init__(self, cog, channel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        message = self.message.value

        # Test formatting
        formatted = self.cog.format_message(
            interaction.user,
            message,
            SafeString("{invite}")
        )

        if not formatted:
            await interaction.response.send_message(
                "❌ Invalid welcome message.",
                ephemeral=True
            )
            return

        await self.cog.db.find_one_and_update(
            {"_id": "config"},
            {
                "$set": {
                    "welcomer": {
                        "channel": str(self.channel.id),
                        "message": message,
                        "type": "message"
                    }
                }
            },
            upsert=True
        )

        await interaction.response.send_message(
            f"✅ Welcome message saved for {self.channel.mention}.",
            ephemeral=True
        )


class EmbedModal(discord.ui.Modal, title="Set Welcome Embed"):
    embed_json = discord.ui.TextInput(
        label="Embed JSON",
        placeholder='{"title":"Welcome!","description":"Welcome {member.mention}!"}',
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
    )

    def __init__(self, cog, channel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        raw_json = self.embed_json.value

        try:
            data = json.loads(raw_json)

            if not isinstance(data, dict):
                raise ValueError("Embed JSON must be an object.")

            # Validate Discord embed structure
            discord.Embed.from_dict(data)

        except (json.JSONDecodeError, ValueError, TypeError):
            await interaction.response.send_message(
                "❌ Invalid Embed JSON.",
                ephemeral=True
            )
            return

        # Test formatting
        formatted = self.cog.format_message(
            interaction.user,
            raw_json,
            SafeString("{invite}")
        )

        if not formatted:
            await interaction.response.send_message(
                "❌ Invalid Embed JSON.",
                ephemeral=True
            )
            return

        await self.cog.db.find_one_and_update(
            {"_id": "config"},
            {
                "$set": {
                    "welcomer": {
                        "channel": str(self.channel.id),
                        "message": raw_json,
                        "type": "embed"
                    }
                }
            },
            upsert=True
        )

        await interaction.response.send_message(
            f"✅ Welcome embed saved for {self.channel.mention}.",
            ephemeral=True
        )


class WelcomerView(discord.ui.View):

    def __init__(self, cog, channel):
        super().__init__(timeout=300)
        self.cog = cog
        self.channel = channel

    @discord.ui.button(
        label="Message",
        style=discord.ButtonStyle.primary,
        emoji="💬"
    )
    async def message_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            MessageModal(self.cog, self.channel)
        )

    @discord.ui.button(
        label="Embed JSON",
        style=discord.ButtonStyle.secondary,
        emoji="📦"
    )
    async def embed_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            EmbedModal(self.cog, self.channel)
        )


class Welcomer(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.db = bot.plugin_db.get_partition(self)
        self.invite_cache = {}

        bot.loop.create_task(
            self.populate_invite_cache()
        )

    async def populate_invite_cache(self):
        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            try:
                self.invite_cache[guild.id] = {
                    invite for invite in await guild.invites()
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
                invite for invite in await guild.invites()
            }

            for old_invite in old_invites:

                for new_invite in new_invites:

                    if new_invite.id == old_invite.id:

                        if (
                            new_invite.uses is not None
                            and old_invite.uses is not None
                            and new_invite.uses > old_invite.uses
                        ):
                            self.invite_cache[guild.id] = new_invites
                            return new_invite

            # Invite was deleted
            old_ids = {
                invite.id
                for invite in old_invites
            }

            new_ids = {
                invite.id
                for invite in new_invites
            }

            deleted = old_ids - new_ids

            if deleted:
                return Box(
                    default_box=True,
                    default_box_attr="{unable to get invite}"
                )

            self.invite_cache[guild.id] = new_invites

        except discord.Forbidden:
            pass

        return Box(
            default_box=True,
            default_box_attr="{unable to get invite}"
        )

    def apply_vars_dict(self, member, message, invite):

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
                message[key] = [
                    self.apply_vars_dict(
                        member,
                        item,
                        invite
                    )
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]

            if key == "timestamp" and isinstance(value, str):
                message[key] = value[:-1]

        return message

    def format_message(self, member, message, invite):

        try:
            data = json.loads(message)

        except json.JSONDecodeError:

            # Normal message
            message = apply_vars(
                self,
                member,
                message,
                invite
            )

            return {
                "content": message
            }

        else:

            # Embed JSON
            if not isinstance(data, dict):
                return None

            data = self.apply_vars_dict(
                member,
                data,
                invite
            )

            try:

                if "embed" in data:
                    embed_data = data["embed"]

                else:
                    embed_data = data

                embed = discord.Embed.from_dict(
                    embed_data
                )

                result = {
                    "embed": embed
                }

                if "content" in data:
                    result["content"] = data["content"]

                return result

            except (ValueError, TypeError):
                return None

    @commands.has_permissions(manage_guild=True)
    @commands.command()
    async def welcomer(
        self,
        ctx,
        channel: discord.TextChannel
    ):
        """
        Configure the welcome message.

        Usage:
        !welcomer #general
        """

        embed = discord.Embed(
            title="Welcomer Configuration",
            description=(
                f"Configure the welcome message for "
                f"{channel.mention}.\n\n"
                "Choose one of the options below:"
            ),
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="💬 Message",
            value="Send a normal text welcome message.",
            inline=False
        )

        embed.add_field(
            name="📦 Embed JSON",
            value="Use Discord Embed JSON for a custom embed.",
            inline=False
        )

        await ctx.send(
            embed=embed,
            view=WelcomerView(
                self,
                channel
            )
        )

    @commands.Cog.listener()
    async def on_member_join(self, member):

        config = await self.db.find_one(
            {"_id": "config"}
        )

        if not config:
            return

        welcomer = config.get("welcomer")

        if not welcomer:
            return

        channel = member.guild.get_channel(
            int(welcomer["channel"])
        )

        if not channel:
            return

        invite = await self.get_used_invite(
            member.guild
        )

        message = self.format_message(
            member,
            welcomer["message"],
            invite
        )

        if not message:
            await channel.send(
                "Invalid welcome message."
            )
            return

        try:
            await channel.send(**message)

        except discord.HTTPException as e:
            print(
                f"Welcomer send error: {e}"
            )


async def setup(bot):
    await bot.add_cog(
        Welcomer(bot)
    )
