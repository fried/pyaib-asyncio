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
import time
import typing
import unittest
import unittest.mock

from .. import tasks


async def fast_task() -> None:
    return None


async def slower_task() -> None:
    await asyncio.sleep(1)


async def toolong_task() -> None:
    await asyncio.sleep(2.1)


async def raises_task() -> None:
    raise Exception


class ManagerTests(unittest.TestCase):
    loop: asyncio.AbstractEventLoop
    existing_tasks: typing.Set[asyncio.Task]

    def setUp(self) -> None:
        self.loop = asyncio.get_event_loop()
        self.existing_tasks = asyncio.Task.all_tasks()
        self.tm = tasks.Manager(2, 0.1)

    def tearDown(self) -> None:
        import gc

        new_tasks = asyncio.Task.all_tasks() - self.existing_tasks
        self.assertEqual(set(), new_tasks, "Left over tasks")
        self.existing_tasks = set()

    def test_add_and_service(self) -> None:
        async def inner_test() -> None:
            self.tm.add(fast_task())
            self.tm.add(slower_task())
            self.tm.add(toolong_task())
            self.tm.add(raises_task())
            self.assertEqual(len(self.tm), 4)
            await asyncio.sleep(0)
            self.tm.service()   # The fast_task should be gone by now.
            await asyncio.sleep(0)
            self.assertEqual(len(self.tm), 2)
            await self.tm.cancel_all()

        self.loop.run_until_complete(inner_test())

    def test_cancel(self) -> None:
        async def inner_test() -> None:
            t = self.tm.add(toolong_task())
            await asyncio.sleep(0)  # let loop run
            now = time.time()
            with unittest.mock.patch('pyaib.tasks.time') as tmock:
                tmock.time.return_value = now + 5
                self.tm.service()
                self.assertTrue(tmock.time.called)
            self.assertTrue(t.cancelled)
            await self.tm.cancel_all()

        self.loop.run_until_complete(inner_test())

    @unittest.mock.patch('pyaib.tasks.Manager.service')
    def test_auto_service(self, smock) -> None:
        self.tm.auto_service()
        self.assertTrue(smock.called)

        async def inner_test() -> None:
            await asyncio.sleep(0.5)
            self.assertEqual(smock.call_count, 5)
            self.tm.stop()
            await asyncio.sleep(0)
            self.assertEqual(smock.call_count, 5)

        self.loop.run_until_complete(inner_test())
