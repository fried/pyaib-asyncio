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
import collections.abc
import heapq
import inspect
import logging
import time
import typing

from . import irc
from . import tasks

ONE_DAY = 3600 * 24
logger = logging.getLogger(__name__)


class Timer:
    """A Single Timer"""
    # message = Message That gets passed to the callable
    # at = Time when trigger will ring
    # every = How long to push the 'at' time after timer rings
    # count = Number of times the timer will fire before clearing
    # callable = a callable object
    expired: bool
    message: str
    at: float
    every: typing.Optional[float]
    count: typing.Optional[int]

    def __init__(
        self,
        message: str,
        callable: typing.Callable,
        at: typing.Optional[float]=None,
        every: typing.Optional[float]=None,
        count: typing.Optional[int]=None,
    ) -> None:
        self.expired = False
        self.message = message
        if at is None:
            self.at = time.time()
            if every:
                self.at += every
        else:
            self.at = at
        self.count = count
        self.every = every
        self.callable = callable
        if count is not None and count < 1:
            raise ValueError('This timer will never run when count < 1')

        if not isinstance(callable, collections.Callable):  # type: ignore
            raise TypeError('{callable!r} is not callable')

    def __bool__(self) -> bool:
        return not self.expired

    def reset(self) -> None:
        if self.every:
            self.at = time.time() + self.every
            if self.count:
                self.count -= 1
                if self.count <= 1:
                    self.expire()
        else:
            self.expire()

    def expire(self) -> None:
        self.expired = True

    # Ring Check
    def __call__(
        self, timestamp: float, irc_c: irc.Context
    ) -> typing.Optional[typing.Awaitable]:

        try:
            result = self.callable(irc_c, self.message)
        except Exception:
            logger.exception(
                f'Timer({self.message}, {self.callable}) raised exception'
            )

        self.reset()
        if result and inspect.isawaitable(result):  # Awaitable
            return result
        return None

    # To be sortable
    def __lt__(self, other: 'Timer') -> bool:
        return self.at < other.at


class Manager(object):
    """ A Timers Manager """
    _heapq: typing.List[Timer]
    _tasks: tasks.Manager
    _loop: asyncio.AbstractEventLoop
    _handle: typing.Optional[asyncio.Handle] = None
    irc_c: irc.Context

    def __init__(self, context):
        self._heapq = []
        self._tasks = tasks.Manager()
        self._loop = asyncio.get_event_loop()
        self.irc_c = context

    async def __aenter__(self) -> "Manager":
        self._tasks.auto_service()
        return self

    async def __aexit__(self, *args: typing.Any) -> None:
        self._cancel_alarm()
        self._tasks.cancel_all()
        self._tasks.stop()

    def _cancel_alarm(self) -> None:
        if self._handle is not None:
            self._handle.cancel()

    def _set_alarm(self) -> None:
        if not self._heapq:
            self._cancel_alarm()
        next_timer = self._heapq[0].at
        self._cancel_alarm()
        self._handle = self._loop.call_at(min(next_timer, ONE_DAY), self._alarm)

    def _alarm(self) -> None:
        irc_c = self.irc_c
        poped_timers: typing.List[Timer] = []
        if time.time() >= self._heapq[0].at:
            try:
                while True:
                    now = time.time()
                    if not now >= self._heapq[0].at:
                        break
                    timer = heapq.heappop(self._heapq)
                    poped_timers.append(timer)
                    if not timer:
                        continue
                    task = timer(now, irc_c)
                    if task:
                        self._tasks.add(task)
            except IndexError:
                # We can move on, we have run through all the timers
                pass

        for timer in poped_timers:
            if timer:
                heapq.heappush(self._heapq, timer)

        self._set_alarm()

    def set(self, *args, **keywargs) -> bool:
        timer = Timer(*args, **keywargs)
        if timer:
            heapq.heappush(self._heapq, timer)
            self._set_alarm()
        return bool(timer)

    def reset(self, message: str, callable: typing.Callable) -> None:
        rebuild = True
        for timer in self._heapq:
            if timer.message == message and timer.callable == callable:
                timer.reset()
                rebuild = True
        if rebuild:
            heapq.heapify(self._heapq)

    def clear(self, message: str, callable: typing.Callable) -> None:
        for timer in self._heapq:
            if timer.message == message and timer.callable == callable:
                timer.expire()

    def __len__(self) -> int:
        return len(self._heapq)
