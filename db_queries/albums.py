"""
Database queries for media albums functionality.
"""
from db import get_db
import uuid


def create_album(owner_puid, title, description=None, group_puid=None):
    """
    Creates a new media album.
    
    Args:
        owner_puid: PUID of the user creating the album
        title: Album title
        description: Optional album description
        group_puid: Optional PUID of group if this is a group album
    
    Returns:
        str: The album_uid of the created album, or None on failure
    """
    db = get_db()
    cursor = db.cursor()
    
    album_uid = str(uuid.uuid4())
    
    try:
        cursor.execute("""
            INSERT INTO media_albums (album_uid, owner_puid, group_puid, title, description)
            VALUES (?, ?, ?, ?, ?)
        """, (album_uid, owner_puid, group_puid, title, description))
        db.commit()
        return album_uid
    except Exception as e:
        print(f"Error creating album: {e}")
        db.rollback()
        return None


def get_albums_for_user(puid):
    """
    Retrieves all albums owned by a user (excluding group albums).
    
    Args:
        puid: User's PUID
    
    Returns:
        list: List of album dictionaries
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT 
            ma.id,
            ma.album_uid,
            ma.owner_puid,
            ma.group_puid,
            ma.title,
            ma.description,
            ma.created_at,
            ma.updated_at,
            COUNT(am.media_id) as media_count
        FROM media_albums ma
        LEFT JOIN album_media am ON ma.id = am.album_id
        WHERE ma.owner_puid = ? AND ma.group_puid IS NULL
        GROUP BY ma.id
        ORDER BY ma.updated_at DESC
    """, (puid,))
    
    return [dict(row) for row in cursor.fetchall()]


def get_albums_for_group(group_puid):
    """
    Retrieves all albums for a group.
    
    Args:
        group_puid: Group's PUID
    
    Returns:
        list: List of album dictionaries
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT 
            ma.id,
            ma.album_uid,
            ma.owner_puid,
            ma.group_puid,
            ma.title,
            ma.description,
            ma.created_at,
            ma.updated_at,
            COUNT(am.media_id) as media_count
        FROM media_albums ma
        LEFT JOIN album_media am ON ma.id = am.album_id
        WHERE ma.group_puid = ?
        GROUP BY ma.id
        ORDER BY ma.updated_at DESC
    """, (group_puid,))
    
    return [dict(row) for row in cursor.fetchall()]


def get_album_by_uid(album_uid):
    """
    Retrieves an album by its UID.
    
    Args:
        album_uid: Album's unique identifier
    
    Returns:
        dict: Album details, or None if not found
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT * FROM media_albums WHERE album_uid = ?
    """, (album_uid,))
    
    result = cursor.fetchone()
    return dict(result) if result else None


