import asyncio
from collections import defaultdict

import discord

from auth import PrivilegeChecker
from components import Response
from utils import defaultmsgs, partial_coro

from config import appconfig, environment


CUSTOM_EVENTS = [           # args:
    'on_command',           # (command, message)
    'on_invalid_command',   # (command)
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

        self.bot_prefix = appconfig.bot_prefix
        self.admin_prefix = appconfig.admin_prefix

        self.privcheck = PrivilegeChecker(client)
        self.event_handlers = defaultdict(list)
        self.commands = {}
        self.async_tasks = []


    async def dispatch(self, channel, resp):
        """Sends Responses to the target channel"""
        if not resp:
            return
        msg, embed, file = resp.msg, resp.embed, resp.file

        # Most messages are just msg and/or embed
        if not file:
            await client.send_message(channel, msg, embed=embed)
        else:
            # If there are files but not embed, send the message with the file
            if not embed:
                await client.send_file(channel, file, content=msg)
            # Otherwise send the msg+embed first, then the file
            else:
                await client.send_message(channel, msg, embed=embed)
                await client.send_file(channel, file)


    async def set_now_playing(self, text):
        """Convenience function for changing Now Playing display"""
        game = discord.Game(name=text)
        await client.change_presence(game=game)


    def bind_to_event(self, coro, event):
        """For binding handlers to discordpy and custom events

        You can use this as a decorator:
            @bot.bind_to_event(event='on_message_delete')
            async def say_something(message):
                # ...

        You can see the arguments provided by custom events above. Arguments
        from discordpy events can be found on:
            https://discordpy.readthedocs.io/en/latest/api.html
        """
        if event not in DISCORDPY_EVENTS + CUSTOM_EVENTS:
            raise ValueError('invalid event provided to '
                             'bind_to_event(): ' + repr(event_name))
        self.event_handlers[event].append(coro)


    def bind_command(self, coro, keyword, privileged=False, hidden=False):
        """Special case of binding to on_message

        Creates a special handler that checks the user's executing privileges
        for the command.
        """
        async def handler_on_command(message, argstr):
            # Check privilege if needed
            if privileged or hidden:
                authorized = self.privcheck.has_privilege(message.author)
                if not authorized and hidden:
                    return
                return defaultmsgs.UNAUTHORIZED
            return await coro(message, argstr)
        self.commands[keyword] = handler_on_command

            
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
        elif message.content.startswith(self.bot_prefix):
            # Remove leading bot_prefix; split into command and argstr
            text = message.content.replace(self.bot_prefix, '')
            keyword, *argstr = text.split(None, maxsplit=1)
            argstr = argstr[0] if argstr else ''

            # Check for valid command, trigger on_command
            handler = self.commands.get(keyword.strip())
            if handler:
                responses.append(await handler(message, argstr))
                responses.extend(
                    await self.trigger_event('on_command', keyword, message))
                
            # Handle invalid command
            else:
                fargs = dict(prefix=self.bot_prefix, command=command)
                msg = defaultmsgs.INVALID_COMMAND.format(**fargs)
                responses.append(Response(msg))
                responses.extend(
                    await self.trigger_event('on_invalid_command', keyword))
            
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
        ).format(client.user.name, client.user.id)
        print(msg)
        await self.trigger_event('on_ready')
        await self.set_now_playing(appconfig.NOW_PLAYING)


    def attach_proxy_callback(self, event_name):
        """Attaches a 'proxy' callback_on_event to the given event_name

        The discordpy package identifies which event to binds callbacks to 
        using the callback's __name__ attribute. 

        This function creates a 'proxy' callback coro, updates its __name__ 
        attribute to the event_name, then attaches it to the client using 
        client.event()
        """
        async def callback_on_event(*evtargs, **evtkwargs):
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


    def start(self):
        # Register custom event handlers
        for event in DISCORDPY_EVENTS + CUSTOM_EVENTS:
            callback = getattr(self, event)
            if callback:
                self.client.event(callback)

            elif self.event_handlers[event]:
                attach_proxy_callback(event)

        client.run(environment.DISCORD)