# Copyright (C) Dnspython Contributors, see LICENSE for text of ISC license

"""asyncio library query support"""

import socket
import asyncio

import dns._asyncbackend
import dns.exception

class _DatagramProtocol:
    def __init__(self):
        self.transport = None
        self.recvfrom = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if self.recvfrom:
            self.recvfrom.set_result((data, addr))
            self.recvfrom = None

    def error_received(self, exc):
        if self.recvfrom:
            self.recvfrom.set_exception(exc)

    def connection_lost(self, exc):
        if self.recvfrom:
            self.recvfrom.set_exception(exc)

    def close(self):
        self.transport.close()


async def _maybe_wait_for(awaitable, timeout):
    if timeout:
        try:
            return await asyncio.wait_for(awaitable, timeout)
        except asyncio.TimeoutError:
            raise dns.exception.Timeout(timeout=timeout)
    else:
        return await awaitable

class DatagramSocket(dns._asyncbackend.DatagramSocket):
    def __init__(self, family, transport, protocol):
        self.family = family
        self.transport = transport
        self.protocol = protocol

    async def sendto(self, what, destination, timeout):
        # no timeout for asyncio sendto
        self.transport.sendto(what, destination)

    async def recvfrom(self, timeout):
        done = asyncio.get_running_loop().create_future()
        assert self.protocol.recvfrom is None
        self.protocol.recvfrom = done
        await _maybe_wait_for(done, timeout)
        return done.result()

    async def close(self):
        self.protocol.close()

    async def getpeername(self):
        return self.transport.get_extra_info('peername')


class StreamSocket(dns._asyncbackend.DatagramSocket):
    def __init__(self, af, reader, writer):
        self.family = af
        self.reader = reader
        self.writer = writer

    async def sendall(self, what, timeout):
        self.writer.write(what),
        return await _maybe_wait_for(self.writer.drain(), timeout)
        raise dns.exception.Timeout(timeout=timeout)

    async def recv(self, count, timeout):
        return await _maybe_wait_for(self.reader.read(count),
                                     timeout)
        raise dns.exception.Timeout(timeout=timeout)

    async def close(self):
        self.writer.close()
        await self.writer.wait_closed()

    async def getpeername(self):
        return self.reader.get_extra_info('peername')


class Backend(dns._asyncbackend.Backend):
    def name(self):
        return 'asyncio'

    async def make_socket(self, af, socktype, proto=0,
                          source=None, destination=None, timeout=None,
                          ssl_context=None, server_hostname=None):
        loop = asyncio.get_running_loop()
        if socktype == socket.SOCK_DGRAM:
            transport, protocol = await loop.create_datagram_endpoint(
                _DatagramProtocol, source, family=af,
                proto=proto)
            return DatagramSocket(af, transport, protocol)
        elif socktype == socket.SOCK_STREAM:
            (r, w) = await _maybe_wait_for(
                asyncio.open_connection(destination[0],
                                        destination[1],
                                        family=af,
                                        proto=proto,
                                        local_addr=source),
                timeout)
            return StreamSocket(af, r, w)
        raise NotImplementedError(f'unsupported socket type {socktype}')

    async def sleep(self, interval):
        await asyncio.sleep(interval)