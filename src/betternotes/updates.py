# SPDX-License-Identifier: GPL-3.0-or-later
"""Check and install stable PinPlan Debian packages from GitHub Releases."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from dataclasses import dataclass
from urllib.request import Request, urlopen

REPOSITORY = 'https://github.com/lbg2002/betternotes'
LATEST_API = 'https://api.github.com/repos/lbg2002/betternotes/releases/latest'
MAX_PACKAGE_SIZE = 32 * 1024 * 1024


@dataclass(frozen=True)
class Release:
    version: str
    name: str
    url: str
    sha256: str


def version_parts(version):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise ValueError('Invalid stable version')
    return tuple(map(int, version.split('.')))


def select_release(data, current):
    tag = data['tag_name']
    if not tag.startswith('v') or data.get('draft') or data.get('prerelease'):
        raise ValueError('Expected a stable release')
    version = tag[1:]
    if version_parts(version) <= version_parts(current):
        return None
    name = f'pinplan-notes_{version}_all.deb'
    url = f'{REPOSITORY}/releases/download/{tag}/{name}'
    for asset in data['assets']:
        digest = asset.get('digest') or ''
        if (asset.get('name') == name and asset.get('browser_download_url') == url
                and re.fullmatch(r'sha256:[0-9a-f]{64}', digest)):
            return Release(version, name, url, digest.removeprefix('sha256:'))
    raise ValueError('Release is missing a verified Debian package')


def open_github(url):
    return urlopen(Request(url, headers={'User-Agent': 'PinPlan-Notes-Updater'}), timeout=15)


def check_for_update(current):
    with open_github(LATEST_API) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError('Release metadata is too large')
    return select_release(json.loads(data), current)


def can_install_update():
    if (os.environ.get('SNAP') or Path('/.flatpak-info').exists()
            or not all(os.access(path, os.X_OK) for path in
                       ('/usr/bin/pkexec', '/usr/bin/apt-get', '/usr/bin/dpkg-query'))):
        return False
    result = subprocess.run(
        ['/usr/bin/dpkg-query', '-W', '-f=${db:Status-Status}', 'pinplan-notes'],
        capture_output=True, text=True, timeout=5, check=False,
    )
    return result.returncode == 0 and result.stdout == 'installed'


def install_update(release):
    with TemporaryDirectory(prefix='pinplan-update-') as directory:
        package = Path(directory) / release.name
        digest = hashlib.sha256()
        size = 0
        with open_github(release.url) as response, package.open('xb') as output:
            while chunk := response.read(64 * 1024):
                size += len(chunk)
                if size > MAX_PACKAGE_SIZE:
                    raise ValueError('Release package is too large')
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != release.sha256:
            raise ValueError('Release package checksum mismatch')

        result = subprocess.run(
            ['/usr/bin/pkexec', '/usr/bin/apt-get', '--assume-yes',
             '--no-remove', '--no-install-recommends', 'install', str(package)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
        )
        if result.returncode == 126:
            return False
        result.check_returncode()
        return True
