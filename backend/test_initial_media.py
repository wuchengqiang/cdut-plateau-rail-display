"""The landing Play button must support Pause without ever moving hardware."""
import asyncio
from unittest.mock import patch

from starlette.requests import Request
from app.main import play, pause, stop, runtime
from app.services import MediaService, SystemState


async def main():
    state = SystemState(current_scene='p00')
    events = []

    async def publish(payload):
        events.append(payload)

    request = Request({'type': 'http', 'method': 'POST', 'path': '/api/control/play', 'headers': []})
    media = MediaService(state, publish)
    with patch.object(runtime, 'state', state), patch.object(runtime, 'media', media):
        await play(request)
        assert state.display_scene == 'p01' and state.video_id
        assert state.current_scene == 'p00' and state.target_scene is None
        await pause(request)
        assert state.playback_state == 'paused'
        await play(request)
        assert state.playback_state == 'playing'
        await stop(request)
        assert state.playback_state == 'stopped'
        assert all(event['motorState'] == 'idle' for event in events)
    print('Passed: landing play/pause/resume/stop; no rail command or hardware contacted')


if __name__ == '__main__':
    asyncio.run(main())
