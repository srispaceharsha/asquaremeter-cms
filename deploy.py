#!/usr/bin/env python3
"""
deploy.py - Build site and deploy to public repository

Usage:
    python deploy.py                    # Build and copy to public repo
    python deploy.py --commit "message" # Build, copy, and commit
    python deploy.py --push             # Build, copy, commit, and push
"""

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
SITE_PATH = PROJECT_ROOT / "site"
PUBLIC_REPO = PROJECT_ROOT.parent / "asquaremeter-public"


def run_command(cmd: list, cwd: Path = None) -> bool:
    """Run a shell command and return success status"""
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return False
        if result.stdout.strip():
            print(result.stdout.strip())
        return True
    except Exception as e:
        print(f"Error running {' '.join(cmd)}: {e}")
        return False


def build_site() -> bool:
    """Run the build script"""
    print("Building site...")
    result = subprocess.run(
        [sys.executable, "build.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"Build failed: {result.stderr}")
        return False
    return True


def copy_to_public() -> bool:
    """Copy built site to public repository"""
    if not PUBLIC_REPO.exists():
        print(f"Error: Public repo not found at {PUBLIC_REPO}")
        print("Create it with: git init ../asquaremeter-public")
        return False

    print(f"\nCopying to {PUBLIC_REPO}...")

    # Remove old files (except .git and .gitignore)
    for item in PUBLIC_REPO.iterdir():
        if item.name in ('.git', '.gitignore'):
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    # Copy new files
    for item in SITE_PATH.iterdir():
        dest = PUBLIC_REPO / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    print("Copied successfully.")
    return True


def git_commit(message: str) -> bool:
    """Stage all changes and commit"""
    print(f"\nCommitting: {message}")

    if not run_command(["git", "add", "-A"], cwd=PUBLIC_REPO):
        return False

    # Check if there are changes to commit
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PUBLIC_REPO,
        capture_output=True,
        text=True
    )

    if not result.stdout.strip():
        print("No changes to commit.")
        return True

    return run_command(["git", "commit", "-m", message], cwd=PUBLIC_REPO)


def git_push() -> bool:
    """Push to remote"""
    print("\nPushing to remote...")
    return run_command(["git", "push"], cwd=PUBLIC_REPO)


def main():
    parser = argparse.ArgumentParser(description="Build and deploy to public repository")
    parser.add_argument("--commit", "-c", metavar="MSG", help="Commit with message")
    parser.add_argument("--push", "-p", action="store_true", help="Push after commit")
    parser.add_argument("--message", "-m", metavar="MSG", help="Commit message (alternative to --commit)")

    args = parser.parse_args()

    # Determine commit message
    commit_msg = args.commit or args.message

    # If --push but no message, use default
    if args.push and not commit_msg:
        commit_msg = f"Update site - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    # Build
    if not build_site():
        sys.exit(1)

    # Copy to public repo
    if not copy_to_public():
        sys.exit(1)

    # Commit if message provided
    if commit_msg:
        if not git_commit(commit_msg):
            sys.exit(1)

    # Push if requested
    if args.push:
        if not git_push():
            sys.exit(1)

    print("\nDone!")


if __name__ == "__main__":
    main()
