import re
import subprocess
from typing import Optional


def get_origin_url(repo_path: str) -> str:
    completed = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def run_git(repo_path: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )


def get_github_repo_slug(repo_path: str) -> str:
    origin_url = get_origin_url(repo_path)

    https_match = re.match(r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?$", origin_url)
    if https_match:
        return https_match.group(1)

    ssh_match = re.match(r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?$", origin_url)
    if ssh_match:
        return ssh_match.group(1)

    raise ValueError(f"Unsupported GitHub origin URL format: {origin_url}")


def get_default_branch(repo_path: str) -> str:
    completed = run_git(repo_path, ["symbolic-ref", "refs/remotes/origin/HEAD"])
    if completed.returncode == 0:
        ref = completed.stdout.strip()
        return ref.split("/")[-1]

    for candidate in ("main", "master"):
        probe = run_git(repo_path, ["rev-parse", "--verify", f"origin/{candidate}"])
        if probe.returncode == 0:
            return candidate

    raise ValueError(f"Unable to determine default branch for {repo_path}")


def has_uncommitted_changes(repo_path: str) -> bool:
    completed = run_git(repo_path, ["status", "--porcelain"])
    return bool(completed.stdout.strip())


def commit_all_if_dirty(repo_path: str, message: str) -> Optional[str]:
    if not has_uncommitted_changes(repo_path):
        return None

    add = run_git(repo_path, ["add", "-A"])
    if add.returncode != 0:
        raise RuntimeError((add.stderr or add.stdout).strip() or "git add failed")

    commit = run_git(repo_path, ["commit", "-m", message])
    if commit.returncode != 0:
        raise RuntimeError((commit.stderr or commit.stdout).strip() or "git commit failed")

    return (commit.stdout or commit.stderr).strip()


def has_commits_ahead_of_default(repo_path: str, branch: str) -> bool:
    default_branch = get_default_branch(repo_path)
    run_git(repo_path, ["fetch", "origin", default_branch])
    completed = run_git(
        repo_path,
        ["rev-list", "--left-right", "--count", f"origin/{default_branch}...{branch}"],
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip() or "git rev-list failed")

    _, ahead = completed.stdout.strip().split()
    return int(ahead) > 0


def create_empty_commit(repo_path: str, message: str) -> str:
    completed = run_git(repo_path, ["commit", "--allow-empty", "-m", message])
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip() or "empty commit failed")
    return (completed.stdout or completed.stderr).strip()


def push_branch(repo_path: str, branch: str) -> str:
    completed = run_git(repo_path, ["push", "--set-upstream", "origin", branch])
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip() or "git push failed")
    return (completed.stdout or completed.stderr).strip()
