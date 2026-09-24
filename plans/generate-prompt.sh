#!/usr/bin/env bash
# Generate an implementation prompt from a plan directory.
# Usage: plans/generate-prompt.sh <plan-dir-name>
set -euo pipefail

PLANS_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$PLANS_DIR/prompt-template.txt"

plan_dir_name="${1:?Usage: $0 <plan-dir-name>}"
plan_path="$PLANS_DIR/$plan_dir_name"
meta="$plan_path/meta.json"
readme="$plan_path/README.md"

plan_name="$(jq -r .name "$meta")"
commit_tag="$(jq -r '.commit_tag // .name' "$meta")"
prerequisite="$(jq -r '.prerequisite // ""' "$meta")"

# --- parse build order from README priority table ---
build_order=()
in_table=0
while IFS= read -r line; do
    if [[ $in_table -eq 0 ]] && echo "$line" | grep -qE '^\|\s*#\s*\|\s*Spec\s*\|'; then
        in_table=1; continue
    fi
    [[ $in_table -eq 0 ]] && continue
    echo "$line" | grep -q '^|---' && continue
    if echo "$line" | grep -q '^|'; then
        fn="$(echo "$line" | grep -oE '\[.*?\]\([^)]+\.md\)' | sed 's/.*(\(.*\))/\1/')"
        [[ -n $fn ]] && build_order+=("$fn")
    else
        break
    fi
done < "$readme"

ticket_count="${#build_order[@]}"
[[ $ticket_count -eq 0 ]] && { echo "No tickets found in $readme priority table" >&2; exit 1; }
last_ticket="$(echo "${build_order[$((ticket_count - 1))]}" | grep -oE '^[0-9]+')"

# --- substitute single-value placeholders, then expand build_order ---
sed \
    -e "s|{{plan_name}}|${plan_name}|g" \
    -e "s|{{plan_dir}}|${plan_dir_name}|g" \
    -e "s|{{commit_tag}}|${commit_tag}|g" \
    -e "s|{{prerequisite}}|${prerequisite}|g" \
    -e "s|{{ticket_count}}|${ticket_count}|g" \
    -e "s|{{last_ticket}}|${last_ticket}|g" \
    "$TEMPLATE" | while IFS= read -r line; do
    if [[ "$line" == *'{{build_order}}'* ]]; then
        for i in "${!build_order[@]}"; do
            printf '%2d. %s\n' "$((i + 1))" "${build_order[$i]}"
        done
    else
        printf '%s\n' "$line"
    fi
done
