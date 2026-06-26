"""Tests for `git_ops` covering the rework hardening (C1, C2, C4).

* Concurrency: two threads commit ADRs through the same Repo and we
  must see two distinct ADR numbers, two distinct branches, and no
  exception.
* Invalid HEAD: we corrupt HEAD's reference and `ensure_repo` must
  fall back to `iter_commits` rather than crashing.
* Slug duplicate: committing twice with the same title must raise
  `BranchAlreadyExistsError` (the handler maps this to HTTP 409).
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Iterator

import pytest
from git import Repo as GitRepo

from app import git_ops


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_repo(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    tmp = Path(tempfile.mkdtemp(prefix="adr-gitops-test-"))
    monkeypatch.setenv("ADR_REPO_PATH", str(tmp))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from app.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield tmp
    get_settings.cache_clear()  # type: ignore[attr-defined]


def _commit_one(repo: GitRepo, title: str, content: str = "body") -> str:
    """Helper: drive `git_ops.commit_adr` for one ADR."""
    from app.git_ops import commit_adr, get_next_adr_number

    with git_ops._repo_lock:
        number = get_next_adr_number(repo)
        filename = f"{number:04d}-{title.lower().replace(' ', '-')}.md"
        branch, sha = commit_adr(
            repo=repo,
            filename=filename,
            content=content,
            adr_number=number,
            title=title,
        )
    return branch


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------

def test_concurrent_commits_get_distinct_numbers(temp_repo: Path) -> None:
    """N threads commit simultaneously — we must see N distinct numbers."""
    repo = git_ops.ensure_repo(temp_repo)

    results: list[tuple[str, int]] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker(idx: int) -> None:
        try:
            barrier.wait(timeout=5)
            # Acquire the same lock the handler does, so the test is
            # really exercising the contended path.
            with git_ops._repo_lock:
                number = git_ops.get_next_adr_number(repo)
                filename = f"{number:04d}-thread-{idx}.md"
                branch, sha = git_ops.commit_adr(
                    repo=repo,
                    filename=filename,
                    content=f"# thread {idx}",
                    adr_number=number,
                    title=f"thread {idx}",
                )
            results.append((branch, number))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"worker errors: {errors}"
    assert len(results) == 8

    numbers = sorted(n for _, n in results)
    assert numbers == list(range(1, 9)), (
        f"Expected sequential 1..8 numbers under lock; got {numbers}"
    )

    branches = {b for b, _ in results}
    assert len(branches) == 8, "all branches must be distinct"


# ---------------------------------------------------------------------------
# Invalid HEAD
# ---------------------------------------------------------------------------

def test_ensure_repo_handles_invalid_head(temp_repo: Path) -> None:
    """A HEAD ref pointing to nowhere must not crash ensure_repo."""
    # Bootstrap a normal repo first.
    repo = git_ops.ensure_repo(temp_repo)
    assert git_ops._repo_has_commits(repo)

    # Now break HEAD by pointing it at a non-existent ref.
    repo.git.symbolic_ref("HEAD", "refs/heads/this-branch-does-not-exist")
    # `head.is_valid()` is allowed to return False; the hardening also
    # has to be safe if it raises GitCommandError — exercise the
    # internal helper directly.
    try:
        from git.exc import GitCommandError
    except ImportError:  # pragma: no cover - GitPython is a hard dep
        GitCommandError = Exception  # type: ignore[assignment,misc]

    # Sanity: under the broken ref, the helper must still return True
    # (we have one bootstrap commit reachable through object DB).
    assert git_ops._repo_has_commits(repo) is True

    # And ensure_repo must be idempotent on the broken repo.
    repo2 = git_ops.ensure_repo(temp_repo)
    assert isinstance(repo2, GitRepo)
    assert git_ops._repo_has_commits(repo2) is True


# ---------------------------------------------------------------------------
# Slug duplicate
# ---------------------------------------------------------------------------

def test_commit_adr_refuses_existing_branch(temp_repo: Path) -> None:
    """A pre-existing branch must trigger BranchAlreadyExistsError → 409."""
    from app.git_ops import BranchAlreadyExistsError, commit_adr

    repo = git_ops.ensure_repo(temp_repo)

    # Manually create the branch the handler would otherwise create on
    # first commit — that's what `checkout -B <branch>` used to silently
    # overwrite before the rework.
    target_branch = "adr/0007-something-existing"
    repo.git.checkout("-B", target_branch)
    (temp_repo / "docs" / "adr" / "0007-something-existing.md").write_text(
        "placeholder", encoding="utf-8"
    )
    repo.index.add(["docs/adr/0007-something-existing.md"])
    repo.index.commit("seed existing branch")
    # Move HEAD back to main so commit_adr has somewhere to switch from.
    repo.git.checkout("main")

    with git_ops._repo_lock:
        with pytest.raises(BranchAlreadyExistsError) as excinfo:
            commit_adr(
                repo=repo,
                filename="0007-something-existing.md",
                content="# new body",
                adr_number=7,
                title="Something existing",
            )
    assert excinfo.value.branch == target_branch


def test_commit_adr_succeeds_when_branch_missing(temp_repo: Path) -> None:
    """Happy path: a fresh ADR number → fresh branch → commit."""
    from app.git_ops import commit_adr

    repo = git_ops.ensure_repo(temp_repo)

    with git_ops._repo_lock:
        branch, sha = commit_adr(
            repo=repo,
            filename="0001-something-fresh.md",
            content="# fresh",
            adr_number=1,
            title="Something fresh",
        )
    assert branch == "adr/0001-something-fresh"
    assert len(sha) == 40


# ---------------------------------------------------------------------------
# Push helper
# ---------------------------------------------------------------------------

def test_push_branch_without_remote_is_noop(temp_repo: Path) -> None:
    """If `origin` is not configured, `push_branch` returns cleanly."""
    repo = git_ops.ensure_repo(temp_repo)
    branch = _commit_one(repo, "No remote push test", content="x")
    # Should not raise even though there is no remote.
    git_ops.push_branch(repo, branch)


def test_authed_remote_url_injects_token() -> None:
    url = "https://github.com/owner/repo.git"
    out = git_ops._authed_remote_url(url, "secrettoken")
    assert out == "https://x-access-token:secrettoken@github.com/owner/repo.git"


def test_authed_remote_url_is_idempotent() -> None:
    url = "https://x-access-token:abc@github.com/owner/repo.git"
    assert git_ops._authed_remote_url(url, "abc") == url


def test_authed_remote_url_ignores_non_github() -> None:
    url = "https://gitlab.com/owner/repo.git"
    assert git_ops._authed_remote_url(url, "abc") == url