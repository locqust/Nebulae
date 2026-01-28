# db_queries/federation.py
# Contains functions for federation, node management, and remote interactions.

import sqlite3
import requests
import json
import hmac
import hashlib
import traceback
from datetime import datetime
from flask import current_app, g
from db import get_db
from .users import get_user_by_id
import threading

def _send_single_request_in_thread(method, url, data, headers, verify_ssl):
    """
    Target function for a thread to send a single HTTP request.
    """
    try:
        response = requests.request(
            method, url, data=data, headers=headers, timeout=10, verify=verify_ssl
        )
        response.raise_for_status()
        print(f"SUCCESS: Sent federated {method} notification to {url}, status {response.status_code}")
    except requests.RequestException as e:
        print(f"ERROR: Failed to send federated {method} notification to {url}: {e}")
        if e.response is not None:
            print(f"Remote server response status: {e.response.status_code}")
            print(f"Remote server response body: {e.response.text}")
    except Exception:
        print(f"ERROR: An unexpected error occurred in background notification thread for {url}:")
        traceback.print_exc()

def get_node_nu_id():
    """Retrieves the Node Unique ID (NUID) from the config table."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT value FROM node_config WHERE key = 'nu_id'")
    row = cursor.fetchone()
    return row['value'] if row else None

def get_or_create_remote_user(puid, display_name, hostname, profile_picture_path=None, user_type='remote'):
    """
    Finds a remote user by their PUID, or creates them if they don't exist.
    It will also update the user_type if it has changed.
    
    PRIVACY FIX: This function does NOT accept a username parameter to prevent
    storing email addresses from remote users. A placeholder username is
    generated based on the PUID instead.
    
    Returns the full user object (as a dict).
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT * FROM users WHERE puid = ?", (puid,))
    existing_user_row = cursor.fetchone()
    if existing_user_row:
        existing_user = dict(existing_user_row)
        # If the user exists, check if we need to update their user_type.
        # This handles cases where a remote user is later identified as a public page.
        if existing_user.get('user_type') != user_type:
             try:
                cursor.execute("UPDATE users SET user_type = ? WHERE puid = ?", (user_type, puid))
                db.commit()
                # Re-fetch to return the updated record
                cursor.execute("SELECT * FROM users WHERE puid = ?", (puid,))
                updated_user_row = cursor.fetchone()
                return dict(updated_user_row) if updated_user_row else None
             except sqlite3.Error as e:
                db.rollback()
                print(f"ERROR: Could not update user_type for remote user {puid}: {e}")
                # Return the existing user object even if update fails
                return existing_user
        return existing_user
    
    # PRIVACY FIX: Generate a placeholder username based on PUID
    # This prevents storing actual email addresses from remote users
    placeholder_username = f"remote_{puid[:8]}"

    try:
        cursor.execute("""
            INSERT INTO users (puid, username, display_name, user_type, hostname, profile_picture_path, password)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
        """, (puid, placeholder_username, display_name, user_type, hostname, profile_picture_path))
        new_user_id = cursor.lastrowid
        db.commit()
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (new_user_id,))
        new_user_row = cursor.fetchone()
        return dict(new_user_row) if new_user_row else None
    except sqlite3.IntegrityError:
        db.rollback()
        cursor.execute("SELECT * FROM users WHERE puid = ?", (puid,))
        user_row = cursor.fetchone()
        return dict(user_row) if user_row else None
    except Exception as e:
        print(f"ERROR: Could not create remote user stub for {display_name}@{hostname}: {e}")
        db.rollback()
        return None

def get_user_by_username_and_hostname(username, hostname):
    """Retrieves a user by a combination of username and hostname."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND hostname = ?", (username, hostname))
    row = cursor.fetchone()
    return dict(row) if row else None

def create_pairing_token(token, user_id, expires_at):
    """Saves a new pairing token to the database."""
    db = get_db()
    try:
        db.execute("INSERT INTO pairing_tokens (token, created_by_user_id, expires_at) VALUES (?, ?, ?)",
                   (token, user_id, expires_at))
        db.commit()
        return True
    except sqlite3.Error as e:
        db.rollback()
        return False

def get_all_connected_nodes():
    """RetrieVes all connected nodes from the database."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, hostname, nickname, status, shared_secret, origin_nu_id,
               connection_type, resource_type, resource_puid, resource_name
        FROM connected_nodes 
        ORDER BY connection_type, hostname
    """)
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def add_pending_node(hostname, connection_type='full'):
    """Adds a new node with 'pending' status."""
    db = get_db()
    try:
        db.execute("INSERT INTO connected_nodes (hostname, status, connection_type) VALUES (?, 'pending', ?)", 
                   (hostname, connection_type))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        db.rollback()
        return False

def remove_node_connection(node_id):
    """Removes a node connection by its ID."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM connected_nodes WHERE id = ?", (node_id,))
    db.commit()
    return cursor.rowcount > 0

