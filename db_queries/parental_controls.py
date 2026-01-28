# db_queries/parental_controls.py
from db import get_db
from datetime import datetime, date
import json

def set_parental_control(child_user_id, parent_user_id):
    """Sets up parental control relationship."""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO parental_controls (child_user_id, parent_user_id)
            VALUES (?, ?)
        """, (child_user_id, parent_user_id))
        db.commit()
        return True
    except Exception as e:
        print(f"Error setting parental control: {e}")
        return False

def get_parent_user_id(child_user_id):
    """Gets the parent user ID for a child."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT parent_user_id FROM parental_controls WHERE child_user_id = ?", (child_user_id,))
    result = cursor.fetchone()
    return result['parent_user_id'] if result else None

def get_all_parent_ids(child_user_id):
    """Gets all parent user IDs for a child (supports multiple parents)."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT parent_user_id 
        FROM parental_controls 
        WHERE child_user_id = ?
    """, (child_user_id,))
    return [row['parent_user_id'] for row in cursor.fetchall()]

def get_children_for_parent(parent_user_id):
    """Gets all children under this parent's supervision."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT u.id, u.puid, u.username, u.display_name, u.profile_picture_path
        FROM users u
        JOIN parental_controls pc ON u.id = pc.child_user_id
        WHERE pc.parent_user_id = ?
    """, (parent_user_id,))
    return [dict(row) for row in cursor.fetchall()]

def is_user_adult(user_id):
    """Checks if a user is 16 or older based on their DOB."""
    from db_queries.profiles import get_profile_info_for_user
    profile_info = get_profile_info_for_user(user_id, user_id, False)
    
    dob_field = profile_info.get('dob')
    if not dob_field or not dob_field.get('value'):
        return True  # If no DOB, assume adult (for safety)
    
    try:
        dob = datetime.strptime(dob_field['value'], '%Y-%m-%d').date()
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return age >= 16
    except:
        return True  # If parsing fails, assume adult

def requires_parental_approval(child_user_id):
    """
    Checks if a user requires parental approval for actions.
    A user requires approval if they have a parent assigned in parental_controls table.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT 1 FROM parental_controls 
        WHERE child_user_id = ? 
        LIMIT 1
    """, (child_user_id,))
    return cursor.fetchone() is not None

def create_approval_request(child_user_id, approval_type, target_puid, target_hostname, request_data):
    """Creates a pending approval request for parent review."""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO parental_approval_queue 
            (child_user_id, approval_type, target_puid, target_hostname, request_data)
            VALUES (?, ?, ?, ?, ?)
        """, (child_user_id, approval_type, target_puid, target_hostname, request_data))
        db.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"Error creating approval request: {e}")
        return None

def get_pending_approvals_for_parent(parent_user_id):
    """Gets all pending approval requests for children under this parent."""
    db = get_db()
    cursor = db.cursor()
    
    print(f"DEBUG: Fetching approvals for parent_user_id={parent_user_id}")
    
    cursor.execute("""
        SELECT 
            paq.*,
            u.display_name as child_display_name, 
            u.username as child_username,
            u.profile_picture_path as child_profile_picture
        FROM parental_approval_queue paq
        JOIN parental_controls pc ON paq.child_user_id = pc.child_user_id
        JOIN users u ON paq.child_user_id = u.id
        WHERE pc.parent_user_id = ? AND paq.status = 'pending'
        ORDER BY paq.created_at DESC
    """, (parent_user_id,))
    
    results = [dict(row) for row in cursor.fetchall()]
    print(f"DEBUG: Found {len(results)} pending approvals for parent {parent_user_id}")
    
    return results

def get_pending_approvals_for_child(child_user_id):
    """Gets all pending approval requests for a specific child."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT * FROM parental_approval_queue
        WHERE child_user_id = ? AND status = 'pending'
        ORDER BY created_at DESC
    """, (child_user_id,))
    return [dict(row) for row in cursor.fetchall()]

def get_pending_approvals_count_for_parent(parent_user_id):
    """Gets count of pending approval requests across all children."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT COUNT(*)
        FROM parental_approval_queue paq
        JOIN parental_controls pc ON paq.child_user_id = pc.child_user_id
        WHERE pc.parent_user_id = ? AND paq.status = 'pending'
    """, (parent_user_id,))
    return cursor.fetchone()[0]

def get_pending_approvals_count_for_child(child_user_id):
    """Gets count of pending approval requests for a specific child."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM parental_approval_queue
        WHERE child_user_id = ? AND status = 'pending'
    """, (child_user_id,))
    return cursor.fetchone()[0]

def approve_request(approval_id, parent_user_id):
    """Approves a parental approval request."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE parental_approval_queue 
        SET status = 'approved', resolved_at = CURRENT_TIMESTAMP, resolved_by_user_id = ?
        WHERE id = ? AND status = 'pending'
    """, (parent_user_id, approval_id))
    db.commit()
    return cursor.rowcount > 0

def deny_request(approval_id, parent_user_id):
    """Denies a parental approval request."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE parental_approval_queue 
        SET status = 'denied', resolved_at = CURRENT_TIMESTAMP, resolved_by_user_id = ?
        WHERE id = ? AND status = 'pending'
    """, (parent_user_id, approval_id))
    db.commit()
    return cursor.rowcount > 0

def get_approval_request_by_id(approval_id):
    """Gets a specific approval request by ID."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM parental_approval_queue WHERE id = ?", (approval_id,))
    result = cursor.fetchone()
    return dict(result) if result else None


