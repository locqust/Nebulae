# db_queries/media.py
# Contains functions for managing media tagging and media comments.

import uuid
import json
from datetime import datetime
from flask import g
from db import get_db
from utils.text_processing import extract_mentions, extract_everyone_mention
from .users import get_user_by_id, get_user_by_puid
from .notifications import create_notification

# ============================================================================
# MEDIA TAGGING FUNCTIONS
# ============================================================================

def add_media_tags(muid, tagged_user_puids, actor_puid):
    """
    Adds tags to a media item. Replaces any existing tags.
    
    Args:
        muid: The MUID of the media item
        tagged_user_puids: List of PUIDs to tag
        actor_puid: PUID of the user performing the tagging
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    # Get the media item and its parent post
    cursor.execute("""
        SELECT pm.id, pm.post_id, p.author_puid, p.group_id, p.event_id
        FROM post_media pm
        JOIN posts p ON pm.post_id = p.id
        WHERE pm.muid = ?
    """, (muid,))
    media_row = cursor.fetchone()
    
    if not media_row:
        return False
    
    media_id = media_row['id']
    post_author_puid = media_row['author_puid']
    group_id = media_row['group_id']
    event_id = media_row['event_id']
    
    # Only the post author can tag people in their media
    if actor_puid != post_author_puid:
        return False
    
    # Convert list to JSON
    tagged_json = json.dumps(tagged_user_puids) if tagged_user_puids else None
    
    # Update the media item
    cursor.execute("""
        UPDATE post_media 
        SET tagged_user_puids = ? 
        WHERE muid = ?
    """, (tagged_json, muid))
    
    db.commit()
    
    # Create notifications for newly tagged users
    # Get the actor's internal ID
    actor_user = get_user_by_puid(actor_puid)
    if not actor_user:
        return True  # Tags were saved, just skip notifications
    
    actor_id = actor_user['id']
    
    # Separate tags into approved and pending
    approved_tags = []
    pending_tags = []
    
    for tagged_puid in tagged_user_puids:
        tagged_user = get_user_by_puid(tagged_puid)
        if not tagged_user:
            continue
            
        # Don't tag the person tagging themselves
        if tagged_puid == actor_puid:
            approved_tags.append(tagged_puid)  # Self-tags don't need approval
            continue
        
        # Check if tagged user requires parental approval
        if tagged_user['hostname'] is None:
            # Local user - check parental approval
            from .parental_controls import requires_parental_approval, create_approval_request, get_all_parent_ids
            
            if requires_parental_approval(tagged_user['id']):
                # This tag needs approval - add to pending list
                pending_tags.append(tagged_puid)
                
                # Create approval request instead of tagging directly
                tagger = get_user_by_puid(actor_puid)
                
                # Get media file path for parent preview
                cursor.execute("SELECT media_file_path FROM post_media WHERE muid = ?", (muid,))
                media_row = cursor.fetchone()
                media_file_path = media_row['media_file_path'] if media_row else None
                
                # Get the media owner's PUID for serving the image
                media_owner = get_user_by_puid(post_author_puid)
                media_owner_puid = media_owner.get('puid') if media_owner else None
                
                request_data = json.dumps({
                    'muid': muid,
                    'tagger_puid': actor_puid,
                    'tagger_display_name': tagger.get('display_name', 'Unknown') if tagger else 'Unknown',
                    'media_file_path': media_file_path,  # So parent can view the photo
                    'media_owner_puid': media_owner_puid,  # So we can serve the image
                    'media_type': 'photo'
                })
                
                approval_id = create_approval_request(
                    tagged_user['id'],
                    'media_tag',
                    muid,
                    None,
                    request_data
                )
                
                if approval_id:
                    # Notify all parents
                    parent_ids = get_all_parent_ids(tagged_user['id'])
                    for parent_id in parent_ids:
                        create_notification(parent_id, tagged_user['id'], 'parental_approval_needed')
            else:
                # No parental approval needed - add to approved tags and create notification
                approved_tags.append(tagged_puid)
                create_notification(
                    tagged_user['id'],
                    actor_id,
                    'tagged_in_media',
                    post_id=None,
                    media_id=media_id,
                    group_id=group_id,
                    event_id=event_id
                )
        else:
            # Remote user - add to approved tags and send federated notification
            approved_tags.append(tagged_puid)
            from .federation import send_remote_notification
            send_remote_notification(
                tagged_user,
                actor_id,
                'tagged_in_media',
                muid=muid,
                group_puid=None,  # TODO: Get group PUID if needed
                event_puid=None   # TODO: Get event PUID if needed
            )
    
    # Update the media item with only approved tags
    # Pending tags will be added if/when approved
    tagged_json = json.dumps(approved_tags) if approved_tags else None
    cursor.execute("""
        UPDATE post_media 
        SET tagged_user_puids = ? 
        WHERE muid = ?
    """, (tagged_json, muid))
    
    db.commit()
    
    # NEW: Distribute media tags to federation (only approved tags)
    try:
        from utils.federation_utils import distribute_media_tags
        distribute_media_tags(muid, approved_tags, actor_puid)
    except Exception as e:
        print(f"ERROR: Failed to distribute media tags: {e}")
        import traceback
        traceback.print_exc()
    
    return True


def remove_media_tag(muid, user_puid):
    """
    Removes a user's tag from a media item.
    
    Args:
        muid: The MUID of the media item
        user_puid: The PUID of the user to untag
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    # Get the media item
    cursor.execute("SELECT tagged_user_puids FROM post_media WHERE muid = ?", (muid,))
    result = cursor.fetchone()
    
    if not result or not result['tagged_user_puids']:
        return False
    
    # Parse the JSON array
    try:
        tagged_puids = json.loads(result['tagged_user_puids'])
    except (json.JSONDecodeError, TypeError):
        return False
    
    # Remove the user's PUID
    if user_puid in tagged_puids:
        tagged_puids.remove(user_puid)
        
        # Update the media item
        new_tagged_json = json.dumps(tagged_puids) if tagged_puids else None
        cursor.execute("UPDATE post_media SET tagged_user_puids = ? WHERE muid = ?", 
                      (new_tagged_json, muid))
        db.commit()

        # NEW: Distribute tag removal to federation
        try:
            from utils.federation_utils import distribute_media_tag_removal
            distribute_media_tag_removal(muid, user_puid)
        except Exception as e:
            print(f"ERROR: Failed to distribute media tag removal: {e}")
            import traceback
            traceback.print_exc()
        
        return True
    
    return False