def validate_pairing_token(token):
    """
    Checks if a token exists and is not expired.
    If valid, it deletes the token to ensure it's single-use and returns its data.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, expires_at FROM pairing_tokens WHERE token = ?", (token,))
        token_data_row = cursor.fetchone()
        
        if not token_data_row: return None

        token_data = dict(token_data_row)
        expires_at_str = token_data['expires_at'].split('.')[0]
        expires_at = datetime.strptime(expires_at_str, '%Y-%m-%d %H:%M:%S')
        if datetime.utcnow() > expires_at:
            cursor.execute("DELETE FROM pairing_tokens WHERE id = ?", (token_data['id'],))
            db.commit()
            return None

        cursor.execute("DELETE FROM pairing_tokens WHERE id = ?", (token_data['id'],))
        db.commit()
        return token_data
    except sqlite3.Error as e:
        db.rollback()
        return None

def get_node_by_hostname(hostname, resource_puid=None):
    """
    Retrieves a single node's details by its hostname.
    Prioritizes full connections over targeted subscriptions.
    If resource_puid is provided, will also check for targeted subscription to that resource.
    """
    db = get_db()
    cursor = db.cursor()
    
    # First, try to get a full connection
    cursor.execute("SELECT * FROM connected_nodes WHERE hostname = ? AND connection_type = 'full'", (hostname,))
    row = cursor.fetchone()
    if row:
        return dict(row)
    
    # If no full connection and resource_puid provided, check for targeted subscription
    if resource_puid:
        cursor.execute("""
            SELECT * FROM connected_nodes 
            WHERE hostname = ? AND connection_type = 'targeted' AND resource_puid = ?
        """, (hostname, resource_puid))
        row = cursor.fetchone()
        if row:
            return dict(row)
    
    # Fallback: get any connection (for backward compatibility)
    cursor.execute("SELECT * FROM connected_nodes WHERE hostname = ? LIMIT 1", (hostname,))
    row = cursor.fetchone()
    return dict(row) if row else None

def update_node_connection_status(hostname, status, shared_secret=None, origin_nu_id=None):
    """Updates a node's status, shared secret, and NUID."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE connected_nodes SET status = ?, shared_secret = ?, origin_nu_id = ? WHERE hostname = ?",
                   (status, shared_secret, origin_nu_id, hostname))
    db.commit()
    return cursor.rowcount > 0

def upsert_node_connection(hostname, status, shared_secret=None, origin_nu_id=None):
    """Inserts a new node connection or updates an existing full connection."""
    db = get_db()
    cursor = db.cursor()
    
    # Check if a full connection already exists
    cursor.execute("""
        SELECT id FROM connected_nodes 
        WHERE hostname = ? AND connection_type = 'full'
    """, (hostname,))
    existing = cursor.fetchone()
    
    if existing:
        # Update existing full connection
        cursor.execute("""
            UPDATE connected_nodes 
            SET status = ?, shared_secret = ?, origin_nu_id = ?
            WHERE hostname = ? AND connection_type = 'full'
        """, (status, shared_secret, origin_nu_id, hostname))
    else:
        # Insert new full connection
        cursor.execute("""
            INSERT INTO connected_nodes 
            (hostname, status, shared_secret, origin_nu_id, connection_type)
            VALUES (?, ?, ?, ?, 'full')
        """, (hostname, status, shared_secret, origin_nu_id))
    
    db.commit()
    return True

