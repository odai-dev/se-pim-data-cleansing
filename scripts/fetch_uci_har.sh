#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
URL='https://archive.ics.uci.edu/static/public/240/human%2Bactivity%2Brecognition%2Busing%2Bsmartphones.zip'
EXPECTED_SHA256='c00b803081a5c797cd5e4b83700a9810b38d53d9d84e01917e090e1fdbc81031'
OUTPUT=${1:-"$ROOT_DIR/datasets/source/uci_har_official_c00b8030.zip"}
PARTIAL="${OUTPUT}.partial"

mkdir -p "$(dirname "$OUTPUT")"

valid_archive() {
    local file=$1
    [[ -f "$file" ]] || return 1
    [[ "$(sha256sum "$file" | awk '{print $1}')" == "$EXPECTED_SHA256" ]] || return 1
    unzip -tq "$file" >/dev/null
}

if valid_archive "$OUTPUT"; then
    printf '[PASS] existing pinned UCI HAR archive: %s\n' "$OUTPUT"
    exit 0
fi

rm -f "$PARTIAL"
printf '[INFO] downloading official UCI HAR archive with curl\n'
if ! curl -fsSL --retry 3 --retry-delay 3 -o "$PARTIAL" "$URL" || ! valid_archive "$PARTIAL"; then
    printf '[WARN] direct curl failed integrity validation; retrying through torsocks\n' >&2
    rm -f "$PARTIAL"
    torsocks curl -fsSL --retry 4 --retry-delay 3 -o "$PARTIAL" "$URL"
fi

if ! valid_archive "$PARTIAL"; then
    actual=missing
    if [[ -f "$PARTIAL" ]]; then
        actual=$(sha256sum "$PARTIAL" | awk '{print $1}')
    fi
    printf '[ERROR] UCI HAR integrity failure: expected=%s actual=%s\n' \
        "$EXPECTED_SHA256" "$actual" >&2
    exit 1
fi

mv "$PARTIAL" "$OUTPUT"
printf '[PASS] downloaded and verified %s\n' "$OUTPUT"
printf '[PASS] sha256=%s\n' "$EXPECTED_SHA256"
