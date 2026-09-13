"""Tour regression tests: in-memory motor only; no sockets, no physical commands."""
import asyncio
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from starlette.requests import Request
from app.main import MediaEventBody, app, carousel_start, carousel_stop, emergency_stop, media_event, restore_demo_content_after_rest, runtime
from app.services import CarouselService, MediaService, MockMotorProvider, SceneService, SystemState


class ControlledMotor(MockMotorProvider):
    def __init__(self, state, publish):
        super().__init__(state, {'homePosition': 'p00', 'mockMoveDurationMs': 0}, publish)
        self.moves = []
        self.release = None
        self.stop_calls = 0

    async def move_to(self, position):
        self.state.motor_state = 'moving'
        self.moves.append(position)
        self.release = asyncio.get_running_loop().create_future()
        await self.publish(self.state.payload())
        await self.release
        self.state.motor_state = 'arrived'
        return True

    async def stop(self):
        self.stop_calls += 1
        await super().stop()


class CarouselTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []

        async def publish(payload):
            self.events.append(payload)

        self.state = SystemState(current_scene='p00', motor_state='arrived')
        self.motor = ControlledMotor(self.state, publish)
        self.media = MediaService(self.state, publish)
        self.scenes = {'p00': {'motorPosition': 'p00', 'visible': False}}
        self.scenes.update({f'p0{i}': {'id': f'p0{i}', 'order': i, 'motorPosition': f'p0{i}', 'videoAvailable': True} for i in range(1, 5)})
        self.scene = SceneService(self.state, self.scenes, self.motor, self.media, publish)
        self.carousel = CarouselService(self.state, self.scene, {'carouselDwellSeconds': .08, 'tourMode': 'pingPong'}, publish)
        self.patches = ExitStack()
        for name, value in {'state': self.state, 'media': self.media, 'motor': self.motor, 'scene': self.scene,
                            'carousel': self.carousel, '_initialize_task': None}.items():
            self.patches.enter_context(patch.object(runtime, name, value))

    async def asyncTearDown(self):
        await self.carousel.stop()
        if self.scene._task:
            self.scene._task.cancel()
            await asyncio.gather(self.scene._task, return_exceptions=True)
        self.patches.close()

    async def until(self, predicate):
        async def wait():
            while not predicate():
                await asyncio.sleep(.005)
        await asyncio.wait_for(wait(), 1.5)

    async def start(self):
        result = await carousel_start(Request({'type': 'http', 'method': 'POST', 'path': '/api/control/carousel/start', 'headers': []}))
        self.assertTrue(result['accepted'])

    async def arrive(self):
        self.motor.release.set_result(None)
        await self.until(lambda: self.state.target_scene is None)

    def feedback(self, event='ended'):
        return MediaEventBody(sessionId=self.state.media_session_id, revision=self.state.playback_revision, event=event)

    async def test_end_before_arrival_and_missing_media_dwell_after_arrival(self):
        self.scenes['p02']['videoAvailable'] = False
        self.scenes['p03']['contentType'] = 'imageText'  # Even a configured video is ignored.
        await self.start()
        await self.until(lambda: self.motor.moves == ['p01'])
        self.assertEqual(self.state.playback_state, 'playing')
        self.assertTrue((await media_event(self.feedback()))['accepted'])
        await asyncio.sleep(.12)
        self.assertEqual(self.motor.moves, ['p01'])
        await self.arrive()
        await self.until(lambda: len(self.motor.moves) == 2)
        self.assertEqual(self.state.playback_state, 'showing')
        self.assertIsNone(self.state.video_id)
        await asyncio.sleep(.12)  # Travel time exceeds the dwell interval.
        self.assertEqual(len(self.motor.moves), 2)
        await self.arrive()
        await asyncio.sleep(.02)
        self.assertEqual(len(self.motor.moves), 2)
        await self.until(lambda: len(self.motor.moves) == 3)
        self.assertEqual(self.state.playback_state, 'showing')
        await self.arrive()
        await self.until(lambda: len(self.motor.moves) == 4)
        self.assertEqual(self.motor.moves, ['p01', 'p02', 'p03', 'p04'])

    async def test_arrival_does_not_finish_video_or_reset_it(self):
        await self.start()
        await self.until(lambda: bool(self.motor.moves))
        identity = (self.state.media_session_id, self.state.playback_revision)
        await self.arrive()
        await asyncio.sleep(.15)
        self.assertEqual(self.motor.moves, ['p01'])
        self.assertEqual(identity, (self.state.media_session_id, self.state.playback_revision))
        ended = self.feedback()
        self.assertTrue((await media_event(ended))['accepted'])
        self.assertFalse((await media_event(ended))['accepted'])
        await self.until(lambda: len(self.motor.moves) == 2)
        self.assertFalse((await media_event(ended))['accepted'])  # Old point event.

    async def test_pause_stop_stale_feedback_and_replay(self):
        await self.start()
        await self.until(lambda: bool(self.motor.moves))
        old_feedback = self.feedback()
        await self.media.pause()
        await self.arrive()
        self.assertFalse((await media_event(old_feedback))['accepted'])
        await asyncio.sleep(.12)
        self.assertEqual(len(self.motor.moves), 1)
        await self.media.play()
        self.assertFalse((await media_event(old_feedback))['accepted'])
        old_feedback = self.feedback()
        await self.media.stop()
        self.assertFalse((await media_event(old_feedback))['accepted'])
        await asyncio.sleep(.12)
        self.assertEqual(len(self.motor.moves), 1)
        await self.media.play()
        await media_event(self.feedback())
        await self.until(lambda: len(self.motor.moves) == 2)

    async def test_pingpong_loop_and_return_home_sequences(self):
        for mode, expected in [('pingPong', ['p01', 'p02', 'p03', 'p04', 'p03', 'p02', 'p01']),
                               ('loop', ['p01', 'p02', 'p03', 'p04', 'p01']),
                               ('returnHome', ['p01', 'p02', 'p03', 'p04', 'p03', 'p02', 'p01', 'p00'])]:
            self.carousel.app_config['tourMode'] = mode
            self.state.current_scene = 'p00'
            self.motor.moves.clear()
            await self.start()
            for index, point in enumerate(expected):
                await self.until(lambda: len(self.motor.moves) == index + 1)
                self.assertEqual(self.motor.moves[-1], point)
                await self.arrive()
                if index + 1 < len(expected):
                    await media_event(self.feedback())
            await self.carousel.stop()

    async def test_return_home_continues_from_second_point_then_stops_at_home(self):
        self.carousel.app_config['tourMode'] = 'returnHome'
        self.state.current_scene = 'p02'
        self.state.motor_state = 'arrived'
        await self.start()
        await self.until(lambda: self.state.playback_state == 'playing')
        await media_event(self.feedback())  # p02 的内容播放结束，下一站才移动到 p03。
        expected = ['p03', 'p04', 'p03', 'p02', 'p01', 'p00']
        for index, point in enumerate(expected):
            await self.until(lambda: len(self.motor.moves) == index + 1)
            self.assertEqual(self.motor.moves[-1], point)
            await self.arrive()
            if point != 'p00':
                await media_event(self.feedback())
        await self.until(lambda: not self.state.carousel_mode)
        self.assertEqual(self.state.current_scene, 'p00')
        self.assertEqual(self.state.carousel_direction, 'backward')

    async def test_return_home_single_visible_point_returns_to_home_once(self):
        for point_id in ('p02', 'p03', 'p04'):
            self.scenes.pop(point_id)
        self.carousel.app_config['tourMode'] = 'returnHome'
        await self.start()
        await self.until(lambda: self.motor.moves == ['p01'])
        await self.arrive()
        await media_event(self.feedback())
        await self.until(lambda: self.motor.moves == ['p01', 'p00'])
        await self.arrive()
        await self.until(lambda: not self.state.carousel_mode)
        self.assertEqual(self.state.current_scene, 'p00')

    async def test_emergency_stop_cancels_move_and_sends_single_soft_stop(self):
        result = await self.scene.activate_scene('p01', {'method': 'POST', 'path': '/test'})
        self.assertTrue(result['accepted'])
        await self.until(lambda: self.motor.moves == ['p01'])
        reply = await emergency_stop(Request({'type': 'http', 'method': 'POST', 'path': '/api/control/emergency-stop', 'headers': []}))
        self.assertTrue(reply['success'])
        self.assertEqual(self.motor.stop_calls, 1)
        self.assertIsNone(self.state.target_scene)
        self.assertEqual(self.state.motor_state, 'idle')
        self.assertIn('STOP 软停', self.state.error or '')

    async def test_demo_rest_point_restores_separate_demo_content(self):
        result = await self.scene.activate_scene('p04', {'method': 'PUT', 'path': '/api/admin/presentation'})
        self.assertTrue(result['accepted'])
        await self.until(lambda: self.motor.moves == ['p04'])
        move_task = self.scene._task
        await self.arrive()
        await restore_demo_content_after_rest(move_task, 'p04', 'p01')
        self.assertEqual(self.state.current_scene, 'p04')
        self.assertEqual(self.state.display_scene, 'p01')
        self.assertEqual(self.state.video_id, 'scene-p01-video')
        self.assertEqual(self.state.playback_state, 'playing')

    async def test_stop_during_motion_and_home_after_arrival(self):
        await self.start()
        await self.until(lambda: bool(self.motor.moves))
        self.assertFalse((await self.carousel.start({}))['accepted'])
        await carousel_stop(Request({'type': 'http', 'method': 'POST', 'path': '/api/control/carousel/stop', 'headers': []}))
        self.assertFalse(self.state.carousel_mode)
        self.assertEqual(self.motor.stop_calls, 0)
        self.assertEqual(self.state.playback_state, 'playing')
        self.assertEqual((await self.carousel.start({}))['error'], 'MOTOR_BUSY')
        await self.arrive()
        await media_event(self.feedback())
        await asyncio.sleep(.12)
        self.assertEqual(self.motor.moves, ['p01'])
        await self.scene.go_home({})
        await self.until(lambda: self.motor.moves[-1] == 'p00')
        self.motor.release.set_result(None)
        await self.scene._task
        self.assertEqual(self.state.current_scene, 'p00')

    async def test_missing_arrival_stops_without_retry(self):
        await self.start()
        await self.until(lambda: bool(self.motor.moves))
        with self.assertLogs('polar_rail', level='ERROR'):
            self.motor.release.set_exception(RuntimeError('simulated lost arrival'))
            await self.until(lambda: not self.state.carousel_mode)
        await asyncio.sleep(.15)
        self.assertEqual(self.motor.moves, ['p01'])
        self.assertEqual(self.state.motor_state, 'error')
        self.assertEqual(self.state.playback_state, 'playing')
        self.assertEqual((await self.carousel.start({}))['error'], 'MOTOR_ERROR')

    async def test_media_error_stops_tour_but_not_current_motion(self):
        await self.start()
        await self.until(lambda: bool(self.motor.moves))
        await media_event(self.feedback('error'))
        self.assertFalse(self.state.carousel_mode)
        self.assertTrue(self.state.media_error)
        self.assertEqual(self.motor.stop_calls, 0)
        await self.arrive()
        await asyncio.sleep(.12)
        self.assertEqual(self.motor.moves, ['p01'])

    async def test_start_here_single_point_replay_and_rapid_restart(self):
        self.scenes.pop('p02'); self.scenes.pop('p03'); self.scenes.pop('p04')
        self.state.current_scene = 'p01'
        await self.scene.present('p01')
        original_session = self.state.media_session_id
        await self.start()
        await asyncio.sleep(.02)
        self.assertEqual(original_session, self.state.media_session_id)
        await media_event(self.feedback())
        await self.until(lambda: self.state.media_session_id != original_session)
        self.assertEqual(self.motor.moves, [])
        stale = self.feedback()
        await self.carousel.stop()
        await self.start()
        await asyncio.sleep(.02)
        self.assertTrue(self.state.carousel_mode)
        # New media load must reject even a matching revision with another session.
        await self.scene.present('p01')
        stale.revision = self.state.playback_revision
        self.assertFalse((await media_event(stale))['accepted'])

    async def test_empty_configuration_and_registered_routes(self):
        for path, endpoint in [('/api/control/carousel/start', carousel_start), ('/api/control/carousel/stop', carousel_stop), ('/api/control/emergency-stop', emergency_stop), ('/api/media/events', media_event)]:
            self.assertTrue(any(route.path == path and 'POST' in route.methods and route.endpoint == endpoint for route in app.routes))
        for point in self.scenes.values():
            point['visible'] = False
        self.assertEqual((await self.carousel.start({}))['error'], 'NO_POINTS')
        self.assertFalse(self.state.carousel_mode)
        self.assertEqual(self.motor.moves, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
