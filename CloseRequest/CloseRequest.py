import discord

from discord.ext import commands

from bot import ModmailBot
from core import checks
from core.models import PermissionLevel


CLOSEREQUEST_SNIPPET = (
    "Would you like to close your support ticket?\n\n"
    "If your issue has been resolved, you can close the ticket using the button below."
)

CLOSEREQUEST_CLOSED_MESSAGE = (
    "Your ticket has been closed."
)

CLOSEREQUEST_KEEP_OPEN_MESSAGE = (
    "No problem. Your ticket will remain open."
)

INACTIVITY_SNIPPET = (
    "This ticket has been scheduled to close in 24 hours due to inactivity.\n\n"
    "If you still need help, simply reply to this ticket."
)

INACTIVITY_CLOSE_MESSAGE = (
    "This ticket has been automatically closed after 24 hours of inactivity."
)


class CloseRequestView(discord.ui.View):
    def __init__(self, bot: ModmailBot, thread_id: int, user_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.thread_id = thread_id
        self.user_id = user_id

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="modmail_closerequest_close"
    )
    async def close_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This button is not for you.",
                ephemeral=True
            )
            return

        thread = await self.bot.threads.find(recipient_id=self.user_id)

        if thread is None or thread.id != self.thread_id:
            await interaction.response.send_message(
                "This ticket is no longer open.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            CLOSEREQUEST_CLOSED_MESSAGE
        )

        await thread.close(
            closer=interaction.user
        )

        for item in self.children:
            item.disabled = True

        try:
            await interaction.message.edit(view=self)
        except (discord.NotFound, discord.Forbidden):
            pass

    @discord.ui.button(
        label="Keep Open",
        style=discord.ButtonStyle.secondary,
        custom_id="modmail_closerequest_keepopen"
    )
    async def keep_open_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This button is not for you.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            CLOSEREQUEST_KEEP_OPEN_MESSAGE
        )

        for item in self.children:
            item.disabled = True

        try:
            await interaction.message.edit(view=self)
        except (discord.NotFound, discord.Forbidden):
            pass


class CloseRequest(commands.Cog):
    def __init__(self, bot: ModmailBot):
        self.bot = bot

    @commands.command(
        name="closerequest"
    )
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def close_request(self, ctx: commands.Context):
        thread = ctx.thread

        if thread is None:
            return

        user = thread.recipient

        if user is None:
            await ctx.send(
                "I could not find the user associated with this ticket."
            )
            return

        view = CloseRequestView(
            self.bot,
            thread.id,
            user.id
        )

        try:
            await user.send(
                content=CLOSEREQUEST_SNIPPET,
                view=view
            )
        except discord.Forbidden:
            await ctx.send(
                "I could not send a DM to the ticket owner."
            )
            return

        await ctx.send(
            "The close request has been sent to the ticket owner."
        )

    @commands.command(
        name="inactivity"
    )
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def inactivity(self, ctx: commands.Context):
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

        try:
            await user.send(
                INACTIVITY_SNIPPET
            )
        except discord.Forbidden:
            await ctx.send(
                "I could not send a DM to the ticket owner."
            )
            return

        await thread.close(
            closer=ctx.author,
            after=24 * 60 * 60,
            message=INACTIVITY_CLOSE_MESSAGE
        )

        await ctx.send(
            "The 24-hour inactivity timer has started."
        )


async def setup(bot: ModmailBot) -> None:
    await bot.add_cog(CloseRequest(bot))

    bot.add_view(
        CloseRequestView(
            bot,
            0,
            0
        )
    )