def get_album_media(album_id, viewer_user_id=None, viewer_is_admin=False, album_owner_puid=None, group_puid=None):
    """
    Retrieves all media items in an album, filtered by viewer's privacy permissions.
    
    Args:
        album_id: Internal album ID
        viewer_user_id: ID of the user viewing the album (None for anonymous)
        viewer_is_admin: Whether the viewer is an admin
        album_owner_puid: PUID of the album owner (for determining visibility)
    
    Returns:
        list: List of media item dictionaries with full details (filtered by privacy)
    """
    from .friends import is_friends_with
    from .users import get_user_by_id
    
    db = get_db()
    cursor = db.cursor()
    
    # Determine visible privacy levels based on viewer relationship
    visible_privacy_levels = {'public'}
    
    if viewer_user_id:
        viewer_user = get_user_by_id(viewer_user_id)
        if viewer_user:
            viewer_puid = viewer_user['puid']
            
            # Viewer is the album owner or admin - can see everything
            if (album_owner_puid and viewer_puid == album_owner_puid) or viewer_is_admin:
                visible_privacy_levels.update(['friends', 'local', 'followers', 'group', 'event'])
            else:
                # Check if this is a group album
                if group_puid:
                    # For group albums, check group membership
                    from .groups import is_user_group_member, get_group_by_puid
                    group = get_group_by_puid(group_puid)
                    if group and is_user_group_member(viewer_user_id, group['id']):
                        visible_privacy_levels.add('group')
                        # Group members can see group posts
                else:
                    # For user albums, check friendship with album owner
                    if album_owner_puid:
                        from .users import get_user_by_puid
                        owner_user = get_user_by_puid(album_owner_puid)
                        if owner_user:
                            owner_user_id = owner_user['id']
                            
                            # Check friendship
                            if is_friends_with(viewer_user_id, owner_user_id):
                                visible_privacy_levels.add('friends')
                                
                                # Local privacy: only if viewer is also local (same node)
                                if viewer_user['hostname'] is None:
                                    visible_privacy_levels.add('local')
    
    # Build the privacy filter
    placeholders = ','.join('?' for _ in visible_privacy_levels)
    
    cursor.execute(f"""
        SELECT 
            pm.id,
            pm.muid,
            pm.media_file_path,
            pm.alt_text,
            u.hostname as origin_hostname,
            pm.tagged_user_puids,
            p.author_puid,
            p.timestamp,
            p.cuid as post_cuid,
            p.privacy_setting,
            u.username,
            u.puid,
            strftime('%Y', p.timestamp) as year,
            strftime('%m', p.timestamp) as month,
            am.display_order
        FROM album_media am
        JOIN post_media pm ON am.media_id = pm.id
        JOIN posts p ON pm.post_id = p.id
        JOIN users u ON p.author_puid = u.puid
        WHERE am.album_id = ? AND p.privacy_setting IN ({placeholders})
        ORDER BY am.display_order ASC, am.added_at DESC
    """, (album_id,) + tuple(visible_privacy_levels))
    
    media_items = []
    for row in cursor.fetchall():
        media_dict = dict(row)
        # Determine media type
        media_path_lower = media_dict['media_file_path'].lower()
        if media_path_lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')):
            media_dict['media_type'] = 'image'
        elif media_path_lower.endswith(('.mp4', '.mov', '.webm', '.avi', '.mkv')):
            media_dict['media_type'] = 'video'
        else:
            media_dict['media_type'] = 'other'
        
        media_items.append(media_dict)
    
    return media_items


def add_media_to_album(album_id, media_id, display_order=0):
    """
    Adds a media item to an album.
    
    Args:
        album_id: Internal album ID
        media_id: Internal media ID (post_media.id)
        display_order: Optional display order
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO album_media (album_id, media_id, display_order)
            VALUES (?, ?, ?)
        """, (album_id, media_id, display_order))
        
        # Update album's updated_at timestamp
        cursor.execute("""
            UPDATE media_albums 
            SET updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (album_id,))
        
        db.commit()
        return True
    except Exception as e:
        print(f"Error adding media to album: {e}")
        db.rollback()
        return False


def remove_media_from_album(album_id, media_id):
    """
    Removes a media item from an album.
    
    Args:
        album_id: Internal album ID
        media_id: Internal media ID
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM album_media 
            WHERE album_id = ? AND media_id = ?
        """, (album_id, media_id))
        
        # Update album's updated_at timestamp
        cursor.execute("""
            UPDATE media_albums 
            SET updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (album_id,))
        
        db.commit()
        return True
    except Exception as e:
        print(f"Error removing media from album: {e}")
        db.rollback()
        return False


