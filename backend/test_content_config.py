"""Configuration classification uses only disposable media fixtures."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import config


class ContentConfigTests(unittest.TestCase):
    def test_media_classification_and_dwell_validation(self):
        with tempfile.TemporaryDirectory(prefix='rail-content-') as directory:
            root = Path(directory)
            (root / 'content').mkdir()
            (root / 'content' / 'clip.mp4').write_bytes(b'fixture')
            (root / 'outside.mp4').write_bytes(b'not-public')
            configs = {
                'config/app.json': {'carouselDwellSeconds': 12},
                'config/machine.json': {'provider': 'mock'},
                'config/points.json': {'homePointId': 'p00', 'points': [
                    {'id': 'p00', 'visible': False, 'positionMm': 0},
                    {'id': 'p01', 'positionMm': 1600, 'videoPath': 'content/clip.mp4'},
                    {'id': 'p02', 'positionMm': 3200, 'videoPath': 'content/missing.mp4'},
                    {'id': 'p03', 'positionMm': 4800, 'contentType': 'imageText', 'videoPath': 'content/clip.mp4'},
                    {'id': 'p04', 'positionMm': 6400, 'imagePath': 'content/photo.jpg'},
                ]},
            }
            with patch.object(config, 'ROOT', root), patch.object(config, 'read_json', side_effect=lambda name: copy.deepcopy(configs[name])):
                app, points, machine = config.load_configuration()
                self.assertEqual(app['carouselDwellSeconds'], 12)
                self.assertEqual(app['presentation'], {'mode': 'visit', 'demoRestPointId': 'p04', 'demoContentPointId': 'p01'})
                self.assertEqual(app['tourMode'], 'pingPong')
                self.assertEqual([points[f'p0{i}']['videoAvailable'] for i in range(1, 5)], [True, False, False, False])
                self.assertEqual(list(machine['positionsMm'].values()), [0, 1600, 3200, 4800, 6400])
                self.assertEqual(points['p04']['videoPath'], '')
                configs['config/points.json']['points'][1]['videoPath'] = 'content/../outside.mp4'
                self.assertFalse(config.load_configuration()[1]['p01']['videoAvailable'])
                for invalid in [0, -1, True, '12', None, float('nan'), float('inf')]:
                    configs['config/app.json']['carouselDwellSeconds'] = invalid
                    with self.assertRaises(ValueError):
                        config.load_configuration()

    def test_presentation_mode_validation_and_atomic_save(self):
        with tempfile.TemporaryDirectory(prefix='rail-presentation-') as directory:
            root = Path(directory)
            (root / 'config').mkdir()
            app_path = root / 'config' / 'app.json'
            app_path.write_text('{"title":"测试","presentation":{"mode":"visit","demoRestPointId":"p04","demoContentPointId":"p01"}}', encoding='utf-8')
            with patch.object(config, 'ROOT', root):
                self.assertEqual(config.save_presentation_mode('demo'), {'mode': 'demo', 'demoRestPointId': 'p04', 'demoContentPointId': 'p01'})
                saved = __import__('json').loads(app_path.read_text(encoding='utf-8'))
                self.assertEqual(saved['presentation'], {'mode': 'demo', 'demoRestPointId': 'p04', 'demoContentPointId': 'p01'})
                for raw in [{'mode': 'hidden'}, {'mode': 'demo', 'demoRestPointId': '../p04'}, {'mode': 'demo', 'demoContentPointId': '../p01'}, []]:
                    with self.assertRaises(ValueError):
                        config.normalize_presentation_configuration(raw)


if __name__ == '__main__':
    unittest.main(verbosity=2)
