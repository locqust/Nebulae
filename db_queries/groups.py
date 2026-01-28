# db_queries/groups.py
import uuid
import sqlite3
from flask import g
from db import get_db
# Add imports for federation and user lookups
from .users import get_user_by_id, get_admin_user
from .federation import notify_remote_node_of_group_acceptance

def get_all_groups():
    """RetrieVes all groups from the database."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT g.*, u.display_name as created_by_username FROM groups g JOIN users u ON g.created_by_user_id = u.id ORDER BY g.name")
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def get_group_by_id(group_id):
    """RetrieVes a single group by its ID."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM groups WHERE id = ?", (group_id,))
    row = cursor.fetchone()
    return dict(row) if row else None

def get_group_by_puid(puid):
    """Retrieves a single group by its PUID."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM groups WHERE puid = ?", (puid,))
    row = cursor.fetchone()
    return dict(row) if row else None

def get_or_create_remote_group_stub(puid, name, description, profile_picture_path, hostname):
    """
    Finds a remote group stub by PUID, or creates one if it doesn't exist.
    Returns the full group object (as a dict).
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM groups WHERE puid = ?", (puid,))
    existing_group = cursor.fetchone()
    if existing_group:
        return dict(existing_group)

    admin_user = get_admin_user()
    if not admin_user:
        print("CRITICAL: Cannot create remote group stub because no local admin user was found.")
        return None

    try:
        cursor.execute("""
            INSERT INTO groups (puid, name, description, profile_picture_path, created_by_user_id, hostname, is_remote)
            VALUES (?, ?, ?, ?, ?, ?, TRUE)
        """, (puid, name, description, profile_picture_path, admin_user['id'], hostname))
        new_group_id = cursor.lastrowid
        db.commit()

        cursor.execute("SELECT * FROM groups WHERE id = ?", (new_group_id,))
        new_group = cursor.fetchone()
        return dict(new_group) if new_group else None
    except sqlite3.IntegrityError:
        db.rollback()
        cursor.execute("SELECT * FROM groups WHERE puid = ?", (puid,))
        group = cursor.fetchone()
        return dict(group) if group else None
    except Exception as e:
        print(f"ERROR: Could not create remote group stub for {name}@{hostname}: {e}")
        db.rollback()
        return None


def add_group(name, description, created_by_user_id, admin_user_id):
    """Adds a new group and sets the initial admin."""
    db = get_db()
    cursor = db.cursor()
    try:
        puid = str(uuid.uuid4())
        # MODIFICATION: Add the initial_admin_id when creating the group
        cursor.execute("INSERT INTO groups (puid, name, description, created_by_user_id, initial_admin_id) VALUES (?, ?, ?, ?, ?)",
                       (puid, name, description, created_by_user_id, admin_user_id))
        group_id = cursor.lastrowid

        cursor.execute("INSERT INTO group_members (group_id, user_id, role) VALUES (?, ?, 'admin')",
                       (group_id, admin_user_id))

        db.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error adding group: {e}")
        db.rollback()
        return False

