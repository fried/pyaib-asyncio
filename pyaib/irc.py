#!/usr/bin/env python3
#
# Copyright 2013-current Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import asyncio
import logging
import re
import sys
from textwrap import wrap
import time
import typing

from .linesocket import LineSocket
from .util import data
from . import __version__ as pyaib_version


MAX_LENGTH = 510
logger = logging.getLogger(__name__)
UNCLEAN_MSG_TYPE = typing.Union[str, typing.Iterable[str]]


def clean_msg(self, msg: UNCLEAN_MSG_TYPE) -> str:
    if not isinstance(msg, str):
        msg = ' '.join(msg)
    msg = re.sub(r'[\r\n]', '', msg).expandtabs(4).rstrip()
    return msg


class Context(data.Object):
    """Dummy Object to hold irc data and send messages"""
    # IRC COMMANDS are all CAPS for sanity with irc information
    # TODO: MOVE irc commands into component and under irc_c.cmd

    # Raw IRC Message
    async def RAW(self, message: UNCLEAN_MSG_TYPE) -> None:
        try:
            message = clean_msg(message)
            if len(message):
                await self.client.socket.writeline(message.encode('utf-8'))
                # Fire raw send event for debug if exists [] instead of ()
                self.events['IRC_RAW_SEND'](self, message)
        except TypeError:
            # Somebody tried to raw a None or something just print exception
            logger.exception(f'Bad RAW message: {message!r}')

    # Set our nick
    async def NICK(self, nick) -> None:
        await self.RAW(f'NICK {nick}')
        # TODO: WE Should have a way to await the nick response event

        if not self.registered:
            # Assume we get the nick we want during registration
            self.botnick = nick

    # privmsg/notice with max line handling
    async def PRIVMSG(self, target: str, msg: UNCLEAN_MSG_TYPE) -> None:
        try:
            msg = clean_msg(msg)
            lines = self._wrap_command('PRIVMSG', target, msg)
            await self.client.socket.writelines(lines)
        except TypeError:
            logger.exception(f'Bad PRIVMSG message: {msg!r}')

    async def NOTICE(self, target: str, msg: UNCLEAN_MSG_TYPE) -> None:
        try:
            msg = clean_msg(msg)
            lines = self._wrap_command('NOTICE', target, msg)
            await self.client.socket.writelines(lines)
        except TypeError:
            logger.exception(f'Bad NOTICE message: {msg!r}')

    def _wrap_command(self, command: str, target: str, msg: str) -> bytes:
        msgtemplate = f'{command} {target} :'
        # length of self.botsender.raw is 0 when not set :P
        # + 2 because of leading : and space after nickmask
        prefix_length = len(self.botsender.raw) + 2 + len(msgtemplate)
        for line in wrap(msg, MAX_LENGTH - prefix_length):
            yield f'{msgtemplate}{line}'.encode('utf-8')

    async def JOIN(
        self,
        channels: typing.Union[typing.Iterable[str], str]
    ) -> None:
        # TODO: this could block until the join completes
        if isinstance(channels, str):
            channels = channels.split(',')

        join = 'JOIN '
        msg = join

        # Build up join messages (wrap won't work)
        lines = []
        for channel in channels:
            channel = channel.strip()
            new_msg = f'{msg}{channel}' if msg is join else f'{msg},{channel}'
            if len(new_msg) > MAX_LENGTH:
                if msg is join:
                    raise ValueError(f'{channel!r} name is too long')
                lines.append(msg)
                new_msg = f'{join}{channel}'
            msg = new_msg

        lines.append(msg)
        await self.client.socket.writelines(lines)

    async def PART(
        self,
        channels: typing.Union[typing.Iterable[str], str],
        message: str=None
    ) -> None:
        if not isinstance(channels, str):
            channels = ','.join(channels)
        if message:
            await self.RAW(f'PART {channels} :{message}')
        else:
            await self.RAW(f'PART {channels}')


