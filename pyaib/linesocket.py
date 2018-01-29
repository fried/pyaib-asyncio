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
"""
Line based asyncio socket impl
"""
import asyncio
import ssl
from types import TracebackType
import typing


LINEENDING = b'\r\n'
SSL_TYPE = typing.Union[ssl.SSLContext, bool]


class LineSocket:
    """ Asyncio Friendly LineSocket """
    host: str
    port: int
    ssl: SSL_TYPE
    _rstream: asyncio.StreamReader
    _wstream: asyncio.StreamWriter
    _in_context: bool

    def __init__(
        self,
        *,
        host: str,
        port: int,
        ssl: SSL_TYPE=False,
    ) -> None:
        self.host = host
        self.port = port
        self.ssl = ssl
        self._in_context = False

    async def __aenter__(self) -> 'LineSocket':
        if self._in_context:
            raise asyncio.InvalidStateError
        self._rstream, self._wstream = await asyncio.open_connection(
            host=self.host,
            port=self.port,
            ssl=self.ssl,
        )
        self._in_context = True
        # Read through for reasons
        # https://vorpus.org/blog/some-thoughts-on-asynchronous-api-design-in-a-post-asyncawait-world/
        typing.cast(
            asyncio.WriteTransport,
            self._wstream.transport
        ).set_write_buffer_limits(low=0, high=0)
        return self

    async def __aexit__(
        self,
        exc_type: typing.Optional[typing.Type[BaseException]],
        value: typing.Optional[Exception],
        traceback: typing.Optional[TracebackType]
    ) -> typing.Optional[bool]:
        if not self._in_context:
            raise asyncio.InvalidStateError
        await self._drain()
        self._wstream.close()
        await asyncio.sleep(0)
        self._in_context = False
        del self._wstream
        del self._rstream
        return None

    async def _drain(self, fatal: bool=False) -> None:
        try:
            await self._wstream.drain()
        except ConnectionResetError:
            if fatal:
                raise

    async def readline(self) -> bytes:
        if self._rstream.at_eof():
            raise EOFError
        await self._drain()
        # Strip off the LINEENDING we don't need it anymore
        return (await self._rstream.readuntil(LINEENDING))[:-2]

    async def writeline(self, line: bytes) -> None:
        self._wstream.write(line + LINEENDING)
        await self._drain(fatal=True)

    def writelines(
        self,
        lines: typing.Iterable[bytes]
    ) -> typing.Awaitable[None]:
        return self.writeline(LINEENDING.join(lines))
