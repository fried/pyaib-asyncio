#!/usr/bin/env python3
#
# Copyright 2018 Facebook
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

from abc import abstractmethod, ABCMeta
import enum
import typing

from .util import data

_Ts = typing.TypeVar('_Ts', bound='Source')
MSG_TYPE = typing.Union[str, typing.Iterable[str]]


class Status(enum.Enum):
    disconnected = enum.auto()
    connecting = enum.auto()
    connected = enum.auto()
    reconnecting = enum.auto()


class Source(metaclass=ABCMeta):
    context: data.Object
    status: Status = Status.disconnected
    name: str
    type: str

    def __init__(self, name: str) -> None:
        self.name = name
        self.context = data.Object()

    @abstractmethod
    async def __aenter__(self: _Ts) -> _Ts:
        """ Async Intialize this source"""
        pass

    @abstractmethod
    async def __aexit__(self, *args: typing.Any) -> None:
        """ Async Shutdown of this source"""
        pass

    @abstractmethod
    async def nick(self, nick: str):
        pass

    @abstractmethod
    async def privmsg(self, target: str, text: MSG_TYPE) -> None:
        pass

    @abstractmethod
    async def notice(self, target: str, text: MSG_TYPE) -> None:
        pass

    @abstractmethod
    async def join(self, channels: MSG_TYPE) -> None:
        pass

    @abstractmethod
    async def part(self, channels: MSG_TYPE, msg: MSG_TYPE) -> None:
        pass


class MetaSource(Source):
    pass


class Manager:
    sources: typing.Dict[str, Source]
    by_type: typing.Dict[str, typing.List[Source]]

    def __init__(self) -> None:


