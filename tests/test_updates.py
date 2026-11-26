# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
from io import BytesIO
import unittest
from unittest.mock import patch

from betternotes import updates


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.name = 'pinplan-notes_0.4.10_all.deb'
        self.url = f'{updates.REPOSITORY}/releases/download/v0.4.10/{self.name}'
        self.digest = hashlib.sha256(b'package').hexdigest()
        self.data = {
            'tag_name': 'v0.4.10',
            'assets': [{'name': self.name, 'browser_download_url': self.url,
                        'digest': f'sha256:{self.digest}'}],
        }

    def test_newer_stable_digest_and_numeric_version(self):
        result = updates.select_release(self.data, '0.4.9')
        self.assertEqual(result, updates.Release('0.4.10', self.name, self.url, self.digest))
        self.assertIsNone(updates.select_release(self.data, '0.4.10'))
        self.assertIsNone(updates.select_release(self.data, '0.5.0'))

    def test_rejects_prerelease_and_unverified_asset(self):
        with self.assertRaises(ValueError):
            updates.select_release(dict(self.data, prerelease=True), '0.4.9')
        self.data['assets'][0]['digest'] = None
        with self.assertRaises(ValueError):
            updates.select_release(self.data, '0.4.9')

    def test_invalid_download_never_reaches_installer(self):
        release = updates.select_release(self.data, '0.4.9')
        with patch.object(updates, 'open_github', return_value=BytesIO(b'altered')):
            with patch.object(updates.subprocess, 'run') as installer:
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    updates.install_update(release)
                installer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
