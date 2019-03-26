from repos.repositories import Repository

import json
import tempfile
import re
import hashlib
import tarfile

from pygit2 import Repository as GitRepo, clone_repository
from datetime import datetime, timezone, timedelta
from pathlib import Path


def _version_from_branch(repo: GitRepo, reference: str, short_hash: str):
    try:
        version = repo.describe(describe_strategy=1)
        version = version.split('-')[0].split('.')
        version = f'{version[0]}.{int(version[1]) + 1}.{version[2]}'
        return version, f'{version}-{short_hash}'
    except Exception:
        return '0.1.0', f'0.1.0-{short_hash}'


def _version_from_tag(self, reference: str, short_hash: str):
    version = reference.split('/tags/')[-1]
    return version, f'{version}-{short_hash}'


def _sha256(filename: str):
    hasher = hashlib.sha256()
    with open(filename, 'rb') as afile:
        buf = afile.read()
        hasher.update(buf)
    return hasher.hexdigest()


class GitRepository(Repository):
    def __init__(self, url, app_root):
        matcher = re.match(r'https?://([^:]*:[^@]*@)?([^/]+/(.+)\.git)$', url)
        if not matcher:
            raise ValueError(f'Invalid url given: {url}')
        self.url = url
        self.app_root = app_root
        self.credentials = matcher.group(1)
        self.safe_url = 'http://' + matcher.group(2)
        self.path = matcher.group(2)
        self.name = matcher.group(3)

    def generate_index(self) -> dict:
        with tempfile.TemporaryDirectory() as workdir:

            print(f'cloning ${self.url}')
            repo: Repository = clone_repository(self.url, workdir)

            chart_defs = [self._chart_def(repo, workdir, ref) for ref in repo.references]
            chart_defs = [d for d in chart_defs if d]

            return {
                "apiVersion": "v1",
                "entries": self._by_name(chart_defs)
            }

    def _chart_def(self, repo: GitRepo, workdir: str, reference: str):
        if 'refs/remotes/origin/' in reference:
            return self._versioned_chart_def(repo, workdir, reference, _version_from_branch)
        elif 'refs/tags/' in reference:
            return self._versioned_chart_def(repo, workdir, reference, _version_from_tag)
        else:
            return None

    def _versioned_chart_def(self, repo: GitRepo, workdir: str, reference: str, versioning_fn):
        repo.checkout(reference)
        commit = repo.revparse_single('HEAD')
        short_hash = commit.short_id
        long_hash = commit.hex
        ts = datetime.fromtimestamp(commit.commit_time,
                                    timezone(timedelta(minutes=commit.commit_time_offset))).isoformat()
        if not Path(f'{workdir}/helm').is_dir():
            return None
        version, long_version = versioning_fn(repo, reference, short_hash)

        digest = _sha256(self._create_helm_package(workdir, version, long_version))

        return {
            "apiVersion": "v1",
            "created": ts,
            "description": self.name,
            "digest": digest,
            "name": self.name,
            "sources": self.safe_url,
            "urls": [
                f"https://{self.credentials}{self.app_root}/{self.path}/{reference}/{long_version}.tgz"
            ],
            "version": f'{long_version}',
            "appVersion": long_hash
        }

    def _create_helm_package(self, workdir: str, version: str, long_version: str):
        # todo:
        with tarfile.open('/tmp/helm.tgz', 'w:gz') as tar:
            tar.add(f'{workdir}/helm')
        return '/tmp/helm.tgz'

    def _by_name(self, defs: [str]):
        result = {}
        for definition in defs:
            if not definition['name'] in result:
                result[definition['name']] = []
            result[definition['name']].append(definition)
        return result



