import re
import subprocess


def get_origin_url(repo_path: str) -> str:
    completed = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def get_github_repo_slug(repo_path: str) -> str:
    origin_url = get_origin_url(repo_path)

    https_match = re.match(r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?$", origin_url)
    if https_match:
        return https_match.group(1)

    ssh_match = re.match(r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?$", origin_url)
    if ssh_match:
        return ssh_match.group(1)

    raise ValueError(f"Unsupported GitHub origin URL format: {origin_url}")