def get_child_parents(child_user_id):
    """Gets all parents assigned to monitor a child account."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT 
            pc.parent_user_id,
            u.username,
            u.display_name,
            u.puid,
            u.profile_picture_path
        FROM parental_controls pc
        JOIN users u ON pc.parent_user_id = u.id
        WHERE pc.child_user_id = ?
        ORDER BY u.display_name
    """, (child_user_id,))
    return [dict(row) for row in cursor.fetchall()]

def is_parent_child_relationship(user_id1, user_id2):
    """Check if two users have a parent-child relationship (in either direction)."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT 1 FROM parental_controls
        WHERE (parent_user_id = ? AND child_user_id = ?)
           OR (parent_user_id = ? AND child_user_id = ?)
        LIMIT 1
    """, (user_id1, user_id2, user_id2, user_id1))
    return cursor.fetchone() is not None

def update_parental_requirement(user_id, requires_approval):
    """Update whether a user requires parental approval."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE users
            SET requires_parental_approval = ?
            WHERE id = ?
        """, (1 if requires_approval else 0, user_id))
        db.commit()
        return cursor.rowcount > 0
    except Exception as e:
        db.rollback()
        print(f"Error updating parental requirement: {e}")
        return False

def add_parent_child_relationship(parent_user_id, child_user_id):
    """Assign a parent to monitor a child account. Multiple parents are allowed."""
    if parent_user_id == child_user_id:
        return False, "A user cannot be their own parent"
    
    db = get_db()
    cursor = db.cursor()
    
    # Check if THIS SPECIFIC relationship already exists
    cursor.execute("""
        SELECT 1 FROM parental_controls
        WHERE parent_user_id = ? AND child_user_id = ?
    """, (parent_user_id, child_user_id))
    
    if cursor.fetchone():
        return False, "This parent is already assigned to this child"
    
    # Add the new parent-child relationship
    try:
        cursor.execute("""
            INSERT INTO parental_controls (child_user_id, parent_user_id)
            VALUES (?, ?)
        """, (child_user_id, parent_user_id))
        
        # IMPORTANT: Automatically create friendship between parent and child
        from db_queries.friends import send_friend_request_db, accept_friend_request_db, get_pending_friend_requests, is_friends_with
        
        # Check if they're already friends
        if not is_friends_with(parent_user_id, child_user_id):
            # Send friend request from child to parent
            send_friend_request_db(child_user_id, parent_user_id)
            
            # Auto-accept the request
            pending = get_pending_friend_requests(parent_user_id)
            for req in pending:
                if req['sender_id'] == child_user_id:
                    accept_friend_request_db(req['id'], parent_user_id)
                    break
        
        db.commit()
        return True, "Parent assigned successfully and friendship established"
    except Exception as e:
        db.rollback()
        print(f"Error adding parent-child relationship: {e}")
        return False, f"Failed to add parent: {str(e)}"

def remove_parent_child_relationship(parent_user_id, child_user_id):
    """Remove a parent assignment from a child account."""
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM parental_controls
            WHERE parent_user_id = ? AND child_user_id = ?
        """, (parent_user_id, child_user_id))
        
        if cursor.rowcount > 0:
            db.commit()
            return True, "Parent assignment removed successfully"
        else:
            return False, "Parent assignment not found"
    except Exception as e:
        db.rollback()
        print(f"Error removing parent-child relationship: {e}")
        return False, f"Database error: {str(e)}"
    
def delete_approval_requests_for_event(event_puid):
    """Deletes all pending approval requests for a specific event."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            DELETE FROM parental_approval_queue 
            WHERE approval_type = 'event_invite' 
            AND target_puid = ? 
            AND status = 'pending'
        """, (event_puid,))
        deleted_count = cursor.rowcount
        db.commit()
        print(f"Deleted {deleted_count} pending event approval requests for event {event_puid}")
        return deleted_count
    except Exception as e:
        print(f"Error deleting approval requests for event: {e}")
        db.rollback()
        return 0