def get_media_tags(muid):
    """
    Gets the list of tagged users for a media item.
    
    Args:
        muid: The MUID of the media item
    
    Returns:
        list: List of user dictionaries with puid, display_name, etc.
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT tagged_user_puids FROM post_media WHERE muid = ?", (muid,))
    result = cursor.fetchone()
    
    if not result or not result['tagged_user_puids']:
        return []
    
    try:
        tagged_puids = json.loads(result['tagged_user_puids'])
    except (json.JSONDecodeError, TypeError):
        return []
    
    # Fetch user details for each tagged PUID
    tagged_users = []
    for puid in tagged_puids:
        user = get_user_by_puid(puid)
        if user:
            tagged_users.append(user)
    
    return tagged_users

def get_media_by_muid(muid):
    """
    Retrieves a media item by its MUID.
    
    Args:
        muid: The MUID of the media item
    
    Returns:
        dict: Media item details, or None if not found
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT pm.id, pm.muid, pm.post_id, pm.media_file_path, pm.alt_text, 
               pm.tagged_user_puids, pm.origin_hostname
        FROM post_media pm
        WHERE pm.muid = ?
    """, (muid,))
    
    result = cursor.fetchone()
    return dict(result) if result else None

def get_tagged_media_for_user(user_puid, viewer_user_id, viewer_is_admin):
    """
    Retrieves all media items where a user is tagged, respecting privacy settings.
    
    Args:
        user_puid: PUID of the user whose tagged media to retrieve
        viewer_user_id: Internal ID of the viewer
        viewer_is_admin: Whether the viewer is an admin
    
    Returns:
        list: List of media items with metadata
    """
    # Import these to avoid circular imports
    from .friends import is_friends_with
    from .followers import is_following
    
    db = get_db()
    cursor = db.cursor()
    
    user = get_user_by_puid(user_puid)
    if not user:
        return []
    
    user_id = user['id']
    
    # Determine visible privacy levels based on viewer relationship
    visible_privacy_levels = {'public'}
    viewer_puid = None
    
    if viewer_user_id:
        viewer_user = get_user_by_id(viewer_user_id)
        if viewer_user:
            viewer_puid = viewer_user['puid']
        
        # Check if viewer is the user themselves or an admin
        if viewer_user and (viewer_user['puid'] == user_puid or viewer_is_admin):
            visible_privacy_levels.update(['friends', 'local', 'followers', 'group', 'event'])
        elif is_friends_with(viewer_user_id, user_id):
            visible_privacy_levels.add('friends')
            if viewer_user and viewer_user['hostname'] is None:
                visible_privacy_levels.add('local')
            # Include 'event' and 'group' so friends can see tagged photos if they're attending/members
            visible_privacy_levels.update(['event', 'group'])
    
    placeholders = ','.join('?' for _ in visible_privacy_levels)
    
    # Query for media where user is tagged
    query = f"""
        SELECT pm.id, pm.muid, pm.media_file_path, pm.alt_text, pm.tagged_user_puids,
            pm.origin_hostname, p.author_puid, p.timestamp, 
            u.username, u.puid, p.privacy_setting, p.cuid as post_cuid, p.event_id, p.group_id,
            strftime('%Y', p.timestamp) as year,
            strftime('%m', p.timestamp) as month
        FROM post_media pm
        JOIN posts p ON pm.post_id = p.id
        JOIN users u ON p.author_puid = u.puid
        WHERE pm.tagged_user_puids IS NOT NULL 
            AND pm.tagged_user_puids != '[]'
            AND EXISTS (
                SELECT 1 FROM json_each(pm.tagged_user_puids) 
                WHERE value = ?
            )
            AND p.privacy_setting IN ({placeholders})
        ORDER BY p.timestamp DESC
    """
    
    params = [user_puid] + list(visible_privacy_levels)
    cursor.execute(query, tuple(params))
    
    tagged_media = []
    for row in cursor.fetchall():
        # For event posts, check if viewer is an attendee
        if row['privacy_setting'] == 'event' and row['event_id'] and viewer_user_id:
            # Check if viewer is invited/attending/tentative (not declined)
            cursor.execute("""
                SELECT response FROM event_attendees 
                WHERE event_id = ? AND user_puid = ?
            """, (row['event_id'], viewer_puid))
            
            attendee_row = cursor.fetchone()
            if not attendee_row or attendee_row['response'] == 'declined':
                # Viewer is not attending this event or declined, skip this media
                continue
        
        # For group posts, check if viewer is a member
        if row['privacy_setting'] == 'group' and row['group_id'] and viewer_user_id:
            # Check if viewer is a member of this group
            cursor.execute("""
                SELECT 1 FROM group_members 
                WHERE group_id = ? AND user_id = ?
            """, (row['group_id'], viewer_user_id))
            
            if not cursor.fetchone():
                # Viewer is not a member of this group, skip this media
                continue
        
        # Determine media type
        media_path_lower = row['media_file_path'].lower()
        media_type = 'other'
        if media_path_lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')):
            media_type = 'image'
        elif media_path_lower.endswith(('.mp4', '.mov', '.webm', '.avi', '.mkv')):
            media_type = 'video'
        
        tagged_media.append({
            'id': row['id'],
            'muid': row['muid'],
            'media_file_path': row['media_file_path'],
            'origin_hostname': row['origin_hostname'],
            'media_type': media_type,
            'alt_text': row['alt_text'],
            'username': row['username'],
            'puid': row['puid'],
            'post_cuid': row['post_cuid'],
            'timestamp': row['timestamp'],
            'year': row['year'],
            'month': row['month'],
            'tagged_user_puids': row['tagged_user_puids']
        })
    
    return tagged_media


# ============================================================================
# MEDIA COMMENT FUNCTIONS
# ============================================================================

def add_media_comment(muid, user_id, content, parent_comment_id=None, media_files=None, nu_id=None, cuid=None, is_remote=False):
    """
    Adds a new comment to a media item.
    
    Args:
        muid: The MUID of the media item being commented on
        user_id: Internal ID of the commenter
        content: Comment text
        parent_comment_id: ID of parent comment if this is a reply
        media_files: List of media attachments
        nu_id: Node unique ID (for federation)
        cuid: Content unique ID (for federation)
        is_remote: Whether this is a federated comment
    
    Returns:
        str: The CUID of the created comment, or None on failure
    """
    from .federation import send_remote_mention_notification, send_remote_notification
    
    db = get_db()
    cursor = db.cursor()
    
    # Get the media item and verify it exists
    cursor.execute("""
        SELECT pm.id, pm.post_id, p.author_puid, p.user_id as post_author_id
        FROM post_media pm
        JOIN posts p ON pm.post_id = p.id
        WHERE pm.muid = ?
    """, (muid,))
    media_row = cursor.fetchone()
    
    if not media_row:
        raise ValueError("Media item not found for the given MUID.")
    
    media_id = media_row['id']
    post_author_id = media_row['post_author_id']
    
    if nu_id is None:
        nu_id = g.nu_id
    
    if cuid is None:
        cuid = str(uuid.uuid4())
    
    # Insert the comment
    cursor.execute("""
        INSERT INTO media_comments (cuid, media_id, user_id, content, parent_comment_id, nu_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (cuid, media_id, user_id, content, parent_comment_id, nu_id))
    
    comment_id = cursor.lastrowid
    
    # Add media attachments if any
    if media_files:
        for media_file_data in media_files:
            media_path = media_file_data.get('media_file_path')
            alt_text = media_file_data.get('alt_text')
            origin_hostname = media_file_data.get('origin_hostname')
            if media_path:
                media_muid = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO media_comment_media (muid, media_comment_id, media_file_path, alt_text, origin_hostname)
                    VALUES (?, ?, ?, ?, ?)
                """, (media_muid, comment_id, media_path, alt_text, origin_hostname))
    
    db.commit()
    
    # Create notifications (only for local comments)
    if not is_remote:
        actor_id = user_id
        
        # Notify the media owner if it's a top-level comment and not their own
        if not parent_comment_id and post_author_id and post_author_id != actor_id:
            post_author = get_user_by_id(post_author_id)
            if post_author:
                if post_author['hostname'] is None:
                    # Local user
                    create_notification(
                        post_author_id,
                        actor_id,
                        'media_comment',
                        media_id=media_id,
                        media_comment_id=comment_id
                    )
                else:
                    # Remote user
                    send_remote_notification(
                        post_author,
                        actor_id,
                        'media_comment',
                        muid=muid,
                        media_comment_cuid=cuid
                    )
        
        # Notify parent comment author if it's a reply
        if parent_comment_id:
            cursor.execute("SELECT user_id FROM media_comments WHERE id = ?", (parent_comment_id,))
            parent_row = cursor.fetchone()
            if parent_row and parent_row['user_id'] != actor_id:
                parent_author = get_user_by_id(parent_row['user_id'])
                if parent_author:
                    if parent_author['hostname'] is None:
                        create_notification(
                            parent_row['user_id'],
                            actor_id,
                            'media_reply',
                            media_id=media_id,
                            media_comment_id=comment_id
                        )
                    else:
                        send_remote_notification(
                            parent_author,
                            actor_id,
                            'media_reply',
                            muid=muid,
                            media_comment_cuid=cuid
                        )

        # Notify tagged users in the media (if comment is on media they're tagged in)
        cursor.execute("SELECT tagged_user_puids FROM post_media WHERE id = ?", (media_id,))
        tagged_row = cursor.fetchone()
        if tagged_row and tagged_row['tagged_user_puids']:
            try:
                import json
                # Get the actor's PUID
                actor_user = get_user_by_id(actor_id)
                actor_puid = actor_user['puid'] if actor_user else None
                
                tagged_puids = json.loads(tagged_row['tagged_user_puids'])
                for tagged_puid in tagged_puids:
                    # Don't notify the commenter if they're tagged
                    if actor_puid and tagged_puid == actor_puid:
                        continue
                    
                    # Don't notify if this is the post author (they already got notified above)
                    if post_author_id:
                        post_author = get_user_by_id(post_author_id)
                        if post_author and post_author.get('puid') == tagged_puid:
                            continue
                        
                    tagged_user = get_user_by_puid(tagged_puid)
                    if not tagged_user:
                        continue
                        
                    if tagged_user['hostname'] is None:
                        # Local user
                        create_notification(
                            tagged_user['id'],
                            actor_id,
                            'tagged_media_comment',
                            media_id=media_id,
                            media_comment_id=comment_id
                        )
                    else:
                        # Remote user - send federated notification
                        send_remote_notification(
                            tagged_user,
                            actor_id,
                            'tagged_media_comment',
                            muid=muid,
                            media_comment_cuid=cuid
                        )
            except (json.JSONDecodeError, TypeError):
                pass  # Invalid JSON, skip notifications

        # Notify mentioned users
        mentioned_users = extract_mentions(content)
        for user in mentioned_users:
            if user['id'] != actor_id:
                # Check if the user has hidden the parent comment or the media
                parent_hidden = False
                if parent_comment_id:
                    parent_hidden = is_media_comment_hidden_for_user(user['id'], parent_comment_id)
                
                # Skip notification if parent is hidden for this user
                if not parent_hidden:
                    if user['hostname'] is None:
                        create_notification(
                            user['id'],
                            actor_id,
                            'media_mention',
                            media_id=media_id,
                            media_comment_id=comment_id
                        )
                    else:
                        send_remote_mention_notification(
                            user,
                            actor_id,
                            muid=muid,
                            media_comment_cuid=cuid
                        )
    
        # NEW: Distribute media comment to federation
    # Only distribute if this is a local comment (not already federated)
    if not is_remote:
        from utils.federation_utils import distribute_media_comment
        distribute_media_comment(cuid)

    return cuid


def get_media_comments(muid, viewer_user_id=None):
    """
    Retrieves all top-level comments for a media item.
    
    Args:
        muid: The MUID of the media item
        viewer_user_id: Internal ID of the viewer (for hidden content filtering)
    
    Returns:
        list: List of comment dictionaries with nested replies
    """
    db = get_db()
    cursor = db.cursor()
    
    # Get the media_id from muid
    cursor.execute("SELECT id FROM post_media WHERE muid = ?", (muid,))
    media_row = cursor.fetchone()
    
    if not media_row:
        return []
    
    media_id = media_row['id']
    
    # Get top-level comments
    cursor.execute("""
        SELECT mc.id, mc.cuid, mc.media_id, mc.user_id, mc.content, mc.timestamp, mc.nu_id,
               u.username, u.display_name, u.profile_picture_path, u.hostname, u.puid
        FROM media_comments mc
        JOIN users u ON mc.user_id = u.id
        WHERE mc.media_id = ? AND mc.parent_comment_id IS NULL
        ORDER BY mc.timestamp ASC
    """, (media_id,))
    
    top_level_comments = [dict(row) for row in cursor.fetchall()]
    
    # Filter out hidden comments and add replies
    filtered_comments = []
    for comment in top_level_comments:
        # Skip hidden comments
        if viewer_user_id and is_media_comment_hidden_for_user(viewer_user_id, comment['id']):
            continue
        
        comment['media_files'] = get_media_for_media_comment(comment['id'])
        comment['replies'] = get_replies_for_media_comment(comment['id'], viewer_user_id)
        filtered_comments.append(comment)
    
    return filtered_comments


def get_replies_for_media_comment(parent_comment_id, viewer_user_id=None):
    """
    Recursively retrieves replies for a media comment.
    
    Args:
        parent_comment_id: Internal ID of the parent comment
        viewer_user_id: Internal ID of the viewer
    
    Returns:
        list: List of reply dictionaries
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT mc.id, mc.cuid, mc.media_id, mc.user_id, mc.content, mc.timestamp, mc.parent_comment_id, mc.nu_id,
               u.username, u.display_name, u.profile_picture_path, u.hostname, u.puid
        FROM media_comments mc
        JOIN users u ON mc.user_id = u.id
        WHERE mc.parent_comment_id = ?
        ORDER BY mc.timestamp ASC
    """, (parent_comment_id,))
    
    replies = [dict(row) for row in cursor.fetchall()]
    
    # Filter out hidden replies and add nested replies
    filtered_replies = []
    for reply in replies:
        # Skip hidden comments
        if viewer_user_id and is_media_comment_hidden_for_user(viewer_user_id, reply['id']):
            continue
        
        reply['media_files'] = get_media_for_media_comment(reply['id'])
        reply['replies'] = get_replies_for_media_comment(reply['id'], viewer_user_id)
        filtered_replies.append(reply)
    
    return filtered_replies


def get_media_for_media_comment(comment_id):
    """
    Retrieves all media attachments for a media comment.
    
    Args:
        comment_id: Internal ID of the comment
    
    Returns:
        list: List of media dictionaries
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT id, muid, media_file_path, alt_text, origin_hostname
        FROM media_comment_media
        WHERE media_comment_id = ?
    """, (comment_id,))
    
    return [dict(row) for row in cursor.fetchall()]


def get_media_comment_by_cuid(cuid):
    """
    Retrieves a media comment by its CUID.
    
    Args:
        cuid: Content Unique ID
    
    Returns:
        dict: Comment data including user_id, comment_id, content, muid, and media_files
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT mc.cuid, mc.id as comment_id, mc.user_id, mc.content, pm.muid
        FROM media_comments mc
        JOIN post_media pm ON mc.media_id = pm.id
        WHERE mc.cuid = ?
    """, (cuid,))
    
    result = cursor.fetchone()
    
    if result:
        comment_dict = dict(result)
        # Add media files
        comment_dict['media_files'] = get_media_for_media_comment(comment_dict['comment_id'])
        return comment_dict
    
    return None


def update_media_comment(cuid, new_content, media_files=None):
    """
    Updates a media comment.
    
    Args:
        cuid: Content Unique ID of the comment
        new_content: New comment text
        media_files: Updated list of media attachments
    
    Returns:
        bool: True if successful, False otherwise
    """
    from .federation import send_remote_mention_notification
    
    db = get_db()
    cursor = db.cursor()
    
    comment_info = get_media_comment_by_cuid(cuid)
    if not comment_info:
        return False
    
    comment_id = comment_info['comment_id']
    
    # Get original comment for comparison
    cursor.execute("SELECT content, user_id, media_id FROM media_comments WHERE id = ?", (comment_id,))
    original = cursor.fetchone()
    if not original:
        return False
    
    original_content = original['content']
    actor_id = original['user_id']
    media_id = original['media_id']
    
    # Update content
    cursor.execute("UPDATE media_comments SET content = ? WHERE id = ?", (new_content, comment_id))
    
    # Handle media attachments (similar to post comment updates)
    current_media_cursor = db.cursor()
    current_media_cursor.execute("""
        SELECT id, media_file_path FROM media_comment_media WHERE media_comment_id = ?
    """, (comment_id,))
    current_media_map = {row['media_file_path']: row['id'] for row in current_media_cursor.fetchall()}
    
    incoming_media_paths = {mf['media_file_path'] for mf in media_files} if media_files else set()
    media_to_delete_ids = [media_id for path, media_id in current_media_map.items() if path not in incoming_media_paths]
    
    if media_to_delete_ids:
        placeholders = ','.join('?' * len(media_to_delete_ids))
        cursor.execute(f"DELETE FROM media_comment_media WHERE id IN ({placeholders})", media_to_delete_ids)
    
    if media_files:
        for media_file_data in media_files:
            media_path = media_file_data.get('media_file_path')
            alt_text = media_file_data.get('alt_text')
            origin_hostname = media_file_data.get('origin_hostname')
            
            if media_path in current_media_map:
                db_media_id = current_media_map[media_path]
                cursor.execute("""
                    UPDATE media_comment_media SET alt_text = ?, origin_hostname = ? WHERE id = ?
                """, (alt_text, origin_hostname, db_media_id))
            else:
                media_muid = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO media_comment_media (muid, media_comment_id, media_file_path, alt_text, origin_hostname)
                    VALUES (?, ?, ?, ?, ?)
                """, (media_muid, comment_id, media_path, alt_text, origin_hostname))
    
    # Notify newly mentioned users
    original_mentioned_users = extract_mentions(original_content)
    new_mentioned_users = extract_mentions(new_content)
    
    original_mentioned_ids = {u['id'] for u in original_mentioned_users}
    
    for user in new_mentioned_users:
        if user['id'] not in original_mentioned_ids and user['id'] != actor_id:
            if user['hostname'] is None:
                create_notification(
                    user['id'],
                    actor_id,
                    'media_mention',
                    media_id=media_id,
                    media_comment_id=comment_id
                )
            else:
                # Get the muid for the media mention notification
                cursor.execute("SELECT muid FROM post_media WHERE id = ?", (media_id,))
                muid_row = cursor.fetchone()
                if muid_row:
                    send_remote_mention_notification(user, actor_id, muid=muid_row['muid'], media_comment_cuid=cuid)
    
    db.commit()
    
    # NEW: Distribute the update to federation
    try:
        from utils.federation_utils import distribute_media_comment_update
        distribute_media_comment_update(cuid)
    except Exception as e:
        print(f"ERROR: Failed to distribute media comment update: {e}")
        import traceback
        traceback.print_exc()
    
    return True

