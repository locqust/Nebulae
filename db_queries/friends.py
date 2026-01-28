# db_queries/friends.py
# Contains functions for the friend system, requests, blocking, and snoozing.

import sys
import traceback
import sqlite3
from datetime import datetime, timedelta
from db import get_db
from .users import get_user_by_id

def get_friend_request_by_id(request_id):
    """
    Retrieves a single friend request by its ID, joining with the sender's user data
    to get their PUID and hostname, which is needed for federation.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT fr.*, u.puid as sender_puid, u.hostname as sender_hostname, u.id as sender_id
        FROM friend_requests fr
        JOIN users u ON fr.sender_id = u.id
        WHERE fr.id = ?
    """, (request_id,))
    row = cursor.fetchone()
    return dict(row) if row else None

def delete_friend_request_by_puids(sender_puid, receiver_puid):
    """
    Deletes a friend request based on the PUIDs of the sender and receiver.
    Used to clear an outgoing request after a remote rejection.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE puid = ?", (sender_puid,))
        sender_row = cursor.fetchone()
        sender = dict(sender_row) if sender_row else None
        
        cursor.execute("SELECT id FROM users WHERE puid = ?", (receiver_puid,))
        receiver_row = cursor.fetchone()
        receiver = dict(receiver_row) if receiver_row else None


        if not sender or not receiver:
            return False

        cursor.execute(
            "DELETE FROM friend_requests WHERE sender_id = ? AND receiver_id = ? AND status = 'pending'",
            (sender['id'], receiver['id'])
        )
        db.commit()
        return cursor.rowcount > 0
    except Exception as e:
        db.rollback()
        print(f"Error in delete_friend_request_by_puids: {e}")
        return False

def send_friend_request_db(sender_id, receiver_id):
    """Sends a friend request and creates a notification."""
    # FIX: Import locally to prevent circular dependency
    from .notifications import create_notification
    
    db = get_db()
    cursor = db.cursor()
    try:
        # Proactively delete any existing non-pending friend requests between these two users
        delete_existing_requests_query = """
            DELETE FROM friend_requests
            WHERE (sender_id = ? AND receiver_id = ? AND status != 'pending')
               OR (sender_id = ? AND receiver_id = ? AND status != 'pending')
        """
        cursor.execute(delete_existing_requests_query, (sender_id, receiver_id, receiver_id, sender_id))

        # Insert the new pending request
        cursor.execute("INSERT INTO friend_requests (sender_id, receiver_id, status) VALUES (?, ?, 'pending')", (sender_id, receiver_id))
        
        create_notification(receiver_id, sender_id, 'friend_request')

        db.commit()
        return True, None
    except sqlite3.IntegrityError as e:
        db.rollback()
        return False, 'exists'
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        return False, 'unknown_error'

def accept_friend_request_db(request_id, notify_remote=True):
    """
    Accepts a friend request, establishes friendship, creates a notification,
    and optionally notifies the remote node if the sender is remote.
    """
    # BUG FIX: Move imports inside function to break circular dependency
    from .notifications import create_notification
    from .federation import notify_remote_node_of_acceptance

    db = get_db()
    cursor = db.cursor()

    request_data = get_friend_request_by_id(request_id)

    if not request_data or request_data['status'] != 'pending':
        return False

    sender_id = request_data['sender_id']
    receiver_id = request_data['receiver_id']

    try:
        user1 = min(sender_id, receiver_id)
        user2 = max(sender_id, receiver_id)
        cursor.execute("INSERT OR IGNORE INTO friends (user_id_1, user_id_2) VALUES (?, ?)", (user1, user2))
        cursor.execute("UPDATE friend_requests SET status = 'accepted' WHERE id = ?", (request_id,))
        
        sender_user = get_user_by_id(sender_id)
        if sender_user and not sender_user['hostname']:
            create_notification(sender_id, receiver_id, 'friend_accept')

        db.commit()

        if notify_remote and sender_user and sender_user['hostname']:
            receiver_user = get_user_by_id(receiver_id)
            notify_remote_node_of_acceptance(sender_user, receiver_user)

        return True
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        return False

def reject_friend_request_db(request_id):
    """Rejects a friend request and notifies remote node if necessary."""
    # BUG FIX: Move import inside function to break circular dependency
    from .federation import notify_remote_node_of_rejection
    db = get_db()
    cursor = db.cursor()
    
    request_data = get_friend_request_by_id(request_id)
    if not request_data or request_data['status'] != 'pending':
        return False

    cursor.execute("UPDATE friend_requests SET status = 'rejected' WHERE id = ?", (request_id,))
    db.commit()
    
    if cursor.rowcount > 0 and request_data['sender_hostname']:
        sender_user = get_user_by_id(request_data['sender_id'])
        receiver_user = get_user_by_id(request_data['receiver_id'])
        notify_remote_node_of_rejection(sender_user, receiver_user)

    return cursor.rowcount > 0

def unfriend_db(user_id1, user_id2):
    """Removes a mutual friendship between two users and clears related friend requests."""
    # PARENTAL CONTROL CHECK: Prevent unfriending if parent-child relationship exists
    from db_queries.parental_controls import is_parent_child_relationship
    
    if is_parent_child_relationship(user_id1, user_id2):
        print(f"PARENTAL CONTROL: Cannot unfriend - parent-child relationship exists between users {user_id1} and {user_id2}")
        return False

    db = get_db()
    cursor = db.cursor()
    try:
        u1 = min(user_id1, user_id2)
        u2 = max(user_id1, user_id2)
        
        cursor.execute("DELETE FROM friends WHERE user_id_1 = ? AND user_id_2 = ?", (u1, u2))
        friends_rows_affected = cursor.rowcount

        delete_requests_query = """
            DELETE FROM friend_requests
            WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)
        """
        cursor.execute(delete_requests_query, (user_id1, user_id2, user_id2, user_id1))
        requests_rows_affected = cursor.rowcount
        
        db.commit()
        return friends_rows_affected > 0 or requests_rows_affected > 0
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        return False

def get_pending_friend_requests(user_id):
    """Retrieves pending friend requests for a user (where user is the receiver)."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT fr.id, fr.sender_id, u.username as sender_username, u.display_name as sender_display_name, 
               u.profile_picture_path as sender_profile_picture, u.hostname as sender_hostname, u.puid as sender_puid
        FROM friend_requests fr
        JOIN users u ON fr.sender_id = u.id
        WHERE fr.receiver_id = ? AND fr.status = 'pending'
        ORDER BY fr.timestamp DESC
    """, (user_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def get_outgoing_friend_requests(user_id):
    """Retrieves pending friend requests sent by a user (where user is the sender)."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT fr.id, fr.receiver_id, u.username as receiver_username, u.display_name as receiver_display_name, 
               u.profile_picture_path as receiver_profile_picture, u.puid as receiver_puid
        FROM friend_requests fr
        JOIN users u ON fr.receiver_id = u.id
        WHERE fr.sender_id = ? AND fr.status = 'pending'
        ORDER BY fr.timestamp DESC
    """, (user_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def get_friends_list(user_id):
    """Retrieves the list of friends for a given user, including their relationship status."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT u.id, u.username, u.display_name, u.profile_picture_path, u.hostname, u.puid, u.user_type, f.established_at,
               fr.is_blocked, fr.snooze_until, cn.nickname as node_nickname
        FROM friends f
        JOIN users u ON (u.id = f.user_id_1 OR u.id = f.user_id_2)
        LEFT JOIN friend_relationships fr ON fr.user_id = ? AND fr.friend_id = u.id
        LEFT JOIN connected_nodes cn ON u.hostname = cn.hostname
        WHERE (f.user_id_1 = ? OR f.user_id_2 = ?) AND u.id != ?
        ORDER BY u.username ASC
    """, (user_id, user_id, user_id, user_id))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def get_all_friends_puid(user_id):
    """Returns a set of PUIDs for all friends of a given user."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT u.puid
        FROM friends f
        JOIN users u ON (u.id = f.user_id_1 OR u.id = f.user_id_2)
        WHERE (f.user_id_1 = ? OR f.user_id_2 = ?) AND u.id != ?
    """, (user_id, user_id, user_id))
    return {row['puid'] for row in cursor.fetchall()}

def is_friends_with(user_id1, user_id2):
    """Checks if two users are friends."""
    if user_id1 is None or user_id2 is None:
        return False
    db = get_db()
    cursor = db.cursor()
    u1 = min(user_id1, user_id2)
    u2 = max(user_id1, user_id2)
    cursor.execute("SELECT COUNT(*) FROM friends WHERE user_id_1 = ? AND user_id_2 = ?", (u1, u2))
    return cursor.fetchone()[0] > 0

def get_friendship_status(current_user_id, target_user_id):
    """Returns the friendship status: 'self', 'friends', 'pending_sent', 'pending_received', 'not_friends'."""
    if current_user_id == target_user_id:
        return 'self', None
    if is_friends_with(current_user_id, target_user_id):
        return 'friends', None
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM friend_requests WHERE sender_id = ? AND receiver_id = ? AND status = 'pending'", (current_user_id, target_user_id))
    sent_request = cursor.fetchone()
    if sent_request:
        return 'pending_sent', sent_request['id']
    cursor.execute("SELECT id FROM friend_requests WHERE sender_id = ? AND receiver_id = ? AND status = 'pending'", (target_user_id, current_user_id))
    result = cursor.fetchone()
    if result:
        return 'pending_received', result['id']
    return 'not_friends', None

def get_friendship_details(user_id1, user_id2):
    """Checks if two users are friends and returns the established_at date."""
    if user_id1 is None or user_id2 is None: return None
    db = get_db()
    cursor = db.cursor()
    u1 = min(user_id1, user_id2)
    u2 = max(user_id1, user_id2)
    cursor.execute("SELECT established_at FROM friends WHERE user_id_1 = ? AND user_id_2 = ?", (u1, u2))
    result = cursor.fetchone()
    return result['established_at'] if result else None

def get_friend_relationship(user_id, friend_id):
    """Retrieves the relationship status between a user and a friend."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM friend_relationships WHERE user_id = ? AND friend_id = ?", (user_id, friend_id))
    row = cursor.fetchone()
    return dict(row) if row else None

