#!/usr/bin/env bash
set -euo pipefail

TARGET="yulliwasameur/Introduction_a_la_cryptographie"
EXPECTED_USER="yulliwasameur"
REPO_URL="https://github.com/${TARGET}.git"
SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/cigma-private-push.XXXXXX")"
CLONE_DIR="${WORK_ROOT}/repository"
trap 'rm -rf "$WORK_ROOT"' EXIT

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required." >&2
  exit 1
fi
if ! command -v rsync >/dev/null 2>&1; then
  echo "ERROR: rsync is required." >&2
  exit 1
fi

if command -v gh >/dev/null 2>&1; then
  gh auth status >/dev/null
  ACTUAL_USER="$(gh api user --jq .login)"
  if [[ "$ACTUAL_USER" != "$EXPECTED_USER" ]]; then
    echo "ERROR: authenticated GitHub user is '$ACTUAL_USER', expected '$EXPECTED_USER'." >&2
    exit 1
  fi
  VISIBILITY="$(gh repo view "$TARGET" --json visibility --jq .visibility)"
  if [[ "${VISIBILITY,,}" != "private" ]]; then
    echo "ERROR: refusing to publish because $TARGET is not private (visibility=$VISIBILITY)." >&2
    exit 1
  fi
  gh repo clone "$TARGET" "$CLONE_DIR"
else
  echo "GitHub CLI not found; using Git HTTPS credentials." >&2
  git clone "$REPO_URL" "$CLONE_DIR"
fi

REMOTE_URL="$(git -C "$CLONE_DIR" remote get-url origin)"
case "$REMOTE_URL" in
  *"github.com/${TARGET}"*|*"github.com:${TARGET}"*) ;;
  *)
    echo "ERROR: cloned unexpected remote: $REMOTE_URL" >&2
    exit 1
    ;;
esac

rsync -a --delete \
  --exclude '.git/' \
  --exclude '.pytest_cache/' \
  --exclude '__pycache__/' \
  --exclude '.venv/' \
  --exclude 'venv/' \
  --exclude 'build/' \
  --exclude 'dist/' \
  "$SOURCE_ROOT/" "$CLONE_DIR/"

find "$CLONE_DIR" -type d -name __pycache__ -prune -exec rm -rf {} +
rm -rf "$CLONE_DIR/.pytest_cache" "$CLONE_DIR/build" "$CLONE_DIR/dist"

git -C "$CLONE_DIR" config user.name "Yulliwas Ameur"
git -C "$CLONE_DIR" config user.email "yulliwas.ameur@efrei.fr"
git -C "$CLONE_DIR" add -A
if git -C "$CLONE_DIR" diff --cached --quiet; then
  echo "Remote tree already matches the clean-room handoff; no branch commit required."
else
  git -C "$CLONE_DIR" commit -m "Add CIGMA clean-room reference implementation v0.1.0"
  git -C "$CLONE_DIR" push origin main
fi

git -C "$CLONE_DIR" tag -f -a v0.1.0-clean-room \
  -m "CIGMA clean-room reference implementation v0.1.0"
git -C "$CLONE_DIR" push origin refs/tags/v0.1.0-clean-room --force-with-lease

HEAD_SHA="$(git -C "$CLONE_DIR" rev-parse HEAD)"
echo "Published private repository: https://github.com/$TARGET"
echo "Remote commit: $HEAD_SHA"
echo "Tag: v0.1.0-clean-room"
if command -v gh >/dev/null 2>&1; then
  gh repo view "$TARGET" --json nameWithOwner,visibility,defaultBranchRef,url
fi
