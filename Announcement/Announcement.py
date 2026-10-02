from __future__ import annotations

import io
import aiohttp
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
                "Select the channel where the announcement will be sent, "
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
            text="Title, footer, image and thumbnail are optional."
        )

        return embed


class Announcement(commands.Cog):
    __doc__ = "Create embed announcements."

    MODAL_PREFIX = "announcement_modal"

    def __init__(self, bot):
        self.bot = bot

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
            text="Only administrators can create announcements."
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
        custom_id = (
            f"{self.MODAL_PREFIX}:"
            f"{interaction.user.id}:"
            f"{channel_id}"
        )

        payload = {
            "type": 9,
            "data": {
                "custom_id": custom_id,
                "title": "Create Announcement",
                "components": [
                    {
                        "type": 18,
                        "label": "Title",
                        "description": "Optional",
                        "component": {
                            "type": 4,
                            "custom_id": "announcement_title",
                            "style": 1,
                            "max_length": 256,
                            "required": False,
                            "placeholder": "Announcement title",
                        },
                    },
                    {
                        "type": 18,
                        "label": "Description",
                        "description": "Required",
                        "component": {
                            "type": 4,
                            "custom_id": "announcement_description",
                            "style": 2,
                            "min_length": 1,
                            "max_length": 4000,
                            "required": True,
                            "placeholder": "Write your announcement...",
                        },
                    },
                    {
                        "type": 18,
                        "label": "Footer",
                        "description": "Optional",
                        "component": {
                            "type": 4,
                            "custom_id": "announcement_footer",
                            "style": 1,
                            "max_length": 2048,
                            "required": False,
                            "placeholder": "Optional footer",
                        },
                    },
                    {
                        "type": 18,
                        "label": "Image",
                        "description": "Optional image",
                        "component": {
                            "type": 19,
                            "custom_id": "announcement_image",
                            "min_values": 0,
                            "max_values": 1,
                            "required": False,
                            "file_types": {
                                "values": [
                                    "image/png",
                                    "image/jpeg",
                                    "image/webp",
                                    "image/gif",
                                ]
                            },
                        },
                    },
                    {
                        "type": 18,
                        "label": "Thumbnail",
                        "description": "Optional thumbnail",
                        "component": {
                            "type": 19,
                            "custom_id": "announcement_thumbnail",
                            "min_values": 0,
                            "max_values": 1,
                            "required": False,
                            "file_types": {
                                "values": [
                                    "image/png",
                                    "image/jpeg",
                                    "image/webp",
                                    "image/gif",
                                ]
                            },
                        },
                    },
                ],
            },
        }

        url = (
            "https://discord.com/api/v10/interactions/"
            f"{interaction.id}/{interaction.token}/callback"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    response_text = await response.text()

                    if response.status >= 300:
                        print(
                            "[Announcement] Failed to open modal: "
                            f"HTTP {response.status} "
                            f"{response_text}"
                        )

        except Exception as exc:
            print(
                "[Announcement] Failed to open modal: "
                f"{type(exc).__name__}: {exc}"
            )

    @commands.Cog.listener()
    async def on_interaction(
        self,
        interaction: discord.Interaction,
    ):
        if interaction.type != discord.InteractionType.modal_submit:
            return

        data = interaction.data or {}

        custom_id = data.get("custom_id", "")

        if not custom_id.startswith(
            f"{self.MODAL_PREFIX}:"
        ):
            return

        parts = custom_id.split(":")

        if len(parts) != 3:
            return

        try:
            owner_id = int(parts[1])
            channel_id = int(parts[2])
        except ValueError:
            return

        if interaction.user.id != owner_id:
            await self.safe_interaction_message(
                interaction,
                "This announcement editor belongs to another user.",
            )
            return

        values = self.parse_modal_values(data)

        title = values.get(
            "announcement_title",
            "",
        ).strip()

        description = values.get(
            "announcement_description",
            "",
        ).strip()

        footer = values.get(
            "announcement_footer",
            "",
        ).strip()

        if not description:
            await self.safe_interaction_message(
                interaction,
                "Description is required.",
            )
            return

        channel = self.bot.get_channel(channel_id)

        if channel is None:
            try:
                channel = await self.bot.fetch_channel(
                    channel_id
                )
            except discord.HTTPException:
                await self.safe_interaction_message(
                    interaction,
                    "I couldn't find that channel.",
                )
                return

        if not isinstance(
            channel,
            (
                discord.TextChannel,
                discord.Thread,
            ),
        ):
            await self.safe_interaction_message(
                interaction,
                "That channel cannot receive this announcement.",
            )
            return

        image_attachment = self.get_attachment(
            data,
            "announcement_image",
        )

        thumbnail_attachment = self.get_attachment(
            data,
            "announcement_thumbnail",
        )

        embed = discord.Embed(
            description=description,
            color=self.bot.main_color,
        )

        if title:
            embed.title = title

        if footer:
            embed.set_footer(
                text=footer,
            )

        files = []

        image_file = None
        thumbnail_file = None

        if image_attachment:
            image_file = await self.download_attachment(
                image_attachment
            )

            if image_file:
                files.append(
                    discord.File(
                        image_file["data"],
                        filename=image_file["filename"],
                    )
                )

                embed.set_image(
                    url=(
                        "attachment://"
                        f"{image_file['filename']}"
                    )
                )

        if thumbnail_attachment:
            thumbnail_file = await self.download_attachment(
                thumbnail_attachment
            )

            if thumbnail_file:
                files.append(
                    discord.File(
                        thumbnail_file["data"],
                        filename=thumbnail_file["filename"],
                    )
                )

                embed.set_thumbnail(
                    url=(
                        "attachment://"
                        f"{thumbnail_file['filename']}"
                    )
                )

        try:
            await channel.send(
                embed=embed,
                files=files,
                allowed_mentions=discord.AllowedMentions.none(),
            )

        except discord.Forbidden:
            await self.safe_interaction_message(
                interaction,
                (
                    "I don't have permission to send "
                    f"messages in {channel.mention}."
                ),
            )
            return

        except discord.HTTPException as exc:
            await self.safe_interaction_message(
                interaction,
                (
                    "Failed to send the announcement.\n"
                    f"`{exc}`"
                ),
            )
            return

        await self.safe_interaction_message(
            interaction,
            (
                "Announcement successfully sent to "
                f"{channel.mention}."
            ),
        )

    def parse_modal_values(self, data):
        values = {}

        for component in data.get(
            "components",
            [],
        ):
            self.parse_component(
                component,
                values,
            )

        return values

    def parse_component(
        self,
        component,
        values,
    ):
        component_type = component.get("type")

        if component_type == 18:
            inner = component.get(
                "component",
                {},
            )

            custom_id = inner.get(
                "custom_id",
            )

            if not custom_id:
                return

            inner_type = inner.get(
                "type",
            )

            if inner_type == 4:
                values[custom_id] = inner.get(
                    "value",
                    "",
                )

            elif inner_type == 19:
                values[custom_id] = inner.get(
                    "values",
                    [],
                )

            return

        if component_type == 1:
            for inner in component.get(
                "components",
                [],
            ):
                self.parse_component(
                    inner,
                    values,
                )

    def get_attachment(
        self,
        data,
        custom_id,
    ):
        values = self.parse_modal_values(
            data
        ).get(
            custom_id,
            [],
        )

        if not values:
            return None

        attachment_id = str(
            values[0]
        )

        resolved = data.get(
            "resolved",
            {},
        )

        attachments = resolved.get(
            "attachments",
            {},
        )

        return attachments.get(
            attachment_id
        )

    async def download_attachment(
        self,
        attachment,
    ):
        url = attachment.get("url")

        if not url:
            return None

        filename = attachment.get(
            "filename",
            "image",
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(
                        total=30
                    ),
                ) as response:

                    if response.status != 200:
                        print(
                            "[Announcement] Failed to "
                            f"download attachment: "
                            f"HTTP {response.status}"
                        )
                        return None

                    data = await response.read()

        except Exception as exc:
            print(
                "[Announcement] Attachment download "
                f"failed: {type(exc).__name__}: {exc}"
            )
            return None

        return {
            "data": io.BytesIO(data),
            "filename": filename,
        }

    async def safe_interaction_message(
        self,
        interaction,
        content,
    ):
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    content,
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    content,
                    ephemeral=True,
                )

        except discord.HTTPException as exc:
            print(
                "[Announcement] Failed to respond to "
                f"interaction: {exc}"
            )

        except Exception as exc:
            print(
                "[Announcement] Failed to respond to "
                f"interaction: "
                f"{type(exc).__name__}: {exc}"
            )


async def setup(bot):
    await bot.add_cog(
        Announcement(bot)
    )
