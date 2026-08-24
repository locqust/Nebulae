# utils/text_processing.py
import re
from html import unescape
from flask import url_for, current_app
from markupsafe import Markup, escape

# =============================================================================
# XSS SAFETY NOTE
# =============================================================================
# The linkify_* functions below all return Markup, which means Jinja will NOT
# escape their output (they are, by design, emitting <a> and <span> tags).
#
# Because of that, every one of them MUST escape its input first. escape() is
# idempotent against Markup, so it is a no-op when these are chained together
# (e.g. `| linkify_mentions | linkify_urls`) and a real escape when a function
# is handed raw user content. That is what makes the chain safe in any order.
#
# If you add a new linkify_* function, escape() the input on the first line and
# wrap the return value in Markup(). Do not add `| safe` in templates - these
# functions already return safe markup, and `| safe` on raw content is exactly
# the bug this module was written to fix.
# =============================================================================

# Trailing characters that should not be swallowed into a link. Covers HTML
# entities produced by escaping (a quote becomes &#34;, an angle bracket
# becomes &gt;, etc.) plus ordinary sentence punctuation.
_TRAILING_JUNK = re.compile(
    r'(?:&(?:amp|quot|apos|lt|gt|nbsp|#0*34|#0*39|#x0*22|#x0*27);|[.,;:!?])+$',
    re.IGNORECASE
)

# URLs starting with http://, https:// or www.
# The lookbehinds keep us from re-linking an href that a previous pass created.
_URL_PATTERN = re.compile(r'(?<!href=")(?<!href=\')(https?://|www\.)[^\s<>"\'()]+')


def linkify_urls(text):
    """
    Finds URLs in text and converts them to clickable links.
    Escapes its input, so it is safe to call on raw user content.
    Returns Markup - do NOT add `| safe` in templates.
    """
    if not text:
        return Markup("")

    # No-op if already Markup (i.e. chained after linkify_mentions).
    text = escape(text)

    def replace_url(match):
        matched = match.group(0)

        # Don't swallow trailing punctuation or escaped entities into the link.
        trailing = ''
        junk = _TRAILING_JUNK.search(matched)
        if junk:
            trailing = matched[junk.start():]
            matched = matched[:junk.start()]

        if not matched:
            return trailing

        # Work with the real URL, not its escaped form, so that truncation
        # never slices an HTML entity in half.
        real_url = unescape(matched)
        href = real_url if real_url.startswith(('http://', 'https://')) else 'http://' + real_url
        display_text = (real_url[:45] + '...') if len(real_url) > 48 else real_url

        # escape() both: href is going into an attribute, display into a text node.
        return (
            f'<a href="{escape(href)}" target="_blank" rel="noopener noreferrer" '
            f'class="text-indigo-600 hover:underline break-all">{escape(display_text)}</a>'
            f'{trailing}'
        )

    return Markup(_URL_PATTERN.sub(replace_url, text))


def linkify_mentions(text):
    """
    Finds @mentions in text and converts them to profile links.
    It uses a multi-pass approach to correctly handle all mention types:
    1. Full remote mentions (@DisplayName@hostname)
    2. Simple remote mentions (@DisplayName)
    3. Simple local mentions (@DisplayName)

    Escapes its input, so it is safe to call on raw user content.
    Returns Markup - do NOT add `| safe` in templates.

    Note: This function does NOT process @everyone/@all - that should be done
    separately using linkify_everyone_mention() when you have context about
    whether it's a group/event post.
    """
    if not text:
        return Markup("")

    # No-op if already Markup. Everything below operates on escaped text.
    text = escape(text)

    from db_queries.users import get_all_users_with_media_paths

    users = get_all_users_with_media_paths()
    if not users:
        return Markup(text)

    # We match on Display Name as this is what users are most likely to type.
    remote_users = [u for u in users if u['hostname'] and u['display_name']]
    local_users = [u for u in users if not u['hostname'] and u['display_name']]

    # Sort by display name length (descending) to avoid partial matches.
    sorted_remote = sorted(remote_users, key=lambda u: len(u['display_name']), reverse=True)
    sorted_local = sorted(local_users, key=lambda u: len(u['display_name']), reverse=True)

    processed_text = str(text)

    # FEDERATION FIX: All links, for both local and remote users, must point to the
    # local user_profile endpoint. This endpoint is responsible for determining if
    # the user is remote and then initiating the viewer token request flow.
    # By creating a direct link to the remote node, we were bypassing this crucial step.

    # XSS FIX: patterns are built from the *escaped* display name, because the
    # text we are searching has already been escaped. A user called "Bob & Sue"
    # appears in the text as "Bob &amp; Sue", so that is what we must match.
    # Replacements go through a lambda so that re.sub does not interpret
    # backslash sequences in a user-controlled display name.

    # Pass 1: Handle fully-qualified remote mentions (@DisplayName@hostname).
    for user in sorted_remote:
        safe_name = str(escape(user['display_name']))
        safe_host = str(escape(user['hostname']))
        pattern = r'(?<!\S)@' + re.escape(safe_name) + r'@' + re.escape(safe_host) + r'\b'
        # Corrected: Point to the local endpoint to handle token logic.
        profile_url = url_for('main.user_profile', puid=user['puid'])
        # The link text can still show the full remote address for clarity.
        replacement_html = (
            f'<a href="{escape(profile_url)}" class="font-semibold text-teal-600 '
            f'hover:underline">@{safe_name}@{safe_host}</a>'
        )
        processed_text = re.sub(pattern, lambda m, r=replacement_html: r,
                                processed_text, flags=re.IGNORECASE)

    # Pass 2: Handle simple mentions (@DisplayName) for REMOTE users.
    for user in sorted_remote:
        safe_name = str(escape(user['display_name']))
        pattern = r'(?<!\S)@' + re.escape(safe_name) + r'(?!@)\b'
        # Corrected: Point to the local endpoint.
        profile_url = url_for('main.user_profile', puid=user['puid'])
        replacement_html = (
            f'<a href="{escape(profile_url)}" class="font-semibold text-teal-600 '
            f'hover:underline">@{safe_name}</a>'
        )
        processed_text = re.sub(pattern, lambda m, r=replacement_html: r,
                                processed_text, flags=re.IGNORECASE)

    # Pass 3: Handle simple mentions (@DisplayName) for LOCAL users.
    for user in sorted_local:
        safe_name = str(escape(user['display_name']))
        pattern = r'(?<!\S)@' + re.escape(safe_name) + r'(?!@)\b'
        # BUG FIX: Check user_type to generate the correct profile URL for public pages.
        if user['user_type'] == 'public_page':
            profile_url = url_for('main.public_page_profile', puid=user['puid'])
        else:
            profile_url = url_for('main.user_profile', puid=user['puid'])
        replacement_html = (
            f'<a href="{escape(profile_url)}" class="font-semibold text-blue-600 '
            f'hover:underline">@{safe_name}</a>'
        )
        processed_text = re.sub(pattern, lambda m, r=replacement_html: r,
                                processed_text, flags=re.IGNORECASE)

    return Markup(processed_text)


