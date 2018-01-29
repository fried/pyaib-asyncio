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

from . import AsyncBase
from .. import events
from .. import irc


class ManagerTests(AsyncBase):

    def setUp(self) -> None:
        super().setUp()
        self.irc_c = irc.Context()
        self.em = events.Manager(self.irc_c)

    def test_context_register_and_fire(self):
        called = 0

        async def aobserver(*args, **kws) -> None:
            nonlocal called
            called += 1

        def observer(*args, **kws) -> None:
            nonlocal called
            called += 1

        async def inner_test():
            async with self.em as em:
                em('TEST_EVENT').observe(aobserver).observe(observer)
                await em['TEST_EVENT'](self.irc_c)
                self.assertEqual(called, 2)
                self.assertIsInstance(self.em['OTHER_EVENT'], events.NullEvent)
                self.assertFalse('OTHER_EVENT' in em)
                self.assertTrue('TEST_EVENT' in em)
                self.assertEqual(['test_event'], list(self.em))

        self.loop.run_until_complete(inner_test())


