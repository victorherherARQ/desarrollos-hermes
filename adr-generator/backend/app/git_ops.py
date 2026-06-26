"""Git operations for the ADR repository.

Responsibilities:
    * `ensure_repo`            — initialise a fresh local repo on first
                                  run, with `docs/adr/` directory and a
                                  `.gitkeep` placeholder.
    * `get_next_adr_number`    — count existing `NNN-*.md` files.
    * `commit_adr`             — create `adr/NNN-slug` branch, commit
                                  the file, return the commit SHA.
    * `create_pull_request`    — push the branch then open a PR via
                                  the GitHub REST API (handles 422
                                  "PR already exists" by returning the
                                  existing PR URL).
    * `list_adrs`              — enumerate committed ADRs.

Hardening (rework):
    * `threading.Lock` serialises concurrent commit/number requests
      so we never produce duplicate ADR numbers or stomp on a branch.
    * `ensure_repo` no longer crashes when HEAD points to a missing
      ref — we fall back to `iter_commits`.
    * `create_pull_request` pushes the branch first and tolerates 422.
"""

from __future__ import annotations

import re
import subprocess
import threading
from pathlib import Path
from typing import List, Optional, Tuple

import httpx
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError

from .config import get_settings
from .models import AdrListItem


# ---------------------------------------------------------------------------
# Process-wide lock for commit + numbering
# ---------------------------------------------------------------------------
#
# All write paths that touch the on-disk ADR directory go through this lock
# so two concurrent /generate requests can't observe the same ADR number
# or both try to reset the same branch.
_repo_lock = threading.Lock()


class BranchAlreadyExistsError(Exception):
    """Raised when the target adr/NNN-slug branch already exists.

    Surfaced as HTTP 409 by the FastAPI handler.
    """

    def __init__(self, branch: str) -> None:
        super().__init__(f"branch {branch!r} already exists")
        self.branch = branch


# ---------------------------------------------------------------------------
# Repo lifecycle
# ---------------------------------------------------------------------------

def ensure_repo(repo_path: str | Path) -> Repo:
    """Initialise the ADR repo if missing; return a live `Repo` handle.

    On first run the function:
        1. `git init` the path.
        2. Create `docs/adr/` with a `.gitkeep` placeholder.
        3. Configure a local user.name / user.email so commits work.
        4. Make an initial commit on the default branch.

    Robust against a corrupt HEAD (e.g. reflog pointing to a deleted
    branch): we try `repo.head.is_valid()` and fall back to
    `iter_commits()` on `GitCommandError`.
    """
    path = Path(repo_path).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)

    try:
        repo = Repo(path)
    except InvalidGitRepositoryError:
        repo = Repo.init(path)
        _configure_local_identity(repo)
        # Make sure the default branch is named `main`.
        try:
            repo.git.symbolic_ref("HEAD", "refs/heads/main")
        except Exception:  # noqa: BLE001 - older git may refuse, ignore
            pass

    adr_dir = path / "docs" / "adr"
    adr_dir.mkdir(parents=True, exist_ok=True)
    keep = adr_dir / ".gitkeep"
    if not keep.exists():
        keep.write_text("# Keeps the ADR directory under version control.\n",
                        encoding="utf-8")

    # Robust HEAD check: GitCommandError can leak from `head.is_valid()`
    # when HEAD points to a non-existent ref. Use iter_commits() as the
    # source of truth in that case.
    has_commits = _repo_has_commits(repo)
    if not has_commits:
        repo.index.add([str(keep.relative_to(path))])
        repo.index.commit("chore: bootstrap ADR repository")
        try:
            repo.git.checkout("-B", "main")
        except Exception:  # noqa: BLE001
            pass

    return repo


def _repo_has_commits(repo: Repo) -> bool:
    """Return True iff the repo has at least one reachable commit.

    `repo.head.is_valid()` raises `GitCommandError` (or even `ValueError`
    via the symbolic-ref dereference machinery) for orphaned HEADs, e.g.
    right after `Repo.init` where HEAD points to `refs/heads/main` but
    the ref hasn't been created yet. `iter_commits()` has the same
    problem because it dereferences HEAD internally.

    The cheapest, safest signal is therefore `repo.heads` — it lists
    the contents of `.git/refs/heads/` *without* dereferencing HEAD.
    As a fallback for packed-only repos we also peek at `packed-refs`.
    """
    try:
        if any(True for _ in repo.heads):
            return True
    except (GitCommandError, ValueError, OSError):
        pass
    return _has_packed_head_ref(repo)


