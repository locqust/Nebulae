# db_queries/comments.py
# Contains functions for managing comments and replies.

import uuid
from datetime import datetime
from flask import g
from db import get_db
from utils.text_processing import extract_mentions, extract_everyone_mention
from .notifications import create_notification
from .users import get_user_by_id, get_user_by_puid

# BUG FIX: Added is_remote flag to prevent duplicate notifications from federated comments.
def add_comment(post_cuid, user_id, content, post_owner_id, parent_comment_id=None, media_files=None, nu_id=None, cuid=None, is_remote=False, timestamp=None):
    """Adds a new comment, handles media, and creates notifications."""
    # CIRCULAR IMPORT FIX: Import federation functions inside the function
    from .federation import send_remote_mention_notification, send_remote_notification
    
    db = get_db()
    cursor = db.cursor()

    from .posts import get_post_by_cuid

    post = get_post_by_cuid(post_cuid)
    if not post:
        raise ValueError("Post not found for the given CUID.")
    post_id = post['id']
    group_id = post['group']['id'] if post.get('group') else None
    
    post_author = get_user_by_id(post.get('user_id')) if post.get('user_id') else get_user_by_puid(post.get('author_puid'))

    if nu_id is None:
        nu_id = g.nu_id
        
    if cuid is None:
        cuid = str(uuid.uuid4())

    # Use provided timestamp or let database default to CURRENT_TIMESTAMP
    if timestamp:
        cursor.execute("INSERT INTO comments (cuid, post_id, user_id, content, parent_comment_id, nu_id, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (cuid, post_id, user_id, content, parent_comment_id, nu_id, timestamp))
    else:
        cursor.execute("INSERT INTO comments (cuid, post_id, user_id, content, parent_comment_id, nu_id) VALUES (?, ?, ?, ?, ?, ?)",
                       (cuid, post_id, user_id, content, parent_comment_id, nu_id))
    comment_id = cursor.lastrowid

    if media_files:
        for media_file_data in media_files:
            media_path = media_file_data.get('media_file_path')
            alt_text = media_file_data.get('alt_text')
            if media_path:
                muid = str(uuid.uuid4())
                cursor.execute("INSERT INTO comment_media (muid, comment_id, media_file_path, alt_text) VALUES (?, ?, ?, ?)",
                               (muid, comment_id, media_path, alt_text))
    
    # NEW: Extract and associate link previews FOR ALL COMMENTS (local and remote)
    if content:  # Extract link previews for any comment with content
        try:
            from db_queries.link_previews import associate_link_previews_with_comment
            associate_link_previews_with_comment(comment_id, content)
        except Exception as e:
            print(f"Error creating link previews for comment: {e}")
            # Don't fail the comment creation if link preview fails

    # BUG FIX: Notification logic only runs for comments created directly on this node.
    if not is_remote:
        already_notified = {user_id} 

        mentioned_users = extract_mentions(content)
        for user in mentioned_users:
            if user['id'] not in already_notified:
                from .posts import is_post_hidden_for_user  # Local import
                # Check if the post or parent comment is hidden for this user
                post_hidden = is_post_hidden_for_user(user['id'], post_id) if post_id else False
                parent_hidden = False
                if parent_comment_id:
                    parent_hidden = is_comment_hidden_for_user(user['id'], parent_comment_id)
                
                # Skip notification if content is hidden
                if not post_hidden and not parent_hidden:
                    if user['hostname'] is None:
                        create_notification(user['id'], user_id, 'mention', post_id, comment_id, group_id=group_id)
                    else:
                        send_remote_mention_notification(user, user_id, post_id, comment_id, group_id=group_id)
                    already_notified.add(user['id'])

        # Handle @everyone/@all for groups
        if group_id is not None:
            has_everyone_mention = extract_everyone_mention(content, 'group')
            
            if has_everyone_mention:
                from .groups import is_user_group_moderator_or_admin, get_group_members, get_group_by_id
                if is_user_group_moderator_or_admin(user_id, group_id):
                    members = get_group_members(group_id)
                    # Get group object to pass PUID to remote nodes
                    group = get_group_by_id(group_id)
                    group_puid = group['puid'] if group else None
                    
                    for member in members:
                        if member['id'] not in already_notified:
                            if member['hostname'] is None:
                                # Local user
                                create_notification(member['id'], user_id, 'everyone_mention', post_id, comment_id, group_id=group_id)
                            else:
                                # Remote user - pass group_puid instead of group_id
                                send_remote_notification(member, user_id, 'everyone_mention', post_cuid, cuid, group_puid=group_puid)
                            already_notified.add(member['id'])
        
        # Handle @everyone/@all for events  
        elif post.get('event_id'):
            event_id = post['event_id']
            has_everyone_mention = extract_everyone_mention(content, 'event')
            
            if has_everyone_mention:
                from .events import get_event_by_id, get_event_attendees
                event = get_event_by_id(event_id)
                commenter = get_user_by_id(user_id)
                if event and commenter and event['created_by_user_puid'] == commenter['puid']:
                    attendees = get_event_attendees(event_id)
                    # Get event PUID to pass to remote nodes
                    event_puid = event['puid'] if event else None
                    
                    for attendee in attendees:
                        if attendee['puid'] != commenter['puid']:
                            attendee_user = get_user_by_puid(attendee['puid'])
                            if attendee_user and attendee_user['id'] not in already_notified:
                                if attendee_user.get('hostname') is None:
                                    # Local user
                                    create_notification(attendee_user['id'], user_id, 'everyone_mention', post_id, comment_id, event_id=event_id)
                                else:
                                    # Remote user - pass event_puid instead of event_id
                                    send_remote_notification(attendee_user, user_id, 'everyone_mention', post_cuid, cuid, event_puid=event_puid)
                                already_notified.add(attendee_user['id'])

        notification_type = 'reply' if parent_comment_id else 'comment'

        # BUG FIX: Use a dictionary to store users to notify to avoid duplicates
        # from a user being both the post author and the post owner.
        users_to_notify_map = {}

        if parent_comment_id:
            parent_comment = get_comment_by_internal_id(parent_comment_id)
            if parent_comment:
                parent_author = get_user_by_id(parent_comment['user_id'])
                if parent_author:
                    # NEW: Only notify if they haven't hidden the parent comment
                    if not is_comment_hidden_for_user(parent_author['id'], parent_comment_id):
                        users_to_notify_map[parent_author['id']] = parent_author
        
        # NOTIFICATION FIX: Always notify the post author, regardless of post type.
        # NEW: But only if they haven't hidden the post
        if post_author:
            from .posts import is_post_hidden_for_user  # Local import
            if not is_post_hidden_for_user(post_author['id'], post_id):
                users_to_notify_map[post_author['id']] = post_author
            
        # For wall posts, also notify the profile owner if they aren't the author.
        # NEW: But only if they haven't hidden the post
        if not group_id and not post.get('event_id') and post_owner_id:
            post_owner = get_user_by_id(post_owner_id)
            if post_owner:
                from .posts import is_post_hidden_for_user  # Local import
                if not is_post_hidden_for_user(post_owner['id'], post_id):
                    users_to_notify_map[post_owner['id']] = post_owner

        for user_id_to_notify, user_to_notify in users_to_notify_map.items():
            if user_id_to_notify not in already_notified:
                if user_to_notify['hostname'] is None:
                    create_notification(user_id_to_notify, user_id, notification_type, post_id, comment_id, group_id=group_id)
                else:
                    # Generic comment/reply notifications are also sent to remote users
                    send_remote_notification(user_to_notify, user_id, notification_type, post_cuid, cuid)
                already_notified.add(user_id_to_notify)

    db.commit()
    return cuid

def get_comments_for_post(post_id, viewer_user_id=None):
    #print(f"🔍 get_comments_for_post called: post_id={post_id}, viewer_user_id={viewer_user_id}")
    """
    Retrieves all top-level comments for a given post (using internal ID),
    and recursively fetches their replies and associated media.
    Filters out hidden comments for the viewer.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT c.id, c.cuid, c.post_id, c.user_id, c.content, c.timestamp, c.nu_id,
               u.username, u.display_name, u.profile_picture_path, u.hostname, u.puid
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.post_id = ? AND c.parent_comment_id IS NULL
        ORDER BY c.timestamp ASC
    """, (post_id,))
    top_level_comments = [dict(row) for row in cursor.fetchall()]

    # NEW: Filter out hidden comments
    filtered_comments = []
    for comment in top_level_comments:
        # Skip hidden comments
        if viewer_user_id and is_comment_hidden_for_user(viewer_user_id, comment['id']):
            continue
            
        comment['media_files'] = get_media_for_comment(comment['id'])
        # Get link previews for this comment
        try:
            from db_queries.link_previews import get_link_previews_for_comment
            comment['link_previews'] = get_link_previews_for_comment(comment['id'])
        except Exception as e:
            print(f"Error fetching link previews for comment {comment['id']}: {e}")
            comment['link_previews'] = []
        comment['replies'] = get_replies_for_comment(comment['id'], viewer_user_id)
        filtered_comments.append(comment)

    return filtered_comments

