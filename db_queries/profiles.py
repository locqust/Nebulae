# db_queries/profiles.py
# Contains functions for managing user profiles and family relationships.

from datetime import datetime
from db import get_db
from .friends import is_friends_with
from .notifications import trigger_birthday_notifications_for_user
from .users import get_user_by_id # Import get_user_by_id to check viewer's hostname

def get_profile_info_for_user(profile_user_id, viewer_user_id, viewer_is_admin):
    """
    Retrieves profile information for a user, respecting privacy settings.
    This function is now defensive and will return a default structure if no info is found.
    """
    db = get_db()
    cursor = db.cursor()

    default_profile_fields = ['dob', 'hometown', 'occupation', 'bio', 'show_username', 'show_friends', 'website', 'email', 'phone', 'address']
    profile_info = {}
    for field in default_profile_fields:
        profile_info[field] = {
            'value': None,
            'privacy_public': 0,
            'privacy_local': 0,
            'privacy_friends': 0
        }

    cursor.execute("SELECT user_type FROM users WHERE id = ?", (profile_user_id,))
    profile_owner_data_row = cursor.fetchone()
    if not profile_owner_data_row:
        return profile_info
    
    profile_owner_data = dict(profile_owner_data_row)
    profile_owner_user_type = profile_owner_data['user_type']
    
    # MODIFICATION: Determine if the viewer is from a remote node.
    is_federated_viewer = False
    if viewer_user_id:
        viewer_user = get_user_by_id(viewer_user_id)
        if viewer_user and viewer_user['hostname'] is not None:
            is_federated_viewer = True

    cursor.execute("SELECT field_name, field_value, privacy_public, privacy_local, privacy_friends FROM user_profile_info WHERE user_id = ?", (profile_user_id,))
    raw_info = cursor.fetchall()

    for item_row in raw_info:
        item = dict(item_row)
        field_name = item['field_name']
        if field_name not in default_profile_fields:
            continue

        field_value = item['field_value']
        is_visible = False

        if viewer_user_id == profile_user_id or viewer_is_admin:
            is_visible = True
        elif item['privacy_public'] == 1:
            is_visible = True
        # MODIFICATION: A federated viewer should NOT see local-only info.
        elif viewer_user_id is not None and item['privacy_local'] == 1 and not is_federated_viewer:
            is_visible = True
        elif viewer_user_id is not None and item['privacy_friends'] == 1 and is_friends_with(viewer_user_id, profile_user_id):
            is_visible = True
        elif profile_owner_user_type == 'admin' and item['privacy_friends'] == 1 and viewer_user_id is not None:
            is_visible = True

        if is_visible:
            final_value = 'visible' if field_name == 'show_username' else field_value
            profile_info[field_name] = {
                'value': final_value,
                'privacy_public': item['privacy_public'],
                'privacy_local': item['privacy_local'],
                'privacy_friends': item['privacy_friends']
            }
        else:
            profile_info[field_name] = {
                'value': '' if viewer_user_id != profile_user_id and not viewer_is_admin else None,
                'privacy_public': item['privacy_public'],
                'privacy_local': item['privacy_local'],
                'privacy_friends': item['privacy_friends']
            }
            
    return profile_info

def update_profile_info_field(user_id, field_name, field_value, privacy_public, privacy_local, privacy_friends):
    """
    Updates a single profile information field for a user and triggers
    birthday notifications if the DOB is updated to today.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_profile_info
        (user_id, field_name, field_value, privacy_public, privacy_local, privacy_friends)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, field_name, field_value, privacy_public, privacy_local, privacy_friends))
    
    if field_name == 'dob' and field_value:
        try:
            dob_date = datetime.strptime(field_value, '%Y-%m-%d').date()
            today = datetime.utcnow().date()
            if dob_date.month == today.month and dob_date.day == today.day and privacy_friends == 1:
                trigger_birthday_notifications_for_user(user_id)
        except ValueError:
            print(f"WARN: Could not parse date '{field_value}' for birthday check.")

    db.commit()
    return cursor.rowcount > 0

def add_family_relationship(user_id, relative_user_id, relationship_type, anniversary_date, privacy_public, privacy_local, privacy_friends):
    """Adds or updates a family relationship."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO family_relationships (user_id, relative_user_id, relationship_type, anniversary_date, privacy_public, privacy_local, privacy_friends)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, relative_user_id) DO UPDATE SET
        relationship_type=excluded.relationship_type,
        anniversary_date=excluded.anniversary_date,
        privacy_public=excluded.privacy_public,
        privacy_local=excluded.privacy_local,
        privacy_friends=excluded.privacy_friends
    """, (user_id, relative_user_id, relationship_type, anniversary_date, privacy_public, privacy_local, privacy_friends))
    db.commit()
    return cursor.lastrowid

def get_relationship_by_id(relationship_id, user_id):
    """Retrieves a single family relationship by its ID, ensuring user has permission."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM family_relationships WHERE id = ? AND user_id = ?", (relationship_id, user_id))
    row = cursor.fetchone()
    return dict(row) if row else None

