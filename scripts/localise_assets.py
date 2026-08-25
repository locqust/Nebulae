#!/usr/bin/env python3
"""
Swaps the CDN <head> references in every template for local assets.

Removes:
  - cdn.tailwindcss.com script + the inline tailwind.config block
  - fonts.googleapis.com / fonts.gstatic.com stylesheet + preconnects
  - cdnjs.cloudflare.com Cropper.js CSS and JS
  - the stray Cloudflare /cdn-cgi/ email-decode scripts

Adds:
  - static/css/tailwind.css   (built by scripts/build-css.sh)
  - static/css/inter.css      (self-hosted Inter)
  - static/css/cropper.min.css and static/js/vendor/cropper.min.js
    (only in templates that referenced Cropper already)

Run from the repository root:

    python3 scripts/localise_assets.py --dry-run     # see what would change
    python3 scripts/localise_assets.py               # apply

Line endings are preserved per file. A .bak copy is written for each file
changed unless --no-backup is passed.
"""

import argparse
import os
import re
import sys

TEMPLATE_DIR = 'templates'

# --- patterns to strip -------------------------------------------------------

REMOVALS = [
    # preconnect / dns-prefetch hints for the CDNs we're dropping
    (r'[ \t]*<link rel="preconnect" href="https://cdn\.tailwindcss\.com"[^>]*>\r?\n', 'tailwind preconnect'),
    (r'[ \t]*<link rel="preconnect" href="https://fonts\.googleapis\.com"[^>]*>\r?\n', 'google fonts preconnect'),
    (r'[ \t]*<link rel="preconnect" href="https://fonts\.gstatic\.com"[^>]*>\r?\n', 'gstatic preconnect'),
    (r'[ \t]*<link rel="dns-prefetch" href="https://cdnjs\.cloudflare\.com"[^>]*>\r?\n', 'cdnjs dns-prefetch'),

    # the Tailwind Play CDN itself, plus the comment above it
    (r'[ \t]*<!--\s*Tailwind CSS CDN\s*-->\r?\n', 'tailwind comment'),
    (r'[ \t]*<script src="https://cdn\.tailwindcss\.com"></script>\r?\n', 'tailwind cdn script'),

    # inline tailwind.config block (darkMode moves into tailwind.config.js)
    (r'[ \t]*<!--[^\n]*Configure Tailwind[^\n]*-->\r?\n', 'tailwind config comment'),
    (r'[ \t]*<script>\s*\r?\n?\s*tailwind\.config\s*=\s*\{.*?\}\s*\r?\n?\s*</script>\r?\n',
     'inline tailwind.config'),

    # Google Fonts stylesheet
    (r'[ \t]*<link href="https://fonts\.googleapis\.com/[^"]*"[^>]*>\r?\n', 'google fonts stylesheet'),

    # Cropper from cdnjs (CSS and JS), plus its comment
    (r'[ \t]*<!--\s*Cropper\.js CSS\s*-->\r?\n', 'cropper comment'),
    (r'[ \t]*<link href="https://cdnjs\.cloudflare\.com/[^"]*cropper[^"]*"[^>]*>\r?\n', 'cropper css'),
    (r'[ \t]*<script src="https://cdnjs\.cloudflare\.com/[^"]*cropper[^"]*"></script>\r?\n', 'cropper js'),

    # Cloudflare email obfuscation - pasted in from a rendered page, 404s here
    (r'<script data-cfasync="false" src="/cdn-cgi/scripts/[^"]*"></script>', 'cdn-cgi email-decode'),
]

# --- what to insert ----------------------------------------------------------

LOCAL_CSS = """    <!-- Local styles (no CDNs - see scripts/build-css.sh) -->
    <link rel="stylesheet" href="{{ url_for('static', filename='css/tailwind.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/inter.css') }}">
"""

CROPPER_CSS = """    <link rel="stylesheet" href="{{ url_for('static', filename='css/cropper.min.css') }}">
"""

CROPPER_JS = """    <script src="{{ url_for('static', filename='js/vendor/cropper.min.js') }}"></script>
"""

# style.css is already present in every template; we anchor our inserts on it.
STYLE_ANCHOR = re.compile(
    r"([ \t]*<link rel=\"stylesheet\" href=\"\{\{ url_for\('static', filename='css/style\.css'\) \}\}\">)"
)


def process(path, dry_run):
    with open(path, 'r', encoding='utf-8', newline='') as f:
        original = f.read()

    crlf = '\r\n' in original
    text = original
    notes = []

    used_cropper = 'cropper' in text.lower()

    for pattern, label in REMOVALS:
        text, n = re.subn(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)
        if n:
            notes.append(f"-{n} {label}")

    if not STYLE_ANCHOR.search(text):
        if notes:
            notes.append("!! no style.css anchor - inserts skipped")
        return original, text, notes

    block = LOCAL_CSS
    if used_cropper:
        block += CROPPER_CSS
    if crlf:
        block = block.replace('\n', '\r\n')

    # Put our stylesheets immediately before style.css so that style.css keeps
    # the last word - it overrides Tailwind defaults in several places.
    text = STYLE_ANCHOR.sub(lambda m: block + m.group(1), text, count=1)
    notes.append("+tailwind.css +inter.css" + (" +cropper.css" if used_cropper else ""))

    if used_cropper and 'js/vendor/cropper.min.js' not in text:
        cjs = CROPPER_JS.replace('\n', '\r\n') if crlf else CROPPER_JS
        if '</body>' in text:
            text = text.replace('</body>', cjs + '</body>', 1)
            notes.append("+cropper.js")

    return original, text, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--no-backup', action='store_true')
    ap.add_argument('--dir', default=TEMPLATE_DIR)
    args = ap.parse_args()

    if not os.path.isdir(args.dir):
        sys.exit(f"No such directory: {args.dir} (run me from the repo root)")

    changed = 0
    for root, _dirs, files in os.walk(args.dir):
        for name in sorted(files):
            if not name.endswith('.html'):
                continue
            path = os.path.join(root, name)
            original, text, notes = process(path, args.dry_run)
            if text == original:
                continue
            changed += 1
            print(f"{name:<40} {', '.join(notes)}")
            if not args.dry_run:
                if not args.no_backup:
                    with open(path + '.bak', 'w', encoding='utf-8', newline='') as f:
                        f.write(original)
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(text)

    print()
    print(f"{changed} template(s) {'would be' if args.dry_run else ''} changed.")
    if not args.dry_run and changed:
        print("Backups written as *.html.bak - delete them once you're happy.")
        print("Now run: ./scripts/build-css.sh")


if __name__ == '__main__':
    main()