def delete_group(group_id):
    """Deletes a group and all associated data."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error deleting group: {e}")
        db.rollback()
        return False

def get_group_admins(group_id):
    """Retrieves all admins for a given group."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT u.id, u.display_name, u.puid, u.hostname
        FROM group_members gm
        JOIN users u ON gm.user_id = u.id
        WHERE gm.group_id = ? AND gm.role = 'admin'
    """, (group_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def add_group_admin(group_id, user_id):
    """Adds a user as an admin to a group. If they are a member, their role is updated."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO group_members (group_id, user_id, role) VALUES (?, ?, 'admin')
            ON CONFLICT(group_id, user_id) DO UPDATE SET role='admin'
        """, (group_id, user_id))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error adding group admin: {e}")
        db.rollback()
        return False

def remove_group_admin(group_id, user_id):
    """Removes admin role from a user, demoting them to a regular member."""
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT COUNT(*) FROM group_members WHERE group_id = ? AND role = 'admin'", (group_id,))
    admin_count = cursor.fetchone()[0]

    if admin_count <= 1:
        return False, "Cannot remove the last admin from a group."

    try:
        cursor.execute("UPDATE group_members SET role = 'member' WHERE group_id = ? AND user_id = ?", (group_id, user_id))
        db.commit()
        return True, "Admin role removed."
    except sqlite3.Error as e:
        print(f"Error removing group admin: {e}")
        db.rollback()
        return False, "An error occurred while removing the admin."

def get_group_members(group_id):
    """Retrieves all members of a group."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT u.id, u.puid, u.username, u.display_name, u.profile_picture_path, u.hostname, gm.role, gm.is_banned, gm.snooze_until
        FROM group_members gm
        JOIN users u ON gm.user_id = u.id
        WHERE gm.group_id = ?
        ORDER BY u.display_name
    """, (group_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def is_user_group_member(user_id, group_id):
    """Checks if a user is a member of a group and not banned."""
    if not user_id or not group_id:
        return False
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM group_members WHERE group_id = ? AND user_id = ? AND is_banned = FALSE", (group_id, user_id))
    return cursor.fetchone()[0] > 0

def is_user_group_admin(user_id, group_id):
    """Checks if a user is an admin of a group."""
    if not user_id or not group_id:
        return False
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM group_members WHERE group_id = ? AND user_id = ? AND role = 'admin'", (group_id, user_id))
    return cursor.fetchone()[0] > 0

def is_user_group_moderator_or_admin(user_id, group_id):
    """Checks if a user is a moderator or an admin of a group."""
    if not user_id or not group_id:
        return False
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM group_members WHERE group_id = ? AND user_id = ? AND role IN ('moderator', 'admin')", (group_id, user_id))
    return cursor.fetchone()[0] > 0

def update_group_member_role(group_id, user_id, new_role, acting_user_id):
    """Updates a group member's role, with permission checks."""
    db = get_db()
    cursor = db.cursor()

    if not is_user_group_admin(acting_user_id, group_id):
        return False, "You do not have permission to change roles."

    group = get_group_by_id(group_id)
    if group and group['initial_admin_id'] == user_id and new_role != 'admin':
        return False, "Cannot change the role of the initial group admin."

    if new_role != 'admin':
        cursor.execute("SELECT role FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id))
        current_role_row = cursor.fetchone()
        current_role = dict(current_role_row) if current_role_row else None
        if current_role and current_role['role'] == 'admin':
            cursor.execute("SELECT COUNT(*) FROM group_members WHERE group_id = ? AND role = 'admin'", (group_id,))
            admin_count = cursor.fetchone()[0]
            if admin_count <= 1:
                return False, "Cannot remove the last admin from the group."

    try:
        cursor.execute("UPDATE group_members SET role = ? WHERE group_id = ? AND user_id = ?", (new_role, group_id, user_id))
        db.commit()
        return cursor.rowcount > 0, f"Role updated to {new_role}."
    except sqlite3.Error as e:
        db.rollback()
        print(f"Database error in update_group_member_role: {e}")
        return False, "A database error occurred."

def send_join_request(group_id, user_id, rules_agreed=False, question_responses=None):
    """Creates a new request for a user to join a group with optional responses."""
    import json
    db = get_db()
    cursor = db.cursor()
    try:
        # Insert the join request
        cursor.execute("""
            INSERT OR IGNORE INTO group_join_requests (group_id, user_id, status) 
            VALUES (?, ?, 'pending')
        """, (group_id, user_id))
        
        if cursor.rowcount > 0:
            request_id = cursor.lastrowid
            
            # Store the responses if provided
            if rules_agreed or question_responses:
                responses_json = json.dumps(question_responses) if question_responses else None
                cursor.execute("""
                    INSERT INTO group_join_request_responses 
                    (request_id, rules_agreed, question_responses)
                    VALUES (?, ?, ?)
                """, (request_id, rules_agreed, responses_json))
            
            db.commit()
            return True, "Request sent."
        else:
            # Request already exists
            return True, "Request already exists."
            
    except sqlite3.IntegrityError:
        db.rollback()
        return True, "Request already exists."
    except sqlite3.Error as e:
        print(f"Error sending join request: {e}")
        db.rollback()
        return False, "Database error."

def update_group_join_settings(group_id, join_rules=None, join_questions=None):
    """Updates the join rules (in profile info) and questions (in groups table) for a group."""
    db = get_db()
    cursor = db.cursor()
    try:
        import json
        
        # Store join_rules in group_profile_info table (like other group info fields)
        if join_rules is not None:
            # This will be handled by update_group_profile_info_field
            # Called separately from the route
            pass
        
        # Store join_questions in the groups table as JSON
        questions_json = json.dumps(join_questions) if join_questions is not None else None
        cursor.execute("""
            UPDATE groups 
            SET join_questions = ?
            WHERE id = ?
        """, (questions_json, group_id))
        db.commit()
        return True, "Join settings updated successfully."
    except sqlite3.Error as e:
        db.rollback()
        print(f"Error updating join settings: {e}")
        return False, "Database error."

def get_group_join_settings(group_id):
    """Gets the join rules (from profile info) and questions (from groups table) for a group."""
    import json
    db = get_db()
    cursor = db.cursor()
    
    # Get join_rules from group_profile_info
    cursor.execute("""
        SELECT field_value, privacy_public, privacy_members_only
        FROM group_profile_info 
        WHERE group_id = ? AND field_name = 'join_rules'
    """, (group_id,))
    rules_row = cursor.fetchone()
    
    # Get join_questions from groups table
    cursor.execute("""
        SELECT join_questions 
        FROM groups 
        WHERE id = ?
    """, (group_id,))
    questions_row = cursor.fetchone()
    
    result = {
        'join_rules': dict(rules_row)['field_value'] if rules_row else None,
        'join_rules_public': bool(dict(rules_row)['privacy_public']) if rules_row else False,
        'join_questions': []
    }
    
    # Parse the JSON questions if they exist
    if questions_row and dict(questions_row).get('join_questions'):
        try:
            result['join_questions'] = json.loads(dict(questions_row)['join_questions'])
        except (json.JSONDecodeError, TypeError):
            result['join_questions'] = []
    
    return result

def get_user_join_request_status(user_id, group_id):
    """Checks the status of a user's join request for a specific group."""
    if not user_id or not group_id:
        return None
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT status FROM group_join_requests WHERE user_id = ? AND group_id = ?", (user_id, group_id))
    result = cursor.fetchone()
    return result['status'] if result else None

def get_pending_join_requests(group_id):
    """Gets all pending join requests for a group with their responses."""
    import json
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT 
            gjr.id, gjr.user_id, u.display_name, u.puid, u.hostname, u.profile_picture_path,
            gjrr.rules_agreed, gjrr.question_responses
        FROM group_join_requests gjr
        JOIN users u ON gjr.user_id = u.id
        LEFT JOIN group_join_request_responses gjrr ON gjr.id = gjrr.request_id
        WHERE gjr.group_id = ? AND gjr.status = 'pending'
    """, (group_id,))
    rows = cursor.fetchall()
    results = []
    for row in rows:
        result = dict(row)
        # Parse question_responses JSON
        if result.get('question_responses'):
            try:
                result['question_responses'] = json.loads(result['question_responses'])
            except (json.JSONDecodeError, TypeError):
                result['question_responses'] = {}
        else:
            result['question_responses'] = {}
        results.append(result)
    return results

def get_join_request_by_id(request_id):
    """Retrieves a single join request by its ID, including the user's hostname."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT gjr.*, u.hostname
        FROM group_join_requests gjr
        JOIN users u ON gjr.user_id = u.id
        WHERE gjr.id = ?
    """, (request_id,))
    row = cursor.fetchone()
    return dict(row) if row else None

def accept_join_request(request_id):
    """Accepts a join request, adds the user as a member, notifies remote node if necessary, and deletes the request."""
    # NEW: Local import to avoid circular dependency
    from .events import invite_user_to_source_future_events

    db = get_db()
    cursor = db.cursor()
    request_data = get_join_request_by_id(request_id)
    if not request_data:
        return False, "Request not found."

    group_id = request_data['group_id']
    user_id = request_data['user_id']
    user = get_user_by_id(user_id) # Fetch the full user object
    group = get_group_by_id(group_id) # Fetch the full group object

    if not user or not group:
        return False, "User or Group not found."

    try:
        # Add the user to the group
        cursor.execute("INSERT OR IGNORE INTO group_members (group_id, user_id, role) VALUES (?, ?, 'member')", (group_id, user_id))
        member_rows_affected = cursor.rowcount

        # Delete the join request
        cursor.execute("DELETE FROM group_join_requests WHERE id = ?", (request_id,))
        request_rows_affected = cursor.rowcount

        db.commit()

        # If the user was successfully added as a member...
        if member_rows_affected > 0:
            # Notify the remote node if the user is remote
            if request_data['hostname']:
                notify_remote_node_of_group_acceptance(user, group)

            # NEW: Invite the user to future group events
            invite_user_to_source_future_events(user, 'group', group['puid'])

            return True, "User added to group and invited to future events."
        # If the user was already a member but the request was still pending (edge case)
        elif request_rows_affected > 0:
            db.commit() # Commit the request deletion
            # NEW: Still invite the user to future group events, as they might have joined before events existed
            invite_user_to_source_future_events(user, 'group', group['puid'])
            return True, "Join request removed (user may have already been a member)."
        else:
            # If nothing changed, something unexpected happened
            return False, "Failed to accept join request (no changes made)."

    except sqlite3.Error as e:
        db.rollback()
        print(f"Database error accepting join request: {e}") # Log the specific error
        return False, f"Database error: {e}"


def reject_join_request(request_id, rejection_reason=None):
    """Rejects a join request and optionally notifies the user."""
    db = get_db()
    cursor = db.cursor()
    
    # Get request data before deleting (for federation notification)
    request_data = get_join_request_by_id(request_id)
    if not request_data:
        return False, "Request not found."
    
    user = get_user_by_id(request_data['user_id'])
    group = get_group_by_id(request_data['group_id'])
    
    try:
        # Delete the request so they can request again in the future
        cursor.execute("DELETE FROM group_join_requests WHERE id = ?", (request_id,))
        rows_affected = cursor.rowcount
        db.commit()
        
        if rows_affected > 0:
            # Notify remote node if user is federated
            if user and group and user.get('hostname'):
                from db_queries.federation import notify_remote_node_of_group_rejection
                notify_remote_node_of_group_rejection(user, group, rejection_reason)
            
            return True, "Request rejected."
        else:
            return False, "Request not found."
            
    except sqlite3.Error as e:
        db.rollback()
        return False, f"Database error: {e}"

def leave_group(group_id, user_id):
    """
    Removes a user from a group.
    Prevents the last admin from leaving the group.
    """
    db = get_db()
    cursor = db.cursor()
    
    # Get user and group info before leaving (for federation notification)
    user = get_user_by_id(user_id)
    group = get_group_by_id(group_id)

    cursor.execute("SELECT role FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id))
    user_role_row = cursor.fetchone()
    user_role = dict(user_role_row) if user_role_row else None

    if user_role and user_role['role'] == 'admin':
        cursor.execute("SELECT COUNT(*) FROM group_members WHERE group_id = ? AND role = 'admin'", (group_id,))
        admin_count = cursor.fetchone()[0]
        if admin_count <= 1:
            return False, "Cannot leave the group as the only admin."

    try:
        cursor.execute("DELETE FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id))
        rows_affected = cursor.rowcount
        db.commit()
        
        if rows_affected > 0:
            # Notify remote node if this is a federated user leaving a local group
            # OR if this is a local user leaving a remote group
            if user and group:
                if user.get('hostname'):
                    # Federated user leaving local group - notify their home node
                    from db_queries.federation import notify_remote_node_of_group_removal
                    notify_remote_node_of_group_removal(user, group, 'leave')
                # Note: If local user leaves remote group, the route handler should notify the remote group's node
            
            return True, "Successfully left the group."
        else:
            return False, "User not a member of group."
            
    except sqlite3.Error as e:
        print(f"Database error in leave_group: {e}")
        db.rollback()
        return False, "Database error."


def kick_group_member(group_id, user_id):
    """Removes a member from a group."""
    db = get_db()
    cursor = db.cursor()
    
    # Get user and group info before removing (for federation notification)
    user = get_user_by_id(user_id)
    group = get_group_by_id(group_id)
    
    try:
        cursor.execute("DELETE FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id))
        rows_affected = cursor.rowcount
        db.commit()
        
        if rows_affected > 0:
            # Notify remote node if user is federated
            if user and group and user.get('hostname'):
                from db_queries.federation import notify_remote_node_of_group_removal
                notify_remote_node_of_group_removal(user, group, 'kick')
            
            return True, "Member kicked."
        else:
            return False, "Member not found in group."
            
    except sqlite3.Error as e:
        db.rollback()
        return False, "Database error."

def ban_group_member(group_id, user_id):
    """Bans a user from a group."""
    db = get_db()
    cursor = db.cursor()
    
    # Get user and group info before banning (for federation notification)
    user = get_user_by_id(user_id)
    group = get_group_by_id(group_id)
    
    try:
        cursor.execute("UPDATE group_members SET is_banned = TRUE WHERE group_id = ? AND user_id = ?", (group_id, user_id))
        rows_affected = cursor.rowcount
        db.commit()
        
        if rows_affected > 0:
            # Notify remote node if user is federated
            if user and group and user.get('hostname'):
                from db_queries.federation import notify_remote_node_of_group_removal
                notify_remote_node_of_group_removal(user, group, 'ban')
            
            return True, "Member banned."
        else:
            return False, "Member not found in group."
            
    except sqlite3.Error as e:
        db.rollback()
        return False, "Database error."

def unban_group_member(group_id, user_id):
    """Unbans a user from a group."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE group_members SET is_banned = FALSE WHERE group_id = ? AND user_id = ?", (group_id, user_id))
        db.commit()
        return cursor.rowcount > 0, "Member unbanned."
    except sqlite3.Error as e:
        db.rollback()
        return False, "Database error."

