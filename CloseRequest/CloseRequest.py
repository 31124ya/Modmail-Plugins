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
    "keep_open_message": {
        "flags": COMPONENTS_V2_FLAG,
        "components": [
            {
                "type": 10,
                "content": "The ticket will remain open."
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
        try:
            return super().get_value(key, args, kwargs)
        except (KeyError, IndexError):
            return "{" + str(key) + "}"


def apply_variables(value, member=None, guild=None, channel=None):
    if not isinstance(value, str):
        return value

    formatter = SafeFormatter()

    variables = {
        "member": member,
        "user": member,
        "guild": guild,
        "channel": channel
    }

    try:
        return formatter.format(value, **variables)
    except Exception:
        return value


def apply_variables_dict(data, member=None, guild=None, channel=None):
    if isinstance(data, str):
        return apply_variables(data, member, guild, channel)

    if isinstance(data, list):
        return [
            apply_variables_dict(item, member, guild, channel)
            for item in data
        ]

    if isinstance(data, dict):
        return {
            key: apply_variables_dict(value, member, guild, channel)
            for key, value in data.items()
        }

    return data


class CloseRequestModal(discord.ui.Modal):
    def __init__(self, cog, config_key, title):
        super().__init__(title=title)
        self.cog = cog
        self.config_key = config_key

        self.json_input = discord.ui.TextInput(
            label="Components V2 JSON",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000,
            default=""
        )

        self.add_item(self.json_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.json_input.value.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            await interaction.response.send_message(
                f"Invalid JSON.\n```text\n{exc}\n```",
                ephemeral=True
            )
            return

        valid, error = self.cog.validate_components(data)

        if not valid:
            await interaction.response.send_message(
                f"Invalid Components V2 configuration.\n\n{error}",
                ephemeral=True
            )
            return

        await self.cog.save_config(self.config_key, data)

        await interaction.response.send_message(
            "Saved successfully.",
            ephemeral=True
        )


class ConfigurationView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    async def open_editor(
        self,
        interaction: discord.Interaction,
        config_key: str,
        title: str
    ):
        config = await self.cog.get_config()

        data = config.get(
            config_key,
            DEFAULT_CONFIG[config_key]
        )

        modal = CloseRequestModal(
            self.cog,
            config_key,
            title
        )

        modal.json_input.default = json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        )

        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Close Request",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def close_request_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.open_editor(
            interaction,
            "close_request",
            "Edit Close Request"
        )

    @discord.ui.button(
        label="Inactivity",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def inactivity_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.open_editor(
            interaction,
            "inactivity",
            "Edit Inactivity"
        )

    @discord.ui.button(
        label="Keep Open Message",
        style=discord.ButtonStyle.primary,
        row=1
    )
    async def keep_open_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.open_editor(
            interaction,
            "keep_open_message",
            "Edit Keep Open Message"
        )

    @discord.ui.button(
        label="Schedule Closed",
        style=discord.ButtonStyle.secondary,
        row=2
    )
    async def schedule_closed_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.open_editor(
            interaction,
            "schedule_closed",
            "Edit Schedule Closed"
        )


class CloseRequest(commands.Cog):
    def __init__(self, bot: ModmailBot):
        self.bot = bot
        self.inactivity_tasks = {}

    async def get_config(self):
        partition = self.bot.plugin_db.get_partition(self)

        config = await partition.find_one({"_id": "config"})

        if not config:
            config = {
                "_id": "config",
                "data": copy.deepcopy(DEFAULT_CONFIG)
            }

            await partition.replace_one(
                {"_id": "config"},
                config,
                upsert=True
            )

        return config.get("data", copy.deepcopy(DEFAULT_CONFIG))

    async def save_config(self, key, value):
        partition = self.bot.plugin_db.get_partition(self)

        config = await self.get_config()

        config[key] = value

        await partition.replace_one(
            {"_id": "config"},
            {
                "_id": "config",
                "data": config
            },
            upsert=True
        )

    def validate_components(self, data):
        if not isinstance(data, dict):
            return False, "The JSON root must be an object."

        if data.get("flags") != COMPONENTS_V2_FLAG:
            return False, (
                f"`flags` must be `{COMPONENTS_V2_FLAG}` "
                "for Components V2."
            )

        components = data.get("components")

        if not isinstance(components, list):
            return False, "`components` must be an array."

        if not components:
            return False, "`components` cannot be empty."

        if "content" in data:
            return False, (
                "Components V2 messages cannot use the legacy "
                "`content` field."
            )

        if "embeds" in data:
            return False, (
                "Components V2 messages cannot use the legacy "
                "`embeds` field."
            )

        if "poll" in data:
            return False, (
                "Components V2 messages cannot use the legacy "
                "`poll` field."
            )

        if "stickers" in data:
            return False, (
                "Components V2 messages cannot use the legacy "
                "`stickers` field."
            )

        return True, None

    def prepare_close_request(
        self,
        data,
        guild_id,
        thread_id,
        user_id
    ):
        data = copy.deepcopy(data)

        def process(value):
            if isinstance(value, list):
                for item in value:
                    process(item)

            elif isinstance(value, dict):
                if value.get("type") == 2:
                    custom_id = value.get("custom_id")

                    if custom_id == CLOSE_REQUEST_CLOSE_ID:
                        value["custom_id"] = (
                            f"cr:close:{guild_id}:{thread_id}:{user_id}"
                        )

                    elif custom_id == CLOSE_REQUEST_KEEP_ID:
                        value["custom_id"] = (
                            f"cr:keep:{guild_id}:{thread_id}:{user_id}"
                        )

                for child in value.values():
                    process(child)

        process(data.get("components", []))

        return data

    async def send_components(self, channel, data):
        payload = copy.deepcopy(data)

        route = discord.http.Route(
            "POST",
            "/channels/{channel_id}/messages",
            channel_id=channel.id
        )

        return await self.bot.http.request(
            route,
            json=payload
        )

    async def send_to_user_and_thread(
        self,
        thread,
        data,
        member
    ):
        guild = getattr(thread.channel, "guild", None)

        data = apply_variables_dict(
            data,
            member=member,
            guild=guild,
            channel=thread.channel
        )

        dm = await member.create_dm()

        await self.send_components(
            dm,
            data
        )

        await self.send_components(
            thread.channel,
            data
        )

    async def send_staff_only(
        self,
        thread,
        data
    ):
        guild = getattr(thread.channel, "guild", None)

        data = apply_variables_dict(
            data,
            member=getattr(thread, "recipient", None),
            guild=guild,
            channel=thread.channel
        )

        await self.send_components(
            thread.channel,
            data
        )

    async def show_config(self, ctx):
        embed = discord.Embed(
            title="CloseRequest Configuration",
            description=(
                "Configure the six Components V2 messages used by "
                "CloseRequest.\n\n"
                "**Close Request**\n"
                "Message sent when `?closerequest` is used.\n\n"
                "**Inactivity**\n"
                "Message sent when `?inactivity` is used.\n\n"
                "**Closed Message**\n"
                "Message used after the user presses **Close Ticket**.\n\n"
                "**Keep Open Message**\n"
                "Message used after the user presses **Keep Open**.\n\n"
                "**Inactivity Close**\n"
                "Message used when the 24-hour timer expires.\n\n"
                "**Schedule Closed**\n"
                "Staff-only message sent when `?inactivity` starts."
            ),
            color=discord.Color.blurple()
        )

        await ctx.send(
            embed=embed,
            view=ConfigurationView(self)
        )

    @commands.command(
        name="closeconfig",
        help="Configure CloseRequest Components V2 messages."
    )
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def close_config(self, ctx):
        await self.show_config(ctx)

    @commands.command(
        name="closerequest",
        help="Send a close request to the ticket opener."
    )
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def close_request(self, ctx):
        thread = ctx.thread

        member = thread.recipient

        config = await self.get_config()

        message = self.prepare_close_request(
            config["close_request"],
            thread.channel.guild.id,
            thread.channel.id,
            member.id
        )

        message = apply_variables_dict(
            message,
            member=member,
            guild=thread.channel.guild,
            channel=thread.channel
        )

        await self.send_components(
            await member.create_dm(),
            message
        )

        await self.send_components(
            thread.channel,
            message
        )

    @commands.command(
        name="inactivity",
        help="Schedule this ticket to close after 24 hours."
    )
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def inactivity(self, ctx):
        thread = ctx.thread

        thread_id = thread.channel.id

        old_task = self.inactivity_tasks.get(thread_id)

        if old_task and not old_task.done():
            old_task.cancel()

        config = await self.get_config()

        inactivity_message = copy.deepcopy(
            config["inactivity"]
        )

        schedule_closed_message = copy.deepcopy(
            config["schedule_closed"]
        )

        member = thread.recipient

        await self.send_to_user_and_thread(
            thread,
            inactivity_message,
            member
        )

        await self.send_staff_only(
            thread,
            schedule_closed_message
        )

        task = asyncio.create_task(
            self._inactivity_timer(thread)
        )

        self.inactivity_tasks[thread_id] = task

    async def _inactivity_timer(self, thread):
        thread_id = thread.channel.id

        try:
            await asyncio.sleep(24 * 60 * 60)

        await thread.close(
            closer=self.bot.user
        )

        except asyncio.CancelledError:
            return

        except Exception:
            raise

        finally:
            current = self.inactivity_tasks.get(thread_id)

            if current is asyncio.current_task():
                self.inactivity_tasks.pop(
                    thread_id,
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
        thread_id = thread.channel.id

        task = self.inactivity_tasks.get(thread_id)

        if task and not task.done():
            task.cancel()

            self.inactivity_tasks.pop(
                thread_id,
                None
            )

    @commands.Cog.listener()
    async def on_interaction(
        self,
        interaction: discord.Interaction
    ):
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id")

        if not custom_id:
            return

        parts = custom_id.split(":")

        if len(parts) != 5:
            return

        if parts[0] != "cr":
            return

        action = parts[1]

        if action not in ("close", "keep"):
            return

        try:
            guild_id = int(parts[2])
            thread_id = int(parts[3])
            user_id = int(parts[4])
        except ValueError:
            return

        if interaction.user.id != user_id:
            await interaction.response.send_message(
                "This button is not for you.",
                ephemeral=True
            )
            return

        guild = self.bot.get_guild(guild_id)

        if guild is None:
            await interaction.response.send_message(
                "The server could not be found.",
                ephemeral=True
            )
            return

        channel = guild.get_channel(thread_id)

        if channel is None:
            await interaction.response.send_message(
                "The ticket could not be found.",
                ephemeral=True
            )
            return

        thread = getattr(channel, "thread", None)

        if thread is None:
            try:
                thread = await self.bot.threads.find(channel)
            except Exception:
                thread = None

        if thread is None:
            await interaction.response.send_message(
                "The Modmail thread could not be found.",
                ephemeral=True
            )
            return

        config = await self.get_config()

        member = interaction.user

        if action == "close":
    await interaction.response.defer()

    task = self.inactivity_tasks.pop(
        thread_id,
        None
    )

    if task and not task.done():
        task.cancel()

    await thread.close(
        closer=interaction.user
    )

    return

        if action == "keep":
            await interaction.response.defer()

            keep_open_message = config[
                "keep_open_message"
            ]

            await self.send_to_user_and_thread(
                thread,
                keep_open_message,
                member
            )


async def setup(bot: ModmailBot) -> None:
    await bot.add_cog(
        CloseRequest(bot)
    )
