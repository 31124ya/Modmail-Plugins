import asyncio
import copy
import json
import string

import discord
from discord.ext import commands

from bot import ModmailBot
from core import checks
from core.models import PermissionLevel


COMPONENTS_V2_FLAG = 1 << 15

CLOSE_REQUEST_CLOSE_ID = "close_request_close"
CLOSE_REQUEST_KEEP_ID = "close_request_keep"


DEFAULT_CONFIG = {
    "close_request": {
        "flags": COMPONENTS_V2_FLAG,
        "components": [
            {
                "type": 10,
                "content": "Would you like to close your support ticket?"
            },
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 4,
                        "label": "Close Ticket",
                        "custom_id": CLOSE_REQUEST_CLOSE_ID
                    },
                    {
                        "type": 2,
                        "style": 2,
                        "label": "Keep Open",
                        "custom_id": CLOSE_REQUEST_KEEP_ID
                    }
                ]
            }
        ]
    },

    "inactivity": {
        "flags": COMPONENTS_V2_FLAG,
        "components": [
            {
                "type": 10,
                "content": "Close Scheduled"
            }
        ]
    },

    "closed_message": {
        "flags": COMPONENTS_V2_FLAG,
        "components": [
            {
                "type": 10,
                "content": "Ticket Closed"
            }
        ]
    },

    "keep_open_message": {
        "flags": COMPONENTS_V2_FLAG,
        "components": [
            {
                "type": 10,
                "content": "The ticket will remain open."
            }
        ]
    },

    "inactivity_close_message": {
        "flags": COMPONENTS_V2_FLAG,
        "components": [
            {
                "type": 10,
                "content": "This ticket has been closed."
            }
        ]
    },

    "schedule_closed": {
        "flags": COMPONENTS_V2_FLAG,
        "components": [
            {
                "type": 10,
                "content": "Close Scheduled"
            }
        ]
    }
}


class SafeFormatter(string.Formatter):
    def get_value(self, key, args, kwargs):
        if isinstance(key, str):
            return kwargs.get(key, "{" + key + "}")

        return super().get_value(key, args, kwargs)


class CloseRequestModal(discord.ui.Modal):
    def __init__(
        self,
        cog,
        guild_id,
        config_key,
        current
    ):
        super().__init__(
            title=f"Edit {config_key.replace('_', ' ').title()}"
        )

        self.cog = cog
        self.guild_id = guild_id
        self.config_key = config_key

        self.json_input = discord.ui.TextInput(
            label="Components V2 JSON",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000,
            default=json.dumps(
                current,
                ensure_ascii=False,
                indent=2
            )
        )

        self.add_item(self.json_input)

    async def on_submit(self, interaction):
        raw = self.json_input.value

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            await interaction.response.send_message(
                f"❌ Invalid JSON:\n```text\n{exc}\n```",
                ephemeral=True
            )
            return

        error = self.cog.validate_components(
            self.config_key,
            data
        )

        if error:
            await interaction.response.send_message(
                f"❌ {error}",
                ephemeral=True
            )
            return

        config = await self.cog.get_config(
            self.guild_id
        )

        config[self.config_key] = data

        await self.cog.save_config(
            self.guild_id,
            config
        )

        await interaction.response.send_message(
            f"✅ `{self.config_key}` has been saved.",
            ephemeral=True
        )