def update_node_nickname(node_id, nickname):
    """Updates the nickname for a specific node connection."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE connected_nodes SET nickname = ? WHERE id = ?", (nickname, node_id))
    db.commit()
    return cursor.rowcount > 0

def get_discoverable_users_for_federation():
    """
    Retrieves users to be shared with other nodes.
    - Shares ONLY local 'user' types (excluding admin).
    - Shares ALL 'public_page' types (both local and remote stubs).
    
    PRIVACY FIX: Does not include username field to prevent sharing email addresses.
    """
    db = get_db()
    cursor = db.cursor()
    # MODIFICATION: This query now selects local 'user' types OR any 'public_page' type.
    # It also includes the 'hostname' column.
    # PRIVACY FIX: Removed username from SELECT to prevent sharing email addresses
    cursor.execute("""
        SELECT puid, display_name, profile_picture_path, user_type, hostname
        FROM users 
        WHERE (user_type = 'user' AND hostname IS NULL AND username != 'admin')
           OR (user_type = 'public_page')
        ORDER BY display_name
    """)
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def send_remote_mention_notification(mentioned_user, actor_id, post_id=None, comment_id=None, group_id=None, muid=None, media_comment_cuid=None):
    """
    Sends a signed API call to a remote node to notify their user of a mention.
    Supports both post/comment mentions and media comment mentions.
    
    For post/comment mentions: provide post_id and optionally comment_id
    For media comment mentions: provide muid and media_comment_cuid
    """
    from utils.federation_utils import get_remote_node_api_url
    from .groups import get_group_by_id
    db = get_db()
    cursor = db.cursor()

    remote_hostname = mentioned_user.get('hostname')
    if not remote_hostname:
        return

    node = get_node_by_hostname(remote_hostname)
    if not node or node['status'] != 'connected' or not node['shared_secret']:
        print(f"ERROR: Cannot send mention to {remote_hostname}, node not connected or missing secret.")
        return

    actor = get_user_by_id(actor_id)
    if not actor:
        return
    
    # Handle post/comment mentions (convert internal IDs to CUIDs)
    post_cuid = None
    comment_cuid = None
    
    if post_id:
        cursor.execute("SELECT cuid FROM posts WHERE id = ?", (post_id,))
        post_row = cursor.fetchone()
        if not post_row:
            print(f"ERROR: Could not find post with ID {post_id} to send mention.")
            return
        post_cuid = post_row['cuid']

    if comment_id:
        cursor.execute("SELECT cuid FROM comments WHERE id = ?", (comment_id,))
        comment_row = cursor.fetchone()
        if comment_row:
            comment_cuid = comment_row['cuid']

    # Get group PUID if group_id provided
    group_puid = None
    if group_id:
        group = get_group_by_id(group_id)
        if group:
            group_puid = group['puid']

    try:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        verify_ssl = not insecure_mode
        remote_url = get_remote_node_api_url(remote_hostname, '/federation/api/v1/receive_mention', insecure_mode)

        payload = {
            'mentioned_puid': mentioned_user['puid'],
            'actor': {
                'puid': actor['puid'],
                'display_name': actor['display_name'],
                'hostname': current_app.config.get('NODE_HOSTNAME'),
                'profile_picture_path': actor.get('profile_picture_path')
            },
            'post_cuid': post_cuid,
            'comment_cuid': comment_cuid,
            'group_puid': group_puid,
            'muid': muid,  # NEW: Support for media mentions
            'media_comment_cuid': media_comment_cuid  # NEW: Support for media comment mentions
        }
        
        request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        headers = {
            'X-Node-Hostname': current_app.config.get('NODE_HOSTNAME'),
            'X-Node-Signature': signature,
            'Content-Type': 'application/json'
        }

        thread = threading.Thread(
            target=_send_single_request_in_thread,
            args=('POST', remote_url, request_body, headers, verify_ssl)
        )
        thread.daemon = True
        thread.start()

    except Exception as e:
        print(f"ERROR: An unexpected error occurred during mention notification setup: {e}")
        traceback.print_exc()

def send_remote_notification(notified_user, actor_id, type, post_cuid=None, comment_cuid=None, group_puid=None, event_puid=None, muid=None, media_comment_cuid=None):
    """
    Sends a generic notification to a remote user's node.
    
    Supports both post-based notifications and media-based notifications.
    For post notifications: post_cuid, comment_cuid, group_puid, event_puid
    For media notifications: muid, media_comment_cuid
    """
    from utils.federation_utils import get_remote_node_api_url
    
    remote_hostname = notified_user.get('hostname')
    if not remote_hostname:
        return

    node = get_node_by_hostname(remote_hostname)
    if not node or node['status'] != 'connected' or not node['shared_secret']:
        print(f"ERROR: Cannot send notification to {remote_hostname}, node not connected or missing secret.")
        return

    actor = get_user_by_id(actor_id)
    if not actor:
        return

    try:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        verify_ssl = not insecure_mode
        remote_url = get_remote_node_api_url(remote_hostname, '/federation/api/v1/receive_notification', insecure_mode)

        payload = {
            'notified_puid': notified_user['puid'],
            'actor': {
                'puid': actor['puid'],
                'display_name': actor['display_name'],
                'hostname': current_app.config.get('NODE_HOSTNAME'),
                'profile_picture_path': actor.get('profile_picture_path')
            },
            'type': type,
            'post_cuid': post_cuid,
            'comment_cuid': comment_cuid,
            'group_puid': group_puid,
            'event_puid': event_puid,
            'muid': muid,  # NEW: Support for media notifications
            'media_comment_cuid': media_comment_cuid  # NEW: Support for media comment notifications
        }
        
        request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        headers = {
            'X-Node-Hostname': current_app.config.get('NODE_HOSTNAME'),
            'X-Node-Signature': signature,
            'Content-Type': 'application/json'
        }

        thread = threading.Thread(
            target=_send_single_request_in_thread,
            args=('POST', remote_url, request_body, headers, verify_ssl)
        )
        thread.daemon = True
        thread.start()

    except Exception as e:
        print(f"ERROR: An unexpected error occurred during notification sending setup: {e}")
        traceback.print_exc()

def notify_remote_node_of_group_join_request(user, group):
    """
    Notifies a remote user's home node that they've requested to join a group.
    This creates a pending request stub on their home node so they can track it.
    """
    from utils.federation_utils import get_remote_node_api_url
    
    remote_hostname = user.get('hostname')
    if not remote_hostname:
        return  # Local user, no notification needed

    node = get_node_by_hostname(remote_hostname)
    if not node or not node['shared_secret']:
        print(f"ERROR: Cannot notify {remote_hostname} of group join request, node not connected or missing secret.")
        return

    try:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        verify_ssl = not insecure_mode

        remote_url = get_remote_node_api_url(
            remote_hostname,
            '/federation/api/v1/group_join_request_created',
            insecure_mode
        )

        payload = {
            "user_puid": user['puid'],
            "group_data": {
                "puid": group['puid'],
                "name": group['name'],
                "description": group.get('description'),
                "profile_picture_path": group.get('profile_picture_path'),
                "hostname": current_app.config.get('NODE_HOSTNAME')
            }
        }
        
        request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        headers = {
            'X-Node-Hostname': current_app.config.get('NODE_HOSTNAME'),
            'X-Node-Signature': signature,
            'Content-Type': 'application/json'
        }

        thread = threading.Thread(
            target=_send_single_request_in_thread,
            args=('POST', remote_url, request_body, headers, verify_ssl)
        )
        thread.daemon = True
        thread.start()
        return True

    except Exception as e:
        print(f"ERROR: An unexpected error occurred during group join request notification setup: {e}")
        traceback.print_exc()
        return False

def notify_remote_node_of_acceptance(sender_user, receiver_user):
    """
    Sends a signed API call to the sender's home node to inform them
    that a friend request has been accepted.
    """
    from utils.federation_utils import get_remote_node_api_url
    
    remote_hostname = sender_user['hostname']
    node = get_node_by_hostname(remote_hostname)

    if not node or not node['shared_secret']:
        print(f"ERROR: Cannot notify {remote_hostname} of acceptance, node not connected or missing secret.")
        return

    try:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        verify_ssl = not insecure_mode

        remote_url = get_remote_node_api_url(
            remote_hostname,
            '/federation/api/v1/friend_request_accepted',
            insecure_mode
        )

        payload = {
            "original_sender_puid": sender_user['puid'],
            "original_receiver_puid": receiver_user['puid'],
            "accepter_display_name": receiver_user['display_name'],
            "accepter_profile_picture_path": receiver_user['profile_picture_path']
        }
        
        request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        headers = {
            'X-Node-Hostname': current_app.config.get('NODE_HOSTNAME'),
            'X-Node-Signature': signature,
            'Content-Type': 'application/json'
        }

        thread = threading.Thread(
            target=_send_single_request_in_thread,
            args=('POST', remote_url, request_body, headers, verify_ssl)
        )
        thread.daemon = True
        thread.start()
        return True # Assume success, fire-and-forget

    except Exception as e:
        print(f"ERROR: An unexpected error occurred during acceptance notification setup: {e}")
        traceback.print_exc()
        return False

def notify_remote_node_of_rejection(sender_user, receiver_user):
    """
    Notifies the original sender's node that a friend request was rejected.
    """
    from utils.federation_utils import get_remote_node_api_url
    try:
        remote_node = get_node_by_hostname(sender_user['hostname'])
        if not remote_node or not remote_node['shared_secret']:
            raise Exception(f"Node {sender_user['hostname']} not found or missing secret.")

        payload = {
            'original_sender_puid': sender_user['puid'],
            'original_receiver_puid': receiver_user['puid']
        }

        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        remote_url = get_remote_node_api_url(
            remote_node['hostname'],
            '/federation/api/v1/friend_request_rejected',
            insecure_mode
        )
        
        local_hostname = current_app.config.get('NODE_HOSTNAME')
        request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            remote_node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        headers = {
            'X-Node-Hostname': local_hostname,
            'X-Node-Signature': signature,
            'Content-Type': 'application/json'
        }
        
        thread = threading.Thread(
            target=_send_single_request_in_thread,
            args=('POST', remote_url, request_body, headers, not insecure_mode)
        )
        thread.daemon = True
        thread.start()
        return True

    except Exception as e:
        print(f"ERROR: Failed to set up 'friend_request_rejected' notification to {sender_user['hostname']}: {e}")
        return False

def notify_remote_node_of_group_rejection(user, group, rejection_reason=None):
    """
    Notifies the remote node that a group join request was rejected.
    Similar to notify_remote_node_of_rejection but for groups.
    """
    from utils.federation_utils import get_remote_node_api_url
    
    if not user.get('hostname'):
        return  # Local user, no notification needed
    
    try:
        remote_node = get_node_by_hostname(user['hostname'])
        if not remote_node or not remote_node['shared_secret']:
            print(f"Cannot notify {user['hostname']}: no connection or shared secret")
            return False

        payload = {
            'user_puid': user['puid'],
            'group_data': {
                'puid': group['puid'],
                'name': group['name'],
                'description': group.get('description'),
                'profile_picture_path': group.get('profile_picture_path'),
                'hostname': current_app.config.get('NODE_HOSTNAME')
            },
            'rejection_reason': rejection_reason
        }

        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        remote_url = get_remote_node_api_url(
            remote_node['hostname'],
            '/federation/api/v1/group_request_rejected',
            insecure_mode
        )
        
        local_hostname = current_app.config.get('NODE_HOSTNAME')
        request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            remote_node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        headers = {
            'X-Node-Hostname': local_hostname,
            'X-Node-Signature': signature,
            'Content-Type': 'application/json'
        }
        
        thread = threading.Thread(
            target=_send_single_request_in_thread,
            args=('POST', remote_url, request_body, headers, not insecure_mode)
        )
        thread.daemon = True
        thread.start()
        
        print(f"Notifying {user['hostname']} of group join rejection for user {user['puid']}")
        return True

    except Exception as e:
        print(f"ERROR: Failed to notify {user.get('hostname')} of group_request_rejected: {e}")
        traceback.print_exc()
        return False

def notify_remote_node_of_group_acceptance(user, group):
    """
    Notifies a remote user's home node that their request to join a group was accepted.
    """
    from utils.federation_utils import get_remote_node_api_url
    
    remote_hostname = user.get('hostname')
    if not remote_hostname:
        return

    node = get_node_by_hostname(remote_hostname)
    if not node or not node['shared_secret']:
        print(f"ERROR: Cannot notify {remote_hostname} of group acceptance, node not connected or missing secret.")
        return

    try:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        verify_ssl = not insecure_mode

        remote_url = get_remote_node_api_url(
            remote_hostname,
            '/federation/api/v1/group_request_accepted',
            insecure_mode
        )

        payload = {
            "user_puid": user['puid'],
            "group_data": {
                "puid": group['puid'],
                "name": group['name'],
                "description": group['description'],
                "profile_picture_path": group['profile_picture_path'],
                "hostname": current_app.config.get('NODE_HOSTNAME') # The group's home node
            }
        }
        
        request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        headers = {
            'X-Node-Hostname': current_app.config.get('NODE_HOSTNAME'),
            'X-Node-Signature': signature,
            'Content-Type': 'application/json'
        }

        thread = threading.Thread(
            target=_send_single_request_in_thread,
            args=('POST', remote_url, request_body, headers, verify_ssl)
        )
        thread.daemon = True
        thread.start()
        return True

    except Exception as e:
        print(f"ERROR: An unexpected error occurred during group acceptance notification setup: {e}")
        traceback.print_exc()
        return False

def notify_remote_node_of_unfriend(local_user, remote_user):
    """
    Sends a signed API call to a remote node to inform them that a user
    has ended their friendship.
    """
    from utils.federation_utils import get_remote_node_api_url
    
    remote_hostname = remote_user.get('hostname')
    if not remote_hostname:
        return False

    node = get_node_by_hostname(remote_hostname)
    if not node or not node['shared_secret']:
        print(f"ERROR: Cannot notify {remote_hostname} of unfriend, node not connected or missing secret.")
        return False

    try:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        verify_ssl = not insecure_mode

        remote_url = get_remote_node_api_url(
            remote_hostname,
            '/federation/api/v1/receive_unfriend',
            insecure_mode
        )

        payload = {
            "unfriender_puid": local_user['puid'],
            "unfriended_puid": remote_user['puid']
        }
        
        request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        headers = {
            'X-Node-Hostname': current_app.config.get('NODE_HOSTNAME'),
            'X-Node-Signature': signature,
            'Content-Type': 'application/json'
        }
        
        thread = threading.Thread(
            target=_send_single_request_in_thread,
            args=('POST', remote_url, request_body, headers, verify_ssl)
        )
        thread.daemon = True
        thread.start()
        return True

    except Exception as e:
        print(f"ERROR: An unexpected error occurred during unfriend notification setup: {e}")
        traceback.print_exc()
        return False

def notify_remote_node_of_leave_group(leaver_user, group):
    """
    Sends a signed API call to a group's home node to inform them that a user
    has left the group.
    """
    from utils.federation_utils import get_remote_node_api_url
    
    remote_hostname = group.get('hostname')
    if not remote_hostname:
        return False

    node = get_node_by_hostname(remote_hostname)
    if not node or node['status'] != 'connected' or not node['shared_secret']:
        print(f"ERROR: Cannot notify {remote_hostname} of leave group action, node not connected or missing secret.")
        return False

    try:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        verify_ssl = not insecure_mode

        remote_url = get_remote_node_api_url(
            remote_hostname,
            '/federation/api/v1/receive_leave_group',
            insecure_mode
        )

        payload = {
            "leaver_puid": leaver_user['puid'],
            "group_puid": group['puid']
        }
        
        request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        headers = {
            'X-Node-Hostname': current_app.config.get('NODE_HOSTNAME'),
            'X-Node-Signature': signature,
            'Content-Type': 'application/json'
        }

        thread = threading.Thread(
            target=_send_single_request_in_thread,
            args=('POST', remote_url, request_body, headers, verify_ssl)
        )
        thread.daemon = True
        thread.start()
        return True

    except Exception as e:
        print(f"ERROR: An unexpected error occurred during leave group notification setup: {e}")
        traceback.print_exc()
        return False

def notify_remote_node_of_group_removal(user, group, removal_type='kick'):
    """
    Notifies a remote node that one of their users has been removed from a group.
    removal_type can be 'kick', 'ban', or 'leave'
    """
    if not user.get('hostname'):
        return  # Local user, no notification needed
    
    node = get_node_by_hostname(user['hostname'])
    if not node or not node.get('shared_secret'):
        print(f"Cannot notify {user['hostname']}: no connection or shared secret")
        return
    
    try:
        from flask import current_app
        import requests
        import hmac
        import hashlib
        import json
        from utils.federation_utils import get_remote_node_api_url
        
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        verify_ssl = not insecure_mode
        local_hostname = current_app.config.get('NODE_HOSTNAME')
        
        remote_url = get_remote_node_api_url(
            user['hostname'],
            '/federation/api/v1/group_member_removed',
            insecure_mode
        )
        
        payload = {
            "user_puid": user['puid'],
            "group_puid": group['puid'],
            "removal_type": removal_type  # 'kick', 'ban', or 'leave'
        }
        
        request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        headers = {
            'X-Node-Hostname': local_hostname,
            'X-Node-Signature': signature,
            'Content-Type': 'application/json'
        }
        
        response = requests.post(remote_url, data=request_body, headers=headers, timeout=10, verify=verify_ssl)
        response.raise_for_status()
        
        print(f"Successfully notified {user['hostname']} of {removal_type} for user {user['puid']} from group {group['puid']}")
        
    except Exception as e:
        print(f"ERROR notifying remote node of group removal: {e}")
        import traceback
        traceback.print_exc()

# --- TARGETED SUBSCRIPTION FUNCTIONS ---

def get_or_create_targeted_subscription(hostname, resource_type, resource_puid, resource_name):
    """
    Creates or retrieves a targeted subscription connection to a specific group or page.
    
    Args:
        hostname: The remote node's hostname
        resource_type: 'group' or 'public_page'
        resource_puid: The PUID of the group or page
        resource_name: Display name of the resource (for admin UI)
    
    Returns:
        dict: The connection record, or None if it failed
    """
    import secrets
    
    db = get_db()
    cursor = db.cursor()
    
    # Check if this exact targeted subscription already exists
    cursor.execute("""
        SELECT * FROM connected_nodes 
        WHERE hostname = ? AND connection_type = 'targeted' AND resource_puid = ?
    """, (hostname, resource_puid))
    
    existing = cursor.fetchone()
    if existing:
        return dict(existing)
    
    # Check if there's a full connection to this hostname
    cursor.execute("""
        SELECT * FROM connected_nodes 
        WHERE hostname = ? AND connection_type = 'full' AND status = 'connected'
    """, (hostname,))
    
    full_connection = cursor.fetchone()
    
    if full_connection:
        # If there's already a full connection, we don't need a targeted one
        # Return the full connection
        return dict(full_connection)
    
    # Need to create a new targeted subscription
    # Use the same handshake process but mark it as targeted
    return _create_targeted_subscription_connection(hostname, resource_type, resource_puid, resource_name)


def _create_targeted_subscription_connection(hostname, resource_type, resource_puid, resource_name):
    """
    Internal function to create a targeted subscription by initiating handshake with remote node.
    Similar to admin node pairing but automated and limited in scope.
    
    Args:
        hostname: Remote node hostname
        resource_type: 'group' or 'public_page'
        resource_puid: PUID of the resource
        resource_name: Display name of resource
    
    Returns:
        dict: The new connection record, or None if failed
    """
    from utils.federation_utils import get_remote_node_api_url
    import secrets
    
    db = get_db()
    cursor = db.cursor()
    
    # First, add a pending targeted connection
    try:
        cursor.execute("""
            INSERT INTO connected_nodes 
            (hostname, status, connection_type, resource_type, resource_puid, resource_name)
            VALUES (?, 'pending', 'targeted', ?, ?, ?)
        """, (hostname, resource_type, resource_puid, resource_name))
        db.commit()
    except sqlite3.IntegrityError:
        # Already exists, fetch and return it
        cursor.execute("""
            SELECT * FROM connected_nodes 
            WHERE hostname = ? AND resource_puid = ?
        """, (hostname, resource_puid))
        result = cursor.fetchone()
        return dict(result) if result else None
    
    # Call the remote node to establish targeted subscription
    try:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        verify_ssl = not insecure_mode
        
        remote_url = get_remote_node_api_url(
            hostname,
            '/federation/initiate_targeted_subscription',
            insecure_mode
        )
        
        local_hostname = current_app.config.get('NODE_HOSTNAME')
        
        # Ensure g.nu_id is available
        if not hasattr(g, 'nu_id'):
            g.nu_id = get_node_nu_id()
        
        payload = {
            'hostname': local_hostname,
            'nu_id': g.nu_id,
            'resource_type': resource_type,
            'resource_puid': resource_puid
        }
        
        response = requests.post(remote_url, json=payload, timeout=10, verify=verify_ssl)
        response.raise_for_status()
        
        response_data = response.json()
        shared_secret = response_data.get('shared_secret')
        remote_nu_id = response_data.get('nu_id')
        
        if not shared_secret or not remote_nu_id:
            print(f"ERROR: Failed to get shared_secret or nu_id from {hostname}")
            # Clean up the pending connection
            cursor.execute("""
                DELETE FROM connected_nodes 
                WHERE hostname = ? AND resource_puid = ? AND status = 'pending'
            """, (hostname, resource_puid))
            db.commit()
            return None
        
        # Update the connection to 'connected' status
        cursor.execute("""
            UPDATE connected_nodes 
            SET status = 'connected', shared_secret = ?, origin_nu_id = ?
            WHERE hostname = ? AND resource_puid = ?
        """, (shared_secret, remote_nu_id, hostname, resource_puid))
        db.commit()
        
        # Fetch and return the updated connection
        cursor.execute("""
            SELECT * FROM connected_nodes 
            WHERE hostname = ? AND resource_puid = ?
        """, (hostname, resource_puid))
        
        result = cursor.fetchone()
        return dict(result) if result else None
        
    except Exception as e:
        print(f"ERROR: Failed to create targeted subscription to {hostname}: {e}")
        traceback.print_exc()
        # Clean up the pending connection
        cursor.execute("""
            DELETE FROM connected_nodes 
            WHERE hostname = ? AND resource_puid = ? AND status = 'pending'
        """, (hostname, resource_puid))
        db.commit()
        return None


def get_all_connected_nodes_grouped():
    """
    Retrieves all connected nodes, separated into full connections and targeted subscriptions.
    
    Returns:
        dict: {'full': [list of full connections], 'targeted': [list of targeted subscriptions]}
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT id, hostname, nickname, status, shared_secret, origin_nu_id, 
               connection_type, resource_type, resource_puid, resource_name
        FROM connected_nodes 
        WHERE connection_type = 'full'
        ORDER BY hostname
    """)
    full_connections = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("""
        SELECT id, hostname, nickname, status, shared_secret, origin_nu_id, 
               connection_type, resource_type, resource_puid, resource_name
        FROM connected_nodes 
        WHERE connection_type = 'targeted'
        ORDER BY hostname, resource_name
    """)
    targeted_subscriptions = [dict(row) for row in cursor.fetchall()]
    
    return {
        'full': full_connections,
        'targeted': targeted_subscriptions
    }


def has_connection_to_node(hostname, resource_puid=None):
    """
    Checks if there's an active connection to a node.
    If resource_puid is provided, checks for either a full connection or a targeted subscription to that resource.
    
    Args:
        hostname: The remote node's hostname
        resource_puid: Optional - specific resource PUID to check for targeted subscription
    
    Returns:
        bool: True if connected, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    if resource_puid:
        # Check for either full connection OR targeted subscription to this resource
        cursor.execute("""
            SELECT COUNT(*) FROM connected_nodes 
            WHERE hostname = ? AND status = 'connected'
            AND (connection_type = 'full' OR resource_puid = ?)
        """, (hostname, resource_puid))
    else:
        # Just check for any full connection
        cursor.execute("""
            SELECT COUNT(*) FROM connected_nodes 
            WHERE hostname = ? AND status = 'connected' AND connection_type = 'full'
        """, (hostname,))
    
    count = cursor.fetchone()[0]
    return count > 0