def remove_mention_from_media_comment(cuid, user_display_name):
    """
    Removes @mentions of a specific user from a media comment's content.
    Converts @DisplayName to just DisplayName.
    
    Args:
        cuid: The CUID of the media comment
        user_display_name: The display name to remove mentions of
    
    Returns:
        bool: True if successful, False otherwise
    """
    import re
    db = get_db()
    cursor = db.cursor()
    
    # Get the comment content directly
    cursor.execute("SELECT content FROM media_comments WHERE cuid = ?", (cuid,))
    result = cursor.fetchone()
    
    if not result or not result['content']:
        return False
    
    content = result['content']
    
    # Remove the @ symbol before the display name (case-insensitive)
    # Pattern: @DisplayName -> DisplayName
    pattern = r'@(' + re.escape(user_display_name) + r')\b'
    new_content = re.sub(pattern, r'\1', content, flags=re.IGNORECASE)

        # DEBUG
    print(f"DEBUG: Removing mention of '{user_display_name}'")
    print(f"DEBUG: Original content: {content}")
    print(f"DEBUG: Pattern: {pattern}")
    print(f"DEBUG: New content: {new_content}")
    print(f"DEBUG: Content changed: {new_content != content}")
    
    # Only update if content actually changed
    if new_content == content:
        return False
    
    # Only update if content actually changed
    if new_content == content:
        return False
    
    # Update the comment content
    cursor.execute("UPDATE media_comments SET content = ? WHERE cuid = ?", (new_content, cuid))
    
    # Get actor PUID for distribution
    cursor.execute("SELECT user_id FROM media_comments WHERE cuid = ?", (cuid,))
    comment_row = cursor.fetchone()
    actor_puid = None
    if comment_row:
        from db_queries.users import get_user_by_id
        actor_user = get_user_by_id(comment_row['user_id'])
        if actor_user:
            actor_puid = actor_user['puid']
    
    db.commit()
    
    # NEW: Distribute mention removal to federation
    if actor_puid:
        try:
            from utils.federation_utils import distribute_mention_removal_media_comment
            distribute_mention_removal_media_comment(cuid, user_display_name, actor_puid)
        except Exception as e:
            print(f"ERROR: Failed to distribute media comment mention removal: {e}")
            import traceback
            traceback.print_exc()
    
    return True

