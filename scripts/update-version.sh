#!/usr/bin/env bash
set -euo pipefail

# Updates the version in pyproject.toml
#
# Usage:
#   ./scripts/update-version.sh <version>
#
# Example:
#   ./scripts/update-version.sh 1.2.3

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <version>"
  echo "Example: $0 1.2.3"
  exit 1
fi

NEW_VERSION="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Validate semver format
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: version must be in semver format (X.Y.Z), got '$NEW_VERSION'"
  exit 1
fi

# Update pyproject.toml
sed -i.bak "s/^version = \".*\"/version = \"${NEW_VERSION}\"/" "$ROOT_DIR/pyproject.toml"
rm -f "$ROOT_DIR/pyproject.toml.bak"

echo "Updated pyproject.toml to version $NEW_VERSION"
