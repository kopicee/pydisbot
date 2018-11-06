import os


def _from_env(varname, default=None, coerce_to=None):
    val = os.environ.get(varname, default)
    if val is None:
        raise ValueError(f"No var '{varname}' defined in the environment.")
    if coerce_to:
        val = coerce_to(val)
    return val

# Flags
DEBUGGING = _from_env('DEBUGGING', default=False, coerce_to=bool)
LOGFILE = _from_env('LOGFILE')

# Discord bot token
DISCORD = _from_env('DISCORD_SECRET')