def delete_media_comment(cuid):
    """
    Deletes a media comment by its CUID.
    
    Args:
        cuid: Content Unique ID
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    comment_info = get_media_comment_by_cuid(cuid)
    if not comment_info:
        return False
    
    comment_id = comment_info['comment_id']
    
    # NEW: Get comment and media info BEFORE deletion for federation
    comment = get_media_comment_by_internal_id(comment_id)
    if comment:
        media_id = comment.get('media_id')
        if media_id:
            # Get media item for distribution
            cursor.execute("SELECT muid, post_id, tagged_user_puids FROM post_media WHERE id = ?", (media_id,))
            media_row = cursor.fetchone()
            if media_row:
                media_item = dict(media_row)
                
                # Distribute delete to federation BEFORE actually deleting
                from utils.federation_utils import distribute_media_comment_delete
                distribute_media_comment_delete(comment, media_item)
    
    # Delete associated media
    cursor.execute("DELETE FROM media_comment_media WHERE media_comment_id = ?", (comment_id,))
    
    # Delete the comment (CASCADE will handle replies)
    cursor.execute("DELETE FROM media_comments WHERE id = ?", (comment_id,))
    
    db.commit()
    return cursor.rowcount > 0

def is_media_comment_hidden_for_user(user_id, media_comment_id):
    """
    Checks if a media comment is hidden for a specific user.
    
    Args:
        user_id: Internal ID of the user
        media_comment_id: Internal ID of the media comment
    
    Returns:
        bool: True if hidden, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as count FROM hidden_content
        WHERE user_id = ? AND content_type = 'media_comment' AND content_id = ?
    """, (user_id, media_comment_id))
    
    result = cursor.fetchone()
    return result['count'] > 0 if result else False


def hide_media_comment_for_user(user_id, media_comment_id):
    """
    Hides a media comment from a user's view and recursively hides all its replies.
    
    Args:
        user_id: Internal ID of the user
        media_comment_id: Internal ID of the media comment
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Hide the comment itself
        cursor.execute("""
            INSERT OR IGNORE INTO hidden_content (user_id, content_type, content_id)
            VALUES (?, 'media_comment', ?)
        """, (user_id, media_comment_id))
        
        # Recursively hide all replies to this comment
        def hide_replies_recursive(parent_id):
            cursor.execute("""
                SELECT id FROM media_comments WHERE parent_comment_id = ?
            """, (parent_id,))
            replies = cursor.fetchall()
            
            for reply in replies:
                reply_id = reply['id']
                # Hide this reply
                cursor.execute("""
                    INSERT OR IGNORE INTO hidden_content (user_id, content_type, content_id)
                    VALUES (?, 'media_comment', ?)
                """, (user_id, reply_id))
                # Recursively hide its replies
                hide_replies_recursive(reply_id)
        
        hide_replies_recursive(media_comment_id)
        
        db.commit()
        return True
    except Exception as e:
        print(f"Error hiding media comment and replies: {e}")
        return False


