import json
import logging

import discord
from discord.ext import commands

from bot import ModmailBot
from core import checks
from core.models import PermissionLevel


log = logging.getLogger(__name__)

COMPONENTS_V2_FLAG = 1 << 15


DEFAULT_CLOSE_REQUEST = {
    "flags": COMPONENTS_V2_FLAG,
    "components": [
        {
            "type": 10,
            "content": "## Close your ticket\n\nWould you like to close your support ticket?"
        },
        {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 4,
                    "label": "Close Ticket",
                    "custom_id": "close_request_close"
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": "Keep Open",
                    "custom_id": "close_request_keep"
                }
            ]
        }
    ]
}


DEFAULT_INACTIVITY = {
    "flags": COMPONENTS_V2_FLAG,
    "components": [
        {
            "type": 10,
            "content": "## Inactivity Notice\n\nThis ticket has been scheduled to close in 24 hours due to inactivity.\n\nIf you still need help, simply reply to this ticket."
        }
    ]
}


DEFAULT_CLOSED = {
    "flags": COMPONENTS_V2_FLAG,
    "components": [
        {
            "type": 10,
            "content": "Your ticket has been closed."
        }
    ]
}


DEFAULT_KEEP_OPEN = {
    "flags": COMPONENTS_V2_FLAG,
    "components": [
        {
            "type": 10,
            "content": "No problem. Your ticket will remain open."
        }
    ]
}


DEFAULT_INACTIVITY_CLOSE = {
    "flags": COMPONENTS_V2_FLAG,
    "components": [
        {
            "type": 10,
            "content": "This ticket has been automatically closed after 24 hours of inactivity."
        }
    ]
}


class ComponentsModal(discord.ui.Modal):
    def __init__(self, cog, guild_id, setting_name, title):
        super().__init__(title=title)

        self.cog = cog
        self.guild_id = guild_id
        self.setting_name = setting_name

        config = cog.config_cache.get(guild_id, {})
        current = config.get(setting_name)

        if current:
            value = json.dumps(
                current,
                ensure_ascii=False,
                indent=2
            )
        else:
            value = json.dumps(
                cog.default_config(setting_name),
                ensure_ascii=False,
                indent=2
            )

        self.json_input = discord.ui.TextInput(
            label="Components V2 JSON",
            style=discord.TextStyle.paragraph,
            placeholder='{"flags":32768,"components":[...]}',
            default=value[:4000],
            required=True,
            max_length=4000
        )

        self.add_item(self.json_input)

    async def on_submit(self, interaction):
        raw = str(self.json_input.value)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            await interaction.response.send_message(
                f"Invalid JSON:\n{exc}",
                ephemeral=True
            )
            return

        try:
            self.cog.validate_components_v2(data)
        except ValueError as exc:
            await interaction.response.send_message(
                str(exc),
                ephemeral=True
            )
            return

        config = await self.cog.get_config(
            self.guild_id
        )

        config[self.setting_name] = data

        await self.cog.save_config(
            self.guild_id,
            config
        )

        await interaction.response.send_message(
            "Components V2 configuration saved.",
            ephemeral=True
        )


