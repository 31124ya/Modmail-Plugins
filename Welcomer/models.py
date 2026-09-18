import string


class SafeFormat(string.Formatter):
    def get_field(self, field_name, args, kwargs):
        try:
            return super().get_field(field_name, args, kwargs)
        except (KeyError, AttributeError, IndexError):
            return "", field_name


class SafeString(str):
    def __getattr__(self, item):
        return ""


def apply_vars(message, member=None, guild=None, bot=None, invite=None):
    """
    Replace variables in the welcome message.

    Supported:
        {member}
        {member.name}
        {member.mention}
        {member.id}

        {guild}
        {guild.name}
        {guild.id}

        {bot}
        {bot.name}

        {invite}
    """

    class Obj:
        def __init__(self, obj):
            self._obj = obj

        def __getattr__(self, name):
            if self._obj is None:
                return SafeString("")

            try:
                value = getattr(self._obj, name)
                return SafeString(str(value))
            except (AttributeError, TypeError):
                return SafeString("")

        def __str__(self):
            if self._obj is None:
                return ""

            try:
                return str(self._obj)
            except Exception:
                return ""

    variables = {
        "member": Obj(member),
        "guild": Obj(guild),
        "bot": Obj(bot),
        "invite": SafeString(invite or ""),
    }

    try:
        return SafeFormat().format(message, **variables)
    except Exception:
        return message