def get_replies_for_comment(parent_comment_id, viewer_user_id=None):
    """
    Recursively retrieves replies for a given parent comment (using internal ID), including their media.
    Filters out hidden comments for the viewer.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT c.id, c.cuid, c.post_id, c.user_id, c.content, c.timestamp, c.parent_comment_id, c.nu_id,
               u.username, u.display_name, u.profile_picture_path, u.hostname, u.puid
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.parent_comment_id = ?
        ORDER BY c.timestamp ASC
    """, (parent_comment_id,))
    replies = [dict(row) for row in cursor.fetchall()]

    # NEW: Filter out hidden replies
    filtered_replies = []
    for reply in replies:
        # Skip hidden comments
        if viewer_user_id and is_comment_hidden_for_user(viewer_user_id, reply['id']):
            continue
            
        reply['media_files'] = get_media_for_comment(reply['id'])
        # Get link previews for this reply
        try:
            from db_queries.link_previews import get_link_previews_for_comment
            reply['link_previews'] = get_link_previews_for_comment(reply['id'])
        except Exception as e:
            print(f"Error fetching link previews for reply {reply['id']}: {e}")
            reply['link_previews'] = []
        reply['replies'] = get_replies_for_comment(reply['id'], viewer_user_id)
        filtered_replies.append(reply)

    return filtered_replies

