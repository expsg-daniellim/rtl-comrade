#!/usr/bin/env bash
#
# Regenerate a dataflow-diagram.svg from the Mermaid flowchart embedded in a
# plan's 00-overview.md.
#
# Extracts the first ```mermaid ... ``` fenced block from the target markdown
# file and renders it to dataflow-diagram.svg *next to that file* with
# mermaid-cli (mmdc) — using an installed mmdc if present, else
# `npx @mermaid-js/mermaid-cli`.
#
# Usage:
#   ./regen-dataflow-diagram.sh SOURCE
#
#   SOURCE  a markdown file containing a ```mermaid block, or a plan directory
#           containing 00-overview.md.
#
# Examples (from the repo root):
#   ./regen-dataflow-diagram.sh implementation-test
#   ./regen-dataflow-diagram.sh implementation-filelist
#   ./regen-dataflow-diagram.sh implementation-filelist/00-overview.md
#
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $(basename "$0") SOURCE   (a plan directory with 00-overview.md, or a markdown file)" >&2
  exit 2
fi

# Resolve the source: an explicit markdown file, or a directory holding 00-overview.md.
arg="$1"
if [ -d "$arg" ]; then
  src="$arg/00-overview.md"
else
  src="$arg"
fi

if [ ! -f "$src" ]; then
  echo "error: source markdown not found: $src" >&2
  exit 1
fi

src="$(cd "$(dirname "$src")" && pwd)/$(basename "$src")"   # absolutise
out="$(dirname "$src")/dataflow-diagram.svg"                # output next to the source

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
