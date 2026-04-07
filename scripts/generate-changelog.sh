#!/usr/bin/env bash
set -euo pipefail

# Generates a changelog entry from conventional commits since the last tag.
#
# Usage:
#   ./scripts/generate-changelog.sh <new-tag> [previous-tag]
#
# If previous-tag is omitted, it is auto-detected from git tags.
# Output is prepended to CHANGELOG.md (created if missing).

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <new-tag> [previous-tag]"
  exit 1
fi

NEW_TAG="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CHANGELOG="$ROOT_DIR/CHANGELOG.md"

if [[ $# -ge 2 ]]; then
  PREV_TAG="$2"
else
  PREV_TAG=$(git -C "$ROOT_DIR" describe --tags --abbrev=0 HEAD^ 2>/dev/null || echo "")
fi

if [[ -z "$PREV_TAG" ]]; then
  RANGE="HEAD"
else
  RANGE="${PREV_TAG}..HEAD"
fi

DATE=$(date +%Y-%m-%d)

# Collect commits by category
added=""
fixed=""
changed=""
performance=""
docs=""

while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  case "$line" in
    feat\(*\):*|feat:*)
      msg="${line#*: }"
      added="${added}\n- ${msg}"
      ;;
    fix\(*\):*|fix:*)
      msg="${line#*: }"
      fixed="${fixed}\n- ${msg}"
      ;;
    perf\(*\):*|perf:*)
      msg="${line#*: }"
      performance="${performance}\n- ${msg}"
      ;;
    docs\(*\):*|docs:*)
      msg="${line#*: }"
      docs="${docs}\n- ${msg}"
      ;;
    refactor\(*\):*|refactor:*)
      msg="${line#*: }"
      changed="${changed}\n- ${msg}"
      ;;
  esac
done < <(git -C "$ROOT_DIR" log "$RANGE" --pretty=format:"%s")

# Build the entry
entry="## [${NEW_TAG#v}] - ${DATE}\n"

[[ -n "$added" ]] && entry="${entry}\n### Added\n${added}\n"
[[ -n "$fixed" ]] && entry="${entry}\n### Fixed\n${fixed}\n"
[[ -n "$changed" ]] && entry="${entry}\n### Changed\n${changed}\n"
[[ -n "$performance" ]] && entry="${entry}\n### Performance\n${performance}\n"
[[ -n "$docs" ]] && entry="${entry}\n### Documentation\n${docs}\n"

# Also write release notes (just this version) for GitHub Release body
echo -e "$entry" > "$ROOT_DIR/release-notes.md"

# Prepend to CHANGELOG.md
if [[ -f "$CHANGELOG" ]]; then
  # Insert after the header line
  existing=$(cat "$CHANGELOG")
  if echo "$existing" | head -1 | grep -q "^# Changelog"; then
    header=$(head -1 "$CHANGELOG")
    rest=$(tail -n +2 "$CHANGELOG")
    printf '%s\n\n' "$header" > "$CHANGELOG"
    echo -e "$entry" >> "$CHANGELOG"
    echo "$rest" >> "$CHANGELOG"
  else
    tmp=$(mktemp)
    echo -e "$entry" > "$tmp"
    cat "$CHANGELOG" >> "$tmp"
    mv "$tmp" "$CHANGELOG"
  fi
else
  printf '# Changelog\n\n' > "$CHANGELOG"
  echo -e "$entry" >> "$CHANGELOG"
fi

echo "Changelog updated for $NEW_TAG"
