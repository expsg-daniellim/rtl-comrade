#!/usr/bin/env bash
#
# Regenerate dataflow-diagram.svg from the Mermaid flowchart embedded in
# implementation-test/00-overview.md.
#
# Extracts the single ```mermaid ... ``` fenced block from 00-overview.md and
# renders it to ./dataflow-diagram.svg in the current working directory with
# mermaid-cli (mmdc) — using an installed mmdc if present, else
# `npx @mermaid-js/mermaid-cli`.
#
# The Mermaid SOURCE is located via git (so the script runs from any cwd); the
# OUTPUT is written to the current directory.
#
# Usage:  ./regen-dataflow-diagram.sh
#
set -euo pipefail

repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
src="$repo_root/implementation-test/00-overview.md"
out="$PWD/dataflow-diagram.svg"   # output to the current working directory

mmd="$(mktemp -t dataflow.XXXXXX.mmd)"
pptr="$(mktemp -t puppeteer.XXXXXX.json)"
trap 'rm -f "$mmd" "$pptr"' EXIT

# Extract the body of the first ```mermaid fenced block.
awk '
  /^```mermaid[[:space:]]*$/ { infence = 1; next }
  infence && /^```[[:space:]]*$/ { exit }
  infence { print }
' "$src" > "$mmd"

if [ ! -s "$mmd" ]; then
  echo "error: no mermaid fenced block found in $src" >&2
  exit 1
fi

# Headless Chromium needs --no-sandbox in many CI/sandbox environments.
printf '%s\n' '{"args":["--no-sandbox","--disable-setuid-sandbox"]}' > "$pptr"

render() { "$@" -i "$mmd" -o "$out" -p "$pptr" -b white; }

if command -v mmdc >/dev/null 2>&1; then
  render mmdc
else
  render npx --yes @mermaid-js/mermaid-cli
fi

echo "regenerated $out from $src"
