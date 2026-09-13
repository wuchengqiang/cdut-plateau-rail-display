"""No real hardware: independently verify displayed content and confirmed position."""
import asyncio
import json
from pathlib import Path

from app.services import MediaService, MockMotorProvider, MotorProtocolError, SceneService, SystemState


class ControlledMotor(MockMotorProvider):
    def __init__(self, state, publish):
        super().__init__(state, {'homePosition': 'p00', 'mockMoveDurationMs': 0}, publish)
        self.started = asyncio.Event()
        self.arrival = asyncio.Event()
        self.fail = False

    async def move_to(self, position):
        self.state.motor_state = 'moving'
        await self.publish(self.state.payload())
        self.started.set()
        await self.arrival.wait()
        if self.fail:
            raise MotorProtocolError('simulated missing arrival acknowledgement')
        self.state.motor_state = 'arrived'
        return True


async def main():
    events = []

    async def publish(payload):
        events.append(payload)

    state = SystemState(current_scene='p00')
    motor = ControlledMotor(state, publish)
    media = MediaService(state, publish)
    scenes = {p: {'motorPosition': p, 'videoPath': f'content/videos/{p}.mp4'} for p in ('p00', 'p01', 'p02')}
    service = SceneService(state, scenes, motor, media, publish)
    await motor.initialize()
    await service.activate_scene('p01', {'method': 'TEST', 'path': '/'})
    await motor.started.wait()
    assert state.playback_state == 'playing' and state.display_scene == 'p01'
    assert state.current_scene == 'p00' and state.target_scene == 'p01'
    assert state.payload()['displayPointId'] == 'p01'
    assert not (await service.activate_scene('p01', {}))['accepted']
    assert (await service.activate_scene('p02', {}))['error'] == 'MOTOR_BUSY'
    playing_revision = state.playback_revision
    motor.arrival.set()
    await service._task
    assert state.playback_state == 'playing', 'Arrival must not stop playback'
    assert state.playback_revision == playing_revision, 'Arrival must not emit any media command'

    motor.started.clear()
    motor.arrival.clear()
    await service.activate_scene('p02', {})
    await motor.started.wait()
    await media.pause()
    paused_revision = state.playback_revision
    motor.arrival.set()
    await service._task
    assert state.current_scene == 'p02' and state.target_scene is None
    assert state.playback_state == 'paused', 'Arrival must not resume/restart user-paused video'
    assert state.playback_revision == paused_revision

    await media.play()
    resumed_revision = state.playback_revision
    await media.play()
    assert state.playback_revision == resumed_revision + 1, 'Explicit replay must reach the browser'

    motor.started.clear()
    motor.arrival.clear()
    motor.fail = True
    await service.activate_scene('p01', {})
    await motor.started.wait()
    assert state.playback_state == 'playing' and state.display_scene == 'p01'
    motor.arrival.set()
    await service._task
    assert state.motor_state == 'error' and state.error
    assert state.current_scene == 'p02' and state.target_scene is None
    assert state.display_scene == 'p01' and state.playback_state == 'playing'
    await media.stop()
    assert state.playback_state == 'stopped'

    project = Path(__file__).resolve().parents[1]
    config = json.loads((project / 'config/points.json').read_text('utf-8'))
    assert [p['positionMm'] for p in config['points']] == [0, 1600, 3200, 4800, 6400]
    network = json.loads((project / 'config/machine.json').read_text('utf-8'))['network']
    assert (network['host'], network['port']) == ('127.0.0.1', 53500)
    print('Passed: immediate video + delayed motion, pause preserved at arrival, no duplicate motion, failure preserves displayed video, positive point config')


if __name__ == '__main__':
    asyncio.run(main())
