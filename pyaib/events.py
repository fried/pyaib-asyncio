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
import inspect
import logging
import typing

from . import tasks
from . import irc

__all__ = ['Event', 'Manager']
logger = logging.getLogger(__name__)
observerT = typing.Union[
    typing.Callable[..., None],
    typing.Callable[..., typing.Awaitable[None]]
]


class Event:
    """ An AsyncIO Event Handler
        Events can be observed or even awaited for the next fire.
        observing means we will (await) call a callable every time it fires.
    """
    name: str
    _manager: "Manager"
    _observers: typing.List[observerT]
    _waiter: typing.Optional[asyncio.Future] = None
    _waiter_once: typing.Optional[asyncio.Future] = None

    def __init__(self, name: str, manager: "Manager") -> None:
        self.name = name
        self._manager = manager
        self._observers = []

    def observe(self, observer: observerT):
        if isinstance(observer, collections.abc.Callable):  # type: ignore
            self._observers.append(observer)
        else:
            logger.error(f'Event Error: {observer!r} not callable')
        return self

    def unobserve(self, observer: observerT):
        self._observers.remove(observer)
        return self

    async def fired_once(self) -> None:
        if self._waiter_once is None:
            self._waiter_once = self._waiter or self._get_waiter()
        return await self._waiter_once

    async def wait(self) -> None:
        return await self._get_waiter()

    def _get_waiter(self) -> asyncio.Future:
        if self._waiter is None or self._waiter.done():
            self._waiter = asyncio.get_event_loop().create_future()
        return self._waiter

    def _clear_waiter(self, cancel: bool=False) -> None:
        if self._waiter is not None and not self._waiter.done():
            if cancel:
                self._waiter.cancel()
            else:
                self._waiter.set_result(None)

    def fire(self, irc_c: irc.Context, *args, **kws) -> asyncio.Task:
        """ call all the observers, return the gathered tasks """
        if not isinstance(irc_c, irc.Context):
            raise TypeError('Error first argument should be the irc context')

        coros: typing.List[typing.Awaitable[None]] = []
        for observer in self._observers:
            try:
                result = observer(irc_c, *args, **kws)
            except Exception:
                logger.exception(
                    f'Event({self.name}) observer raised exception: {observer!r}'
                )
                continue

            if result and inspect.isawaitable(result):  # awaitable.
                coros.append(result)

        if not coros:
            gather = asyncio.get_event_loop().create_future()
            gather.set_result(None)
        elif len(coros) > 1:
            gather = asyncio.gather(*coros, return_exceptions=True)

            def log_exceptions(
                fn: "asyncio.Future[typing.List[typing.Optional[Exception]]]"
            ) -> None:
                if fn.cancelled():
                    return
                for result, coro in zip(fn.result(), coros):
                    if not isinstance(result, Exception):
                        continue
                    if isinstance(result, asyncio.CancelledError):
                        continue
                    logger.error(
                        f'Event({self.name}) observer raised '
                        f'exception: {coro!r} {result!r}'
                    )

            gather.add_done_callback(log_exceptions)
        else:
            gather = coros[0]
        t = self._manager._tasks.add(gather)
        t.add_done_callback(lambda x: self._clear_waiter())
        return gather

    def clearObjectObservers(self, inObject: typing.Any) -> None:
        for observer in self._observers:
            if hasattr(observer, '__self__') and observer.__self__ == inObject:  # type: ignore
                self.unobserve(observer)

    def getObserverCount(self) -> int:
        return len(self._observers)

    def observers(self) -> typing.Iterable[observerT]:
        return iter(self._observers)

    def __bool__(self) -> bool:
        return self.getObserverCount() > 0

    __iadd__ = observe
    __isub__ = unobserve
    __call__ = fire
    __len__ = getObserverCount


class NullEvent(Event):
    """ Null Object Pattern: Don't Do Anything Silently"""
    def fire(self, *args, **keywargs):
        pass

    def clearObjectObservers(self, obj):
        pass

    def getObserverCount(self):
        return 0

    def __bool__(self):
        return False

    def observe(self, observer):
        raise TypeError('Null Events can not have Observers!')

    def unobserve(self, observer):
        raise TypeError('Null Events do not have Observers!')


class Manager(object):
    """ Manage events allow observers before events are defined
        This has the very intresting pattern, of returning NullEvents it it
        does not already exist, when using the [] get syntax, so you can fire
        events even though nobody is listening.  But if you use the call
        pattern (), the even is created or returned if it exists.
    """
    _events: typing.Dict[str, Event]
    _nullEvent: NullEvent
    _tasks: tasks.Manager

    def __init__(self, context) -> None:
        self._events = {}
        self._nullEvent = NullEvent('__NullEvent', self)
        self._tasks = tasks.Manager()

    async def __aenter__(self) -> "Manager":
        self._tasks.auto_service()
        return self

    async def __aexit__(self, *args: typing.Any) -> None:
        await self.cancel_all()
        self._tasks.stop()

    async def cancel_all(self) -> None:
        """ reconnects or shutdowns we should clean up all running tasks"""
        for e in self._events.values():
            e._clear_waiter(cancel=True)
        await self._tasks.cancel_all()

    def __iter__(self) -> typing.Iterable[str]:
        return iter(self._events)

    def isEvent(self, name: str) -> bool:
        return name.lower() in self._events

    def getOrMake(self, name: str) -> Event:
        if not self.isEvent(name):
            # Make Event if it does not exist
            self._events[name.lower()] = Event(name.lower(), self)
        return self.get(name)

    # Do not create the event on a simple get
    # Return the null event on non existent events
    def get(self, name: str) -> Event:
        event = self._events.get(name.lower())
        if event is None:  # Only on undefined events
            return self._nullEvent
        return event

    __contains__ = isEvent
    __call__ = getOrMake
    __getitem__ = get
