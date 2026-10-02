from __future__ import annotations

import io
import discord

from discord.ext import commands

from core import checks
from core.models import PermissionLevel

class AnnouncementModal(discord.ui.Modal):
    def __init__(self, custom_id):
        super().__init__(
            title="Create Announcement",
            custom_id=custom_id,
        )

    def to_components(self):
        return [
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
        ]

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

        await self.cog.show_modal(
            interaction,
            self.channel.id,
        )

    async def cancel(self, interaction: discord.Interaction):
        self.stop()

        embed = discord.Embed(
            title="Announcement Cancelled",
            description="The announcement creation process has been cancelled.",
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

    async def show_modal(self, interaction, channel_id):
    custom_id = (
        f"{self.MODAL_PREFIX}:"
        f"{interaction.user.id}:"
        f"{channel_id}"
    )

    modal = AnnouncementModal(custom_id)

    try:
        await interaction.response.send_modal(modal)

    except discord.HTTPException as exc:
        print(
            "[Announcement] Failed to open modal:"
            f" status={exc.status}"
            f" code={getattr(exc, 'code', None)}"
            f" text={exc.text}"
        )

    except Exception as exc:
        print(
            "[Announcement] Failed to open modal:"
            f" {type(exc).__name__}: {exc}"
        )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.modal_submit:
            return

        data = interaction.data or {}
        custom_id = data.get("custom_id", "")

        if not custom_id.startswith(f"{self.MODAL_PREFIX}:"):
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
            await self.send_interaction_message(
                interaction,
                "This announcement editor belongs to another user.",
                ephemeral=True,
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
            await self.send_interaction_message(
                interaction,
                "Description is required.",
                ephemeral=True,
            )
            return

        channel = self.bot.get_channel(channel_id)

        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                await self.send_interaction_message(
                    interaction,
                    "I couldn't find that channel.",
                    ephemeral=True,
                )
                return

        image = self.get_attachment(
            data,
            "announcement_image",
        )

        thumbnail = self.get_attachment(
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

        if image:
            image_file = await self.download_attachment(image)

            if image_file:
                files.append(
                    discord.File(
                        image_file["data"],
                        filename=image_file["filename"],
                    )
                )

                embed.set_image(
                    url=f"attachment://{image_file['filename']}",
                )

        if thumbnail:
            thumbnail_file = await self.download_attachment(thumbnail)

            if thumbnail_file:
                files.append(
                    discord.File(
                        thumbnail_file["data"],
                        filename=thumbnail_file["filename"],
                    )
                )

                embed.set_thumbnail(
                    url=f"attachment://{thumbnail_file['filename']}",
                )

        try:
            await channel.send(
                embed=embed,
                files=files,
                allowed_mentions=discord.AllowedMentions.none(),
            )

        except discord.Forbidden:
            await self.send_interaction_message(
                interaction,
                f"I don't have permission to send messages in {channel.mention}.",
                ephemeral=True,
            )
            return

        except discord.HTTPException as exc:
            await self.send_interaction_message(
                interaction,
                f"Failed to send the announcement.\n`{exc}`",
                ephemeral=True,
            )
            return

        await self.send_interaction_message(
            interaction,
            f"Announcement successfully sent to {channel.mention}.",
            ephemeral=True,
        )

    def parse_modal_values(self, data):
        values = {}

        for component in data.get("components", []):
            if component.get("type") == 18:
                inner = component.get(
                    "component",
                    {},
                )

                custom_id = inner.get("custom_id")

                if not custom_id:
                    continue

                if inner.get("type") == 4:
                    values[custom_id] = inner.get(
                        "value",
                        "",
                    )

                elif inner.get("type") == 19:
                    values[custom_id] = inner.get(
                        "values",
                        [],
                    )

            elif component.get("type") == 1:
                for inner in component.get(
                    "components",
                    [],
                ):
                    custom_id = inner.get("custom_id")

                    if not custom_id:
                        continue

                    if inner.get("type") == 4:
                        values[custom_id] = inner.get(
                            "value",
                            "",
                        )

                    elif inner.get("type") == 19:
                        values[custom_id] = inner.get(
                            "values",
                            [],
                        )

        return values

    def get_attachment(self, data, custom_id):
        values = self.parse_modal_values(data).get(
            custom_id,
            [],
        )

        if not values:
            return None

        attachment_id = str(values[0])

        resolved = data.get(
            "resolved",
            {},
        )

        attachments = resolved.get(
            "attachments",
            {},
        )

        return attachments.get(
            attachment_id,
        )

    async def download_attachment(self, attachment):
        url = attachment.get("url")

        if not url:
            return None

        filename = attachment.get(
            "filename",
            "image",
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return None

                    data = await response.read()

        except Exception:
            return None

        return {
            "data": io.BytesIO(data),
            "filename": filename,
        }

    async def send_interaction_message(
        self,
        interaction,
        content,
        ephemeral=False,
    ):
        flags = 64 if ephemeral else 0

        payload = {
            "type": 4,
            "data": {
                "content": content,
                "flags": flags,
            },
        }

        url = (
            f"https://discord.com/api/v10/interactions/"
            f"{interaction.id}/{interaction.token}/callback"
        )

        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                )
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(Announcement(bot))