def _has_packed_head_ref(repo: Repo) -> bool:
    """Return True if `packed-refs` mentions any refs/heads/* entry."""
    packed = Path(repo.common_dir) / "packed-refs"
    try:
        with packed.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "refs/heads/" in line:
                    return True
    except OSError:
        return False
    return False


def _configure_local_identity(repo: Repo) -> None:
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", "ADR Generator Bot")
        cfg.set_value("user", "email", "adr-bot@example.invalid")


# ---------------------------------------------------------------------------
# ADR numbering
# ---------------------------------------------------------------------------

ADR_FILENAME_RE = re.compile(r"^(\d{4,5})-.*\.md$")


def get_next_adr_number(repo: Repo) -> int:
    """Return the next ADR number based on existing files in `docs/adr/`.

    Callers must hold `_repo_lock` when they want consistency with
    `commit_adr`. Reading alone is safe but races with concurrent
    writers — `commit_adr` documents this requirement.
    """
    adr_dir = Path(repo.working_tree_dir or ".") / "docs" / "adr"
    if not adr_dir.exists():
        return 1
    numbers: List[int] = []
    for f in adr_dir.iterdir():
        if not f.is_file():
            continue
        m = ADR_FILENAME_RE.match(f.name)
        if m:
            try:
                numbers.append(int(m.group(1)))
            except ValueError:
                continue
    return (max(numbers) if numbers else 0) + 1


# ---------------------------------------------------------------------------
# Branch & commit
# ---------------------------------------------------------------------------

def _slugify(title: str, max_len: int = 60) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s[:max_len] or "adr"


def commit_adr(
    repo: Repo,
    filename: str,
    content: str,
    adr_number: int,
    title: str,
) -> Tuple[str, str]:
    """Write the ADR file on a fresh branch and commit it.

    Returns `(branch_name, commit_sha)`. The repo is left on the new
    branch so a subsequent push will push exactly the new file.

    Concurrency:
        The branch-existence check + checkout + commit must be atomic
        across processes — callers MUST hold `_repo_lock` (the FastAPI
        handler does this in `main.py`). If the branch already exists
        we raise `BranchAlreadyExistsError` instead of silently
        resetting it.
    """
    settings = get_settings()
    repo_root = Path(repo.working_tree_dir or ".")
    adr_dir = repo_root / "docs" / "adr"
    adr_dir.mkdir(parents=True, exist_ok=True)

    target = adr_dir / filename
    target.write_text(content, encoding="utf-8")

    # Branch name: adr/<NNN>-<slug>
    branch_name = f"{settings.ADR_BRANCH_PREFIX}{adr_number:04d}-{_slugify(title)}"

    # Refuse to clobber an existing branch — this is the lock-protected
    # counterpart to the unsafe `checkout -B` we had before.
    existing_branches = {h.name for h in repo.heads}
    if branch_name in existing_branches:
        raise BranchAlreadyExistsError(branch_name)

    repo.git.checkout("-B", branch_name)

    repo.index.add([str(target.relative_to(repo_root))])
    commit = repo.index.commit(
        f"docs(adr): {adr_number:04d} {title[:60]}"
    )

    return branch_name, commit.hexsha


def push_branch(repo: Repo, branch: str) -> None:
    """Push the given branch to `origin`, configuring auth if a token is set.

    This is best-effort: callers that don't need PR creation can ignore
    network failures. When `GITHUB_TOKEN` is configured we rewrite the
    `origin` URL to embed it so pushes don't prompt for credentials.
    """
    settings = get_settings()
    try:
        origin = repo.remote("origin")
    except ValueError:
        # No remote configured — nothing to push.
        return

    if settings.GITHUB_TOKEN:
        authed_url = _authed_remote_url(origin.url, settings.GITHUB_TOKEN)
        if authed_url:
            origin.set_url(authed_url)

    origin.push(refspec=f"refs/heads/{branch}:refs/heads/{branch}",
                set_upstream=True)