def snooze_friend(user_id, friend_id):
    """Snoozes a friend for 30 days."""
    db = get_db()
    snooze_end_date = datetime.now() + timedelta(days=30)
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO friend_relationships (user_id, friend_id, snooze_until) VALUES (?, ?, ?)
        ON CONFLICT(user_id, friend_id) DO UPDATE SET snooze_until=excluded.snooze_until
    """, (user_id, friend_id, snooze_end_date))
    db.commit()
    return cursor.rowcount > 0

def unsnooze_friend(user_id, friend_id):
    """Unsnoozes a friend."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE friend_relationships SET snooze_until = NULL WHERE user_id = ? AND friend_id = ?", (user_id, friend_id))
    db.commit()
    return cursor.rowcount > 0

def block_friend(user_id, friend_id):
    """Blocks a friend and records the timestamp."""
    db = get_db()
    cursor = db.cursor()
    block_time = datetime.now()
    cursor.execute("""
        INSERT INTO friend_relationships (user_id, friend_id, is_blocked, blocked_at) VALUES (?, ?, TRUE, ?)
        ON CONFLICT(user_id, friend_id) DO UPDATE SET is_blocked=TRUE, blocked_at=?
    """, (user_id, friend_id, block_time, block_time))
    db.commit()
    return cursor.rowcount > 0

