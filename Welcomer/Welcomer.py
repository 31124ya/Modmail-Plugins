import json
import string

import discord
from discord.ext import commands


class SafeFormatter(string.Formatter):
    def get_field(self, field_name, args, kwargs):
        try:
            return super().get_field(field_name, args, kwargs)
        except (KeyError, AttributeError, IndexError, TypeError):
            return "", field_name


def apply_vars(message, member=None, guild=None, bot=None, invite=None):
    if not isinstance(message, str):
        return message

    variables = {
        "member": member,
        "guild": guild,
        "bot": bot,
        "invite": invite or "",
    }

    try:
        return SafeFormatter().format(message, **variables)
    except Exception:
        return message


def apply_vars_dict(data, member, guild, bot, invite):
    if isinstance(data, dict):
        return {
            key: apply_vars_dict(
                value,
                member,
                guild,
                bot,
                invite
            )
            for key, value in data.items()
        }

    if isinstance(data, list):
        return [
            apply_vars_dict(
                value,
                member,
                guild,
                bot,
                invite
            )
            for value in data
        ]

    if isinstance(data, str):
        return apply_vars(
            data,
            member=member,
            guild=guild,
            bot=bot,
            invite=invite
        )

    return data


class MessageModal(discord.ui.Modal):
    def __init__(self, cog, guild_id):
        super().__init__(title="Set Welcome Message")

        self.cog = cog
        self.guild_id = guild_id

        config = cog.config_cache.get(guild_id, {})
        current = config.get("message", "")

        self.message_input = discord.ui.TextInput(
            label="Welcome Message",
            style=discord.TextStyle.paragraph,
            placeholder="Enter the message members will receive...",
            default=current if current and not current.startswith("{") else "",
            required=True,
            max_length=4000
        )

        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        message = str(self.message_input.value)

        config = await self.cog.get_config(self.guild_id)

        config["message"] = message
        config["enabled"] = True

        await self.cog.save_config(self.guild_id, config)

        await interaction.response.send_message(
            "Welcome message saved.",
            ephemeral=True
        )


