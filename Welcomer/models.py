import string


class SafeString(str):
    def __getattr__(self, item):
        return ""


def apply_vars(bot, member, message, invite=None):
    """
    Replace Welcomer variables.

    Supported:
        {member}
        {member.name}
        {member.mention}
        {member.id}

        {guild}
        {guild.name}
        {guild.id}

        {bot}
        {invite}
    """

    if not isinstance(message, str):
        return message

    guild = getattr(member, "guild", None)

    variables = {
        "member": member,
        "guild": guild,
        "bot": bot,
        "invite": invite or "",
    }

    class SafeFormatter(string.Formatter):

        def get_field(self, field_name, args, kwargs):
            try:
                return super().get_field(
                    field_name,
                    args,
                    kwargs
                )
            except (KeyError, AttributeError, IndexError):
                return "", field_name

    try:
        return SafeFormatter().format(
            message,
            **variables
        )

    except Exception:
        return message