def unblock_friend(user_id, friend_id):
    """Unblocks a friend and clears the block timestamp."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE friend_relationships SET is_blocked = FALSE, blocked_at = NULL WHERE user_id = ? AND friend_id = ?", (user_id, friend_id))
    db.commit()
    return cursor.rowcount > 0

def get_snoozed_friends(user_id):
    """Returns a set of friend IDs that the user has currently snoozed."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT friend_id FROM friend_relationships WHERE user_id = ? AND snooze_until > ?", (user_id, datetime.now()))
    return {row['friend_id'] for row in cursor.fetchall()}

def get_blocked_friends(user_id):
    """Returns a set of friend IDs that the user has blocked."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT friend_id FROM friend_relationships WHERE user_id = ? AND is_blocked = TRUE", (user_id,))
    return {row['friend_id'] for row in cursor.fetchall()}

def get_blocked_friends_list(user_id):
    """Returns full user data for all friends that the user has blocked."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT u.id, u.puid, u.username, u.display_name, 
               u.profile_picture_path, u.hostname, fr.blocked_at
        FROM friend_relationships fr
        JOIN users u ON fr.friend_id = u.id
        WHERE fr.user_id = ? AND fr.is_blocked = TRUE
        ORDER BY u.display_name, u.username
    """, (user_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def get_who_blocked_user(user_id):
    """Returns a dictionary of users who have blocked the given user and when."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT user_id, blocked_at FROM friend_relationships WHERE friend_id = ? AND is_blocked = TRUE AND blocked_at IS NOT NULL", (user_id,))
    return {row['user_id']: datetime.strptime(row['blocked_at'].split('.')[0], '%Y-%m-%d %H:%M:%S') for row in cursor.fetchall()}