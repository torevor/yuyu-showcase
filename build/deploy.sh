#!/usr/bin/env bash
# deploy.sh — push the GENERATED gallery to the box, leaving item app dirs untouched.
#
# Deploys only the served, generated artifacts (index.html, showcase.css, detail/, assets/).
# It NEVER touches the item application directories (/big-five-matchmaker/, /two-ai/,
# /yuyu-linguistic-risk-detector/, /foundry/, ...) — those are built and served independently;
# the generator and this script only own the landing, the detail pages, and their assets.
#
# Source of truth = this git repo. The box is a deploy target (retiring ~2026-08-07; when the
# target moves to elua, only BOX_HOST / BOX_DIR below change).
#
# Usage:  bash build/deploy.sh
set -euo pipefail

BOX_HOST="${BOX_HOST:-root@100.74.37.45}"
BOX_DIR="${BOX_DIR:-/var/www/yuyu-showcase}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> building from manifests"
( cd "$REPO" && python build/build_showcase.py )

echo "==> backing up the current box index.html"
ssh "$BOX_HOST" "cp -a $BOX_DIR/index.html $BOX_DIR/index.html.bak.\$(date +%Y%m%d-%H%M%S) 2>/dev/null || true"

echo "==> deploying generated artifacts (index.html, showcase.css, detail/, assets/)"
scp -q "$REPO/index.html" "$REPO/showcase.css" "$BOX_HOST:$BOX_DIR/"
# detail/ and assets/ — recursive, but only the generated subtrees (never item app dirs)
ssh "$BOX_HOST" "mkdir -p $BOX_DIR/detail $BOX_DIR/assets"
scp -qr "$REPO/detail/." "$BOX_HOST:$BOX_DIR/detail/"
scp -qr "$REPO/assets/." "$BOX_HOST:$BOX_DIR/assets/"

echo "==> done. Verifying the landing responds:"
ssh "$BOX_HOST" "curl -s -o /dev/null -w 'HTTP %{http_code}  %{size_download} bytes\n' http://127.0.0.1:8090/index.html || true"
echo "==> live (tailnet): http://100.74.37.45:8090/  |  gated: https://showcase.elua2.org/"