def get_media_for_comment(comment_id):
    """Retrieves all media files associated with a given comment (using internal ID)."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, muid, media_file_path, alt_text FROM comment_media WHERE comment_id = ?", (comment_id,))
    return [dict(row) for row in cursor.fetchall()]

def get_comment_by_internal_id(comment_id):
    """Retrieves a single comment by its internal integer ID, including associated media and the author's PUID."""
    db = get_db()
    cursor = db.cursor()
    # MODIFICATION: Join with the users table to fetch the author's PUID.
    cursor.execute("""
        SELECT c.*, u.puid
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.id = ?
    """, (comment_id,))
    comment = cursor.fetchone()
    if comment:
        comment_dict = dict(comment)
        comment_dict['media_files'] = get_media_for_comment(comment_id)
        # Get link previews for this comment
        try:
            from db_queries.link_previews import get_link_previews_for_comment
            comment_dict['link_previews'] = get_link_previews_for_comment(comment_id)
        except Exception as e:
            print(f"Error fetching link previews for comment {comment_id}: {e}")
            comment_dict['link_previews'] = []
        return comment_dict
    return None

def get_comment_by_cuid(cuid):
    """Retrieves a comment by its CUID and also finds the CUID of its parent post."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT c.cuid as comment_cuid, c.id as comment_id, p.cuid as post_cuid
        FROM comments c
        JOIN posts p ON c.post_id = p.id
        WHERE c.cuid = ?
    """, (cuid,))
    result = cursor.fetchone()
    return dict(result) if result else None

