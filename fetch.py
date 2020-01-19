import json
import tempfile
import re
import hashlib
import tarfile

from pygit2 import Repository, clone_repository
from datetime import datetime, timezone, timedelta
from pathlib import Path

root = 'git-helm.herokuapp.com'
url = 'https://Kjoep:XWExxnmCfwd3WBuUrXEy@gitlab.com/flexgrid/flexgrid-api.git'

with tempfile.TemporaryDirectory() as workdir:
    matcher = re.match(r'https?://([^:]*:[^@]*@)?([^/]+/(.+)\.git)$', url)
    if not matcher:
        raise Exception('Invalid url given: '+url)
    credentials = matcher.group(1)
    safe_url = 'http://' + matcher.group(2)
    path = matcher.group(2)
    name = matcher.group(3)
    repo: Repository = clone_repository(url, workdir)

    def chart_def(reference: str):
        if 'refs/remotes/origin/' in reference:
            return versioned_chart_def(reference, version_from_branch)
        elif 'refs/tags/' in reference:
            return versioned_chart_def(reference, version_from_tag)
        else:
            return None

    def versioned_chart_def(reference: str, versioning_fn):
        repo.checkout(reference)
        commit = repo.revparse_single('HEAD')
        short_hash = commit.short_id
        long_hash = commit.hex
        ts = datetime.fromtimestamp(commit.commit_time, timezone(timedelta(minutes=commit.commit_time_offset))).isoformat()
        if not Path(f'{workdir}/helm').is_dir():
            return None
        version, long_version = versioning_fn(reference, short_hash)

        digest = sha256(create_helm_package(version, long_version))

        return {
            "created": ts,
            "description": name,
            "digest": digest,
            "name": name,
            "sources": safe_url,
            "urls": [
                f"https://{credentials}{root}/{path}/{reference}/{long_version}.tgz"
            ],
            "version": f'{long_version}',
            "appVersion": long_hash
        }


    def version_from_branch(reference: str, short_hash: str):
        try:
            version = repo.describe(describe_strategy=1)
            version = version.split('-')[0].split('.')
            version = f'{version[0]}.{int(version[1]) + 1}.{version[2]}'
            return version, f'{version}-{short_hash}'
        except Exception:
            return '0.1.0', f'0.1.0-{short_hash}'

    def version_from_tag(reference: str, short_hash: str):
        version = reference.split('/tags/')[-1]
        return version, f'{version}-{short_hash}'

    def create_helm_package(version: str, long_version: str):
        # todo:
        with tarfile.open('/tmp/helm.tgz', 'w:gz') as tar:
            tar.add(f'{workdir}/helm')
        return '/tmp/helm.tgz'

    def sha256(filename: str):
        hasher = hashlib.sha256()
        with open(filename, 'rb') as afile:
            buf = afile.read()
            hasher.update(buf)
        return hasher.hexdigest()

    chart_defs = [chart_def(ref) for ref in repo.references]
    chart_defs = [d for d in chart_defs if d]

    print(json.dumps(chart_defs, indent=2))
