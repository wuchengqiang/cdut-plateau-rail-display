"""Media-error recovery regression tests; no service startup or motor sockets."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from app.services import MediaService, SystemState


def rail_state(state: SystemState) -> dict:
    """Fields which a media retry must not modify."""
    return deepcopy({name: getattr(state, name) for name in (
        'current_scene', 'target_scene', 'display_scene', 'motor_state',
        'carousel_mode', 'carousel_direction', 'error', 'last_command',
    )})


class MediaRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = SystemState(
            current_scene='p02', target_scene='p03', display_scene='p03',
            motor_state='moving', carousel_mode=True, carousel_direction='backward',
            error='retained hardware diagnostic',
            last_command={'method': 'TEST', 'path': '/unchanged-motion-command'},
        )
        self.publish = AsyncMock()
        self.media = MediaService(self.state, self.publish)
        await self.media.load('p03')
        await self.media.play()
        self.publish.reset_mock()

    async def fail_current_media(self):
        result = await self.media.report_event(
            self.state.media_session_id, self.state.playback_revision, 'error')
        self.assertTrue(result['accepted'])
        self.assertEqual(self.state.playback_state, 'error')
        self.assertTrue(self.state.media_error)

    async def test_error_play_creates_one_fresh_session_without_motion_changes(self):
        await self.fail_current_media()
        before_rail = rail_state(self.state)
        before_session = self.state.media_session_id
        before_revision = self.state.playback_revision
        before_video = self.state.video_id
        self.publish.reset_mock()

        await self.media.play()

        self.assertNotEqual(self.state.media_session_id, before_session)
        self.assertTrue(self.state.media_session_id)
        self.assertEqual(self.state.playback_revision, before_revision + 1)
        self.assertEqual(self.state.video_id, before_video)
        self.assertEqual(self.state.playback_state, 'playing')
        self.assertIsNone(self.state.media_error)
        self.assertEqual(rail_state(self.state), before_rail)
        self.publish.assert_awaited_once_with(self.state.payload())

    async def test_old_session_feedback_cannot_poison_recovered_playback(self):
        old_session = self.state.media_session_id
        old_revision = self.state.playback_revision
        await self.fail_current_media()
        await self.media.play()
        recovered = deepcopy(self.state.payload())
        self.publish.reset_mock()
        for event in ('ended', 'error'):
            for revision in (old_revision, self.state.playback_revision):
                with self.subTest(event=event, revision=revision):
                    result = await self.media.report_event(old_session, revision, event)
                    self.assertFalse(result['accepted'])
                    self.assertEqual(self.state.payload(), recovered)
        self.publish.assert_not_awaited()
        current = await self.media.report_event(
            self.state.media_session_id, self.state.playback_revision, 'ended')
        self.assertTrue(current['accepted'])
        self.assertEqual(self.state.playback_state, 'ended')

    async def test_pause_or_stop_after_error_does_not_lose_retry_marker(self):
        for operation in ('pause', 'stop'):
            with self.subTest(operation=operation):
                await self.media.load('p03')
                await self.media.play()
                await self.fail_current_media()
                failed_session = self.state.media_session_id
                await getattr(self.media, operation)()
                self.assertTrue(self.state.media_error)
                await self.media.play()
                self.assertNotEqual(self.state.media_session_id, failed_session)
                self.assertIsNone(self.state.media_error)
                self.assertEqual(self.state.playback_state, 'playing')

    async def test_normal_play_pause_stop_and_end_keep_session(self):
        session = self.state.media_session_id
        for state in ('playing', 'paused', 'stopped', 'ended'):
            with self.subTest(state=state):
                self.state.playback_state = state
                self.state.media_error = None
                revision = self.state.playback_revision
                before_rail = rail_state(self.state)
                await self.media.play()
                self.assertEqual(self.state.media_session_id, session)
                self.assertEqual(self.state.playback_revision, revision + 1)
                self.assertEqual(self.state.playback_state, 'playing')
                self.assertEqual(rail_state(self.state), before_rail)

    async def test_error_state_alone_is_enough_to_recover(self):
        self.state.playback_state = 'error'
        self.state.media_error = None
        previous = self.state.media_session_id
        await self.media.play()
        self.assertNotEqual(self.state.media_session_id, previous)
        self.assertEqual(self.state.playback_state, 'playing')

    async def test_repeated_play_after_recovery_does_not_repeat_session_reset(self):
        await self.fail_current_media()
        await self.media.play()
        recovered_session = self.state.media_session_id
        for _ in range(3):
            await self.media.play()
            self.assertEqual(self.state.media_session_id, recovered_session)

    async def test_no_video_has_no_side_effects(self):
        self.state.video_id = None
        self.state.media_error = 'no active media'
        self.state.playback_state = 'error'
        before = deepcopy(self.state.payload())
        await self.media.play()
        self.assertEqual(self.state.payload(), before)
        self.publish.assert_not_awaited()

    async def test_existing_play_endpoint_recovers_without_calling_motion(self):
        # Prevent even provider construction from choosing a real device when
        # app.main is imported. The application lifespan is never started.
        with patch('app.services.create_motor_provider', return_value=SimpleNamespace()), \
                patch('app.config.load_admin_password', return_value='test-only'):
            from app.main import play, runtime
        from starlette.requests import Request

        forbidden = []

        def blocked(name):
            method = AsyncMock(side_effect=AssertionError('Unexpected call: ' + name))
            forbidden.append(method)
            return method

        scene = SimpleNamespace(**{name: blocked('scene.' + name)
                                  for name in ('activate_scene', 'present', 'go_home')})
        motor = SimpleNamespace(**{name: blocked('motor.' + name)
                                  for name in ('move_to', 'home', 'stop', 'ping', 'initialize')})
        carousel = SimpleNamespace(**{name: blocked('carousel.' + name)
                                     for name in ('start', 'stop')})
        reload_content = blocked('reload_content')
        await self.fail_current_media()
        before_rail = rail_state(self.state)
        old_session = self.state.media_session_id
        request = Request({'type': 'http', 'method': 'POST', 'path': '/api/control/play', 'headers': []})
        with (patch.object(runtime, 'state', self.state),
              patch.object(runtime, 'media', self.media),
              patch.object(runtime, 'scene', scene),
              patch.object(runtime, 'motor', motor),
              patch.object(runtime, 'carousel', carousel),
              patch.object(runtime, 'reload_content', reload_content),
              patch.object(runtime, 'last_wakefusion_action_id', None)):
            result = await play(request)
        self.assertTrue(result['success'])
        self.assertNotEqual(self.state.media_session_id, old_session)
        # The endpoint intentionally records the existing play command; it must
        # not invent a point-activation/motion command or change mechanical state.
        before_rail['last_command'] = {'method': 'POST', 'path': '/api/control/play'}
        self.assertEqual(rail_state(self.state), before_rail)
        self.assertEqual(self.state.playback_state, 'playing')
        for method in forbidden:
            method.assert_not_awaited()


if __name__ == '__main__':
    unittest.main(verbosity=2)