class Client(object):
    """IRC Client contains irc logic"""
    def __init__(self, irc_c):
        self.config = irc_c.config.irc
        self.servers = self.config.servers
        self.irc_c = irc_c
        irc_c.client = self
        self.reconnect = True
        self.__register_client_hooks(self.config)

    # The IRC client Event Loop
    # Call events for every irc message
    def _try_connect(self):
        for server in self.servers:
            host, port, ssl = self.__parseserver(server)
            sock = LineSocket(host, port, SSL=ssl)
            if sock.connect():
                self.socket = sock
                return sock
        return None

    def _fire_msg_events(self, sock, irc_c):
        while True:  # Event still running
            raw = sock.readline()  # Yield
            if raw:
                # Fire RAW MSG if it has observers
                irc_c.events['IRC_RAW_MSG'](irc_c, raw)
                # Parse the RAW message
                msg = Message(irc_c, raw)
                if msg:  # This is a valid message
                    # So we can do length calculations for PRIVMSG WRAPS
                    if (msg.nick == irc_c.botnick
                            and irc_c.botsender != msg.sender):
                        irc_c.botsender = msg.sender
                    # Event for kind of message [if exists]
                    eventKey = 'IRC_MSG_%s' % msg.kind
                    irc_c.events[eventKey](irc_c, msg)
                    # Event for parsed messages [if exists]
                    irc_c.events['IRC_MSG'](irc_c, msg)

    async def start(self):
        irc_c = self.irc_c

        # Function to Fire Timers
        # TODO: Re-write timers using asyncio and a heapq
        def _timers(irc_c):
            print("Starting Timers Loop")
            while True:
                # gevent.sleep(1)
                irc_c.timers(irc_c)

        # If servers is not a list make it one
        if isinstance(self.servers, str):
            self.servers = self.servers.split(',')
        server_list = iter(self.servers)
        while self.reconnect:
            try:
                server = next(server_list)
            except StopIteration:
                logger.info("Retrying Server List in 10s...")
                asyncio.sleep(10)
                server_list = iter(self.servers)
                continue

            try:
                async with LineSocket(**self.__parseserver(server)) as sock:
                    # Fire Socket Connect Event (Always)
                    irc_c.events('IRC_SOCKET_CONNECT')(irc_c)
                    # Start Timers
                    # Fire events
                    await self._fire_msg_events(sock, irc_c)
            except OSError:
                # propigate a reconnect exception to all event waiters
                # cancel all tasks belonging to the bot
                # stop timers
                # gather all tasks
                logger.exception('Error creating Socket, going to reconnect')
        else:
            logger.info("Bot Dying.")

    async def die(self, message="Dying"):
        await self.irc_c.RAW(f'QUIT :{message}')
        self.reconnect = False

    async def cycle(self):
        await self.irc_c.RAW('QUIT :Reconnecting')

    async def signal_handler(self):
        """ Handle Ctrl+C """
        await self.irc_c.RAW("QUIT :Received a ctrl+c exiting")
        self.reconnect = False

    # Register our own hooks for basic protocol handling
    def __register_client_hooks(self, options):
        events = self.irc_c.events
        timers = self.irc_c.timers

        # AUTO_PING TIMER
        async def AUTO_PING(irc_c, msg):
            await irc_c.RAW(f'PING :{irc_c.server}')

        # if auto_ping unless set to 0
        if options.auto_ping != 0:
            timers.set('AUTO_PING', AUTO_PING,
                       every=options.auto_ping or 600)

        # Handle PINGs
        async def PONG(irc_c, msg):
            await irc_c.RAW(f'PONG :{msg.args}')
            # On a ping from the server reset our timer for auto-ping
            timers.reset('AUTO_PING', AUTO_PING)
        events('IRC_MSG_PING').observe(PONG)

        # On the socket connecting we should attempt to register
        async def REGISTER(irc_c):
            irc_c.registered = False
            if options.password:  # Use a password if one is issued
                # TODO allow password to be associated with server url
                await irc_c.RAW(f'PASS {options.password}')
            realname = options.realname.format(version=pyaib_version)
            await irc_c.RAW(f'USER {options.user} 8 * :{realname}')
            await irc_c.NICK(options.nick)
        events('IRC_SOCKET_CONNECT').observe(REGISTER)

        # Trigger an IRC_ONCONNECT event on 001 msg's
        async def ONCONNECT(irc_c, msg):
            irc_c.server = msg.sender
            irc_c.registered = True
            irc_c.events('IRC_ONCONNECT')(irc_c)
        events('IRC_MSG_001').observe(ONCONNECT)

        def NICK_INUSE(irc_c, msg):
            if not irc_c.registered:
                irc_c.NICK('%s_' % irc_c.botnick)
            _, nick, _ = msg.args.split(' ', 2)
            #Fire event for other modules [if its watched]
            irc_c.events['IRC_NICK_INUSE'](irc_c, nick)
        events('IRC_MSG_433').observe(NICK_INUSE)

        #When we change nicks handle botnick updates
        def NICK(irc_c, msg):
            if msg.nick.lower() == irc_c.botnick.lower():
                irc_c.botnick = msg.args
            irc_c.events['IRC_NICK_CHANGE'](irc_c, msg.nick, msg.args)
        events('IRC_MSG_NICK').observe(NICK)

    #Parse Server Records
    # (ssl:)?host(:port)? // after ssl: is optional
    # TODO allow password@ in server strings
    def __parseserver(self, server):
        match = re.search(r'^(ssl:(?://)?)?([^:]+)(?::(\d+))?$',
                          server.lower())
        if match is None:
            print('BAD Server String: %s' % server)
            sys.exit(1)
        #Pull out the pieces of the server line
        ssl = match.group(1) is not None
        host = match.group(2)
        port = int(match.group(3)) or 6667
        return [host, port, ssl]