def _authed_remote_url(url: str, token: str) -> str:
    """Inject `x-access-token:TOKEN` into a GitHub remote URL."""
    if not url or not token:
        return url or ""
    if "@" in url:  # already has credentials
        return url
    if url.startswith("https://github.com/"):
        return url.replace(
            "https://",
            f"https://x-access-token:{token}@",
            1,
        )
    return url


# ---------------------------------------------------------------------------
# GitHub PR
# ---------------------------------------------------------------------------

def create_pull_request(
    repo: Repo,
    branch: str,
    title: str,
    body: str,
    *,
    base: str = "main",
) -> Optional[str]:
    """Push `branch` to origin and open a PR on GitHub.

    Returns the PR URL or `None` on failure. A 422 ("PR already exists")
    is treated as success — we GET the existing PR and return its URL
    so the caller doesn't need to special-case this race.
    """
    settings = get_settings()
    if not settings.github_enabled:
        return None

    # 1. Push first — otherwise the PR will reference a non-existent ref.
    try:
        push_branch(repo, branch)
    except Exception:  # noqa: BLE001 - push is best-effort for PR callers
        # Fall through to the PR call; if it fails we surface that too.
        pass

    url = f"https://api.github.com/repos/{settings.GITHUB_REPO}/pulls"
    headers = {
        "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "adr-generator",
    }
    payload = {
        "title": title,
        "head": branch,
        "base": base,
        "body": body,
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=15.0)
    except httpx.HTTPError:
        return None
    if resp.status_code in (200, 201):
        return resp.json().get("html_url")

    # 422: validation failed — most commonly "A pull request already
    # exists for <branch>". Find the existing PR and return its URL.
    if resp.status_code == 422:
        existing = _find_existing_pr(branch, base, settings, headers)
        if existing:
            return existing
    return None


def _find_existing_pr(
    branch: str,
    base: str,
    settings: Any,
    headers: dict,
) -> Optional[str]:
    url = (
        f"https://api.github.com/repos/{settings.GITHUB_REPO}/pulls"
        f"?head={settings.GITHUB_REPO.split('/')[0]}:{branch}&base={base}&state=open"
    )
    try:
        resp = httpx.get(url, headers=headers, timeout=15.0)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    data = resp.json()
    if isinstance(data, list) and data:
        return data[0].get("html_url")
    return None


# ---------------------------------------------------------------------------
# Read API for /adrs
# ---------------------------------------------------------------------------

def list_adrs(repo: Repo) -> List[AdrListItem]:
    """Enumerate committed ADRs in `docs/adr/`."""
    repo_root = Path(repo.working_tree_dir or ".")
    adr_dir = repo_root / "docs" / "adr"
    items: List[AdrListItem] = []
    if not adr_dir.exists():
        return items
    for f in sorted(adr_dir.iterdir()):
        if not f.is_file():
            continue
        m = ADR_FILENAME_RE.match(f.name)
        if not m:
            continue
        number = int(m.group(1))
        title, status = _read_frontmatter(f)
        items.append(AdrListItem(number=number, filename=f.name,
                                 status=status, title=title))
    return items


def _read_frontmatter(path: Path) -> Tuple[Optional[str], Optional[str]]:
    """Very small YAML-frontmatter reader — title + status only."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, None
    if not text.startswith("---"):
        return None, None
    end = text.find("\n---", 3)
    if end == -1:
        return None, None
    block = text[3:end]
    title = None
    status = None
    for line in block.splitlines():
        if line.startswith("title:"):
            title = line.split(":", 1)[1].strip().strip('"')
        elif line.startswith("status:"):
            status = line.split(":", 1)[1].strip().strip('"')
    return title, status


# Re-export subprocess for tests that want to assert git was invoked.
__all__ = [
    "ensure_repo",
    "get_next_adr_number",
    "commit_adr",
    "push_branch",
    "create_pull_request",
    "list_adrs",
    "ADR_FILENAME_RE",
    "BranchAlreadyExistsError",
    "_repo_lock",
    "subprocess",  # for test patches
]