def extract_mentions(text):
    """
    Finds @mentions in text and returns a list of full user objects.
    It uses a multi-pass approach to correctly identify all mention types.

    NOTE: this operates on RAW (unescaped) text. It is used to work out who to
    notify, not to render anything, so it must not be escape-aware - the raw
    stored content is what it should be matching against.

    Note: This function does NOT extract @everyone/@all - use extract_everyone_mention()
    for that purpose.
    """
    # BUG FIX: If the text is None (like in an event post), return an empty list immediately.
    if not text:
        return []

    from db_queries.users import get_all_users_with_media_paths

    users = get_all_users_with_media_paths()
    if not users:
        return []

    remote_users = [u for u in users if u['hostname'] and u['display_name']]
    local_users = [u for u in users if not u['hostname'] and u['display_name']]

    sorted_remote = sorted(remote_users, key=lambda u: len(u['display_name']), reverse=True)
    sorted_local = sorted(local_users, key=lambda u: len(u['display_name']), reverse=True)

    mentioned_users = []
    mentioned_puids = set()
    temp_text = text # We modify this copy to avoid re-matching parts of names

    def add_mentioned_user(user):
        if user['puid'] not in mentioned_puids:
            mentioned_users.append(user)
            mentioned_puids.add(user['puid'])

    # Pass 1: Find fully-qualified remote mentions (@DisplayName@hostname)
    for user in sorted_remote:
        pattern = r'(?<!\S)@' + re.escape(user['display_name']) + r'@' + re.escape(user['hostname']) + r'\b'
        if re.search(pattern, temp_text, flags=re.IGNORECASE):
            add_mentioned_user(user)
            temp_text = re.sub(pattern, '', temp_text, flags=re.IGNORECASE)

    # Pass 2: Find simple mentions (@DisplayName) for remote users
    for user in sorted_remote:
        pattern = r'(?<!\S)@' + re.escape(user['display_name']) + r'(?!@)\b'
        if re.search(pattern, temp_text, flags=re.IGNORECASE):
            add_mentioned_user(user)
            temp_text = re.sub(pattern, '', temp_text, flags=re.IGNORECASE)

    # Pass 3: Find simple mentions (@DisplayName) for local users
    for user in sorted_local:
        pattern = r'(?<!\S)@' + re.escape(user['display_name']) + r'(?!@)\b'
        if re.search(pattern, temp_text, flags=re.IGNORECASE):
            add_mentioned_user(user)
            temp_text = re.sub(pattern, '', temp_text, flags=re.IGNORECASE)

    return mentioned_users


# NEW: Functions for @everyone/@all support
def extract_everyone_mention(text, context_type=None):
    """
    Checks if the text contains @everyone or @all.
    Returns True if found, False otherwise.
    Only applicable in group or event contexts.

    NOTE: operates on RAW text - used for notification targeting, not rendering.

    Args:
        text: The text to check
        context_type: 'group' or 'event' (only these contexts support @everyone)
    """
    if not text or context_type not in ['group', 'event']:
        return False

    # Match @everyone or @all (case insensitive, must be word boundary)
    pattern = r'(?<!\S)@(everyone|all)\b'
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def linkify_everyone_mention(text, context_type=None):
    """
    Converts @everyone or @all mentions to styled spans.
    This makes them visually distinct from regular mentions.

    Escapes its input, so it is safe to call on raw user content.
    Returns Markup - do NOT add `| safe` in templates.

    Registered as a Jinja filter so templates can do:
        {{ content | linkify_mentions | linkify_urls | linkify_everyone_mention('group') }}
    instead of the old `| replace('@everyone', '<span ...>')` chain, which
    silently breaks against Markup input (Jinja's replace escapes its args).

    Args:
        text: The text to process
        context_type: 'group' or 'event'
    """
    if not text:
        return Markup("")

    # No-op if already Markup (i.e. chained after the other linkify filters).
    text = escape(text)

    if context_type not in ['group', 'event']:
        return Markup(text)

    # Match @everyone or @all (preserve case in replacement)
    pattern = r'(?<!\S)@(everyone|all)\b'
    replacement = r'<span class="font-bold text-orange-600 dark:text-orange-400">@\1</span>'
    return Markup(re.sub(pattern, replacement, str(text), flags=re.IGNORECASE))
