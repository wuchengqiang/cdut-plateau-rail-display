import asyncio

from app.services import CarouselService, MediaService, MockMotorProvider, SceneService, SystemState


async def _publish(_: dict) -> None:
    return None


async def _exercise_services() -> None:
    scenes = {
        "p01": {"id": "p01", "order": 10, "motorPosition": "p01"},
        "p02": {"id": "p02", "order": 20, "motorPosition": "p02"},
        "p03": {"id": "p03", "order": 30, "motorPosition": "p03"},
        "p04": {"id": "p04", "order": 40, "motorPosition": "p04"},
    }
    state = SystemState(current_scene="p01")
    motor = MockMotorProvider(state, {"homePosition": "p01", "mockMoveDurationMs": 0}, _publish)
    media = MediaService(state, _publish)
    service = SceneService(state, scenes, motor, media, _publish)
    carousel = CarouselService(state, service, {"carouselDwellSeconds": 0}, _publish)
    await motor.initialize()

    accepted = await service.activate_scene("p03", {"method": "POST", "path": "/api/control/points/p03/activate"})
    duplicate = await service.activate_scene("p03", {"method": "GET", "path": "/api/control/points/p03/activate"})
    assert accepted["accepted"] is True and duplicate["accepted"] is False
    await asyncio.sleep(0.05)
    assert state.current_scene == "p03" and state.playback_state == "playing"
    assert (await service.activate_scene("p09", {"method": "GET", "path": "/api/control/points/p09/activate"}))["error"] == "INVALID_SCENE"

    assert (await carousel.start({"method": "POST", "path": "/api/control/carousel/start"}))["accepted"] is True
    await asyncio.sleep(0.05)
    assert state.carousel_mode is True
    assert (await carousel.stop({"method": "POST", "path": "/api/control/carousel/stop"}))["accepted"] is True


if __name__ == "__main__":
    asyncio.run(_exercise_services())
    print("Service smoke test passed")