def check_remote_user_parental_controls(remote_user):
    """
    Check if a remote/federated user requires parental approval.
    This is done by checking their local user record on this node.
    """
    if not remote_user or not remote_user.get('id'):
        return False
    
    from db_queries.parental_controls import requires_parental_approval
    return requires_parental_approval(remote_user['id'])


def notify_home_node_of_group_join_attempt(federated_user, group, rules_agreed, question_responses):
    """
    Notify a federated user's home node that they attempted to join a group,
    so the home node can create a parental approval request.
    """
    from utils.federation_utils import get_remote_node_api_url
    
    home_hostname = federated_user.get('hostname')
    if not home_hostname:
        return False
    
    node = get_node_by_hostname(home_hostname)
    if not node or not node['shared_secret']:
        return False
    
    try:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        verify_ssl = not insecure_mode
        local_hostname = current_app.config.get('NODE_HOSTNAME')
        
        remote_url = get_remote_node_api_url(
            home_hostname,
            '/federation/api/v1/create_parental_approval',
            insecure_mode
        )
        
        payload = {
            'user_puid': federated_user['puid'],
            'approval_type': 'group_join_remote',
            'target_puid': group['puid'],
            'target_hostname': local_hostname,
            'request_data': {
                'group_puid': group['puid'],
                'group_name': group['name'],
                'group_hostname': local_hostname,
                'rules_agreed': rules_agreed,
                'question_responses': question_responses
            }
        }
        
        request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        headers = {
            'X-Node-Hostname': local_hostname,
            'X-Node-Signature': signature,
            'Content-Type': 'application/json'
        }
        
        response = requests.post(remote_url, data=request_body, headers=headers, timeout=10, verify=verify_ssl)
        response.raise_for_status()
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"ERROR notifying home node of group join attempt: {e}")
        traceback.print_exc()
        return False


