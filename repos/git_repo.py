import io
from _pygit2 import GIT_RESET_HARD

from repos.repositories import Repository

import json
import tempfile
import re
import hashlib
import tarfile
import yaml

from pygit2 import Repository as GitRepo, clone_repository
from datetime import datetime, timezone, timedelta
from pathlib import Path

semver_pattern = re.compile(r'^((0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*))(?:-(0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)'
                            r'(\.(0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*)?(\+[0-9a-zA-Z-]+(\.[0-9a-zA-Z-]+)*)?$')
semver_pattern_grp_prerelease = 5
semver_pattern_grp_version = 1
semver_pattern_grp_meta = 8

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
    return version, f'{version}+{short_hash}'


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
            repo: GitRepo = clone_repository(self.url, workdir)

            chart_defs = [self._chart_def(repo, workdir, ref) for ref in repo.references]
            chart_defs = [d for d in chart_defs if d]

            return {
                "apiVersion": "v1",
                "entries": self._by_name(chart_defs)
            }

    def fetch(self, name, version):
        semver = semver_pattern.match(version)
        if not semver:
            raise ValueError
        if semver.group(semver_pattern_grp_prerelease):
            return self._fetch_commit(semver.group(semver_pattern_grp_prerelease))
        else:
            return self._fetch_commit(semver.group(semver_pattern_grp_version))

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

        repo.reset(long_hash, GIT_RESET_HARD)

        return {
            "apiVersion": "v1",
            "created": ts,
            "description": self.name,
            "digest": digest,
            "name": self.name,
            "sources": [self.safe_url],
            "urls": [
                f"https://{self.credentials}{self.app_root}/{self.path}/"
                f"charts/{self.name.replace('/', '%20')}-{long_version}.tgz"
            ],
            "version": f'{long_version}',
            "appVersion": long_hash
        }

    def _fetch_commit(self, hash):
        with tempfile.TemporaryDirectory() as workdir:

            print(f'cloning ${self.url}')
            repo: GitRepo = clone_repository(self.url, workdir)

            commit = repo.revparse_single(hash)
            repo.checkout_tree(commit)
            filename = self._create_helm_package(workdir, hash, str(commit.id))
            with open(filename, 'rb') as content:
                return io.BytesIO(content.read())

    def _create_helm_package(self, workdir: str, version: str, long_version: str):
        chart_details = yaml.load(open(f'{workdir}/helm/Chart.yaml', 'r'))
        chart_details['version'] = version
        chart_details['appVersion'] = long_version
        yaml.dump(chart_details, open(f'{workdir}/helm/Chart.yaml', 'w'))

        values_details = yaml.load(open(f'{workdir}/helm/values.yaml', 'r'))
        values_details['image']['tag'] = version
        yaml.dump(values_details, open(f'{workdir}/helm/values.yaml', 'w'))

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



