"""Media diagnostics tests: temporary folders only, no server or motor."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from app.media_diagnostics import (BACKUP_COUNT, MAX_LOG_BYTES, MAX_RATE_KEYS,
                                   MediaDiagnosticEvent, MediaDiagnostics)


PAGE = 'ecda2efb-6bab-4c65-a85b-ab5aa7cd5b1b'
SESSION = 'a' * 32


def event(**extra):
    values = dict(event='media_error', pageId=PAGE, sessionId=SESSION,
                  pointId='p03', revision=10, errorCode=3, currentTime=37.5,
                  readyState=2, networkState=2, pageMode='embedded',
                  browserFamily='Edge', browserVersion='156.0.4314.58')
    values.update(extra)
    return MediaDiagnosticEvent(**values)


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='rail-anomaly-test-')
        self.root = Path(self.tmp.name)
        self.now = 0.0
        self.store = MediaDiagnostics(self.root, clock=lambda: self.now)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def record(self, value=None, **kwargs):
        return self.store.record(value or event(), allowed_point_ids=('p01', 'p03'), **kwargs)

    def test_lazy_only_anomaly_and_strict_fields(self):
        self.assertFalse(self.store.path.exists())
        self.assertTrue(self.record())
        data = json.loads(self.store.path.read_text('utf-8'))
        self.assertEqual(data['event'], 'media_error')
        self.assertEqual(data['pointId'], 'p03')
        self.assertEqual(data['browserVersion'], '156.0.4314.58')
        self.assertNotIn('client_id', data)
        for extra in ({'token':'secret'}, {'url':'http://private/?token=secret'},
                      {'message':'secret'}, {'userAgent':'arbitrary secret'},
                      {'event':'timeupdate'}, {'browserVersion':'token=secret'},
                      {'currentTime':float('nan')}, {'bufferedSeconds':float('inf')},
                      {'currentTime':-1.0}, {'errorCode':99}, {'muted':'true'}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                event(**extra)

    def test_unknown_points_and_client_identity_never_written(self):
        self.assertTrue(self.record(event(pointId='do-not-store-this'), client_id='Bearer confidential'))
        raw = self.store.path.read_text('utf-8')
        self.assertNotIn('do-not-store-this', raw)
        self.assertNotIn('Bearer', raw)
        self.assertNotIn('confidential', raw)
        self.assertNotIn('pointId', json.loads(raw))

    def test_same_key_cooldown_and_global_budget(self):
        self.assertTrue(self.record())
        self.assertFalse(self.record())
        self.now = 9.9
        self.assertFalse(self.record())
        self.now = 10
        self.assertTrue(self.record())
        for i in range(58):
            self.assertTrue(self.record(event(sessionId=f'{i:032x}')))
        self.assertFalse(self.record(event(sessionId='f'*32)))
        self.assertEqual(len(self.store._window), 60)
        self.now = 71
        self.assertTrue(self.record(event(sessionId='f'*32)))

    def test_limiter_memory_is_bounded(self):
        for i in range(MAX_RATE_KEYS + 20):
            self.now += 61
            self.assertTrue(self.record(event(sessionId=f'{i:032x}')))
        self.assertEqual(len(self.store._recent), MAX_RATE_KEYS)
        self.assertLessEqual(len(self.store._window), 60)

    def test_rotation_has_five_files_with_bounded_size(self):
        # Smaller threshold exercises exactly the same RotatingFileHandler path.
        with patch('app.media_diagnostics.MAX_LOG_BYTES', 2048):
            for i in range(70):
                self.now += 11
                self.assertTrue(self.record(event(revision=i)))
        files = list(self.store.path.parent.glob('media-errors.jsonl*'))
        self.assertEqual(len(files), BACKUP_COUNT + 1)
        self.assertLessEqual(sum(p.stat().st_size for p in files), 2048 * (BACKUP_COUNT + 1))
        for file in files:
            self.assertLessEqual(file.stat().st_size, 2048)
            for line in file.read_text('utf-8').splitlines():
                self.assertEqual(json.loads(line)['schema'], 'rail.media-anomaly/v1')
        self.assertEqual(MAX_LOG_BYTES, 1024 * 1024)

    def test_io_error_does_not_escape_or_print(self):
        (self.root / 'logs').write_text('Not a directory', encoding='utf-8')
        with patch('sys.stderr.write') as stderr:
            self.assertFalse(self.record())
        stderr.assert_not_called()

    def test_handler_io_failure_is_quiet(self):
        self.assertTrue(self.record())
        self.now += 11
        with patch.object(self.store._handler, 'shouldRollover', side_effect=OSError('disk full')), patch('sys.stderr.write') as stderr:
            self.assertFalse(self.record())
        stderr.assert_not_called()

    def test_concurrent_calls_share_one_handler_and_deduplicate(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.record(), range(30)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(len(self.store.path.read_text('utf-8').splitlines()), 1)

    def test_bypassed_model_validation_does_not_leak_extras(self):
        unsafe = MediaDiagnosticEvent.model_construct(event='media_error', pageId='secret-token')
        self.assertFalse(self.record(unsafe))
        self.assertFalse(self.store.path.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