def notify_home_node_of_friend_request_attempt(federated_user, target_user):
    """
    Notify a federated user's home node that they attempted to send a friend request,
    so the home node can create a parental approval request.
    """
    from utils.federation_utils import get_remote_node_api_url
    
    home_hostname = federated_user.get('hostname')
    if not home_hostname:
        return False
    
    node = get_node_by_hostname(home_hostname)
    if not node or not node['shared_secret']:
        return False
    
    try:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        verify_ssl = not insecure_mode
        local_hostname = current_app.config.get('NODE_HOSTNAME')
        
        remote_url = get_remote_node_api_url(
            home_hostname,
            '/federation/api/v1/create_parental_approval',
            insecure_mode
        )
        
        payload = {
            'user_puid': federated_user['puid'],
            'approval_type': 'friend_request_out',
            'target_puid': target_user['puid'],
            'target_hostname': target_user.get('hostname') or local_hostname,
            'request_data': {
                'receiver_puid': target_user['puid'],
                'receiver_display_name': target_user.get('display_name', 'Unknown'),
                'receiver_hostname': target_user.get('hostname') or local_hostname
            }
        }
        
        request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        headers = {
            'X-Node-Hostname': local_hostname,
            'X-Node-Signature': signature,
            'Content-Type': 'application/json'
        }
        
        response = requests.post(remote_url, data=request_body, headers=headers, timeout=10, verify=verify_ssl)
        response.raise_for_status()
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"ERROR notifying home node of friend request attempt: {e}")
        traceback.print_exc()
        return False