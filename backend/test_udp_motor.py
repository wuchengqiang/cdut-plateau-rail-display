"""Loopback-only UDP protocol and concurrent playback regression tests."""
import asyncio
import socket

from app.services import MotorProtocolError, SystemState, UdpMotorProvider, MediaService, SceneService


class Controller(asyncio.DatagramProtocol):
    def __init__(self):
        self.commands = []
        self.mode = 'normal'

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, raw, address):
        assert raw.endswith(b'\r\n')
        command = raw.decode('ascii').strip()
        self.commands.append(command)
        if command.startswith('KEY secret;'):
            command = command.split(';', 1)[1]
        if self.mode == 'silent':
            return
        reply = {'PING': 'PONG', 'STATUS': 'OK:POS=0;ALM=0;RDY=1', 'STOP': 'OK:STOP'}.get(command)
        if command.startswith('MOVE '):
            reply = 'OK:' + command
        if self.mode == 'error':
            reply = 'ERR:MOVE_FAIL'
        elif self.mode == 'wrong_target':
            reply = 'OK:MOVE -6400'
        elif self.mode == 'spoof':
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as stranger:
                stranger.sendto(b'ERR:BAD_SENDER\r\n', address)
        delay = .15 if self.mode == 'late' else .05
        asyncio.get_running_loop().call_later(delay, self.transport.sendto, (reply + '\r\n').encode(), address)


async def main():
    transport, controller = await asyncio.get_running_loop().create_datagram_endpoint(Controller, local_addr=('127.0.0.1', 0))
    state = SystemState()

    async def publish(_):
        pass

    machine = {'homePosition': 'p00', 'positionsMm': {f'p{i:02}': -1600 * i for i in range(5)},
               'network': {'host': '127.0.0.1', 'port': transport.get_extra_info('sockname')[1],
                           'commandTimeoutMs': 500, 'moveTimeoutMs': 500}}
    provider = UdpMotorProvider(state, machine, publish)
    try:
        await provider.initialize()
        assert controller.commands == ['PING', 'STATUS']
        for i in range(1, 5):
            assert await provider.move_to(f'p{i:02}')
            assert controller.commands[-1] == f'MOVE {-1600 * i}'
        await provider.home()
        assert controller.commands[-1] == 'MOVE 0'
        await provider.stop()
        controller.mode = 'spoof'
        assert await provider.ping() == 'PONG'
        provider.shared_key = 'secret'
        assert await provider.ping() == 'PONG'
        assert controller.commands[-1] == 'KEY secret;PING'
        provider.shared_key = ''
        for mode in ('silent', 'error', 'wrong_target'):
            controller.mode = mode
            provider.move_timeout = .08
            before = len(controller.commands)
            try:
                await provider.move_to('p01')
                raise AssertionError('Invalid/missing acknowledgement accepted')
            except MotorProtocolError:
                pass
            assert len(controller.commands) == before + 1, 'MOVE must not be retried'
            assert state.motor_state != 'arrived'
        controller.mode = 'late'
        try:
            await provider._request('PING', .03)
            raise AssertionError('Expected timeout')
        except MotorProtocolError:
            pass
        controller.mode = 'normal'
        assert await provider.get_state() == 'arrived'
        await asyncio.sleep(.2)
        assert await provider.ping() == 'PONG', 'Late reply contaminated next command'
        controller.mode = 'silent'
        task = asyncio.create_task(provider.ping())
        await asyncio.sleep(.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert provider._socket is None
        controller.mode = 'normal'
        provider.move_timeout = .5
        scenes = {'p01': {'motorPosition': 'p01'}}
        service = SceneService(state, scenes, provider, MediaService(state, publish), publish)
        await service.activate_scene('p01', {'method': 'TEST', 'path': '/'})
        await asyncio.sleep(.01)
        assert state.playback_state == 'playing' and state.target_scene == 'p01'
        assert state.display_scene == 'p01' and state.current_scene is None
        await service._task
        assert state.playback_state == 'playing' and state.current_scene == 'p01'
        assert not any('WATCH' in command or command == 'ZERO' for command in controller.commands)
        print('UDP passed: signed coordinates, home, STOP, KEY, sender filter, timeout/no retry, late reply, cancellation, concurrent playback; no real hardware')
    finally:
        await provider.dispose()
        transport.close()


if __name__ == '__main__':
    asyncio.run(main())
