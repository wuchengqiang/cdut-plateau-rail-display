"""Check mascot configuration without starting lifespan or contacting hardware."""
import asyncio
from unittest.mock import patch

from app.main import display_config, runtime


async def main():
    assert runtime.app_config.get('showMascots') is False
    assert (await display_config())['showMascots'] is False
    with patch.dict(runtime.app_config, {'showMascots': True}):
        assert (await display_config())['showMascots'] is True
    with patch.dict(runtime.app_config, {'showMascots': 'false'}):
        assert (await display_config())['showMascots'] is False
    old_config = {key: value for key, value in runtime.app_config.items() if key != 'showMascots'}
    with patch.dict(runtime.app_config, old_config, clear=True):
        response = await display_config()
        assert response['showMascots'] is False
        assert response['mascots']['main'], 'Keep assets available for an explicit opt-in'
    print('Display configuration passed: default off, explicit opt-in, old config off; no hardware contacted')


if __name__ == '__main__':
    asyncio.run(main())
