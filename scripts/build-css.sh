#!/usr/bin/env bash
# Builds static/css/tailwind.css from the templates.
#
# Run this before packaging a release, and any time you add a Tailwind class
# to a template that wasn't already used somewhere. Tailwind only keeps
# classes it can find as literal text in the files listed under `content` in
# tailwind.config.js - if a class is assembled at runtime in JavaScript, add
# it to the `safelist` there or it will be stripped from the build.
#
# The standalone CLI is a single binary; no Node or node_modules required.

set -euo pipefail

TAILWIND_VERSION="v3.4.17"
BIN_DIR=".tailwind"
CONFIG="tailwind/tailwind.config.js"
INPUT="tailwind/tailwind-input.css"
OUTPUT="static/css/tailwind.css"

# Work from the repository root regardless of where this is called from.
cd "$(dirname "$0")/.."

case "$(uname -s)-$(uname -m)" in
    Linux-x86_64)         ASSET="tailwindcss-linux-x64" ;;
    Linux-aarch64)        ASSET="tailwindcss-linux-arm64" ;;
    Linux-armv7l)         ASSET="tailwindcss-linux-armv7" ;;
    Darwin-x86_64)        ASSET="tailwindcss-macos-x64" ;;
    Darwin-arm64)         ASSET="tailwindcss-macos-arm64" ;;
    # Git Bash / MSYS2 / Cygwin on Windows
    MINGW*|MSYS*|CYGWIN*) ASSET="tailwindcss-windows-x64.exe" ;;
    *) echo "Unsupported platform: $(uname -s)-$(uname -m)"
       echo "Download the right binary manually from"
       echo "  https://github.com/tailwindlabs/tailwindcss/releases/tag/${TAILWIND_VERSION}"
       echo "and place it in ${BIN_DIR}/"
       exit 1 ;;
esac

BIN="$BIN_DIR/$ASSET"

if [ ! -x "$BIN" ]; then
    echo "Fetching Tailwind CLI $TAILWIND_VERSION ($ASSET)..."
    mkdir -p "$BIN_DIR"
    curl -sL -o "$BIN" \
        "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/${ASSET}"
    chmod +x "$BIN"
fi

echo "Building $OUTPUT ..."
"$BIN" -c "$CONFIG" -i "$INPUT" -o "$OUTPUT" --minify

SIZE=$(wc -c < "$OUTPUT")
echo "Done. $OUTPUT is $((SIZE / 1024)) KB."
echo
echo "Sanity check - these should all appear in the output:"
for c in "bg-white" "grid-cols-1" "rounded-lg"; do
    if grep -q "\.$c" "$OUTPUT"; then echo "  OK      .$c"; else echo "  MISSING .$c"; fi
done
