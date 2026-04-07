#!/usr/bin/env bash
set -euo pipefail

# Release script for juris
# Detects version bump type from conventional commits and creates a git tag.
#
# Usage:
#   ./scripts/release.sh [patch|minor|major]
#
# If no argument is given, the bump type is inferred from commit messages
# since the last tag using conventional commit prefixes:
#   - BREAKING CHANGE / feat!: / fix!: -> major
#   - feat:                             -> minor
#   - fix: / perf: / docs: / test:      -> patch

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Ensure we're on main and the tree is clean
current_branch=$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD)
if [[ "$current_branch" != "main" ]]; then
  echo "Error: releases must be created from the main branch (currently on '$current_branch')"
  exit 1
fi

if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
  echo "Error: working tree is not clean — commit or stash your changes first"
  exit 1
fi

# Read current version from pyproject.toml
current_version=$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT_DIR/pyproject.toml")
if [[ -z "$current_version" ]]; then
  echo "Error: could not read version from pyproject.toml"
  exit 1
fi

IFS='.' read -r major minor patch <<< "$current_version"

# Determine bump type
if [[ $# -ge 1 ]]; then
  bump="$1"
else
  last_tag=$(git -C "$ROOT_DIR" describe --tags --abbrev=0 2>/dev/null || echo "")
  if [[ -z "$last_tag" ]]; then
    range="HEAD"
  else
    range="${last_tag}..HEAD"
  fi

  commits=$(git -C "$ROOT_DIR" log "$range" --pretty=format:"%s%n%b")

  if echo "$commits" | grep -qiE "BREAKING CHANGE|^[a-z]+!:"; then
    bump="major"
  elif echo "$commits" | grep -qE "^feat(\(.+\))?:"; then
    bump="minor"
  else
    bump="patch"
  fi

  echo "Detected bump type from commits: $bump"
fi

case "$bump" in
  major) major=$((major + 1)); minor=0; patch=0 ;;
  minor) minor=$((minor + 1)); patch=0 ;;
  patch) patch=$((patch + 1)) ;;
  *)
    echo "Error: invalid bump type '$bump' (expected patch, minor, or major)"
    exit 1
    ;;
esac

new_version="${major}.${minor}.${patch}"
tag="v${new_version}"

echo "Bumping version: $current_version -> $new_version"
echo "Creating tag: $tag"

git -C "$ROOT_DIR" tag -a "$tag" -m "Release $tag"
git -C "$ROOT_DIR" push origin "$tag"

echo "Tag $tag pushed. The release workflow will handle the rest."
