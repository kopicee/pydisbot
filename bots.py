import asyncio
from collections import defaultdict

import discord

from pydisbot.auth import PrivilegeChecker
from pydisbot.components import Response
from pydisbot.utils import partial_coro

from pydisbot.config import defaults, defaultmsgs


CUSTOM_EVENTS = [           # args:
    'on_command',           # (message, command, argstr)
    'on_invalid_command',   # (message, command)
    'on_own_message'        # (message)
]

DISCORDPY_EVENTS = """
    on_ready
    on_resumed
    on_error
    on_message
    on_socket_raw_receive
    on_socket_raw_send
    on_message_delete
    on_message_edit
    on_reaction_add
    on_reaction_remove
    on_reaction_clear
    on_channel_delete
    on_channel_create
    on_channel_update
    on_member_join
    on_member_remove
    on_member_update
    on_server_join
    on_server_remove
    on_server_update
    on_server_role_create
    on_server_role_delete
    on_server_role_update
    on_server_emojis_update
    on_server_available
    on_server_unavailable
    on_voice_state_update
    on_member_ban
    on_member_unban
    on_typing
    on_group_join
    on_group_remove
""".split()


class BasicDiscordBot:
    def __init__(self):
        self.client = discord.Client()

        self.event_handlers = defaultdict(list)
        self.commands = {}
        self.privcheck = None
        self.async_tasks = []

        self.feedback = {
            'unauthorized': defaultmsgs.UNAUTHORIZED,
            'invalid_command': defaultmsgs.INVALID_COMMAND
        }
        self.command_prefix = defaults.COMMAND_PREFIX
        self.default_now_playing = defaults.NOW_PLAYING


    def setup_auth(self, authfile_path):
        self.privcheck = PrivilegeChecker(self.client, authfile_path)
        self.async_tasks.append(self.privcheck.authcode_task)

    async def dispatch(self, channel, resp):
        """Sends Responses to the target channel"""
        if not resp:
            return
        msg, embed, file = resp.msg, resp.embed, resp.file

        # Most messages are just msg and/or embed
        if not file:
            await self.client.send_message(channel, msg, embed=embed)
        else:
            # If there are files but not embed, send the message with the file
            if not embed:
                await self.client.send_file(channel, file, content=msg)
            # Otherwise send the msg+embed first, then the file
            else:
                await self.client.send_message(channel, msg, embed=embed)
                await self.client.send_file(channel, file)


    async def set_now_playing(self, text):
        """Convenience function for changing Now Playing display"""
        game = discord.Game(name=text)
        await self.client.change_presence(game=game)


    def bind_to_event(self, event):
        """For binding handlers to discordpy and custom events

        You can use this as a decorator:
            @bot.bind_to_event(event='on_message_delete')
            async def say_something(message):
                # ...

        You can see the arguments provided by custom events above. Arguments
        from discordpy events can be found on:
            https://discordpy.readthedocs.io/en/latest/api.html
        """
        def decorator(coro):
            if event not in DISCORDPY_EVENTS + CUSTOM_EVENTS:
                raise ValueError('invalid event provided to '
                                 'bind_to_event(): ' + repr(event_name))
            self.event_handlers[event].append(coro)
        return decorator


    def bind_command(self, keyword, privileged=False, hidden=False):
        """Factory that returns decorators that register commands to the bot.

        Commands are specially handled cases in on_message.
        This interface allows @bind_command(keyword='foo') to return a 
        decorator that wraps the following function/coro declaration.

        The returned decorator will associate the defined function with a
        command keyword, which is used within on_message to pass arguments to
        handler_on_command.

        handler_on_command checks the user's executing context for privileges
        and hidden commands.
        """
        def decorator(coro):
            async def handler_on_command(message, comm, argstr):
                # Hidden commands only take effect via private message
                if hidden and not message.channel.is_private:
                    return

                # Check privilege if needed
                authorized = True
                if privileged:
                    if not self.privcheck:
                        e = (f"command '{comm}' required privileges but "
                             "setup_auth() was never run")
                        raise NotImplementedError(e)
                    authorized = self.privcheck.has_privilege(message.author)

                if not authorized:
                    print(f'Blocked unauthorized user {str(message.author)} '
                          f'from running command {comm}')
                    if hidden:
                        return
                    else:
                        return Response(msg=self.feedback['unauthorized'])

                # Return if authorized and in the right channel
                resp = await coro(message, argstr)
                await self.dispatch(message.channel, resp)

            # Associate this handler to the command
            self.commands[keyword] = handler_on_command
        return decorator

            
    async def trigger_event(self, event, *args, **kwargs):
        partials = [
            partial_coro(coro, *args, **kwargs)
            for coro in self.event_handlers[event]
        ]
        return await asyncio.gather(*partials, loop=self.client.loop)


    async def on_message(self, message):
        """Default on_message callback that triggers handlers on custom events
        
        If you want to attach additional on_message handlers without affecting
        the command-invoking logic, use this:
            bind_to_event(your_handler, event="on_message")
        """
        responses = []

        # If this is own message:
        if message.author == self.client.user:
            responses.extend(
                await self.trigger_event('on_own_message', message))
        
        # Elif looks like command
        elif message.content.startswith(self.command_prefix):
            # Remove leading command_prefix; split into command and argstr
            text = message.content.replace(self.command_prefix, '')
            keyword, *argstr = text.split(None, maxsplit=1)
            argstr = argstr[0] if argstr else ''

            # Check for valid command, trigger on_command
            handler = self.commands.get(keyword.strip())
            if handler:
                responses.append(await handler(message, keyword, argstr))
                responses.extend(
                    await self.trigger_event(
                        'on_command', message, keyword, argstr))
                
            # Handle invalid command
            else:
                fargs = dict(prefix=self.command_prefix, command=keyword)
                msg = self.feedback['invalid_command'].format(**fargs)
                responses.append(Response(msg))
                responses.extend(
                    await self.trigger_event(
                        'on_invalid_command', message, keyword))
            
        # Else just trigger on_message
        else:
            responses.extend(await self.trigger_event('on_message', message))

        channel = message.channel
        for resp in responses:
            await self.dispatch(channel, resp)


    async def on_ready(self):
        """Default on_ready callback
        
        If you want to attach additional on_ready handlers without affecting
        this information being printed, use this:
            bind_to_event(your_handler, event="on_ready")
        """
        msg = ('------\n'
               'Logged in.\n'
               '  UN: {}\n'
               '  Invite link:\n'
               '    https://discordapp.com/oauth2/authorize?client_id={}&scope=bot&permissions=0\n'
               '------\n'
        ).format(self.client.user.name, self.client.user.id)
        print(msg)
        await self.trigger_event('on_ready')
        await self.set_now_playing(self.default_now_playing)


    def attach_proxy_callback(self, event_name):
        """Attaches a 'proxy' callback_on_event to the given event_name

        The discordpy package identifies which event to binds callbacks to 
        using the callback's __name__ attribute. 

        This function creates a 'proxy' callback coro, updates its __name__ 
        attribute to the event_name, then attaches it to the client using 
        client.event()
        """
        async def callback_on_event(*eventargs, **eventkwargs):
            """Emulates some callback handler, such as client.on_ready()
            
            Gathers output from coros in self.event_handlers[event_name] and
            feeds them to self.dispatch.
            """
            output = await self.trigger_event(
                event_name, *eventargs, **eventkwargs)
            
            # Try and find an output channel
            channel = None
            arg = (eventargs and eventargs[0]) or None
            if isinstance(arg, discord.Channel):
                channel = arg
            elif isinstance(getattr(arg, 'channel'), discord.Channel):
                channel = arg.channel
            elif isinstance(getattr(arg, 'message'), discord.Message):
                channel = arg.message.channel

            if channel:
                for resp in output:
                    self.dispatch(channel, resp)

        if event_name not in DISCORDPY_EVENTS + CUSTOM_EVENTS:
            raise ValueError('invalid event provided to '
                             'create_custom_handler(): ' + repr(event_name))
        callback_on_event.__name__ = event_name
        self.client.event(callback_on_event)


    def start(self, token, quickfail=False):
        # Extra handler for quickfail
        if quickfail:
            @self.bind_to_event('on_error')
            async def interrupt_on_error(*a, **k):
                raise KeyboardInterrupt

        # Register custom event handlers
        for event in DISCORDPY_EVENTS + CUSTOM_EVENTS:
            if hasattr(self, event):
                callback = getattr(self, event)
                self.client.event(callback)

            elif self.event_handlers[event]:
                self.attach_proxy_callback(event)

        # Register background coros
        for awaitable in self.async_tasks:
            self.client.loop.create_task(awaitable(self.client))

        if not quickfail:
            self.client.run(token)
        
        else:
            try:
                print('WARNING: Running on QUICKFAIL mode.\n'
                      '         Errors will trigger client logout/shutdown.')
                self.client.loop.run_until_complete(self.client.start(token))
            except KeyboardInterrupt:
                print('(QUICKFAIL) Halting...')
                self.client.loop.run_until_complete(self.client.logout())
                # cancel all tasks lingering
            finally:
                self.client.loop.close()