def get_media_comment_count(muid):
    """
    Gets the total count of comments (including replies) for a media item.
    
    Args:
        muid: The MUID of the media item
    
    Returns:
        int: Total comment count
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM media_comments mc
        JOIN post_media pm ON mc.media_id = pm.id
        WHERE pm.muid = ?
    """, (muid,))
    
    result = cursor.fetchone()
    return result['count'] if result else 0


def get_comment_media_details_by_muid(muid):
    """
    Get complete comment media details by MUID for displaying in media view page.
    Returns data structure similar to post media for consistency.
    
    Args:
        muid: The MUID of the comment media item
        
    Returns:
        dict: Media details with keys: id, muid, comment_id, media_file_path, alt_text, 
              origin_hostname, post_cuid, media_type
        None if not found
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT 
            cm.id,
            cm.muid,
            cm.comment_id,
            cm.media_file_path,
            cm.alt_text,
            u.hostname as origin_hostname,
            p.cuid as post_cuid
        FROM comment_media cm
        JOIN comments c ON cm.comment_id = c.id
        JOIN posts p ON c.post_id = p.id
        JOIN users u ON c.user_id = u.id
        WHERE cm.muid = ?
    """, (muid,))
    
    result = cursor.fetchone()
    
    if result:
        media_dict = dict(result)
        # Add media_type based on file extension (consistent with post media)
        file_path = media_dict['media_file_path'].lower()
        if file_path.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')):
            media_dict['media_type'] = 'image'
        elif file_path.endswith(('.mp4', '.mov', '.webm', '.avi', '.mkv')):
            media_dict['media_type'] = 'video'
        else:
            media_dict['media_type'] = 'other'
        return media_dict
    return None

def get_media_comment_by_internal_id(comment_id):
    """
    Retrieves a media comment by its internal ID.
    
    Args:
        comment_id: The internal ID of the comment
    
    Returns:
        dict: Comment details, or None if not found
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT mc.id, mc.cuid, mc.media_id, mc.user_id, mc.content, 
               mc.timestamp, mc.parent_comment_id, mc.nu_id
        FROM media_comments mc
        WHERE mc.id = ?
    """, (comment_id,))
    
    result = cursor.fetchone()
    if not result:
        return None
    
    comment = dict(result)
    
    # Add media files
    comment['media_files'] = get_media_for_media_comment(comment_id)
    
    return comment