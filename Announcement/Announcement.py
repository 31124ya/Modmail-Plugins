from __future__ import annotations

import asyncio
import io

import discord
from discord.ext import commands

from core import checks
from core.models import PermissionLevel


class AnnouncementPanel(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)

        self.cog = cog
        self.channel = None

        self.channel_select = discord.ui.ChannelSelect(
            placeholder="Select a channel",
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.news,
            ],
            min_values=1,
            max_values=1,
        )

        self.channel_select.callback = self.channel_selected
        self.add_item(self.channel_select)

        self.create_button = discord.ui.Button(
            label="Create Announcement",
            style=discord.ButtonStyle.primary,
            disabled=True,
        )

        self.create_button.callback = self.create_announcement
        self.add_item(self.create_button)

        self.cancel_button = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
        )

        self.cancel_button.callback = self.cancel
        self.add_item(self.cancel_button)

    async def channel_selected(self, interaction: discord.Interaction):
        self.channel = self.channel_select.values[0]

        self.create_button.disabled = False

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self,
        )

    async def create_announcement(self, interaction: discord.Interaction):
        if self.channel is None:
            await interaction.response.send_message(
                "Please select a channel first.",
                ephemeral=True,
            )
            return

        await self.cog.open_modal(
            interaction,
            self.channel.id,
        )

    async def cancel(self, interaction: discord.Interaction):
        self.stop()

        embed = discord.Embed(
            title="Announcement Cancelled",
            description=(
                "The announcement creation process has been cancelled."
            ),
            color=self.cog.bot.main_color,
        )

        await interaction.response.edit_message(
            embed=embed,
            view=None,
        )

    def build_embed(self):
        embed = discord.Embed(
            title="Announcement Creation",
            description=(
                "Create a new embed announcement.\n\n"
                "Select the destination channel below, "
                "then click **Create Announcement**."
            ),
            color=self.cog.bot.main_color,
        )

        if self.channel:
            embed.add_field(
                name="Selected Channel",
                value=self.channel.mention,
                inline=False,
            )
        else:
            embed.add_field(
                name="Selected Channel",
                value="No channel selected.",
                inline=False,
            )

        embed.set_footer(
            text="Title, footer and images are optional.",
        )

        return embed


class AnnouncementModal(discord.ui.Modal):
    def __init__(self, cog, channel_id):
        super().__init__(
            title="Create Announcement",
        )

        self.cog = cog
        self.channel_id = channel_id

        self.title_input = discord.ui.TextInput(
            label="Title",
            placeholder="Optional announcement title",
            required=False,
            max_length=256,
            style=discord.TextStyle.short,
        )

        self.description_input = discord.ui.TextInput(
            label="Description",
            placeholder="Write your announcement...",
            required=True,
            min_length=1,
            max_length=4000,
            style=discord.TextStyle.paragraph,
        )

        self.footer_input = discord.ui.TextInput(
            label="Footer",
            placeholder="Optional footer",
            required=False,
            max_length=2048,
            style=discord.TextStyle.short,
        )

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.footer_input)

    async def on_submit(self, interaction: discord.Interaction):
        title = self.title_input.value.strip()
        description = self.description_input.value.strip()
        footer = self.footer_input.value.strip()

        self.cog.pending[interaction.user.id] = {
            "channel_id": self.channel_id,
            "title": title,
            "description": description,
            "footer": footer,
        }

        await interaction.response.send_message(
            (
                "Announcement prepared.\n\n"
                "**Optional images**\n"
                "Send up to **2 image attachments** in this channel.\n\n"
                "• 1 image → Image\n"
                "• 2 images → First = Image, Second = Thumbnail\n"
                "• No image → send `skip`\n\n"
                "You have **60 seconds**."
            ),
            ephemeral=True,
        )

        asyncio.create_task(
            self.cog.wait_for_images(
                interaction,
            )
        )