def snooze_group_member(group_id, user_id):
    """Snoozes a group member for 30 days."""
    from datetime import datetime, timedelta
    db = get_db()
    snooze_end_date = datetime.utcnow() + timedelta(days=30)
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE group_members SET snooze_until = ? WHERE group_id = ? AND user_id = ?", (snooze_end_date, group_id, user_id))
        db.commit()
        return cursor.rowcount > 0, "Member snoozed for 30 days."
    except sqlite3.Error as e:
        db.rollback()
        return False, "Database error."

def unsnooze_group_member(group_id, user_id):
    """Unsnoozes a group member."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE group_members SET snooze_until = NULL WHERE group_id = ? AND user_id = ?", (group_id, user_id))
        db.commit()
        return cursor.rowcount > 0, "Member unsnoozed."
    except sqlite3.Error as e:
        db.rollback()
        return False, "Database error."

def update_group_profile_picture_path(group_puid, profile_picture_path, original_profile_picture_path=None, admin_puid=None):
    """
    Updates a group's profile picture path, original path, and the admin who uploaded it.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        if original_profile_picture_path is not None:
            cursor.execute("""
                UPDATE groups
                SET profile_picture_path = ?, original_profile_picture_path = ?, picture_admin_puid = ?
                WHERE puid = ?
            """, (profile_picture_path, original_profile_picture_path, admin_puid, group_puid))
        else:
            cursor.execute("""
                UPDATE groups
                SET profile_picture_path = ?, original_profile_picture_path = NULL, picture_admin_puid = ?
                WHERE puid = ?
            """, (profile_picture_path, admin_puid, group_puid))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Database error updating group profile picture: {e}")
        db.rollback()
        return False