def get_media_by_muid_from_comment(muid):
    """Retrieves a media item from a comment by its MUID and finds the CUID of its parent post."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT cm.muid, p.cuid as post_cuid
        FROM comment_media cm
        JOIN comments c ON cm.comment_id = c.id
        JOIN posts p ON c.post_id = p.id
        WHERE cm.muid = ?
    """, (muid,))
    result = cursor.fetchone()
    return dict(result) if result else None

def update_comment(cuid, new_content, media_files=None):
    """Updates a comment by its CUID and handles new mentions."""
    # CIRCULAR IMPORT FIX: Import federation functions inside the function
    from .federation import send_remote_mention_notification
    
    db = get_db()
    cursor = db.cursor()

    comment_info = get_comment_by_cuid(cuid)
    if not comment_info:
        return False
    comment_id = comment_info['comment_id']

    original_comment = get_comment_by_internal_id(comment_id)
    if not original_comment:
        return False

    original_content = original_comment['content'] if original_comment else ''

    cursor.execute("UPDATE comments SET content = ? WHERE id = ?", (new_content, comment_id))

    current_media_ids_cursor = db.cursor()
    current_media_ids_cursor.execute("SELECT id, media_file_path FROM comment_media WHERE comment_id = ?", (comment_id,))
    current_media_map = {row['media_file_path']: row['id'] for row in current_media_ids_cursor.fetchall()}
    incoming_media_paths = {mf['media_file_path'] for mf in media_files} if media_files else set()
    media_to_delete_ids = [media_id for path, media_id in current_media_map.items() if path not in incoming_media_paths]
    if media_to_delete_ids:
        placeholders = ','.join('?' * len(media_to_delete_ids))
        cursor.execute(f"DELETE FROM comment_media WHERE id IN ({placeholders})", media_to_delete_ids)
    if media_files:
        for media_file_data in media_files:
            media_path = media_file_data.get('media_file_path')
            alt_text = media_file_data.get('alt_text')
            if media_path in current_media_map:
                db_media_id = current_media_map[media_path]
                cursor.execute("UPDATE comment_media SET alt_text = ? WHERE id = ?", (alt_text, db_media_id))
            else:
                muid = str(uuid.uuid4())
                cursor.execute("INSERT INTO comment_media (muid, comment_id, media_file_path, alt_text) VALUES (?, ?, ?, ?)",
                               (muid, comment_id, media_path, alt_text))

    actor_id = original_comment['user_id']
    post_id = original_comment['post_id'] 
    
    original_mentioned_users = extract_mentions(original_content)
    new_mentioned_users = extract_mentions(new_content)
    
    original_mentioned_ids = {u['id'] for u in original_mentioned_users}

    for user in new_mentioned_users:
        if user['id'] not in original_mentioned_ids and user['id'] != actor_id:
            if user['hostname'] is None: # Local user
                create_notification(user['id'], actor_id, 'mention', post_id, comment_id)
            else: # Remote user
                send_remote_mention_notification(user, actor_id, post_id, comment_id)

    # NEW: Regenerate link previews when content changes
    if new_content != original_content:
        try:
            from db_queries.link_previews import remove_link_previews_for_comment, associate_link_previews_with_comment
            remove_link_previews_for_comment(comment_id)
            associate_link_previews_with_comment(comment_id, new_content)
        except Exception as e:
            print(f"Error updating link previews for comment: {e}")
            
    db.commit()
    return cursor.rowcount > 0

def delete_comment(cuid):
    """Deletes a comment by its CUID, including its associated media and replies."""
    db = get_db()
    cursor = db.cursor()

    comment_info = get_comment_by_cuid(cuid)
    if not comment_info:
        return False
    comment_id = comment_info['comment_id']

    cursor.execute("DELETE FROM comment_media WHERE comment_id = ?", (comment_id,))
    cursor.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    db.commit()
    return cursor.rowcount > 0

