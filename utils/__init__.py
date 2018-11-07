def truncate(s, maxlen=15):
    if len(s) > maxlen:
        s = s[:maxlen - 3] + '...'
    return s


def partial_coro(coro, *args, **kwargs):
    async def wrapper():
        return await coro(*args, **kwargs)
    return wrapper