class Announcement(commands.Cog):
    __doc__ = "Create embed announcements."

    def __init__(self, bot):
        self.bot = bot
        self.pending = {}

    @commands.command(name="announce")
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def announce(self, ctx: commands.Context):
        embed = discord.Embed(
            title="Announcement Creation",
            description=(
                "Create a new embed announcement.\n\n"
                "Select the destination channel below, "
                "then click **Create Announcement**."
            ),
            color=self.bot.main_color,
        )

        embed.set_footer(
            text="Only administrators can create announcements.",
        )

        view = AnnouncementPanel(self)

        await ctx.send(
            embed=embed,
            view=view,
        )

    async def open_modal(
        self,
        interaction: discord.Interaction,
        channel_id: int,
    ):
        modal = AnnouncementModal(
            self,
            channel_id,
        )

        await interaction.response.send_modal(modal)

    async def wait_for_images(
        self,
        interaction: discord.Interaction,
    ):
        user_id = interaction.user.id

        def check(message: discord.Message):
            if message.author.id != user_id:
                return False

            if message.channel.id != interaction.channel_id:
                return False

            if message.content.lower().strip() == "skip":
                return True

            image_attachments = [
                attachment
                for attachment in message.attachments
                if (
                    attachment.content_type
                    and attachment.content_type.startswith("image/")
                )
            ]

            return len(image_attachments) > 0

        try:
            message = await self.bot.wait_for(
                "message",
                check=check,
                timeout=60,
            )

        except asyncio.TimeoutError:
            self.pending.pop(
                user_id,
                None,
            )

            try:
                await interaction.followup.send(
                    (
                        "Announcement cancelled because no "
                        "image or `skip` message was received "
                        "within 60 seconds."
                    ),
                    ephemeral=True,
                )
            except discord.HTTPException:
                pass

            return

        config = self.pending.pop(
            user_id,
            None,
        )

        if config is None:
            return

        if message.content.lower().strip() == "skip":
            attachments = []
        else:
            attachments = [
                attachment
                for attachment in message.attachments
                if (
                    attachment.content_type
                    and attachment.content_type.startswith("image/")
                )
            ]

            attachments = attachments[:2]

        await self.send_announcement(
            interaction,
            config,
            attachments,
        )

    async def send_announcement(
        self,
        interaction: discord.Interaction,
        config,
        attachments,
    ):
        channel = self.bot.get_channel(
            config["channel_id"],
        )

        if channel is None:
            try:
                channel = await self.bot.fetch_channel(
                    config["channel_id"],
                )
            except discord.HTTPException:
                await interaction.followup.send(
                    "I couldn't find the destination channel.",
                    ephemeral=True,
                )
                return

        if not hasattr(channel, "send"):
            await interaction.followup.send(
                "That channel cannot receive announcements.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            description=config["description"],
            color=self.bot.main_color,
        )

        if config["title"]:
            embed.title = config["title"]

        if config["footer"]:
            embed.set_footer(
                text=config["footer"],
            )

        files = []

        if len(attachments) >= 1:
            image = await self.download_attachment(
                attachments[0],
            )

            if image is not None:
                files.append(
                    discord.File(
                        image["data"],
                        filename=image["filename"],
                    )
                )

                embed.set_image(
                    url=(
                        "attachment://"
                        f"{image['filename']}"
                    )
                )

        if len(attachments) >= 2:
            thumbnail = await self.download_attachment(
                attachments[1],
            )

            if thumbnail is not None:
                files.append(
                    discord.File(
                        thumbnail["data"],
                        filename=thumbnail["filename"],
                    )
                )

                embed.set_thumbnail(
                    url=(
                        "attachment://"
                        f"{thumbnail['filename']}"
                    )
                )

        try:
            await channel.send(
                embed=embed,
                files=files,
                allowed_mentions=discord.AllowedMentions.none(),
            )

        except discord.Forbidden:
            await interaction.followup.send(
                (
                    "I don't have permission to send messages "
                    f"in {channel.mention}."
                ),
                ephemeral=True,
            )
            return

        except discord.HTTPException as exc:
            await interaction.followup.send(
                (
                    "Failed to send the announcement.\n"
                    f"`{exc}`"
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            (
                "Announcement successfully sent to "
                f"{channel.mention}."
            ),
            ephemeral=True,
        )

    async def download_attachment(
        self,
        attachment: discord.Attachment,
    ):
        try:
            data = await attachment.read()
        except Exception:
            return None

        return {
            "data": io.BytesIO(data),
            "filename": attachment.filename,
        }


async def setup(bot):
    await bot.add_cog(
        Announcement(bot),
    )
