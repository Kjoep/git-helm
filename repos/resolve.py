from typing import Optional

from repos.git_repo import GitRepository
from repos.repositories import Repository


def get_repo(qualifier: str, app_root: str, credentials: Optional[dict]) -> Repository:
    credential_string = f'{credentials.username}:{credentials.password}@' if credentials else ''
    return GitRepository(f'https://{credential_string}{qualifier}', app_root)