def update_album(album_uid, title=None, description=None):
    """
    Updates an album's details.
    
    Args:
        album_uid: Album's unique identifier
        title: New title (optional)
        description: New description (optional)
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        updates = []
        params = []
        
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        
        if not updates:
            return True
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(album_uid)
        
        query = f"UPDATE media_albums SET {', '.join(updates)} WHERE album_uid = ?"
        cursor.execute(query, params)
        db.commit()
        return True
    except Exception as e:
        print(f"Error updating album: {e}")
        db.rollback()
        return False


def delete_album(album_uid):
    """
    Deletes an album (but not the media items themselves).
    
    Args:
        album_uid: Album's unique identifier
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM media_albums WHERE album_uid = ?
        """, (album_uid,))
        db.commit()
        return True
    except Exception as e:
        print(f"Error deleting album: {e}")
        db.rollback()
        return False


def check_album_ownership(album_uid, user_puid):
    """
    Checks if a user owns an album.
    
    Args:
        album_uid: Album's unique identifier
        user_puid: User's PUID
    
    Returns:
        bool: True if user owns the album, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as count FROM media_albums 
        WHERE album_uid = ? AND owner_puid = ?
    """, (album_uid, user_puid))
    
    result = cursor.fetchone()
    return result['count'] > 0 if result else False


def get_media_albums(media_id):
    """
    Gets all albums that contain a specific media item.
    
    Args:
        media_id: Internal media ID (post_media.id)
    
    Returns:
        list: List of album dictionaries
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT ma.*
        FROM media_albums ma
        JOIN album_media am ON ma.id = am.album_id
        WHERE am.media_id = ?
    """, (media_id,))
    
    return [dict(row) for row in cursor.fetchall()]

def check_album_management_permission(album_uid, user_puid, user_id):
    """
    Checks if a user can manage (edit/delete) an album.
    For user albums: only owner can manage
    For group albums: owner, group admins, and group moderators can delete (only owner can edit)
    
    Args:
        album_uid: Album's unique identifier
        user_puid: User's PUID
        user_id: User's internal ID (for group role checks)
    
    Returns:
        dict: {'can_edit': bool, 'can_delete': bool}
    """
    db = get_db()
    cursor = db.cursor()
    
    # First check if user owns the album
    is_owner = check_album_ownership(album_uid, user_puid)
    
    # Get album details to check if it's a group album
    cursor.execute("""
        SELECT group_puid FROM media_albums WHERE album_uid = ?
    """, (album_uid,))
    
    album = cursor.fetchone()
    if not album:
        return {'can_edit': False, 'can_delete': False}
    
    # For non-group albums, only owner can edit/delete
    if not album['group_puid']:
        return {'can_edit': is_owner, 'can_delete': is_owner}
    
    # It's a group album - owner can edit and delete
    if is_owner:
        return {'can_edit': True, 'can_delete': True}
    
    # Check if user is admin or moderator (they can delete but not edit)
    from db_queries.groups import get_group_by_puid, is_user_group_moderator_or_admin
    
    group = get_group_by_puid(album['group_puid'])
    if not group:
        return {'can_edit': False, 'can_delete': False}
    
    is_mod_or_admin = is_user_group_moderator_or_admin(user_id, group['id'])
    
    return {
        'can_edit': False,  # Only owner can edit
        'can_delete': is_mod_or_admin  # Admins/mods can delete
    }


def get_group_media_for_user(group_puid, user_puid):
    """
    Gets all media posted by a specific user in a specific group.
    This is used to populate the media selection when creating/editing group albums.
    
    Args:
        group_puid: Group's PUID
        user_puid: User's PUID
    
    Returns:
        list: List of media item dictionaries
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT 
            pm.id,
            pm.muid,
            pm.media_file_path,
            pm.alt_text,
            u.hostname as origin_hostname,
            pm.tagged_user_puids,
            p.author_puid,
            p.timestamp,
            p.cuid as post_cuid,
            u.username,
            u.puid,
            strftime('%Y', p.timestamp) as year,
            strftime('%m', p.timestamp) as month
        FROM post_media pm
        JOIN posts p ON pm.post_id = p.id
        JOIN users u ON p.author_puid = u.puid
        JOIN groups g ON p.group_id = g.id
        WHERE g.puid = ? AND p.author_puid = ?
        ORDER BY p.timestamp DESC
    """, (group_puid, user_puid))
    
    media_items = []
    for row in cursor.fetchall():
        media_dict = dict(row)
        # Determine media type
        media_path_lower = media_dict['media_file_path'].lower()
        if media_path_lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')):
            media_dict['media_type'] = 'image'
        elif media_path_lower.endswith(('.mp4', '.mov', '.webm', '.avi', '.mkv')):
            media_dict['media_type'] = 'video'
        else:
            media_dict['media_type'] = 'other'
        
        media_items.append(media_dict)
    
    return media_items