class Message (object):
    """Parse raw irc text into easy to use class"""

    MSG_REGEX = re.compile(r'^(?::([^ ]+) )?([^ ]+) (.+)$')
    DIRECT_REGEX = re.compile(r'^([^ ]+) :?(.+)$')

    #Some Message prefixes for channel prefixes
    PREFIX_OP = 1
    PREFIX_HALFOP = 2
    PREFIX_VOICE = 3

    # Place to store parsers for complex message types
    _parsers = {}

    @classmethod
    def add_parser(cls, kind, handler):
        cls._parsers[kind] = handler

    @classmethod
    def get_parser(cls, kind):
        return cls._parsers.get(kind)

    def copy(self, irc_c):
        return type(self)(irc_c, self.raw)

    def __init__(self, irc_c, raw):
        self.raw = raw
        match = Message.MSG_REGEX.search(raw)
        if match is None:
            self._error_out('IRC Message')

        #If the prefix is blank its the server
        self.sender = Sender(match.group(1) or irc_c.server)
        self.kind = match.group(2)
        self.args = match.group(3)
        self.nick = self.sender.nick

        #Time Stamp every message (Floating Point is Fine)
        self.timestamp = time.time()

        #Handle more message types
        if self.kind in Message._parsers:
            Message._parsers[self.kind](self, irc_c)

        #Be nice strip off the leading : on args
        self.args = re.sub(r'^:', '', self.args)

    def _error_out(self, text):
        print('BAD %s: %s' % (text, self.raw))
        self.kind = None

    def __bool__(self):
        return self.kind is not None

    __nonzero__ = __bool__

    def __str__(self):
        return self.raw

    #Friendly get that doesnt blow up on non-existent entries
    def __getattr__(self, key):
        return None

    @staticmethod
    def _directed_message(msg, irc_c):
        match = Message.DIRECT_REGEX.search(msg.args)
        if match is None:
            return msg._error_out('PRIVMSG')
        msg.target = match.group(1).lower()
        msg.message = match.group(2)

        #If the target is not the bot its a channel message
        if msg.target != irc_c.botnick:
            msg.reply_target = msg.target
            #Strip off any message prefixes
            msg.raw_channel = msg.target.lstrip('@%+')
            msg.channel = msg.raw_channel.lower()  # Normalized to lowercase
            #Record the perfix
            if msg.target.startswith('@'):
                msg.channel_prefix = msg.PREFIX_OP
            elif msg.target.startswith('%'):
                msg.channel_prefix = msg.PREFIX_HALFOP
            elif msg.target.startswith('+'):
                msg.channel_prefix = msg.PREFIX_VOICE
        else:
            msg.reply_target = msg.nick

        #Setup a reply method
        def __reply(text):
            irc_c.PRIVMSG(msg.reply_target, text)
        msg.reply = __reply


#Install some common parsers
Message.add_parser('PRIVMSG', Message._directed_message)
Message.add_parser('NOTICE', Message._directed_message)
Message.add_parser('INVITE', Message._directed_message)
Message.add_parser('TOPIC', Message._directed_message)


class Sender(str):
    """all the logic one would need for understanding sender part of irc msg"""
    def __new__(cls, sender):
        #Pull out each of the pieces at instance time
        if '!' in sender:
            nick, _, usermask = sender.partition('!')
            inst = str.__new__(cls, nick)
            inst._user, _, inst._hostname = usermask.partition('@')
            return inst
        else:
            return str.__new__(cls, sender)

    @property
    def raw(self):
        """ get the raw sender string """
        if self.nick:
            return '%s!%s@%s' % (self, self._user, self._hostname)
        else:
            return self

    @property
    def nick(self):
        """ get the nick """
        if hasattr(self, '_hostname'):
            return self

    @property
    def user(self):
        """ get the user name """
        if self.nick:
            return self._user.lstrip('~')

    @property
    def hostname(self):
        """ get the hostname """
        if self.nick:
            return self._hostname
        else:
            return self

    @property
    def usermask(self):
        """ get the usermask user@hostname """
        if self.nick:
            return '%s@%s' % (self._user, self._hostname)