class ConfigurationView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=300)

        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(
        label="Close Request",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def close_request_button(
        self,
        interaction,
        button
    ):
        await interaction.response.send_modal(
            ComponentsModal(
                self.cog,
                self.guild_id,
                "close_request",
                "Close Request Components"
            )
        )

    @discord.ui.button(
        label="Inactivity",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def inactivity_button(
        self,
        interaction,
        button
    ):
        await interaction.response.send_modal(
            ComponentsModal(
                self.cog,
                self.guild_id,
                "inactivity",
                "Inactivity Components"
            )
        )

    @discord.ui.button(
        label="Closed Message",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def closed_button(
        self,
        interaction,
        button
    ):
        await interaction.response.send_modal(
            ComponentsModal(
                self.cog,
                self.guild_id,
                "closed_message",
                "Closed Message Components"
            )
        )

    @discord.ui.button(
        label="Keep Open Message",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def keep_open_button(
        self,
        interaction,
        button
    ):
        await interaction.response.send_modal(
            ComponentsModal(
                self.cog,
                self.guild_id,
                "keep_open_message",
                "Keep Open Components"
            )
        )

    @discord.ui.button(
        label="Inactivity Close",
        style=discord.ButtonStyle.secondary,
        row=2
    )
    async def inactivity_close_button(
        self,
        interaction,
        button
    ):
        await interaction.response.send_modal(
            ComponentsModal(
                self.cog,
                self.guild_id,
                "inactivity_close_message",
                "Inactivity Close Components"
            )
        )


class CloseRequestView(discord.ui.View):
    def __init__(
        self,
        bot,
        thread_id,
        user_id
    ):
        super().__init__(timeout=None)

        self.bot = bot
        self.thread_id = thread_id
        self.user_id = user_id

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="close_request_close"
    )
    async def close_button(
        self,
        interaction,
        button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This button is not for you.",
                ephemeral=True
            )
            return

        thread = await self.bot.threads.find(
            recipient_id=self.user_id
        )

        if thread is None:
            await interaction.response.send_message(
                "This ticket is no longer open.",
                ephemeral=True
            )
            return

        if thread.id != self.thread_id:
            await interaction.response.send_message(
                "This button belongs to another ticket.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        await thread.close(
            closer=interaction.user
        )

    @discord.ui.button(
        label="Keep Open",
        style=discord.ButtonStyle.secondary,
        custom_id="close_request_keep"
    )
    async def keep_open_button(
        self,
        interaction,
        button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This button is not for you.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Your ticket will remain open.",
            ephemeral=True
        )


class CloseRequest(commands.Cog):
    def __init__(self, bot: ModmailBot):
        self.bot = bot

        self.db = bot.plugin_db.get_partition(
            self
        )

        self.config_cache = {}

    async def get_config(self, guild_id):
        if guild_id in self.config_cache:
            return self.config_cache[guild_id]

        data = await self.db.find_one(
            {"_id": str(guild_id)}
        )

        if data:
            data.pop("_id", None)
        else:
            data = {
                "close_request": DEFAULT_CLOSE_REQUEST,
                "inactivity": DEFAULT_INACTIVITY,
                "closed_message": DEFAULT_CLOSED,
                "keep_open_message": DEFAULT_KEEP_OPEN,
                "inactivity_close_message": DEFAULT_INACTIVITY_CLOSE
            }

        self.config_cache[guild_id] = data

        return data

    async def save_config(
        self,
        guild_id,
        config
    ):
        self.config_cache[guild_id] = config

        data = dict(config)
        data["_id"] = str(guild_id)

        await self.db.replace_one(
            {"_id": str(guild_id)},
            data,
            upsert=True
        )

    def default_config(self, name):
        defaults = {
            "close_request": DEFAULT_CLOSE_REQUEST,
            "inactivity": DEFAULT_INACTIVITY,
            "closed_message": DEFAULT_CLOSED,
            "keep_open_message": DEFAULT_KEEP_OPEN,
            "inactivity_close_message": DEFAULT_INACTIVITY_CLOSE
        }

        return defaults[name]

    def validate_components_v2(self, data):
        if not isinstance(data, dict):
            raise ValueError(
                "The JSON root must be an object."
            )

        if data.get("flags") != COMPONENTS_V2_FLAG:
            raise ValueError(
                f"Components V2 messages must use flags {COMPONENTS_V2_FLAG}."
            )

        components = data.get("components")

        if not isinstance(components, list):
            raise ValueError(
                '"components" must be an array.'
            )

        if not components:
            raise ValueError(
                '"components" cannot be empty.'
            )

        for component in components:
            if not isinstance(component, dict):
                raise ValueError(
                    "Every component must be an object."
                )

            if "type" not in component:
                raise ValueError(
                    "Every component must contain a type."
                )

    async def send_components_v2(
        self,
        channel,
        data,
        view=None
    ):
        payload = dict(data)

        payload["flags"] = COMPONENTS_V2_FLAG

        components = payload.get(
            "components",
            []
        )

        if view is not None:
            has_close_button = False
            has_keep_button = False

            for component in components:
                if component.get("type") != 1:
                    continue

                for child in component.get(
                    "components",
                    []
                ):
                    custom_id = child.get(
                        "custom_id"
                    )

                    if custom_id == "close_request_close":
                        has_close_button = True

                    if custom_id == "close_request_keep":
                        has_keep_button = True

            if has_close_button or has_keep_button:
                return await self.send_raw_message(
                    channel,
                    payload
                )

        return await self.send_raw_message(
            channel,
            payload
        )

    async def send_raw_message(
        self,
        channel,
        payload
    ):
        route = discord.http.Route(
            "POST",
            "/channels/{channel_id}/messages",
            channel_id=channel.id
        )

        return await self.bot.http.request(
            route,
            json=payload
        )

    @commands.command(
        name="closerequest"
    )
    @checks.has_permissions(
        PermissionLevel.SUPPORTER
    )
    @checks.thread_only()
    async def close_request(
        self,
        ctx,
        action=None
    ):
        if action is not None:
            if action.lower() in (
                "config",
                "setup",
                "settings"
            ):
                await self.show_config(
                    ctx
                )
                return

        thread = ctx.thread

        if thread is None:
            return

        user = thread.recipient

        if user is None:
            await ctx.send(
                "I could not find the user associated with this ticket."
            )
            return

        config = await self.get_config(
            ctx.guild.id
        )

        data = config.get(
            "close_request",
            DEFAULT_CLOSE_REQUEST
        )

        try:
            await self.send_raw_message(
                await user.create_dm(),
                data
            )

            await ctx.send(
                "The close request has been sent to the ticket owner."
            )

        except discord.HTTPException as exc:
            log.exception(
                "Failed to send close request: %s",
                exc
            )

            await ctx.send(
                "I could not send the close request."
            )

    @commands.command(
        name="inactivity"
    )
    @checks.has_permissions(
        PermissionLevel.SUPPORTER
    )
    @checks.thread_only()
    async def inactivity(
        self,
        ctx
    ):
        thread = ctx.thread

        if thread is None:
            return

        user = thread.recipient

        if user is None:
            await ctx.send(
                "I could not find the user associated with this ticket."
            )
            return

        if thread.close_task is not None:
            await ctx.send(
                "This ticket already has an inactivity timer running."
            )
            return

        config = await self.get_config(
            ctx.guild.id
        )

        data = config.get(
            "inactivity",
            DEFAULT_INACTIVITY
        )

        try:
            await self.send_raw_message(
                await user.create_dm(),
                data
            )
        except discord.HTTPException as exc:
            log.exception(
                "Failed to send inactivity message: %s",
                exc
            )

            await ctx.send(
                "I could not send the inactivity message."
            )

            return

        await thread.close(
            closer=ctx.author,
            after=24 * 60 * 60,
            message=None
        )

        await ctx.send(
            "The 24-hour inactivity timer has started."
        )

    async def show_config(self, ctx):
        embed = discord.Embed(
            title="CloseRequest Configuration",
            description=(
                "Use the buttons below to configure the "
                "Components V2 messages.\n\n"
                "**Close Request**\n"
                "Message sent by `closerequest`.\n\n"
                "**Inactivity**\n"
                "Message sent when `inactivity` starts.\n\n"
                "**Closed Message**\n"
                "Message used when the user closes the ticket.\n\n"
                "**Keep Open Message**\n"
                "Message shown when the user chooses to keep it open.\n\n"
                "**Inactivity Close**\n"
                "Message used when the inactivity timer expires."
            ),
            color=discord.Color.blurple()
        )

        await ctx.send(
            embed=embed,
            view=ConfigurationView(
                self,
                ctx.guild.id
            )
        )


async def setup(bot: ModmailBot):
    cog = CloseRequest(bot)

    await bot.add_cog(cog)
