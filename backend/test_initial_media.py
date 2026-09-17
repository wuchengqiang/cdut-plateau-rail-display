"""The landing Play button must support Pause without ever moving hardware."""
import asyncio
from unittest.mock import AsyncMock, patch

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
    with (
        patch.object(runtime, 'state', state),
        patch.object(runtime, 'media', media),
        patch.object(runtime, 'app_config', {'presentation': {'mode': 'visit'}}),
        patch.object(runtime.scene, 'has_video', return_value=True),
    ):
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

    late_state = SystemState(current_scene='p00')
    late_media = MediaService(late_state, publish)
    reload_mock = AsyncMock(return_value={'success': True})
    with (
        patch.object(runtime, 'state', late_state),
        patch.object(runtime, 'media', late_media),
        patch.object(runtime, 'app_config', {'presentation': {'mode': 'visit'}}),
        patch.object(runtime.scene, 'has_video', side_effect=[False, True]),
        patch.object(runtime, 'reload_content', reload_mock),
    ):
        await play(request)
        reload_mock.assert_awaited_once()
        assert late_state.display_scene == 'p01'
        assert late_state.playback_state == 'playing'

    fixed_state = SystemState(current_scene='p00')
    fixed_media = MediaService(fixed_state, publish)
    with (
        patch.object(runtime, 'state', fixed_state),
        patch.object(runtime, 'media', fixed_media),
        patch.object(runtime, 'app_config', {'presentation': {'mode': 'demo', 'demoContentPointId': 'p04'}}),
        patch.object(runtime.scene, 'has_video', return_value=True),
    ):
        await play(request)
        assert fixed_state.display_scene == 'p04'
        assert fixed_state.playback_state == 'playing'
    print('Passed: landing play/pause/resume/stop; no rail command or hardware contacted')


if __name__ == '__main__':
    asyncio.run(main())
