import asyncio

from app.services import SystemState, TcpMotorProvider


async def _publish(_: dict) -> None:
    return None


async def _controller(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while line := await reader.readline():
            command = line.decode("ascii").strip().upper()
            if command == "PING":
                reply = "PONG\r\n"
            elif command == "STATUS":
                reply = "OK:POS=0;ALM=0;RDY=1\r\n"
            elif command.startswith("WATCH "):
                reply = "OK:WATCH 100ms\r\nPOS:0.00mm\r\n"
            elif command.startswith("MOVE "):
                target = command.split()[1]
                reply = f"POS:{target}mm\r\nOK:MOVE {target}\r\n"
            elif command == "STOP":
                reply = "OK:STOP\r\n"
            elif command == "UNWATCH":
                reply = "OK:UNWATCH\r\n"
            else:
                reply = "ERR:UNKNOWN_CMD\r\n"
            writer.write(reply.encode("ascii"))
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def _exercise_tcp_provider() -> None:
    server = await asyncio.start_server(_controller, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    machine = {
        "homePosition": "P1",
        "positionsMm": {"P1": 0, "P2": 1250},
        "network": {"host": "127.0.0.1", "port": port, "watchIntervalMs": 100, "commandTimeoutMs": 500, "moveTimeoutMs": 500},
    }
    provider = TcpMotorProvider(SystemState(), machine, _publish)
    try:
        await provider.initialize()
        assert await provider.ping() == "PONG"
        assert await provider.move_to("P2") is True
        assert provider.last_position_mm == 1250
        await provider.stop()
    finally:
        await provider.dispose()
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(_exercise_tcp_provider())
    print("TCP motor protocol smoke test passed")