class EmbedModal(discord.ui.Modal):
    def __init__(self, cog, guild_id):
        super().__init__(title="Set Embed JSON")

        self.cog = cog
        self.guild_id = guild_id

        config = cog.config_cache.get(guild_id, {})
        current = config.get("message", "")

        if not current:
            current = '{\n  "embeds": [\n    {\n      "title": "Welcome",\n      "description": "Welcome {member.mention}!"\n    }\n  ]\n}'

        self.json_input = discord.ui.TextInput(
            label="Discord Message JSON",
            style=discord.TextStyle.paragraph,
            placeholder='{"embeds":[{"title":"Welcome"}]}',
            default=current[:4000],
            required=True,
            max_length=4000
        )

        self.add_item(self.json_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = str(self.json_input.value)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            await interaction.response.send_message(
                f"Invalid JSON:\n{exc}",
                ephemeral=True
            )
            return

        if not isinstance(data, dict):
            await interaction.response.send_message(
                "The JSON root must be an object.",
                ephemeral=True
            )
            return

        try:
            self.cog.validate_message_payload(data)
        except ValueError as exc:
            await interaction.response.send_message(
                str(exc),
                ephemeral=True
            )
            return

        config = await self.cog.get_config(self.guild_id)

        config["message"] = raw
        config["enabled"] = True

        await self.cog.save_config(self.guild_id, config)

        await interaction.response.send_message(
            "Embed JSON saved.",
            ephemeral=True
        )


class WelcomerView(discord.ui.View):
    def __init__(self, cog, guild_id, channel):
        super().__init__(timeout=300)

        self.cog = cog
        self.guild_id = guild_id
        self.channel = channel

    @discord.ui.button(
        label="Message",
        style=discord.ButtonStyle.primary
    )
    async def message_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            MessageModal(
                self.cog,
                self.guild_id
            )
        )

    @discord.ui.button(
        label="Embed JSON",
        style=discord.ButtonStyle.primary
    )
    async def embed_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            EmbedModal(
                self.cog,
                self.guild_id
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
        config = await self.cog.get_config(self.guild_id)

        message = config.get("message")

        if not message:
            await interaction.response.send_message(
                "No welcome message has been configured.",
                ephemeral=True
            )
            return

        try:
            payload = self.cog.format_message(
                interaction.user,
                message,
                self.cog.default_invite(self.guild_id)
            )
        except Exception as exc:
            await interaction.response.send_message(
                f"Unable to format the message:\n{exc}",
                ephemeral=True
            )
            return

        try:
            await self.channel.send(**payload)

            await interaction.response.send_message(
                "Test message sent.",
                ephemeral=True
            )

        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"Discord rejected the message:\n{exc}",
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
        config = await self.cog.get_config(self.guild_id)

        config["enabled"] = False

        await self.cog.save_config(
            self.guild_id,
            config
        )

        await interaction.response.send_message(
            "Welcomer has been disabled.",
            ephemeral=True
        )

    @discord.ui.button(
        label="Enable",
        style=discord.ButtonStyle.secondary
    )
    async def enable_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        config = await self.cog.get_config(self.guild_id)

        if not config.get("message"):
            await interaction.response.send_message(
                "Please configure a welcome message first.",
                ephemeral=True
            )
            return

        config["enabled"] = True

        await self.cog.save_config(
            self.guild_id,
            config
        )

        await interaction.response.send_message(
            "Welcomer has been enabled.",
            ephemeral=True
        )


class Welcomer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.db = bot.plugin_db.get_partition(self)

        self.config_cache = {}

        self.invite_cache = {}

        bot.loop.create_task(
            self.populate_invite_cache()
        )

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
                "channel_id": None,
                "message": None,
                "enabled": False
            }

        self.config_cache[guild_id] = data

        return data

    async def save_config(self, guild_id, config):
        self.config_cache[guild_id] = config

        data = dict(config)
        data["_id"] = str(guild_id)

        await self.db.replace_one(
            {"_id": str(guild_id)},
            data,
            upsert=True
        )

    def validate_message_payload(self, data):
        if "embeds" in data:
            if not isinstance(data["embeds"], list):
                raise ValueError(
                    '`"embeds"` must be an array.'
                )

            if len(data["embeds"]) > 10:
                raise ValueError(
                    "Discord allows a maximum of 10 embeds."
                )

            for index, embed in enumerate(data["embeds"]):
                if not isinstance(embed, dict):
                    raise ValueError(
                        f'Embed #{index + 1} must be an object.'
                    )

                try:
                    discord.Embed.from_dict(embed)
                except Exception as exc:
                    raise ValueError(
                        f"Invalid embed #{index + 1}: {exc}"
                    )

        elif "embed" in data:
            if not isinstance(data["embed"], dict):
                raise ValueError(
                    '`"embed"` must be an object.'
                )

            try:
                discord.Embed.from_dict(
                    data["embed"]
                )
            except Exception as exc:
                raise ValueError(
                    f"Invalid embed: {exc}"
                )

        elif any(
            key in data
            for key in (
                "title",
                "description",
                "color",
                "fields",
                "footer",
                "author",
                "thumbnail",
                "image"
            )
        ):
            try:
                discord.Embed.from_dict(data)
            except Exception as exc:
                raise ValueError(
                    f"Invalid embed: {exc}"
                )

        else:
            if "content" not in data:
                raise ValueError(
                    'JSON must contain `"content"` or `"embeds"`.'
                )

    def format_message(
        self,
        member,
        message,
        invite=None
    ):
        guild = getattr(member, "guild", None)

        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return {
                "content": apply_vars(
                    message,
                    member=member,
                    guild=guild,
                    bot=self.bot,
                    invite=invite
                )
            }

        if not isinstance(data, dict):
            return {
                "content": apply_vars(
                    message,
                    member=member,
                    guild=guild,
                    bot=self.bot,
                    invite=invite
                )
            }

        data = apply_vars_dict(
            data,
            member,
            guild,
            self.bot,
            invite
        )

        result = {}

        if "content" in data:
            result["content"] = data["content"]

        if "embeds" in data:
            embeds = []

            for embed_data in data["embeds"]:
                embeds.append(
                    discord.Embed.from_dict(embed_data)
                )

            result["embeds"] = embeds

        elif "embed" in data:
            result["embed"] = discord.Embed.from_dict(
                data["embed"]
            )

        elif any(
            key in data
            for key in (
                "title",
                "description",
                "color",
                "fields",
                "footer",
                "author",
                "thumbnail",
                "image"
            )
        ):
            result["embed"] = discord.Embed.from_dict(
                data
            )

        if "allowed_mentions" in data:
            result["allowed_mentions"] = (
                discord.AllowedMentions.from_dict(
                    data["allowed_mentions"]
                )
            )

        return result

    async def populate_invite_cache(self):
        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            try:
                invites = await guild.invites()

                self.invite_cache[guild.id] = {
                    invite.code: invite.uses or 0
                    for invite in invites
                }

            except (
                discord.Forbidden,
                discord.HTTPException
            ):
                self.invite_cache[guild.id] = {}

    async def update_invite_cache(self, guild):
        try:
            invites = await guild.invites()

            self.invite_cache[guild.id] = {
                invite.code: invite.uses or 0
                for invite in invites
            }

        except (
            discord.Forbidden,
            discord.HTTPException
        ):
            self.invite_cache[guild.id] = {}

    def default_invite(self, guild_id):
        invites = self.invite_cache.get(
            guild_id,
            {}
        )

        if not invites:
            return ""

        return next(
            iter(invites.keys()),
            ""
        )

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.command()
    async def welcomer(
        self,
        ctx,
        channel: discord.TextChannel = None
    ):
        if channel is None:
            config = await self.get_config(
                ctx.guild.id
            )

            channel_id = config.get("channel_id")

            if channel_id:
                channel = ctx.guild.get_channel(
                    channel_id
                )

            if channel is None:
                channel = ctx.channel

        config = await self.get_config(
            ctx.guild.id
        )

        config["channel_id"] = channel.id

        await self.save_config(
            ctx.guild.id,
            config
        )

        embed = discord.Embed(
            title="Welcomer Configuration",
            description=(
                f"Welcome channel: {channel.mention}\n\n"
                "Choose how you want to configure the "
                "welcome message.\n\n"
                "**Message**\n"
                "Create a normal text welcome message.\n\n"
                "**Embed JSON**\n"
                "Paste a Discord message JSON payload.\n\n"
                "**Test**\n"
                "Send the current configuration as a test.\n\n"
                "**Disable**\n"
                "Disable automatic welcome messages.\n\n"
                "**Enable**\n"
                "Enable automatic welcome messages."
            ),
            color=discord.Color.blurple()
        )

        await ctx.send(
            embed=embed,
            view=WelcomerView(
                self,
                ctx.guild.id,
                channel
            )
        )

    @commands.Cog.listener()
    async def on_member_join(self, member):
        config = await self.get_config(
            member.guild.id
        )

        if not config.get("enabled"):
            return

        channel_id = config.get("channel_id")

        if not channel_id:
            return

        channel = member.guild.get_channel(
            int(channel_id)
        )

        if channel is None:
            return

        message = config.get("message")

        if not message:
            return

        invite = self.default_invite(
            member.guild.id
        )

        try:
            payload = self.format_message(
                member,
                message,
                invite
            )

            await channel.send(
                **payload
            )

        except discord.HTTPException:
            return

        except Exception:
            return

        await self.update_invite_cache(
            member.guild
        )


async def setup(bot):
    await bot.add_cog(
        Welcomer(bot)
    )
