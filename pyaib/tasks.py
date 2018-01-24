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

import asyncio
import contextlib
import io
import logging
import time
import typing


__all__ = ['Manager']
logger = logging.getLogger(__name__)


class Manager(typing.Sized):
    """ Manage a set of tasks, so we can make sure they don't run too long """
    _tasks: typing.Dict[asyncio.Task, float]
    _ttl: float
    _service_every: float
    _loop: asyncio.AbstractEventLoop
    _handle: asyncio.Handle

    def __init__(self, ttl: float=300, service_every: float=60) -> None:
        self._tasks = {}
        self._ttl = ttl
        self._service_every = service_every
        self._loop = asyncio.get_event_loop()

    def auto_service(self) -> None:
        """ Runs Service every 60s """
        self.service()
        self._handle = self._loop.call_later(
            self._service_every,
            self.auto_service
        )

    def stop(self) -> None:
        """ Stop the auto_service handler """
        self._handle.cancel()

    def service(self) -> None:
        """ Service the task list """
        now = time.time()
        ttl = self._ttl
        with contextlib.ExitStack() as stack:
            for t, ctime in self._tasks.items():
                if t.done():
                    stack.callback(self._tasks.pop, t)
                    if t.cancelled():
                        logger.debug(f'Task was canceled: {t}')
                        continue
                    exc = t.exception()
                    if exc is None:
                        t.result()
                    else:
                        with io.StringIO() as f:
                            t.print_stack(file=f)
                            logger.info(f'Task had an error: {t} {exc!r}\n{f.getvalue()}')
                elif now - ctime > ttl:
                    t.cancel()

    async def cancel_all(self) -> None:
        """ Cancel all the tasks """
        for t in tuple(self._tasks.keys()):
            t.cancel()
        await asyncio.sleep(0)
        self.service()
        await asyncio.sleep(0)

    def add(self, coro: typing.Awaitable[None]) -> asyncio.Task:
        """ Take an awaitable, schedule it and return the task """
        now = time.time()
        task = self._loop.create_task(coro)
        self._tasks[task] = now
        return task

    def __len__(self) -> int:
        return len(self._tasks)