def get_user_groups(user_id):
    """Retrieves all groups a user is a member of, including remote group hostnames."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT g.puid, g.name, g.profile_picture_path, g.hostname, gm.role, gm.joined_at
        FROM groups g
        JOIN group_members gm ON g.id = gm.group_id
        WHERE gm.user_id = ?
        ORDER BY g.name
    """, (user_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def get_user_group_ids(user_id):
    """RetrieVes a list of group IDs a user is a member of."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT group_id FROM group_members WHERE user_id = ? AND is_banned = FALSE", (user_id,))
    return [row['group_id'] for row in cursor.fetchall()]

def get_user_outgoing_join_requests(user_id):
    """
    Retrieves all pending join requests sent by a user.
    This query now correctly gets the group's home node hostname.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT
            g.name as group_name,
            g.puid as group_puid,
            g.profile_picture_path as group_profile_picture_path,
            g.hostname as node_hostname
        FROM group_join_requests gjr
        JOIN groups g ON gjr.group_id = g.id
        WHERE gjr.user_id = ? AND gjr.status = 'pending'
        ORDER BY gjr.timestamp DESC
    """, (user_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def get_group_profile_info(group_id, is_member, is_admin):
    """
    Retrieves profile information for a group, respecting privacy settings.
    """
    db = get_db()
    cursor = db.cursor()

    default_fields = {
        'website': {'value': None, 'privacy_public': 0, 'privacy_members_only': 0},
        'email': {'value': None, 'privacy_public': 0, 'privacy_members_only': 0},
        'about': {'value': None, 'privacy_public': 0, 'privacy_members_only': 0},
        'show_admins': {'value': 'visible', 'privacy_public': 0, 'privacy_members_only': 1},
        'show_members': {'value': 'visible', 'privacy_public': 0, 'privacy_members_only': 1},
        'join_rules': {'value': None, 'privacy_public': 1, 'privacy_members_only': 0}  # NEW: Default to public so non-members can see rules before joining
    }

    cursor.execute("SELECT field_name, field_value, privacy_public, privacy_members_only FROM group_profile_info WHERE group_id = ?", (group_id,))
    raw_info = cursor.fetchall()

    for item_row in raw_info:
        item = dict(item_row)
        field_name = item['field_name']
        if field_name in default_fields:
            is_visible = False
            if is_admin:
                is_visible = True
            elif item['privacy_public'] == 1:
                is_visible = True
            elif is_member and item['privacy_members_only'] == 1:
                is_visible = True

            if is_visible:
                default_fields[field_name] = {
                    'value': item['field_value'] if field_name != 'show_admins' else 'visible',
                    'privacy_public': item['privacy_public'],
                    'privacy_members_only': item['privacy_members_only']
                }
            else:
                default_fields[field_name]['value'] = None
                default_fields[field_name]['privacy_public'] = item['privacy_public']
                default_fields[field_name]['privacy_members_only'] = item['privacy_members_only']

    return default_fields

def update_group_profile_info_field(group_id, field_name, field_value, privacy_public, privacy_members_only):
    """Updates a single profile information field for a group."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO group_profile_info
        (group_id, field_name, field_value, privacy_public, privacy_members_only)
        VALUES (?, ?, ?, ?, ?)
    """, (group_id, field_name, field_value, privacy_public, privacy_members_only))
    db.commit()
    return cursor.rowcount > 0

def get_friends_in_group(user_id, group_id):
    """
    Retrieves a list of a user's friends who are also members of a specific group.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT u.puid, u.display_name, u.hostname, u.profile_picture_path
        FROM users u
        JOIN group_members gm ON u.id = gm.user_id
        WHERE gm.group_id = ?
          AND u.id IN (
            SELECT f.user_id_2 FROM friends f WHERE f.user_id_1 = ?
            UNION
            SELECT f.user_id_1 FROM friends f WHERE f.user_id_2 = ?
        )
    """, (group_id, user_id, user_id))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def get_discoverable_groups():
    """RetrieVes all groups to be shared with other nodes."""
    db = get_db()
    cursor = db.cursor()
    # MODIFICATION: Select 'hostname' and remove 'WHERE is_remote = FALSE'
    # This allows us to share groups we learned about from other nodes.
    cursor.execute("""
        SELECT puid, name, description, profile_picture_path, hostname
        FROM groups
        ORDER BY name
    """)
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def get_friends_to_invite(user_id, group_id):
    """
    Retrieves a list of a user's friends who are eligible to be invited to a group.
    Excludes friends who are already members, are banned, or have a pending join request.
    """
    # Import here to avoid circular dependency at startup
    from .friends import get_friends_list

    db = get_db()
    cursor = db.cursor()

    # 1. Get IDs of users who are banned from the group
    cursor.execute("SELECT user_id FROM group_members WHERE group_id = ? AND is_banned = TRUE", (group_id,))
    banned_user_ids = {row['user_id'] for row in cursor.fetchall()}

    # 2. Get IDs of all current members of the group
    cursor.execute("SELECT user_id FROM group_members WHERE group_id = ?", (group_id,))
    member_ids = {row['user_id'] for row in cursor.fetchall()}

    # 3. Get IDs of all users with a pending join request for the group
    cursor.execute("SELECT user_id FROM group_join_requests WHERE group_id = ? AND status = 'pending'", (group_id,))
    pending_request_ids = {row['user_id'] for row in cursor.fetchall()}

    # Combine all ineligible user IDs into a single set
    ineligible_ids = banned_user_ids.union(member_ids).union(pending_request_ids)

    # 4. Get all friends of the current user
    all_friends = get_friends_list(user_id)

    # 5. Filter the friends list in Python
    invitable_friends = []
    for friend_row in all_friends:
        friend = dict(friend_row)
        if friend['id'] not in ineligible_ids:
            invitable_friends.append(friend)

    return invitable_friends

def send_group_invite(group_id, sender_id, receiver_id):
    """Creates a 'group_invite' notification."""
    # Import locally to prevent circular dependency
    from .notifications import create_notification

    # Check if a pending invite or join request already exists to avoid spam.
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM notifications
        WHERE user_id = ? AND actor_id = ? AND group_id = ? AND type = 'group_invite' AND is_read = FALSE
    """, (receiver_id, sender_id, group_id))
    if cursor.fetchone()[0] > 0:
        return False, "An invitation has already been sent recently."

    if get_user_join_request_status(receiver_id, group_id) == 'pending':
        return False, "This user has already requested to join the group."

    # If no pending invite or request, create the notification
    create_notification(
        user_id=receiver_id,
        actor_id=sender_id,
        type='group_invite',
        group_id=group_id
    )
    return True, "Invitation sent."

def check_new_posts_in_group(group_puid, viewer_user_id, since_timestamp):
    """
    Check if there are new posts in a group since a given timestamp.
    """
    from datetime import datetime
    
    try:
        since_dt = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return False
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get the group
    group = get_group_by_puid(group_puid)
    if not group:
        return False
    
    # Check posts table (not group_posts) with microsecond precision
    query = """
        SELECT 1
        FROM posts p
        WHERE p.group_id = ?
        AND p.timestamp > ?
        LIMIT 1
    """
    
    cursor.execute(query, (group['id'], since_dt.strftime('%Y-%m-%d %H:%M:%S.%f')))
    result = cursor.fetchone()
    return result is not None