def filter_comments(comments, snoozed_ids, viewer_blocked_by_map):
    """
    Recursively filters comments to remove content from snoozed users or
    content posted after a block was initiated.
    """
    filtered = []
    for comment in comments:
        commenter_id = comment['user_id']
        comment_timestamp_str = comment['timestamp'].split('.')[0]
        comment_timestamp = datetime.strptime(comment_timestamp_str, '%Y-%m-%d %H:%M:%S')

        if commenter_id in snoozed_ids:
            continue
        
        if commenter_id in viewer_blocked_by_map:
            blocked_at_ts = viewer_blocked_by_map[commenter_id]
            if comment_timestamp > blocked_at_ts:
                continue
        
        if 'replies' in comment and comment['replies']:
            comment['replies'] = filter_comments(comment['replies'], snoozed_ids, viewer_blocked_by_map)
        
        filtered.append(comment)
    return filtered

def remove_mention_from_comment(comment_cuid, user_display_name):
    """
    Removes @mentions of a specific user from a comment's content.
    Converts @DisplayName to just DisplayName.
    
    Args:
        comment_cuid: The CUID of the comment
        user_display_name: The display name to remove mentions of
    
    Returns:
        bool: True if successful, False otherwise
    """
    import re
    db = get_db()
    cursor = db.cursor()
    
    # Get the comment content
    cursor.execute("SELECT content FROM comments WHERE cuid = ?", (comment_cuid,))
    result = cursor.fetchone()
    
    if not result or not result['content']:
        return False
    
    content = result['content']
    
    # Remove the @ symbol before the display name (case-insensitive)
    # Pattern: @DisplayName -> DisplayName
    pattern = r'@(' + re.escape(user_display_name) + r')\b'
    new_content = re.sub(pattern, r'\1', content, flags=re.IGNORECASE)
    
    # Only update if content actually changed
    if new_content != content:
        cursor.execute("UPDATE comments SET content = ? WHERE cuid = ?", (new_content, comment_cuid))
        db.commit()
        return True
    
    return False

def hide_comment_for_user(user_id, comment_id):
    """
    Hides a comment for a specific user and recursively hides all its replies.
    
    Args:
        user_id: The ID of the user hiding the comment
        comment_id: The ID of the comment to hide
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Hide the comment itself
        cursor.execute("""
            INSERT OR IGNORE INTO hidden_content (user_id, content_type, content_id)
            VALUES (?, 'comment', ?)
        """, (user_id, comment_id))
        
        # NEW: Recursively hide all replies to this comment
        def hide_replies_recursive(parent_id):
            cursor.execute("""
                SELECT id FROM comments WHERE parent_comment_id = ?
            """, (parent_id,))
            replies = cursor.fetchall()
            
            for reply in replies:
                reply_id = reply['id']
                # Hide this reply
                cursor.execute("""
                    INSERT OR IGNORE INTO hidden_content (user_id, content_type, content_id)
                    VALUES (?, 'comment', ?)
                """, (user_id, reply_id))
                # Recursively hide its replies
                hide_replies_recursive(reply_id)
        
        hide_replies_recursive(comment_id)
        
        db.commit()
        return True
    except Exception as e:
        print(f"Error hiding comment and replies: {e}")
        return False

def is_comment_hidden_for_user(user_id, comment_id):
    """
    Check if a comment is hidden for a specific user.
    
    Args:
        user_id: The ID of the user
        comment_id: The ID of the comment
    
    Returns:
        bool: True if hidden, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT COUNT(*) as count FROM hidden_content
        WHERE user_id = ? AND content_type = 'comment' AND content_id = ?
    """, (user_id, comment_id))
    result = cursor.fetchone()
    return result['count'] > 0 if result else False

def get_hidden_comment_ids_for_user(user_id):
    """
    Get all comment IDs hidden by a specific user.
    
    Args:
        user_id: The ID of the user
    
    Returns:
        set: Set of comment IDs that are hidden
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT content_id FROM hidden_content
        WHERE user_id = ? AND content_type = 'comment'
    """, (user_id,))
    return {row['content_id'] for row in cursor.fetchall()}