def update_family_relationship(relationship_id, user_id, relative_user_id, relationship_type, anniversary_date, privacy_public, privacy_local, privacy_friends):
    """Updates an existing family relationship, ensuring user has permission."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE family_relationships SET
        relative_user_id = ?,
        relationship_type = ?,
        anniversary_date = ?,
        privacy_public = ?,
        privacy_local = ?,
        privacy_friends = ?
        WHERE id = ? AND user_id = ?
    """, (relative_user_id, relationship_type, anniversary_date, privacy_public, privacy_local, privacy_friends, relationship_id, user_id))
    db.commit()
    return cursor.rowcount > 0

def remove_family_relationship(relationship_id, user_id):
    """Removes a family relationship, ensuring the user has permission."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM family_relationships WHERE id = ? AND user_id = ?", (relationship_id, user_id))
    db.commit()
    return cursor.rowcount > 0

def get_family_relationships_for_user(profile_user_id, viewer_user_id, viewer_is_admin):
    """Retrieves family relationships for a user, respecting privacy settings."""
    db = get_db()
    cursor = db.cursor()
    
    # BUG FIX: Added u.profile_picture_path to the SELECT statement
    query = """
        SELECT fr.id, fr.relative_user_id, fr.relationship_type, fr.anniversary_date,
               u.username as relative_username, u.display_name as relative_display_name, 
               u.puid as relative_puid, u.hostname as relative_hostname, u.profile_picture_path,
               fr.privacy_public, fr.privacy_local, fr.privacy_friends
        FROM family_relationships fr
        JOIN users u ON fr.relative_user_id = u.id
        WHERE fr.user_id = ?
    """
    cursor.execute(query, (profile_user_id,))
    all_relations = cursor.fetchall()
    
    visible_relations = []
    is_profile_owner = (profile_user_id == viewer_user_id)
    # BUG FIX: Correctly check friendship status. It requires viewer_user_id to be not None.
    are_friends = False
    if viewer_user_id:
        are_friends = is_friends_with(profile_user_id, viewer_user_id)
    
    # MODIFICATION: Determine if the viewer is from a remote node.
    is_federated_viewer = False
    if viewer_user_id:
        viewer_user = get_user_by_id(viewer_user_id)
        if viewer_user and viewer_user['hostname'] is not None:
            is_federated_viewer = True

    for rel_row in all_relations:
        rel = dict(rel_row)
        is_visible = False
        if is_profile_owner or viewer_is_admin:
            is_visible = True
        elif rel['privacy_public'] == 1:
            is_visible = True
        # MODIFICATION: A federated viewer should NOT see local-only info.
        elif viewer_user_id is not None and rel['privacy_local'] == 1 and not is_federated_viewer:
            is_visible = True
        elif are_friends and rel['privacy_friends'] == 1:
            is_visible = True
        
        if is_visible:
            visible_relations.append(rel)
            
    return visible_relations

def update_profile_info_privacy_only(user_id, field_name, privacy_public, privacy_local, privacy_friends):
    """
    Updates only the privacy settings for a profile field without changing its value.
    Used specifically for DOB which should not be editable after account creation.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE user_profile_info
        SET privacy_public = ?,
            privacy_local = ?,
            privacy_friends = ?
        WHERE user_id = ? AND field_name = ?
    """, (privacy_public, privacy_local, privacy_friends, user_id, field_name))
    db.commit()
    return cursor.rowcount > 0