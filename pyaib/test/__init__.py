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
import unittest


class AsyncBase(unittest.TestCase):

    def setUp(self) -> None:
        self.loop = asyncio.get_event_loop()
        self.existing_tasks = asyncio.Task.all_tasks()

    def tearDown(self) -> None:
        new_tasks = asyncio.Task.all_tasks() - self.existing_tasks
        self.assertEqual(set(), new_tasks, "Left over tasks")
        self.existing_tasks = set()