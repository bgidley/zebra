"""A small recording HTTP proxy for tests (#337).

It listens on an ephemeral 127.0.0.1 port and records every request line a client sends it
(``CONNECT host:443`` for https, ``GET http://host/path`` for plain http), so a test can assert
that a client really went through ``HTTPS_PROXY``.

- By default it answers 403 and records, so a client's real code path runs to its failure.
- ``tunnel_to=(host, port)`` makes it a CONNECT tunnel to that one address whatever the
  client asked for: with a TLS server behind it whose certificate comes from a test CA, it
  behaves like a TLS-inspecting corporate proxy.
- ``http_reply=(status, body)`` answers plain-http proxy requests (absolute-URI form).
"""

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class ProxyRequest:
    """One request line the proxy received."""

    method: str
    target: str

    @property
    def host(self) -> str:
        """The host the client asked for, without scheme, port or path."""
        target = self.target.split("://", 1)[-1].split("/", 1)[0]
        return target.rsplit(":", 1)[0] if ":" in target else target


class RecordingProxy:
    """Records requests; refuses, tunnels or answers them as configured."""

    def __init__(
        self,
        tunnel_to: tuple[str, int] | None = None,
        http_reply: tuple[int, bytes] | None = None,
    ):
        self.requests: list[ProxyRequest] = []
        self.tunnel_to = tunnel_to
        self.http_reply = http_reply
        self._server: asyncio.Server | None = None
        self.port = 0

    @property
    def url(self) -> str:
        """The proxy's URL, for ``HTTPS_PROXY``."""
        return f"http://127.0.0.1:{self.port}"

    @property
    def connects(self) -> list[str]:
        """The ``host:port`` of every CONNECT received."""
        return [r.target for r in self.requests if r.method == "CONNECT"]

    async def start(self) -> None:
        """Start listening on an ephemeral loopback port."""
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Stop listening."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            lines = head.decode("latin-1").split("\r\n")
            method, target, _version = lines[0].split(" ", 2)
            self.requests.append(ProxyRequest(method, target))
            if method == "CONNECT" and self.tunnel_to is not None:
                await self._tunnel(reader, writer)
            elif method != "CONNECT" and self.http_reply is not None:
                await self._drain_body(reader, lines)
                status, body = self.http_reply
                writer.write(
                    f"HTTP/1.1 {status} X\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
                    + body
                )
            else:
                writer.write(
                    b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, ValueError):
            pass
        finally:
            writer.close()

    @staticmethod
    async def _drain_body(reader: asyncio.StreamReader, lines: list[str]) -> None:
        for line in lines:
            if line.lower().startswith("content-length:"):
                await reader.readexactly(int(line.split(":", 1)[1]))

    async def _tunnel(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        assert self.tunnel_to is not None
        up_reader, up_writer = await asyncio.open_connection(*self.tunnel_to)
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()

        async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
            try:
                while data := await src.read(65536):
                    dst.write(data)
                    await dst.drain()
            except ConnectionError:
                pass
            finally:
                dst.close()

        await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))