class ConfigurationView(discord.ui.View):
    def __init__(
        self,
        cog,
        author_id,
        guild_id
    ):
        super().__init__(timeout=300)

        self.cog = cog
        self.author_id = author_id
        self.guild_id = guild_id

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ You cannot use this configuration panel.",
                ephemeral=True
            )
            return False

        return True

    async def open_editor(
        self,
        interaction,
        key
    ):
        config = await self.cog.get_config(
            self.guild_id
        )

        current = config.get(
            key,
            DEFAULT_CONFIG[key]
        )

        await interaction.response.send_modal(
            CloseRequestModal(
                self.cog,
                self.guild_id,
                key,
                current
            )
        )

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
        await self.open_editor(
            interaction,
            "close_request"
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
        await self.open_editor(
            interaction,
            "inactivity"
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
        await self.open_editor(
            interaction,
            "closed_message"
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
        await self.open_editor(
            interaction,
            "keep_open_message"
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
        await self.open_editor(
            interaction,
            "inactivity_close_message"
        )

    @discord.ui.button(
        label="Schedule Closed",
        style=discord.ButtonStyle.success,
        row=2
    )
    async def schedule_closed_button(
        self,
        interaction,
        button
    ):
        await self.open_editor(
            interaction,
            "schedule_closed"
        )


class CloseRequest(commands.Cog):
    def __init__(self, bot: ModmailBot):
        self.bot = bot
        self.db = bot.plugin_db.get_partition(self)

        self.inactivity_tasks = {}

    async def get_config(self, guild_id):
        data = await self.db.find_one(
            {"_id": str(guild_id)}
        )

        config = copy.deepcopy(DEFAULT_CONFIG)

        if data:
            saved = data.get("config", {})

            for key, value in saved.items():
                if key in config:
                    config[key] = value

        return config

    async def save_config(
        self,
        guild_id,
        config
    ):
        await self.db.update_one(
            {"_id": str(guild_id)},
            {
                "$set": {
                    "config": config
                }
            },
            upsert=True
        )

    def validate_components(
        self,
        key,
        data
    ):
        if not isinstance(data, dict):
            return "The JSON root must be an object."

        flags = data.get("flags", 0)

        if not isinstance(flags, int):
            return "`flags` must be an integer."

        if not flags & COMPONENTS_V2_FLAG:
            return (
                "This message must use Components V2. "
                f"Add `\"flags\": {COMPONENTS_V2_FLAG}`."
            )

        components = data.get("components")

        if not isinstance(components, list):
            return "`components` must be an array."

        if key == "close_request":
            found_close = False
            found_keep = False

            def scan(items):
                nonlocal found_close
                nonlocal found_keep

                for item in items:
                    if not isinstance(item, dict):
                        continue

                    if item.get("type") == 2:
                        custom_id = item.get("custom_id")

                        if custom_id == CLOSE_REQUEST_CLOSE_ID:
                            found_close = True

                        if custom_id == CLOSE_REQUEST_KEEP_ID:
                            found_keep = True

                    children = item.get("components")

                    if isinstance(children, list):
                        scan(children)

            scan(components)

            if not found_close:
                return (
                    "Close Request must contain a button with "
                    f"`custom_id` = `{CLOSE_REQUEST_CLOSE_ID}`."
                )

            if not found_keep:
                return (
                    "Close Request must contain a button with "
                    f"`custom_id` = `{CLOSE_REQUEST_KEEP_ID}`."
                )

        return None

    def apply_variables(
        self,
        value,
        member=None,
        guild=None
    ):
        if isinstance(value, str):
            formatter = SafeFormatter()

            values = {
                "member": member,
                "user": member,
                "guild": guild,
                "bot": self.bot
            }

            try:
                return formatter.vformat(
                    value,
                    (),
                    values
                )
            except Exception:
                return value

        if isinstance(value, list):
            return [
                self.apply_variables(
                    item,
                    member,
                    guild
                )
                for item in value
            ]

        if isinstance(value, dict):
            return {
                key: self.apply_variables(
                    item,
                    member,
                    guild
                )
                for key, item in value.items()
            }

        return value

    def prepare_close_request(
        self,
        data,
        guild_id,
        thread_id,
        user_id
    ):
        data = copy.deepcopy(data)

        close_id = (
            f"cr:close:{guild_id}:"
            f"{thread_id}:{user_id}"
        )

        keep_id = (
            f"cr:keep:{guild_id}:"
            f"{thread_id}:{user_id}"
        )

        def replace(items):
            for item in items:
                if not isinstance(item, dict):
                    continue

                if item.get("type") == 2:
                    custom_id = item.get("custom_id")

                    if custom_id == CLOSE_REQUEST_CLOSE_ID:
                        item["custom_id"] = close_id

                    elif custom_id == CLOSE_REQUEST_KEEP_ID:
                        item["custom_id"] = keep_id

                children = item.get("components")

                if isinstance(children, list):
                    replace(children)

        replace(data.get("components", []))

        return data

    async def send_components(
        self,
        channel,
        data,
        member=None,
        guild=None
    ):
        payload = copy.deepcopy(data)

        payload = self.apply_variables(
            payload,
            member,
            guild
        )

        payload["flags"] = (
            payload.get("flags", 0)
            | COMPONENTS_V2_FLAG
        )

        route = discord.http.Route(
            "POST",
            "/channels/{channel_id}/messages",
            channel_id=channel.id
        )

        return await self.bot.http.request(
            route,
            json=payload
        )

    async def send_to_both(
        self,
        thread,
        data
    ):
        member = thread.recipient
        guild = thread.guild

        payload = copy.deepcopy(data)

        payload = self.apply_variables(
            payload,
            member,
            guild
        )

        payload["flags"] = (
            payload.get("flags", 0)
            | COMPONENTS_V2_FLAG
        )

        await self.send_components(
            member,
            payload,
            member,
            guild
        )

        await self.send_components(
            thread.channel,
            payload,
            member,
            guild
        )

    async def show_config(
        self,
        ctx
    ):
        config = await self.get_config(
            ctx.guild.id
        )

        embed = discord.Embed(
            title="CloseRequest Configuration",
            description=(
                "Configure every Components V2 message used "
                "by CloseRequest.\n\n"
                "**All messages except `Schedule Closed` are "
                "shown identically to the user and Staff.**\n\n"
                "`Schedule Closed` is Staff-only."
            ),
            color=discord.Color.blurple()
        )

        for key, label in (
            ("close_request", "Close Request"),
            ("inactivity", "Inactivity"),
            ("closed_message", "Closed Message"),
            ("keep_open_message", "Keep Open Message"),
            ("inactivity_close_message", "Inactivity Close"),
            ("schedule_closed", "Schedule Closed")
        ):
            data = config.get(
                key,
                DEFAULT_CONFIG[key]
            )

            component_count = len(
                data.get("components", [])
            )

            embed.add_field(
                name=label,
                value=(
                    f"Components: `{component_count}`\n"
                    f"V2: `Yes`"
                ),
                inline=True
            )

        await ctx.send(
            embed=embed,
            view=ConfigurationView(
                self,
                ctx.author.id,
                ctx.guild.id
            )
        )

    @commands.command(
        name="closerequest"
    )
    @checks.has_permissions(
        PermissionLevel.SUPPORTER
    )
    async def closerequest(
        self,
        ctx,
        action=None
    ):
        if action and action.lower() == "config":
            await self.show_config(ctx)
            return

        if not ctx.thread:
            await ctx.send(
                "This command can only be used inside a Modmail thread."
            )
            return

        config = await self.get_config(
            ctx.guild.id
        )

        data = self.prepare_close_request(
            config["close_request"],
            ctx.guild.id,
            ctx.thread.id,
            ctx.thread.recipient.id
        )

        await self.send_to_both(
            ctx.thread,
            data
        )

    @commands.command(
        name="inactivity"
    )
    @checks.has_permissions(
        PermissionLevel.SUPPORTER
    )
    async def inactivity(
        self,
        ctx,
        action=None
    ):
        if action and action.lower() == "config":
            await self.show_config(ctx)
            return

        if not ctx.thread:
            await ctx.send(
                "This command can only be used inside a Modmail thread."
            )
            return

        thread = ctx.thread

        old_task = self.inactivity_tasks.get(
            thread.id
        )

        if old_task and not old_task.done():
            old_task.cancel()

        config = await self.get_config(
            ctx.guild.id
        )

        # This message is identical on both sides.
        await self.send_to_both(
            thread,
            config["inactivity"]
        )

        # This message is Staff-only.
        await self.send_components(
            thread.channel,
            config["schedule_closed"],
            thread.recipient,
            thread.guild
        )

        task = asyncio.create_task(
            self.inactivity_worker(
                thread,
                ctx.guild.id
            )
        )

        self.inactivity_tasks[
            thread.id
        ] = task

    async def inactivity_worker(
        self,
        thread,
        guild_id
    ):
        try:
            await asyncio.sleep(
                24 * 60 * 60
            )

            current = self.inactivity_tasks.get(
                thread.id
            )

            if current is not asyncio.current_task():
                return

            config = await self.get_config(
                guild_id
            )

            # Same message on both sides.
            await self.send_to_both(
                thread,
                config["inactivity_close_message"]
            )

            await thread.close(
                closer=self.bot.user
            )

        except asyncio.CancelledError:
            return

        except Exception as exc:
            print(
                "CloseRequest inactivity error:",
                repr(exc)
            )

        finally:
            current = self.inactivity_tasks.get(
                thread.id
            )

            if current is asyncio.current_task():
                self.inactivity_tasks.pop(
                    thread.id,
                    None
                )

    @commands.Cog.listener()
    async def on_thread_reply(
        self,
        thread,
        from_mod,
        message,
        anonymous,
        plain
    ):
        task = self.inactivity_tasks.get(
            thread.id
        )

        if not task or task.done():
            return

        # Any real reply cancels this particular
        # inactivity countdown.
        task.cancel()

        self.inactivity_tasks.pop(
            thread.id,
            None
        )

    @commands.Cog.listener()
    async def on_interaction(
        self,
        interaction
    ):
        if interaction.type != discord.InteractionType.component:
            return

        data = interaction.data or {}

        custom_id = data.get(
            "custom_id"
        )

        if not custom_id:
            return

        parts = custom_id.split(":")

        if len(parts) != 5:
            return

        if parts[0] != "cr":
            return

        action = parts[1]

        try:
            guild_id = int(parts[2])
            thread_id = int(parts[3])
            user_id = int(parts[4])
        except ValueError:
            return

        if action not in ("close", "keep"):
            return

        if interaction.user.id != user_id:
            await interaction.response.send_message(
                "This button belongs to another ticket.",
                ephemeral=True
            )
            return

        guild = self.bot.get_guild(
            guild_id
        )

        if not guild:
            await interaction.response.send_message(
                "The server for this ticket could not be found.",
                ephemeral=True
            )
            return

        thread = guild.get_channel(
            thread_id
        )

        if not thread:
            await interaction.response.send_message(
                "This ticket is no longer open.",
                ephemeral=True
            )
            return

        config = await self.get_config(
            guild_id
        )

        if action == "keep":
            await self.send_components(
                interaction.user,
                config["keep_open_message"],
                interaction.user,
                guild
            )

            await self.send_components(
                thread,
                config["keep_open_message"],
                interaction.user,
                guild
            )

            await interaction.response.send_message(
                "The ticket will remain open.",
                ephemeral=True
            )

            return

        task = self.inactivity_tasks.pop(
            thread.id,
            None
        )

        if task and not task.done():
            task.cancel()

        await self.send_components(
            interaction.user,
            config["closed_message"],
            interaction.user,
            guild
        )

        await self.send_components(
            thread,
            config["closed_message"],
            interaction.user,
            guild
        )

        await interaction.response.send_message(
            "Ticket closed.",
            ephemeral=True
        )

        await thread.close(
            closer=interaction.user
        )

    async def cog_unload(self):
        for task in self.inactivity_tasks.values():
            if not task.done():
                task.cancel()

        self.inactivity_tasks.clear()


async def setup(bot: ModmailBot) -> None:
    await bot.add_cog(
        CloseRequest(bot)
    )
