from __future__ import annotations

import discord

from discord.ext import commands

from core import checks
from core.models import PermissionLevel


class AnnouncementModal(discord.ui.Modal, title="Create Announcement"):
    title_input = discord.ui.Label(
        text="Title",
        description="Optional",
        component=discord.ui.TextInput(
            custom_id="announcement_title",
            placeholder="Announcement title",
            max_length=256,
            required=False,
        ),
    )

    description_input = discord.ui.Label(
        text="Description",
        description="Required",
        component=discord.ui.TextInput(
            custom_id="announcement_description",
            placeholder="Write your announcement...",
            style=discord.TextStyle.paragraph,
            max_length=4000,
            required=True,
        ),
    )

    footer_input = discord.ui.Label(
        text="Footer",
        description="Optional",
        component=discord.ui.TextInput(
            custom_id="announcement_footer",
            placeholder="Optional footer",
            max_length=2048,
            required=False,
        ),
    )

    image_upload = discord.ui.Label(
        text="Image",
        description="Optional",
        component=discord.ui.FileUpload(
            custom_id="announcement_image",
            min_values=0,
            max_values=1,
            required=False,
        ),
    )

    thumbnail_upload = discord.ui.Label(
        text="Thumbnail",
        description="Optional",
        component=discord.ui.FileUpload(
            custom_id="announcement_thumbnail",
            min_values=0,
            max_values=1,
            required=False,
        ),
    )

    def __init__(self, cog: "Announcement", channel: discord.TextChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        title = self.title_input.component.value.strip()
        description = self.description_input.component.value.strip()
        footer = self.footer_input.component.value.strip()

        image = None
        thumbnail = None

        if self.image_upload.values:
            image = self.image_upload.values[0]

        if self.thumbnail_upload.values:
            thumbnail = self.thumbnail_upload.values[0]

        embed = discord.Embed(
            description=description,
            color=self.cog.bot.main_color,
        )

        if title:
            embed.title = title

        if footer:
            embed.set_footer(text=footer)

        files = []

        if image:
            image_file = await image.to_file()
            files.append(image_file)
            embed.set_image(url=f"attachment://{image_file.filename}")

        if thumbnail:
            thumbnail_file = await thumbnail.to_file()
            files.append(thumbnail_file)
            embed.set_thumbnail(url=f"attachment://{thumbnail_file.filename}")

        try:
            await self.channel.send(
                embed=embed,
                files=files,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"I don't have permission to send messages in {self.channel.mention}.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"Failed to send the announcement.\n`{exc}`",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Announcement successfully sent to {self.channel.mention}.",
            ephemeral=True,
        )


class AnnouncementPanel(discord.ui.View):
    def __init__(self, cog: "Announcement"):
        super().__init__(timeout=300)
        self.cog = cog
        self.channel: discord.TextChannel | discord.NewsChannel | None = None

        self.channel_select = discord.ui.ChannelSelect(
            placeholder="Select a channel",
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.news,
            ],
            min_values=1,
            max_values=1,
            custom_id="announcement_channel_select",
        )

        self.channel_select.callback = self.channel_selected
        self.add_item(self.channel_select)

        self.create_button = discord.ui.Button(
            label="Create Announcement",
            style=discord.ButtonStyle.primary,
            custom_id="announcement_create",
            disabled=True,
        )

        self.create_button.callback = self.create_announcement
        self.add_item(self.create_button)

        self.cancel_button = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            custom_id="announcement_cancel",
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

        modal = AnnouncementModal(
            self.cog,
            self.channel,
        )

        await interaction.response.send_modal(modal)

    async def cancel(self, interaction: discord.Interaction):
        self.stop()

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Announcement Cancelled",
                description="The announcement creation process has been cancelled.",
                color=self.cog.bot.main_color,
            ),
            view=None,
        )

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Announcement Creation",
            description=(
                "Create a new announcement.\n\n"
                "Select the channel where the announcement should be sent, "
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
    __doc__ = "Create embed announcements with a simple interactive panel."

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="announce")
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def announce(self, ctx: commands.Context):
        """
        Open the announcement creation panel.
        """

        embed = discord.Embed(
            title="Announcement Creation",
            description=(
                "Create an embed announcement.\n\n"
                "1. Select the destination channel.\n"
                "2. Click **Create Announcement**.\n"
                "3. Fill in the announcement and optionally upload "
                "an image or thumbnail."
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


async def setup(bot):
    await bot.add_cog(Announcement(bot))
