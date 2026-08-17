import asyncio

from app.services import CarouselService, MediaService, MockMotorProvider, SceneService, SystemState


async def _publish(_: dict) -> None:
    return None


async def _exercise_services() -> None:
    scenes = {
        1: {"id": 1, "motorPosition": "P1"},
        2: {"id": 2, "motorPosition": "P2"},
        3: {"id": 3, "motorPosition": "P3"},
        4: {"id": 4, "motorPosition": "P4"},
    }
    state = SystemState(current_scene=1)
    motor = MockMotorProvider(state, {"homePosition": "P1", "mockMoveDurationMs": 0}, _publish)
    media = MediaService(state, _publish)
    service = SceneService(state, scenes, motor, media, _publish)
    carousel = CarouselService(state, service, {"carouselDwellSeconds": 0}, _publish)
    await motor.initialize()

    accepted = await service.activate_scene(3, {"method": "POST", "path": "/api/control/scene/3"})
    duplicate = await service.activate_scene(3, {"method": "GET", "path": "/api/control/scene/3"})
    assert accepted["accepted"] is True and duplicate["accepted"] is False
    await asyncio.sleep(0.05)
    assert state.current_scene == 3 and state.playback_state == "playing"
    assert (await service.activate_scene(9, {"method": "GET", "path": "/api/control/scene/9"}))["error"] == "INVALID_SCENE"

    assert (await carousel.start({"method": "POST", "path": "/api/control/carousel/start"}))["accepted"] is True
    await asyncio.sleep(0.05)
    assert state.carousel_mode is True
    assert (await carousel.stop({"method": "POST", "path": "/api/control/carousel/stop"}))["accepted"] is True


if __name__ == "__main__":
    asyncio.run(_exercise_services())
    print("Service smoke test passed")
