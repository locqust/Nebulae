# utils/text_processing.py
import re
from flask import url_for, current_app

def linkify_urls(text):
    """
    Finds URLs in text and converts them to clickable links.
    This function operates independently of mention linkifying.
    """
    if not text:
        return ""

    # Regex to find URLs that start with http, https, or www.
    # It avoids matching URLs that are already inside an <a> tag.
    url_pattern = re.compile(r'(?<!href=")(?<!href=\')(https?://|www\.)[^\s<>"\'()]+')
    
    def replace_url(match):
        url = match.group(0)
        href = url if url.startswith(('http://', 'https://')) else 'http://' + url
        display_text = (url[:45] + '...') if len(url) > 48 else url
        return f'<a href="{href}" target="_blank" rel="noopener noreferrer" class="text-indigo-600 hover:underline break-all">{display_text}</a>'

    return url_pattern.sub(replace_url, text)

def linkify_mentions(text):
    """
    Finds @mentions in text and converts them to profile links.
    It uses a multi-pass approach to correctly handle all mention types:
    1. Full remote mentions (@DisplayName@hostname)
    2. Simple remote mentions (@DisplayName)
    3. Simple local mentions (@DisplayName)
    
    Note: This function does NOT process @everyone/@all - that should be done
    separately using linkify_everyone_mention() when you have context about
    whether it's a group/event post.
    """
    if not text:
        return ""
        
    from db_queries.users import get_all_users_with_media_paths
    
    users = get_all_users_with_media_paths()
    if not users:
        return text

    # We match on Display Name as this is what users are most likely to type.
    remote_users = [u for u in users if u['hostname'] and u['display_name']]
    local_users = [u for u in users if not u['hostname'] and u['display_name']]

    # Sort by display name length (descending) to avoid partial matches.
    sorted_remote = sorted(remote_users, key=lambda u: len(u['display_name']), reverse=True)
    sorted_local = sorted(local_users, key=lambda u: len(u['display_name']), reverse=True)

    processed_text = text
    
    # FEDERATION FIX: All links, for both local and remote users, must point to the
    # local user_profile endpoint. This endpoint is responsible for determining if
    # the user is remote and then initiating the viewer token request flow.
    # By creating a direct link to the remote node, we were bypassing this crucial step.

    # Pass 1: Handle fully-qualified remote mentions (@DisplayName@hostname).
    for user in sorted_remote:
        pattern = r'(?<!\S)@' + re.escape(user['display_name']) + r'@' + re.escape(user['hostname']) + r'\b'
        # Corrected: Point to the local endpoint to handle token logic.
        profile_url = url_for('main.user_profile', puid=user['puid'])
        # The link text can still show the full remote address for clarity.
        replacement_html = f'<a href="{profile_url}" class="font-semibold text-teal-600 hover:underline">@{user["display_name"]}@{user["hostname"]}</a>'
        processed_text = re.sub(pattern, replacement_html, processed_text, flags=re.IGNORECASE)

    # Pass 2: Handle simple mentions (@DisplayName) for REMOTE users.
    for user in sorted_remote:
        pattern = r'(?<!\S)@' + re.escape(user['display_name']) + r'(?!@)\b'
        # Corrected: Point to the local endpoint.
        profile_url = url_for('main.user_profile', puid=user['puid'])
        replacement_html = f'<a href="{profile_url}" class="font-semibold text-teal-600 hover:underline">@{user["display_name"]}</a>'
        processed_text = re.sub(pattern, replacement_html, processed_text, flags=re.IGNORECASE)

    # Pass 3: Handle simple mentions (@DisplayName) for LOCAL users.
    for user in sorted_local:
        pattern = r'(?<!\S)@' + re.escape(user['display_name']) + r'(?!@)\b'
        # BUG FIX: Check user_type to generate the correct profile URL for public pages.
        if user['user_type'] == 'public_page':
            profile_url = url_for('main.public_page_profile', puid=user['puid'])
        else:
            profile_url = url_for('main.user_profile', puid=user['puid'])
        replacement_html = f'<a href="{profile_url}" class="font-semibold text-blue-600 hover:underline">@{user["display_name"]}</a>'
        processed_text = re.sub(pattern, replacement_html, processed_text, flags=re.IGNORECASE)

    return processed_text

def extract_mentions(text):
    """
    Finds @mentions in text and returns a list of full user objects.
    It uses a multi-pass approach to correctly identify all mention types.
    
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
    
    Args:
        text: The text to process
        context_type: 'group' or 'event'
    """
    if not text or context_type not in ['group', 'event']:
        return text
    
    # Match @everyone or @all (preserve case in replacement)
    pattern = r'(?<!\S)@(everyone|all)\b'
    replacement = r'<span class="font-bold text-orange-600 dark:text-orange-400">@\1</span>'
    return re.sub(pattern, replacement, text, flags=re.IGNORECASE)