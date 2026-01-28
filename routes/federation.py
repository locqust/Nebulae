# routes/federation.py
from flask import Blueprint, request, jsonify, current_app, session, g, redirect, url_for, flash
import secrets
import traceback
import sqlite3
from datetime import datetime
import json
import base64
import zlib
import time
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from itsdangerous.exc import BadSignature

# Import database functions from the new query modules
from db import get_db
from db_queries.federation import (validate_pairing_token, upsert_node_connection,
                                   get_discoverable_users_for_federation, get_or_create_remote_user,
                                   get_node_by_hostname)
from db_queries.users import (get_user_by_username, get_user_id_by_username, get_user_by_puid,
                              update_remote_user_details)
from db_queries.friends import (send_friend_request_db, accept_friend_request_db,
                                delete_friend_request_by_puids, is_friends_with, unfriend_db)
from db_queries.notifications import create_notification
from db_queries.posts import (add_post, get_post_by_cuid, update_post, delete_post,
                              disable_comments_for_post) # NEW: Import
from db_queries.comments import get_comment_by_cuid, add_comment, update_comment, delete_comment
from db_queries.groups import (get_discoverable_groups, get_group_by_puid, send_join_request,
                               reject_join_request, get_or_create_remote_group_stub, leave_group)
from db_queries.followers import follow_page
# MODIFICATION: Import the new event discovery function
from db_queries.events import (get_or_create_remote_event_stub, invite_friend_to_event,
                               get_event_by_puid, update_event_details, cancel_event, respond_to_event,
                               get_discoverable_public_events)

from utils.federation_utils import signature_required, distribute_comment

federation_bp = Blueprint('federation', __name__)

@federation_bp.route('/federation/initiate_pairing', methods=['POST'])
def receive_pairing_request():
    """
    API endpoint for another node to initiate pairing with us.
    This is the second half of the handshake.
    """
    data = request.get_json()
    remote_hostname = data.get('hostname')
    token = data.get('token')
    remote_nu_id = data.get('nu_id')

    if not remote_hostname or not token or not remote_nu_id:
        return jsonify({'error': 'Hostname, token, and NUID are required.'}), 400

    if not validate_pairing_token(token):
        return jsonify({'error': 'Invalid or expired pairing token.'}), 403

    shared_secret = secrets.token_hex(32)

    if not upsert_node_connection(remote_hostname, 'connected', shared_secret, remote_nu_id):
        return jsonify({'error': 'Failed to save node connection.'}), 500

    # Ensure g.nu_id is available (might not be if request context is different)
    if 'nu_id' not in g:
        from db_queries.federation import get_node_nu_id
        g.nu_id = get_node_nu_id()


    return jsonify({
        'message': 'Pairing successful!',
        'shared_secret': shared_secret,
        'nu_id': g.nu_id
    }), 200

@federation_bp.route('/federation/initiate_targeted_subscription', methods=['POST'])
def receive_targeted_subscription_request():
    """
    API endpoint for another node to create a targeted subscription with us.
    Similar to pairing but validates that the resource exists and is accessible.
    """
    from db_queries.groups import get_group_by_puid
    from db_queries.users import get_user_by_puid
    
    data = request.get_json()
    remote_hostname = data.get('hostname')
    remote_nu_id = data.get('nu_id')
    resource_type = data.get('resource_type')
    resource_puid = data.get('resource_puid')
    
    if not all([remote_hostname, remote_nu_id, resource_type, resource_puid]):
        return jsonify({'error': 'Missing required fields.'}), 400
    
    if resource_type not in ['group', 'public_page']:
        return jsonify({'error': 'Invalid resource_type.'}), 400
    
    # Verify the resource exists and is discoverable
    if resource_type == 'group':
        resource = get_group_by_puid(resource_puid)
        if not resource or resource.get('is_remote'):
            return jsonify({'error': 'Group not found or not hosted here.'}), 404
    elif resource_type == 'public_page':
        resource = get_user_by_puid(resource_puid)
        if not resource or resource.get('user_type') != 'public_page' or resource.get('hostname'):
            return jsonify({'error': 'Public page not found or not hosted here.'}), 404
    
    # Generate shared secret
    shared_secret = secrets.token_hex(32)
    
    # Create the targeted subscription connection
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO connected_nodes 
            (hostname, status, shared_secret, origin_nu_id, connection_type, resource_type, resource_puid, resource_name)
            VALUES (?, 'connected', ?, ?, 'targeted', ?, ?, ?)
        """, (remote_hostname, shared_secret, remote_nu_id, resource_type, resource_puid, 
              resource.get('name') or resource.get('display_name')))
        db.commit()
    except sqlite3.IntegrityError:
        # Already exists, update it
        cursor.execute("""
            UPDATE connected_nodes 
            SET status = 'connected', shared_secret = ?, origin_nu_id = ?
            WHERE hostname = ? AND resource_puid = ?
        """, (shared_secret, remote_nu_id, remote_hostname, resource_puid))
        db.commit()
    
    # Ensure g.nu_id is available
    if 'nu_id' not in g:
        from db_queries.federation import get_node_nu_id
        g.nu_id = get_node_nu_id()
    
    return jsonify({
        'message': 'Targeted subscription successful!',
        'shared_secret': shared_secret,
        'nu_id': g.nu_id
    }), 200

@federation_bp.route('/federation/api/v1/discover_users', methods=['GET'])
@signature_required
def discover_users():
    """Provides a list of discoverable users on this node."""
    users = get_discoverable_users_for_federation()
    users_list = [dict(user) for user in users]
    return jsonify(users_list)

@federation_bp.route('/federation/api/v1/discover_groups', methods=['GET'])
@signature_required
def discover_groups():
    """Provides a list of discoverable groups on this node."""
    groups = get_discoverable_groups()
    return jsonify(groups)

@federation_bp.route('/federation/api/v1/group_join_settings/<puid>', methods=['GET'])
@signature_required
def get_group_join_settings_federated(puid):
    """Federation endpoint to get join settings for a group."""
    from db_queries.groups import get_group_by_puid, get_group_join_settings
    
    try:
        group = get_group_by_puid(puid)
        if not group:
            return jsonify({'error': 'Group not found'}), 404
        
        # For federation requests, always return full settings
        # The requesting node will handle privacy filtering for their user
        settings = get_group_join_settings(group['id'])
        
        return jsonify(settings), 200
        
    except Exception as e:
        print(f"ERROR in get_group_join_settings_federated: {e}")
        traceback.print_exc()
        return jsonify({'error': f'An internal error occurred: {str(e)}'}), 500

# --- NEW ENDPOINT for discovering public events ---
@federation_bp.route('/federation/api/v1/discover_public_events', methods=['GET'])
@signature_required
def discover_public_events():
    """Provides a list of discoverable future public events known to this node."""
    try:
        events = get_discoverable_public_events()
        # Ensure datetime objects are converted to strings for JSON serialization
        for event in events:
            if isinstance(event.get('event_datetime'), datetime):
                event['event_datetime'] = event['event_datetime'].strftime('%Y-%m-%d %H:%M:%S')
            if isinstance(event.get('event_end_datetime'), datetime):
                 event['event_end_datetime'] = event['event_end_datetime'].strftime('%Y-%m-%d %H:%M:%S')
        return jsonify(events)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'An internal error occurred: {str(e)}'}), 500
# --- END NEW ENDPOINT ---

@federation_bp.route('/federation/api/v1/group_join_request_created', methods=['POST'])
@signature_required
def group_join_request_created():
    """
    Receives notification that a local user has requested to join a remote group.
    Creates a pending request stub on the user's home node.
    """
    from db_queries.groups import get_or_create_remote_group_stub, send_join_request

    try:
        data = request.get_json(force=True)
        user_puid = data.get('user_puid')
        group_data = data.get('group_data')
        group_puid = group_data.get('puid') if group_data else None

        if not user_puid or not group_data or not group_puid:
            return jsonify({'error': 'Missing user_puid or group_data in payload.'}), 400

        # Find the local user
        user = get_user_by_puid(user_puid)
        if not user or user['hostname'] is not None:
            return jsonify({'error': 'Notified user is not a valid local user on this node.'}), 404

        # Create or get the remote group stub
        group_stub = get_or_create_remote_group_stub(
            puid=group_puid,
            name=group_data.get('name'),
            description=group_data.get('description'),
            profile_picture_path=group_data.get('profile_picture_path'),
            hostname=group_data.get('hostname')
        )
        
        if not group_stub:
            return jsonify({'error': 'Failed to process remote group stub.'}), 500

        # Create the pending request (without responses - those stay on the group's node)
        success, message = send_join_request(group_stub['id'], user['id'])
        
        if success:
            return jsonify({'message': 'Join request stub created on home node.'}), 200
        else:
            return jsonify({'message': message}), 200

    except Exception as e:
        print(f"ERROR in group_join_request_created: {e}")
        traceback.print_exc()
        return jsonify({'error': f'An internal error occurred: {str(e)}'}), 500

@federation_bp.route('/federation/api/v1/receive_group_join_request', methods=['POST'])
@signature_required
def receive_group_join_request():
    """Receives a group join request from a federated node."""
    try:
        data = request.get_json()
        if not data:
            raise ValueError("Request body must be valid JSON.")

        group_puid = data.get('group_puid')
        requester_data = data.get('requester_data')
        # NEW: Extract responses
        rules_agreed = data.get('rules_agreed', False)
        question_responses = data.get('question_responses', {})

        if not group_puid or not requester_data:
            raise ValueError("Missing group_puid or requester_data in payload.")

        group = get_group_by_puid(group_puid)
        if not group:
            return jsonify({'error': 'Group not found on this node.'}), 404

        remote_user = get_or_create_remote_user(
            puid=requester_data.get('puid'),
            display_name=requester_data.get('display_name'),
            hostname=requester_data.get('hostname'),
            profile_picture_path=requester_data.get('profile_picture_path')
        )
        if not remote_user:
            return jsonify({'error': 'Could not process remote user.'}), 500

        update_remote_user_details(
            puid=requester_data.get('puid'),
            display_name=requester_data.get('display_name'),
            profile_picture_path=requester_data.get('profile_picture_path')
        )

        # When calling send_join_request, include the responses:
        success, message = send_join_request(
            group['id'], 
            remote_user['id'],
            rules_agreed=rules_agreed,
            question_responses=question_responses
        )

        if success:
            # FEDERATION FIX: Notify the user's home node so they can track the pending request
            from db_queries.federation import notify_remote_node_of_group_join_request
            notify_remote_node_of_group_join_request(remote_user, group)
            
            return jsonify({'status': 'success', 'message': message}), 200
        else:
            # If request already exists, it's not an error, return info status
            return jsonify({'status': 'info', 'message': message}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'An internal error occurred: {str(e)}'}), 500

@federation_bp.route('/federation/api/v1/group_request_accepted', methods=['POST'])
@signature_required
def group_request_accepted():
    """
    Receives notification that a group join request was accepted.
    This finds the original request, adds the user to the local group stub,
    deletes the request, creates a notification, and invites to future events.
    """
    # Local import to avoid circular dependency
    from db_queries.events import invite_user_to_source_future_events
    from db_queries.groups import reject_join_request # Keep this local import too

    db = get_db()
    cursor = db.cursor()

    try:
        data = request.get_json(force=True)
        user_puid = data.get('user_puid')
        group_data = data.get('group_data')
        group_puid = group_data.get('puid') if group_data else None

        if not user_puid or not group_data or not group_puid:
            return jsonify({'error': 'Missing user_puid or group_data in payload.'}), 400

        user = get_user_by_puid(user_puid)
        if not user or user['hostname'] is not None:
            return jsonify({'error': 'Notified user is not a valid local user on this node.'}), 404

        group_stub = get_or_create_remote_group_stub(
            puid=group_puid,
            name=group_data.get('name'),
            description=group_data.get('description'),
            profile_picture_path=group_data.get('profile_picture_path'),
            hostname=group_data.get('hostname')
        )
        if not group_stub:
            return jsonify({'error': 'Failed to process remote group stub.'}), 500

        cursor.execute("""
            SELECT id FROM group_join_requests
            WHERE user_id = ? AND group_id = ? AND status = 'pending'
        """, (user['id'], group_stub['id']))
        request_to_process = cursor.fetchone()

        if not request_to_process:
            print(f"INFO: Received group acceptance for user {user_puid} and group {group_puid}, but no pending request was found.")
            # Even if no request found, maybe user joined via invite. Invite to events anyway.
            invite_user_to_source_future_events(user, 'group', group_stub['puid'])
            return jsonify({'message': 'Acknowledgement received, no pending request found.'}), 200

        cursor.execute("INSERT OR IGNORE INTO group_members (group_id, user_id, role) VALUES (?, ?, 'member')",
                       (group_stub['id'], user['id']))
        rows_affected = cursor.rowcount

        # Delete the processed request
        reject_join_request(request_to_process['id']) # This now just deletes

        create_notification(
            user_id=user['id'],
            actor_id=user['id'], # Self-notification essentially
            type='group_request_accepted',
            group_id=group_stub['id']
        )

        db.commit()

        # Invite the user to future group events after successful join
        if rows_affected > 0:
            invite_user_to_source_future_events(user, 'group', group_stub['puid'])

        return jsonify({'message': 'Group membership acceptance acknowledged.'}), 200

    except Exception as e:
        db.rollback()
        traceback.print_exc()
        return jsonify({'error': f'An internal error occurred: {str(e)}'}), 500


@federation_bp.route('/federation/api/v1/receive_mention', methods=['POST'])
@signature_required
def receive_mention():
    """Receives a mention notification from a federated node."""
    try:
        data = request.get_json()
        if not data:
            raise ValueError("Request body must be valid JSON.")

        mentioned_puid = data.get('mentioned_puid')
        actor_data = data.get('actor')
        post_cuid = data.get('post_cuid')
        comment_cuid = data.get('comment_cuid')
        group_puid = data.get('group_puid')

        if not mentioned_puid or not actor_data or not post_cuid:
            raise ValueError("Missing mentioned_puid, actor, or post_cuid in payload.")

        mentioned_user = get_user_by_puid(mentioned_puid)
        if not mentioned_user or mentioned_user['hostname'] is not None:
            return jsonify({'error': 'Mentioned user is not a valid local user.'}), 404

        actor = get_or_create_remote_user(
            puid=actor_data['puid'],
            display_name=actor_data['display_name'],
            hostname=actor_data['hostname'],
            profile_picture_path=actor_data.get('profile_picture_path')
        )
        if not actor:
            return jsonify({'error': 'Could not process remote actor.'}), 500

        post = get_post_by_cuid(post_cuid)
        if not post:
            # It's possible the post hasn't arrived yet due to federation lag.
            # We can't create a notification without a post_id.
            # Maybe retry later? For now, just return success.
            print(f"WARN: Mention received for unknown post {post_cuid}. Skipping notification.")
            return jsonify({'message': 'Mention acknowledged, post not found locally yet.'}), 200
        post_id = post['id']

        comment_id = None
        if comment_cuid:
            comment_info = get_comment_by_cuid(comment_cuid)
            if comment_info:
                comment_id = comment_info['comment_id']

        group_id = None
        if group_puid:
            group = get_group_by_puid(group_puid)
            if group:
                group_id = group['id']

        create_notification(
            user_id=mentioned_user['id'],
            actor_id=actor['id'],
            type='mention',
            post_id=post_id,
            comment_id=comment_id,
            group_id=group_id
        )

        return jsonify({'message': 'Mention notification received and processed.'}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'An internal error occurred: {str(e)}'}), 500


@federation_bp.route('/federation/api/v1/receive_friend_request', methods=['POST'])
@signature_required
def receive_friend_request():
    """Receives a friend request from a federated node."""
    try:
        data = request.get_json()
        if not data:
            raise ValueError("Request body must be valid JSON.")

        receiver_puid = data.get('receiver_puid')
        sender_puid = data.get('sender_puid')
        sender_hostname = data.get('sender_hostname')
        sender_display_name = data.get('sender_display_name')
        sender_profile_picture_path = data.get('sender_profile_picture_path')

        if not sender_puid or not receiver_puid or not sender_hostname:
            raise ValueError("Missing sender/receiver PUID or sender hostname.")

        receiver_user = get_user_by_puid(receiver_puid)
        if not receiver_user or receiver_user['hostname'] is not None:
            return jsonify({'error': 'Receiver is not a valid local user.'}), 404

        remote_user = get_or_create_remote_user(
            puid=sender_puid,
            display_name=sender_display_name,
            hostname=sender_hostname,
            profile_picture_path=sender_profile_picture_path
        )
        if not remote_user:
            return jsonify({'error': 'Could not process remote user.'}), 500

        # Ensure latest details are stored
        update_remote_user_details(
            puid=sender_puid,
            display_name=sender_display_name,
            profile_picture_path=sender_profile_picture_path
        )

        # NEW: PARENTAL CONTROL CHECK - Intercept incoming remote friend requests for users requiring approval
        from db_queries.parental_controls import requires_parental_approval, create_approval_request, get_all_parent_ids
        
        if requires_parental_approval(receiver_user['id']):
            # Create approval request instead of adding directly to friend_requests
            request_data = json.dumps({
                'sender_puid': sender_puid,
                'sender_display_name': sender_display_name,
                'sender_hostname': sender_hostname,
                'sender_profile_picture_path': sender_profile_picture_path
            })
            
            approval_id = create_approval_request(
                receiver_user['id'],
                'friend_request_in',  # Note: 'in' for incoming, 'out' for outgoing
                sender_puid,
                sender_hostname,
                request_data
            )
            
            if approval_id:
                # Get ALL parents for notification (supports multiple parents)
                parent_ids = get_all_parent_ids(receiver_user['id'])
                
                # Notify all parents
                for parent_id in parent_ids:
                    create_notification(parent_id, receiver_user['id'], 'parental_approval_needed')
                
                return jsonify({
                    'status': 'info',
                    'message': 'Friend request pending parental approval.'
                }), 200
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to create approval request.'
                }), 500

        # No parental approval needed, process normally
        success, error_type = send_friend_request_db(remote_user['id'], receiver_user['id'])

        if success:
            return jsonify({'status': 'success', 'message': 'Friend request received successfully.'}), 200
        elif error_type == 'exists':
            return jsonify({'status': 'info', 'message': 'Friend request already exists.'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Failed to process friend request.'}), 500

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'An internal error occurred: {str(e)}'}), 500

@federation_bp.route('/federation/api/v1/receive_follow', methods=['POST'])
@signature_required
def receive_follow():
    """
    Receives a follow request from a federated node for a local public page.
    Invites the follower to future page events.
    """
    # Local import to avoid circular dependency
    from db_queries.events import invite_user_to_source_future_events

    try:
        data = request.get_json()
        if not data:
            raise ValueError("Request body must be valid JSON.")

        page_to_follow_puid = data.get('page_to_follow_puid')
        follower_puid = data.get('follower_puid')
        follower_hostname = data.get('follower_hostname')
        follower_display_name = data.get('follower_display_name')

        if not all([page_to_follow_puid, follower_puid, follower_hostname, follower_display_name]):
            raise ValueError("Missing required data for follow action.")

        page_to_follow = get_user_by_puid(page_to_follow_puid)
        if not page_to_follow or page_to_follow['user_type'] != 'public_page' or page_to_follow['hostname'] is not None:
            return jsonify({'error': 'Target is not a valid local public page.'}), 404

        remote_follower = get_or_create_remote_user(
            puid=follower_puid,
            display_name=follower_display_name,
            hostname=follower_hostname,
            profile_picture_path=None
        )
        if not remote_follower:
            return jsonify({'error': 'Could not process remote follower.'}), 500

        if follow_page(remote_follower['id'], page_to_follow['id']):
            # Create the follow notification
            create_notification(
                user_id=page_to_follow['id'],
                actor_id=remote_follower['id'],
                type='follow' # Assuming 'follow' is a valid notification type
            )

            # Invite the remote follower to future page events
            invite_user_to_source_future_events(remote_follower, 'public_page', page_to_follow['puid'])

            return jsonify({'status': 'success', 'message': 'Follow action successful and user invited to future events.'}), 200
        else:
            # If follow_page returned false, it likely means they were already following
            # In this case, still attempt to invite them to events as a safeguard
            invite_user_to_source_future_events(remote_follower, 'public_page', page_to_follow['puid'])
            return jsonify({'status': 'info', 'message': 'User already following. Ensured invitation to future events.'}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'An internal error occurred: {str(e)}'}), 500


@federation_bp.route('/federation/api/v1/friend_request_accepted', methods=['POST'])
@signature_required
def friend_request_accepted():
    """
    Endpoint to be called by a remote node when one of our local users'
    friend requests has been accepted.
    """
    try:
        data = request.get_json(force=True)
    except (json.JSONDecodeError, TypeError):
        return jsonify({'error': 'Invalid or missing JSON in request body.'}), 400

    original_sender_puid = data.get('original_sender_puid')
    original_receiver_puid = data.get('original_receiver_puid')
    accepter_display_name = data.get('accepter_display_name')
    accepter_profile_picture_path = data.get('accepter_profile_picture_path')


    if not original_sender_puid or not original_receiver_puid:
        return jsonify({'error': 'Missing required PUIDs in payload.'}), 400

    sender = get_user_by_puid(original_sender_puid)
    if not sender or sender['hostname'] is not None:
        return jsonify({'error': 'Sender is not a valid local user on this node.'}), 404

    receiver = get_user_by_puid(original_receiver_puid)
    if not receiver or receiver['hostname'] is None:
        # Need to create the remote user if they don't exist yet.
        # Fallback username/display name might be needed if not provided.
        receiver = get_or_create_remote_user(
            puid=original_receiver_puid,
            display_name=accepter_display_name or f"User {original_receiver_puid[:8]}", # Use provided name or placeholder
            hostname=request.headers.get('X-Node-Hostname'), # Get hostname from header
            profile_picture_path=accepter_profile_picture_path
        )
        if not receiver:
            return jsonify({'error': 'Receiver is not a valid remote user and could not be created.'}), 404


    # Ensure remote user details are up-to-date
    if accepter_display_name:
        update_remote_user_details(
            puid=original_receiver_puid,
            display_name=accepter_display_name,
            profile_picture_path=accepter_profile_picture_path
        )

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id FROM friend_requests
        WHERE sender_id = ? AND receiver_id = ? AND status = 'pending'
    """, (sender['id'], receiver['id']))
    request_to_accept_row = cursor.fetchone()
    request_to_accept = dict(request_to_accept_row) if request_to_accept_row else None


    if not request_to_accept:
        # Check if they are already friends (maybe acceptance crossed paths)
        if is_friends_with(sender['id'], receiver['id']):
            return jsonify({'message': 'Friendship already established.'}), 200
        else:
            return jsonify({'error': 'No matching pending friend request found to accept.'}), 404

    if accept_friend_request_db(request_to_accept['id'], notify_remote=False):
    # Note: notification already created inside accept_friend_request_db for local sender
        return jsonify({'message': 'Friendship confirmed and established locally.'}), 200
    else:
        return jsonify({'error': 'Failed to establish friendship locally.'}), 500

@federation_bp.route('/federation/api/v1/friend_request_rejected', methods=['POST'])
@signature_required
def friend_request_rejected():
    """
    Receives notification that a friend request sent by a local user was rejected.
    """
    try:
        data = request.get_json(force=True)
        original_sender_puid = data.get('original_sender_puid')
        original_receiver_puid = data.get('original_receiver_puid')

        if not original_sender_puid or not original_receiver_puid:
            return jsonify({'error': 'Missing required PUIDs in payload.'}), 400

        if delete_friend_request_by_puids(original_sender_puid, original_receiver_puid):
            return jsonify({'message': 'Friend request rejection acknowledged and removed.'}), 200
        else:
            # It's possible the user cancelled the request locally before rejection arrived
            return jsonify({'message': 'Friend request rejection acknowledged, request not found locally.'}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'An internal error occurred: {str(e)}'}), 500

@federation_bp.route('/federation/api/v1/receive_unfriend', methods=['POST'])
@signature_required
def receive_unfriend():
    """
    Receives notification that a remote user has unfriended a local user.
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON payload.'}), 400

    unfriender_puid = data.get('unfriender_puid')
    unfriended_puid = data.get('unfriended_puid')

    if not unfriender_puid or not unfriended_puid:
        return jsonify({'error': 'Missing PUIDs in payload.'}), 400

    unfriender_user = get_user_by_puid(unfriender_puid)
    unfriended_user = get_user_by_puid(unfriended_puid)

    if not unfriender_user or not unfriended_user:
        # Ignore if one of the users doesn't exist locally
        return jsonify({'message': 'Unfriend ignored, one or both users not found locally.'}), 200

    # Ensure the action makes sense (remote unfriending local)
    if unfriender_user.get('hostname') is None:
         return jsonify({'error': 'Action can only be initiated by a remote user.'}), 400
    if unfriended_user.get('hostname') is not None:
         return jsonify({'error': 'Target user must be a local user.'}), 400

    if unfriend_db(unfriender_user['id'], unfriended_user['id']):
        print(f"INFO: Friendship removed between {unfriender_puid} and {unfriended_puid} based on remote action.")
        return jsonify({'message': 'Unfriend action acknowledged and processed.'}), 200
    else:
        print(f"INFO: Received unfriend action for {unfriender_puid} / {unfriended_puid}, but no friendship found.")
        return jsonify({'message': 'Unfriend action acknowledged, no existing friendship found.'}), 200

@federation_bp.route('/federation/api/v1/receive_leave_group', methods=['POST'])
@signature_required
def receive_leave_group():
    """
    Receives notification that a remote user has left a local group.
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON payload.'}), 400

    leaver_puid = data.get('leaver_puid')
    group_puid = data.get('group_puid')

    if not leaver_puid or not group_puid:
        return jsonify({'error': 'Missing PUIDs in payload.'}), 400

    leaver_user = get_user_by_puid(leaver_puid)
    group = get_group_by_puid(group_puid)

    if not leaver_user or not group:
         return jsonify({'message': 'Leave group ignored, user or group not found locally.'}), 200

    # Ensure the action makes sense (remote leaving local group)
    if leaver_user.get('hostname') is None:
         return jsonify({'error': 'Action can only be initiated by a remote user.'}), 400
    if group.get('hostname') is not None:
         return jsonify({'error': 'Target group must be a local group.'}), 400

    success, message = leave_group(group['id'], leaver_user['id'])

    if success:
        print(f"INFO: User {leaver_puid} left group {group_puid} based on remote action.")
        return jsonify({'message': 'Leave group action acknowledged and processed.'}), 200
    else:
        print(f"INFO: Received leave group for {leaver_puid} / {group_puid}, but action failed: {message}")
        # Even if local removal failed (e.g., not a member), acknowledge receipt.
        return jsonify({'message': f'Leave group action acknowledged, but local removal failed: {message}'}), 200

@federation_bp.route('/federation/api/v1/group_member_removed', methods=['POST'])
@signature_required
def group_member_removed():
    """
    Receives notification that one of our users was removed from a remote group.
    This can be due to kick, ban, or voluntary leave.
    """
    try:
        data = request.get_json()
        if not data:
            raise ValueError("Request body must be valid JSON.")
        
        user_puid = data.get('user_puid')
        group_puid = data.get('group_puid')
        removal_type = data.get('removal_type', 'kick')  # 'kick', 'ban', or 'leave'
        
        if not user_puid or not group_puid:
            raise ValueError("Missing user_puid or group_puid in payload.")
        
        user = get_user_by_puid(user_puid)
        group = get_group_by_puid(group_puid)
        
        if not user:
            return jsonify({'error': 'User not found on this node'}), 404
        
        # Ensure this is a local user
        if user.get('hostname') is not None:
            return jsonify({'error': 'User must be local to this node'}), 400
        
        if not group:
            return jsonify({'error': 'Group not found on this node'}), 404
        
        db = get_db()
        cursor = db.cursor()
        
        # Remove the user from the group locally
        cursor.execute("DELETE FROM group_members WHERE group_id = ? AND user_id = ?", 
                      (group['id'], user['id']))
        
        # If banned, mark them as banned (don't just delete)
        if removal_type == 'ban':
            cursor.execute("""
                INSERT OR REPLACE INTO group_members (group_id, user_id, role, is_banned)
                VALUES (?, ?, 'member', TRUE)
            """, (group['id'], user['id']))
        
        db.commit()
        
        # Create notification for the user
        if removal_type == 'kick':
            notification_type = 'group_kicked'
        elif removal_type == 'ban':
            notification_type = 'group_banned'
        else:
            # Don't notify for voluntary leave
            notification_type = None
        
        if notification_type:
            create_notification(
                user_id=user['id'],
                actor_id=None,  # System notification
                type=notification_type,
                group_id=group['id']
            )
        
        print(f"INFO: User {user_puid} removed from group {group_puid} ({removal_type})")
        
        return jsonify({
            'status': 'success',
            'message': f'User removed from group ({removal_type})'
        }), 200
        
    except Exception as e:
        print(f"ERROR in group_member_removed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@federation_bp.route('/federation/api/v1/group_request_rejected', methods=['POST'])
@signature_required
def group_request_rejected():
    """
    Receives notification that a group join request was rejected.
    """
    try:
        data = request.get_json()
        if not data:
            raise ValueError("Request body must be valid JSON.")
        
        user_puid = data.get('user_puid')
        group_data = data.get('group_data')
        rejection_reason = data.get('rejection_reason')
        
        if not user_puid or not group_data:
            raise ValueError("Missing user_puid or group_data in payload.")
        
        user = get_user_by_puid(user_puid)
        if not user:
            return jsonify({'error': 'User not found on this node'}), 404
        
        # Ensure this is a local user
        if user.get('hostname') is not None:
            return jsonify({'error': 'User must be local to this node'}), 400
        
        group_puid = group_data.get('puid')
        if not group_puid:
            return jsonify({'error': 'Missing group puid'}), 400
        
        # Get or create the remote group stub
        group_stub = get_or_create_remote_group_stub(
            puid=group_puid,
            name=group_data.get('name'),
            description=group_data.get('description'),
            profile_picture_path=group_data.get('profile_picture_path'),
            hostname=group_data.get('hostname')
        )
        
        if not group_stub:
            return jsonify({'error': 'Failed to process remote group stub'}), 500
        
        db = get_db()
        cursor = db.cursor()
        
        # Delete the pending join request locally
        cursor.execute("""
            DELETE FROM group_join_requests 
            WHERE user_id = ? AND group_id = ? AND status = 'pending'
        """, (user['id'], group_stub['id']))
        
        db.commit()
        
        # Create notification for the user
        notification_message = "Your request to join the group was not approved"
        if rejection_reason:
            notification_message = f"Your request to join the group was not approved: {rejection_reason}"
        
        create_notification(
            user_id=user['id'],
            actor_id=user['id'], # Self-notification essentially
            type='group_request_rejected',
            group_id=group_stub['id']
        )
        
        print(f"INFO: User {user_puid} notified of rejection from group {group_puid}")
        
        return jsonify({
            'status': 'success',
            'message': 'Rejection notification processed'
        }), 200
        
    except Exception as e:
        print(f"ERROR in group_request_rejected: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@federation_bp.route('/federation/api/v1/request_viewer_token', methods=['POST'])
@signature_required
def request_viewer_token():
    """
    Generates a short-lived token for a remote user to view a local profile/group/event.
    """
    data = request.get_json()
    viewer_puid = data.get('viewer_puid')
    target_puid = data.get('target_puid')
    viewer_settings = data.get('viewer_settings') # Expect settings from the requesting node

    if not viewer_puid or not target_puid:
        return jsonify({'error': 'viewer_puid and target_puid are required.'}), 400

    viewer = get_user_by_puid(viewer_puid)
    # Check users, groups, and events for the target
    target = get_user_by_puid(target_puid)
    if not target:
        target = get_group_by_puid(target_puid)
    if not target:
        target = get_event_by_puid(target_puid)


    if not viewer or not target:
        return jsonify({'error': 'One or both entities not found in local records.'}), 404

    # Target must be local, viewer must be remote
    if target.get('hostname') is not None:
        return jsonify({'error': 'Target entity is not local.'}), 400
    if viewer.get('hostname') is None:
        return jsonify({'error': 'Viewer is not a remote user.'}), 400

    remote_hostname = request.headers.get('X-Node-Hostname')
    node = get_node_by_hostname(remote_hostname)

    if not node or not node['shared_secret']:
        return jsonify({'error': 'Could not find connection details for the requesting node.'}), 403

    # Use the requesting node's shared secret to sign the token
    serializer = URLSafeTimedSerializer(node['shared_secret'])

    payload = {
        'viewer_puid': viewer_puid,
        'origin_hostname': remote_hostname,
        'settings': viewer_settings # Include received settings in the token
    }
    # Token expires after 5 minutes (300 seconds)
    token = serializer.dumps(payload, salt='viewer-token-salt')

    return jsonify({'viewer_token': token}), 200


@federation_bp.route('/federation/api/v1/initiate_viewer_session', methods=['POST'])
def initiate_viewer_session():
    """
    Validates a viewer token from another node and establishes a temporary
    federated viewing session for the current browser session.
    """
    data = request.get_json()
    token = data.get('viewer_token')

    if not token:
        return jsonify({'error': 'Viewer token is required.'}), 400

    try:
        # 1. Decode without verification to get origin_hostname
        unsafe_serializer = URLSafeTimedSerializer('dummy-secret') # Use a dummy key
        try:
            # We don't care about expiration here, just getting the origin
            is_timed, unverified_payload = unsafe_serializer.loads_unsafe(
                token,
                salt='viewer-token-salt'
            )
        except BadSignature as e:
            # This handles malformed tokens
            raise BadSignature("Token is malformed and cannot be decoded.") from e

        origin_hostname = unverified_payload.get('origin_hostname')
        if not origin_hostname:
            raise BadSignature("Token payload is missing the origin_hostname.")

        # 2. Get the correct shared secret for the origin node
        origin_node = get_node_by_hostname(origin_hostname)
        if not origin_node or not origin_node['shared_secret']:
            raise BadSignature(f"Cannot verify token: Unknown node or missing shared secret for {origin_hostname}.")

        # 3. Verify the token using the correct secret and check expiration (max_age=300 seconds / 5 minutes)
        final_serializer = URLSafeTimedSerializer(origin_node['shared_secret'])
        token_data = final_serializer.loads(token, salt='viewer-token-salt', max_age=300)

        # 4. Token is valid, establish session
        viewer_puid = token_data.get('viewer_puid')
        if not viewer_puid:
            raise Exception("Invalid token payload") # Should not happen if signature is valid

        # Ensure a local stub exists for the remote viewer
        get_or_create_remote_user(
            puid=viewer_puid,
            display_name=f"User {viewer_puid[:8]}", # Placeholder display name
            hostname=origin_hostname,
            profile_picture_path=None
        )

        # Set session variables to indicate a federated viewer
        session['is_federated_viewer'] = True
        session['federated_viewer_puid'] = viewer_puid
        # Store the viewer's settings received in the token
        session['federated_viewer_settings'] = token_data.get('settings')

        # Construct and store the viewer's home URL for redirects
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = "http" if insecure_mode else "https"
        viewer_home_url = f"{protocol}://{origin_hostname}"
        session['viewer_home_url'] = viewer_home_url

        return jsonify({'message': 'Viewer session initiated successfully.'}), 200

    except SignatureExpired:
        return jsonify({'error': 'Viewer token has expired.'}), 401
    except (BadTimeSignature, BadSignature) as e:
        # Catches verification errors, invalid salt, bad format
        return jsonify({'error': f'Invalid viewer token: {e}'}), 401
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'An internal error occurred: {str(e)}'}), 500

@federation_bp.route('/federation/inbox', methods=['POST', 'PUT', 'DELETE'])
@signature_required
def receive_federated_action():
    """
    Receives a federated action (create, update, delete) from another node
    and processes it accordingly.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON payload.'}), 400

        action_type = data.get('type')
        if not action_type:
            return jsonify({'error': 'Missing "type" in payload.'}), 400

        remote_hostname = request.headers.get('X-Node-Hostname') # Node sending the action

        # --- Post Actions ---
        if action_type == 'post_create':
            # ... (post creation logic as before) ...
            author_data = data.get('author_data')
            if not author_data:
                return jsonify({'error': 'Missing author_data for post_create action.'}), 400

            is_repost = data.get('is_repost', False)
            is_group_post = 'group_data' in data and data['group_data'] is not None

            # Validation for original posts vs reposts
            if not is_repost:
                if not is_group_post and 'profile_puid' not in data and not data.get('event_data'):
                     return jsonify({'error': 'Missing profile_puid for a profile post or event_data for an event post.'}), 400
                if is_group_post and 'group_data' not in data:
                    return jsonify({'error': 'Missing group_data for a group post.'}), 400
                required_fields = ['cuid', 'timestamp', 'privacy_setting', 'nu_id']
                # Content or media required unless it's an event post
                if 'content' not in data and 'media_files' not in data and not data.get('event_data'):
                     required_fields.append('content') # Force content requirement

                if not all(field in data for field in required_fields):
                    missing = [f for f in required_fields if f not in data]
                    return jsonify({'error': f"Missing one or more required fields for post_create action: {', '.join(missing)}"}), 400
            else: # Repost validation
                required_fields = ['cuid', 'timestamp', 'privacy_setting', 'nu_id', 'original_post_cuid']
                if not all(field in data for field in required_fields):
                    missing = [f for f in required_fields if f not in data]
                    return jsonify({'error': f"Missing one or more required fields for repost_create action: {', '.join(missing)}"}), 400
                # Ensure the original post exists locally before accepting the repost
                if get_post_by_cuid(data.get('original_post_cuid')) is None:
                    # Maybe request the original post from the remote node here?
                    # For now, reject if original isn't known.
                    return jsonify({'error': 'Original post for repost not found locally.'}), 404


            # Avoid duplicates
            if get_post_by_cuid(data['cuid']):
                return jsonify({'message': 'Post already exists.'}), 200

            # Ensure author exists locally (create stub if needed)
            author = get_or_create_remote_user(
                puid=author_data.get('puid'),
                display_name=author_data.get('display_name'),
                hostname=author_data.get('hostname'),
                profile_picture_path=author_data.get('profile_picture_path'),
                user_type=author_data.get('user_type', 'remote') # Default to 'remote'
            )
            if not author:
                return jsonify({'error': 'Could not process remote author.'}), 500

            # Ensure latest details are stored for the author
            update_remote_user_details(
                puid=author_data.get('puid'),
                display_name=author_data.get('display_name'),
                profile_picture_path=author_data.get('profile_picture_path')
            )

            profile_user_id = None
            group_puid = None
            group_id = None
            event_id = None
            event_data = data.get('event_data')

            # Process event data if present
            if event_data:
                try:
                    event_datetime = datetime.strptime(event_data['event_datetime'], '%Y-%m-%d %H:%M:%S')
                    event_end_datetime = None
                    if event_data.get('event_end_datetime'):
                        event_end_datetime = datetime.strptime(event_data['event_end_datetime'], '%Y-%m-%d %H:%M:%S')

                    event_stub = get_or_create_remote_event_stub(
                        puid=event_data.get('puid'),
                        created_by_user_puid=event_data.get('created_by_user_puid'),
                        source_type=event_data.get('source_type'),
                        source_puid=event_data.get('source_puid'),
                        title=event_data.get('title'),
                        event_datetime=event_datetime,
                        event_end_datetime=event_end_datetime,
                        location=event_data.get('location'),
                        details=event_data.get('details'),
                        is_public=event_data.get('is_public', False),
                        hostname=event_data.get('hostname')
                    )
                    if not event_stub:
                         raise ValueError("Failed to process remote event stub.")
                    event_id = event_stub['id']
                except (ValueError, TypeError, KeyError) as e:
                     print(f"Error processing event data: {e}")
                     return jsonify({'error': f'Invalid event data in payload: {e}'}), 400


            # Process group data if it's a group post
            elif is_group_post:
                group_data = data['group_data']
                group_puid = group_data.get('puid')
                group_stub = get_or_create_remote_group_stub(
                    puid=group_puid,
                    name=group_data.get('name'),
                    description=group_data.get('description'),
                    profile_picture_path=group_data.get('profile_picture_path'),
                    hostname=remote_hostname # Group's origin is the node sending the post
                )
                if not group_stub:
                    return jsonify({'error': 'Failed to process remote group stub.'}), 500
                group_id = group_stub['id']
            # Otherwise, it's a profile post
            elif not is_repost and data.get('profile_puid'):
                profile_user = get_user_by_puid(data['profile_puid'])
                if not profile_user:
                     # If profile user doesn't exist, maybe it's a remote user not known yet?
                     # For now, treat as error. Could potentially create a stub.
                    return jsonify({'error': 'Profile user not found in local records.'}), 404
                profile_user_id = profile_user['id']
                # Create wall post notification if applicable (local profile owner)
                if author['id'] != profile_user['id'] and profile_user['hostname'] is None:
                    create_notification(profile_user_id, author['id'], 'wall_post')


            # Add the post to the database
            new_post_cuid = add_post(
                user_id=author['id'],
                profile_user_id=profile_user_id,
                content=data.get('content'),
                privacy_setting=data['privacy_setting'],
                media_files=data.get('media_files', []),
                nu_id=data['nu_id'],
                cuid=data['cuid'],
                author_puid=author['puid'],
                profile_puid=data.get('profile_puid'),
                group_puid=group_puid,
                is_remote=True,
                author_hostname=author_data.get('hostname'),
                is_repost=is_repost,
                original_post_cuid=data.get('original_post_cuid'),
                event_id=event_id,
                comments_disabled=data.get('comments_disabled', False), # NEW: Add this
                tagged_user_puids=data.get('tagged_user_puids', []),  # NEW: Tagged users
                location=data.get('location'),
                timestamp=data.get('timestamp')
            )

            # Create notifications for local mentions/group members/followers
            if new_post_cuid:
                newly_created_post = get_post_by_cuid(new_post_cuid)
                if newly_created_post:
                    post_id = newly_created_post['id']

                    # Local Mentions
                    mentioned_puids = data.get('mentioned_puids', [])
                    for puid in mentioned_puids:
                        mentioned_user = get_user_by_puid(puid)
                        if mentioned_user and mentioned_user['hostname'] is None:
                            create_notification(mentioned_user['id'], author['id'], 'mention', post_id, group_id=group_id)

                    # Local Group Members (for non-reposts in groups)
                    if is_group_post and group_id and not is_repost:
                        from db_queries.groups import get_group_members
                        local_members = get_group_members(group_id)
                        # NEW: Check if this is an @everyone mention
                        has_everyone = data.get('has_everyone_mention', False)
                        notification_type = 'everyone_mention' if has_everyone else 'group_post'
                        
                        for member in local_members:
                            if member['hostname'] is None and member['puid'] != author_data.get('puid'):
                                create_notification(member['id'], author['id'], notification_type, post_id, group_id=group_id)

                    # Local Original Author (for reposts)
                    if is_repost:
                        original_post_cuid = data.get('original_post_cuid')
                        original_post = get_post_by_cuid(original_post_cuid) # Assumes original post exists locally
                        if original_post and original_post['author']['hostname'] is None:
                             create_notification(original_post['user_id'], author['id'], 'repost', newly_created_post['id'])

                    # Local Followers (for public page posts)
                    if author and author['user_type'] == 'public_page' and not is_repost:
                        from db_queries.followers import get_followers
                        local_followers = get_followers(author['id'])
                        for follower in local_followers:
                             if follower.get('hostname') is None:
                                create_notification(follower['id'], author['id'], 'page_post', post_id)

                    # NEW: Local Event Attendees (for event posts)
                    if event_id and not is_repost:
                        from db_queries.events import get_event_attendees
                        attendees = get_event_attendees(event_id)
                        
                        # Check if this is an @everyone mention
                        has_everyone = data.get('has_everyone_mention', False)
                        mentioned_puids = data.get('mentioned_puids', [])
                        
                        already_notified = set()
                        for attendee in attendees:
                            # Skip the author
                            if attendee['puid'] == author_data.get('puid'):
                                continue
                                
                            attendee_user = get_user_by_puid(attendee['puid'])
                            if attendee_user and attendee_user['hostname'] is None and attendee_user['id'] not in already_notified:
                                # Determine notification type
                                if has_everyone:
                                    create_notification(attendee_user['id'], author['id'], 'everyone_mention', post_id, event_id=event_id)
                                    already_notified.add(attendee_user['id'])
                                elif attendee['puid'] in mentioned_puids:
                                    create_notification(attendee_user['id'], author['id'], 'mention', post_id, event_id=event_id)
                                    already_notified.add(attendee_user['id'])
                                else:
                                    # Regular event post notification
                                    create_notification(attendee_user['id'], author['id'], 'event_post', post_id, event_id=event_id)
                                    already_notified.add(attendee_user['id'])

                    # NEW: Local Tagged Users (for posts with tagged friends)
                    tagged_puids = data.get('tagged_user_puids', [])
                    for puid in tagged_puids:
                        tagged_user = get_user_by_puid(puid)
                        if tagged_user and tagged_user['hostname'] is None:
                            # Avoid duplicate notifications
                            if 'already_notified' not in locals():
                                already_notified = set()
                            if tagged_user['id'] not in already_notified:
                                create_notification(
                                    tagged_user['id'], 
                                    author['id'], 
                                    'tagged_in_post', 
                                    post_id, 
                                    group_id=group_id,
                                    event_id=event_id
                                )
                                already_notified.add(tagged_user['id'])


            return jsonify({'message': 'Post created successfully.'}), 201

        elif action_type == 'event_post_create':
            author_data = data.get('author_data')
            if not author_data:
                return jsonify({'error': 'Missing author_data for event_post_create action.'}), 400

            event_puid = data.get('event_puid')
            if not event_puid:
                return jsonify({'error': 'Missing event_puid for event_post_create action.'}), 400

            event = get_event_by_puid(event_puid)
            if not event:
                return jsonify({'error': 'Event not found locally.'}), 404

            author = get_or_create_remote_user(
                puid=author_data.get('puid'),
                display_name=author_data.get('display_name'),
                hostname=author_data.get('hostname'),
                profile_picture_path=author_data.get('profile_picture_path'),
                user_type=author_data.get('user_type', 'remote')
            )
            if not author:
                return jsonify({'error': 'Could not process remote author.'}), 500

            # Add the post linked to the event
            post_cuid = add_post(
                user_id=author['id'],
                profile_user_id=None,
                content=data.get('content'),
                privacy_setting='event',
                media_files=data.get('media_files', []),
                event_id=event['id'],
                author_hostname=author_data.get('hostname'),
                cuid=data.get('cuid'),
                is_remote=True,
                nu_id=data.get('nu_id'),
                timestamp=data.get('timestamp')
            )

            if post_cuid:
                # NOTE: Notifications for event posts (including @everyone mentions) are now
                # handled in the main post_create section above, so we don't duplicate them here.
                # The post_create handler checks for event_id and handles all notification logic.
                
                return jsonify({'message': 'Event post created successfully.'}), 201
            else:
                return jsonify({'error': 'Failed to save event post locally.'}), 500


        elif action_type == 'event_invite':
            required_fields = ['puid', 'created_by_user_puid', 'source_type', 'source_puid', 'title', 'event_datetime', 'hostname', 'invitee_puid']
            if not all(field in data for field in required_fields):
                missing = [f for f in required_fields if f not in data]
                return jsonify({'error': f"Missing one or more required fields for event_invite action: {', '.join(missing)}"}), 400

            invitee = get_user_by_puid(data['invitee_puid'])
            if not invitee or invitee.get('hostname') is not None: # Ensure invitee is local
                return jsonify({'message': 'Event invite ignored: invitee is not a local user.'}), 200

            # PARENTAL CONTROL CHECK - Intercept event invitations for users requiring approval
            from db_queries.parental_controls import requires_parental_approval, create_approval_request, get_all_parent_ids
            from db_queries.notifications import create_notification
            
            if requires_parental_approval(invitee['id']):
                # Parse event datetime for storage
                try:
                    event_datetime_parsed = datetime.strptime(data['event_datetime'], '%Y-%m-%d %H:%M:%S')
                    event_datetime_str = event_datetime_parsed.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    event_datetime_str = str(data.get('event_datetime'))
                
                # Create approval request for the invitation
                request_data = json.dumps({
                    'event_puid': data['puid'],
                    'event_title': data.get('title', 'Unknown Event'),
                    'event_hostname': data['hostname'],
                    'event_datetime': event_datetime_str,
                    'creator_puid': data['created_by_user_puid'],
                    'creator_display_name': data.get('creator_display_name'),  # NEW: Add creator name
                    'source_type': data['source_type'],
                    'source_puid': data['source_puid'],
                    'group_name': data.get('group_name'),  # NEW: Add group name if applicable
                    'location': data.get('location'),
                    'details': data.get('details'),
                    'is_public': data.get('is_public', False),
                    'profile_picture_path': data.get('profile_picture_path'),
                    'event_end_datetime': data.get('event_end_datetime')
                })
                
                approval_id = create_approval_request(
                    invitee['id'],
                    'event_invite',
                    data['puid'],
                    data['hostname'],
                    request_data
                )
                
                if approval_id:
                    # Get ALL parents for notification
                    parent_ids = get_all_parent_ids(invitee['id'])
                    
                    # Notify all parents
                    for parent_id in parent_ids:
                        create_notification(parent_id, invitee['id'], 'parental_approval_needed')
                    
                    return jsonify({'message': 'Event invitation pending parental approval.'}), 200
                else:
                    return jsonify({'error': 'Failed to create approval request.'}), 500

            # Get or create stub for the event
            try:
                event_datetime = datetime.strptime(data['event_datetime'], '%Y-%m-%d %H:%M:%S')
                event_end_datetime = datetime.strptime(data['event_end_datetime'], '%Y-%m-%d %H:%M:%S') if data.get('event_end_datetime') else None
            except (ValueError, TypeError):
                 return jsonify({'error': 'Invalid event date format in payload.'}), 400

            event_stub = get_or_create_remote_event_stub(
                puid=data['puid'],
                created_by_user_puid=data['created_by_user_puid'],
                source_type=data['source_type'],
                source_puid=data['source_puid'],
                title=data['title'],
                event_datetime=event_datetime,
                event_end_datetime=event_end_datetime,
                location=data.get('location'),
                details=data.get('details'),
                is_public=data.get('is_public', False),
                hostname=data['hostname']
            )

            if event_stub:
                # Get or create stub for the inviter
                inviter = get_or_create_remote_user(puid=data['created_by_user_puid'],
                                                     display_name=f"User from {data['hostname']}", # Placeholder
                                                     hostname=data['hostname'],
                                                     profile_picture_path=None)
                if inviter:
                    # Add invitee to local attendee list and create notification
                    invite_friend_to_event(event_stub['id'], inviter['id'], data['invitee_puid'])
                    return jsonify({'message': 'Event invitation received and processed.'}), 200

            return jsonify({'error': 'Failed to process event invitation.'}), 500

        elif action_type == 'event_update':
            # ... (event update logic as before) ...
             required_fields = ['puid', 'title', 'event_datetime', 'location', 'details', 'actor_data']
             if not all(field in data for field in required_fields):
                 missing = [f for f in required_fields if f not in data]
                 return jsonify({'error': f"Missing one or more required fields for event_update action: {', '.join(missing)}"}), 400

             actor_data = data['actor_data']
             actor = get_user_by_puid(actor_data.get('puid')) # Actor could be local or remote
             event = get_event_by_puid(data['puid']) # Event could be local or remote stub

             if not actor or not event:
                  return jsonify({'error': 'Actor or event not found locally.'}), 404

             # Authorization: Check if the actor sending the update matches the event creator
             if event.get('created_by_user_puid') != actor.get('puid'):
                 return jsonify({'error': 'Unauthorized: Only the event creator can update the event.'}), 403

             try:
                 event_datetime = datetime.strptime(data['event_datetime'], '%Y-%m-%d %H:%M:%S')
                 event_end_datetime = datetime.strptime(data['event_end_datetime'], '%Y-%m-%d %H:%M:%S') if data.get('event_end_datetime') else None
             except (ValueError, TypeError):
                 return jsonify({'error': 'Invalid date format in payload.'}), 400

             # Perform the update locally, but don't re-distribute
             success, message = update_event_details(
                 puid=data['puid'],
                 title=data['title'],
                 event_datetime=event_datetime,
                 location=data['location'],
                 details=data['details'],
                 updated_by_user=actor, # Pass the actor object
                 event_end_datetime=event_end_datetime,
                 distribute=False # IMPORTANT: Prevent re-distribution loop
             )
             if success and data.get('profile_picture_path'):
                 from db_queries.events import update_event_picture_path
                 update_event_picture_path(data['puid'], data['profile_picture_path'])
                 
             if success:
                 return jsonify({'message': 'Event update received and processed.'}), 200
             else:
                 return jsonify({'error': f'Failed to process event update locally: {message}'}), 500


        elif action_type == 'event_cancel':
            # ... (event cancel logic as before) ...
            if 'puid' not in data or 'actor_puid' not in data:
                 return jsonify({'error': 'Missing puid or actor_puid for event_cancel action.'}), 400

            actor = get_user_by_puid(data['actor_puid'])
            event = get_event_by_puid(data['puid'])

            if not actor or not event:
                 return jsonify({'error': 'Actor or event not found locally.'}), 404

            if event.get('created_by_user_puid') != actor.get('puid'):
                 return jsonify({'error': 'Unauthorized: Only the event creator can cancel the event.'}), 403

            # Perform cancellation locally, don't re-distribute
            success, message = cancel_event(data['puid'], actor['id'], distribute=False)
            if success:
                # Also clean up any pending parental approvals for this event
                from db_queries.parental_controls import delete_approval_requests_for_event
                delete_approval_requests_for_event(data['puid'])
                return jsonify({'message': 'Event cancellation received and processed.'}), 200
            else:
                 return jsonify({'error': f'Failed to process event cancellation locally: {message}'}), 500


        elif action_type == 'event_response':
            # ... (event response logic as before) ...
            if not all(k in data for k in ['event_puid', 'responder_puid', 'response']):
                 return jsonify({'error': 'Missing fields for event_response action.'}), 400

            event = get_event_by_puid(data['event_puid'])
            # Responder could be local or remote (if they viewed the event via token)
            responder = get_user_by_puid(data['responder_puid'])

            if not event or not responder:
                 return jsonify({'error': 'Event or responder not found locally.'}), 404

            # Update local attendee status, don't re-distribute
            success, message = respond_to_event(data['event_puid'], data['responder_puid'], data['response'], distribute=False)

            if success:
                 return jsonify({'message': 'Event response received and processed.'}), 200
            else:
                 return jsonify({'error': f'Failed to process event response locally: {message}'}), 500


        # --- Post Update/Delete ---
        elif action_type == 'post_update':
            # ... (post update logic as before) ...
            required_fields = ['cuid', 'content', 'privacy_setting']
            if not all(field in data for field in required_fields):
                missing = [f for f in required_fields if f not in data]
                return jsonify({'error': f"Missing one or more required fields for post_update action: {', '.join(missing)}"}), 400

            post_to_update = get_post_by_cuid(data['cuid'])
            if not post_to_update:
                return jsonify({'error': 'Post to update not found.'}), 404

            # Authorization check would ideally happen here, comparing sender node/user with post author
            # For simplicity now, we assume the signature check implies authorization

            author = get_user_by_puid(post_to_update['author']['puid']) # Get local author ID
            if not author:
                 return jsonify({'error': 'Author not found for post update.'}), 404


            # Create notifications for newly mentioned local users
            mentioned_puids = data.get('mentioned_puids', [])
            for puid in mentioned_puids:
                mentioned_user = get_user_by_puid(puid)
                if mentioned_user and mentioned_user['hostname'] is None:
                     # Check if they were mentioned *before* this update to avoid duplicate notifications?
                     # For now, create notification regardless.
                     create_notification(mentioned_user['id'], author['id'], 'mention', post_to_update['id'], group_id=post_to_update.get('group_id'))

            update_post(
                cuid=data['cuid'],
                content=data['content'],
                privacy_setting=data['privacy_setting'],
                media_files=data.get('media_files', []),
                tagged_user_puids=data.get('tagged_user_puids'),  # NEW: Include tags
                location=data.get('location')  # NEW: Include location
            )
            return jsonify({'message': 'Post updated successfully.'}), 200

        elif action_type == 'post_delete':
            # ... (post delete logic as before) ...
            if 'cuid' not in data:
                 return jsonify({'error': 'Missing "cuid" for post_delete action.'}), 400

            post_to_delete = get_post_by_cuid(data['cuid'])
            if not post_to_delete:
                 return jsonify({'message': 'Post not found, assumed already deleted.'}), 200

            # Authorization check (similar to update) - omitted for brevity

            delete_post(data['cuid'])
            return jsonify({'message': 'Post deleted successfully.'}), 200


        # --- Comment Actions ---
        elif action_type == 'comment_create':
            # ... (comment creation logic as before) ...
            if 'author_data' not in data and 'author_puid' not in data:
                 return jsonify({'error': 'Missing author_data or author_puid for comment_create action.'}), 400

            required_fields = ['cuid', 'post_cuid', 'timestamp', 'nu_id']
            # Content or media required
            if 'content' not in data and 'media_files' not in data:
                 required_fields.append('content') # Force content requirement

            if not all(field in data for field in required_fields):
                missing = [f for f in required_fields if f not in data]
                return jsonify({'error': f"Missing one or more required fields for comment_create action: {', '.join(missing)}"}), 400

            # Avoid duplicates
            if get_comment_by_cuid(data['cuid']):
                return jsonify({'message': 'Comment already exists.'}), 200

            post = get_post_by_cuid(data['post_cuid'])
            if not post:
                return jsonify({'error': 'Parent post not found on this node.'}), 404

            # Get/Create author stub
            author = None
            if 'author_data' in data:
                author_data = data['author_data']
                author = get_or_create_remote_user(
                    puid=author_data.get('puid'),
                    display_name=author_data.get('display_name'),
                    hostname=author_data.get('hostname'),
                    profile_picture_path=author_data.get('profile_picture_path')
                )
                if author: # Update details just in case
                     update_remote_user_details(puid=author_data.get('puid'), display_name=author_data.get('display_name'), profile_picture_path=author_data.get('profile_picture_path'))
            elif 'author_puid' in data: # Fallback if only PUID sent
                 author = get_user_by_puid(data['author_puid'])

            if not author:
                return jsonify({'error': 'Could not find or process remote author.'}), 500

            # Find parent comment locally if it's a reply
            parent_comment_id = None
            if data.get('parent_cuid'):
                parent_comment_info = get_comment_by_cuid(data['parent_cuid'])
                if parent_comment_info:
                    parent_comment_id = parent_comment_info['comment_id']

            # Add the comment locally
            new_comment_cuid = add_comment(
                post_cuid=data['post_cuid'],
                user_id=author['id'],
                content=data.get('content'),
                post_owner_id=post.get('profile_user_id'),
                parent_comment_id=parent_comment_id,
                media_files=data.get('media_files', []),
                nu_id=data['nu_id'],
                cuid=data['cuid'],
                timestamp=data.get('timestamp'),
                is_remote=True # Mark as remote to prevent re-notification loops
            )

            # Re-distribute if the *post* originated locally (needed for replies/mentions)
            if new_comment_cuid and not post.get('is_remote'):
                 distribute_comment(new_comment_cuid)


            return jsonify({'message': 'Comment created successfully.'}), 201

        elif action_type == 'comment_update':
            # ... (comment update logic as before) ...
            required_fields = ['cuid', 'content'] # Media is optional for update
            if not all(field in data for field in required_fields):
                 missing = [f for f in required_fields if f not in data]
                 return jsonify({'error': f"Missing one or more required fields for comment_update action: {', '.join(missing)}"}), 400

            comment_to_update = get_comment_by_cuid(data['cuid'])
            if not comment_to_update:
                return jsonify({'error': 'Comment to update not found.'}), 404

            # Authorization check omitted for brevity

            update_comment(
                data['cuid'],
                data['content'],
                data.get('media_files') # Pass media if provided
            )
            return jsonify({'message': 'Comment updated successfully.'}), 200


        elif action_type == 'comment_delete':
            # ... (comment delete logic as before) ...
            if 'cuid' not in data:
                 return jsonify({'error': 'Missing "cuid" for comment_delete action.'}), 400

            comment_to_delete = get_comment_by_cuid(data['cuid'])
            if not comment_to_delete:
                 return jsonify({'message': 'Comment not found, assumed already deleted.'}), 200

            # Auth check omitted

            delete_comment(data['cuid'])
            return jsonify({'message': 'Comment deleted successfully.'}), 200

        # --- NEW: Handle Comment Status Update ---
        elif action_type == 'post_comment_status_update':
            required_fields = ['cuid', 'comments_disabled', 'actor_data']
            if not all(field in data for field in required_fields):
                missing = [f for f in required_fields if f not in data]
                return jsonify({'error': f"Missing one or more required fields for post_comment_status_update action: {', '.join(missing)}"}), 400

            post_to_update = get_post_by_cuid(data['cuid'])
            if not post_to_update:
                return jsonify({'error': 'Post to update not found.'}), 404
            
            # We trust the federated node (via signature) that the actor was authorized
            
            if data['comments_disabled']:
                if disable_comments_for_post(data['cuid']):
                    print(f"INFO: Comments disabled for remote post {data['cuid']} via federation.")
                    return jsonify({'message': 'Post comment status updated.'}), 200
                else:
                    return jsonify({'error': 'Failed to update post comment status locally.'}), 500
            else:
                # As per user request, we only disable, never re-enable.
                return jsonify({'message': 'Post comment status update (enable) ignored.'}), 200

        # --- Media Comment Actions ---
        elif action_type == 'media_comment_create':
            # Handle federated media comment creation
            if 'author_data' not in data:
                return jsonify({'error': 'Missing author_data for media_comment_create action.'}), 400

            required_fields = ['cuid', 'muid', 'timestamp', 'nu_id']
            # Content or media required
            if 'content' not in data and 'media_files' not in data:
                required_fields.append('content')

            if not all(field in data for field in required_fields):
                missing = [f for f in required_fields if f not in data]
                return jsonify({'error': f"Missing one or more required fields for media_comment_create action: {', '.join(missing)}"}), 400

            # Avoid duplicates
            from db_queries.media import get_media_comment_by_cuid
            if get_media_comment_by_cuid(data['cuid']):
                return jsonify({'message': 'Media comment already exists.'}), 200

            # Verify media exists locally
            from db_queries.media import get_media_by_muid
            media = get_media_by_muid(data['muid'])
            if not media:
                return jsonify({'error': 'Media item not found on this node.'}), 404

            # Get/Create author stub
            author_data = data['author_data']
            author = get_or_create_remote_user(
                puid=author_data.get('puid'),
                display_name=author_data.get('display_name'),
                hostname=author_data.get('hostname'),
                profile_picture_path=author_data.get('profile_picture_path')
            )
            if author:
                update_remote_user_details(
                    puid=author_data.get('puid'),
                    display_name=author_data.get('display_name'),
                    profile_picture_path=author_data.get('profile_picture_path')
                )

            if not author:
                return jsonify({'error': 'Could not find or process remote author.'}), 500

            # Find parent comment locally if it's a reply
            parent_comment_id = None
            if data.get('parent_cuid'):
                parent_comment_info = get_media_comment_by_cuid(data['parent_cuid'])
                if parent_comment_info:
                    parent_comment_id = parent_comment_info['comment_id']

            # Add the media comment locally
            from db_queries.media import add_media_comment
            new_comment_cuid = add_media_comment(
                muid=data['muid'],
                user_id=author['id'],
                content=data.get('content'),
                parent_comment_id=parent_comment_id,
                media_files=data.get('media_files', []),
                nu_id=data['nu_id'],
                cuid=data['cuid'],
                timestamp=data.get('timestamp'),
                is_remote=True  # Mark as remote to prevent re-notification loops
            )

            # Re-distribute if the media originated locally (needed for replies/mentions)
            if new_comment_cuid:
                # Check if media is local
                if media.get('origin_hostname') is None or media.get('origin_hostname') == current_app.config.get('NODE_HOSTNAME'):
                    from utils.federation_utils import distribute_media_comment
                    distribute_media_comment(new_comment_cuid)

            return jsonify({'message': 'Media comment created successfully.'}), 201

        elif action_type == 'media_comment_update':
            # Handle federated media comment updates
            required_fields = ['cuid', 'muid', 'content']
            if not all(field in data for field in required_fields):
                missing = [f for f in required_fields if f not in data]
                return jsonify({'error': f"Missing one or more required fields for media_comment_update action: {', '.join(missing)}"}), 400

            from db_queries.media import get_media_comment_by_cuid, update_media_comment
            comment_info = get_media_comment_by_cuid(data['cuid'])
            if not comment_info:
                return jsonify({'error': 'Media comment not found on this node.'}), 404

            # Update the comment
            success = update_media_comment(
                cuid=data['cuid'],
                new_content=data['content'],
                media_files=data.get('media_files', [])
            )

            if success:
                # Re-distribute update if media is local
                from db_queries.media import get_media_by_muid
                media = get_media_by_muid(data['muid'])
                if media and (media.get('origin_hostname') is None or media.get('origin_hostname') == current_app.config.get('NODE_HOSTNAME')):
                    from utils.federation_utils import distribute_media_comment_update
                    distribute_media_comment_update(data['cuid'])

                return jsonify({'message': 'Media comment updated successfully.'}), 200
            else:
                return jsonify({'error': 'Failed to update media comment.'}), 500

        elif action_type == 'media_comment_delete':
            # Handle federated media comment deletion
            required_fields = ['cuid', 'muid']
            if not all(field in data for field in required_fields):
                missing = [f for f in required_fields if f not in data]
                return jsonify({'error': f"Missing one or more required fields for media_comment_delete action: {', '.join(missing)}"}), 400

            from db_queries.media import get_media_comment_by_cuid, delete_media_comment
            comment_info = get_media_comment_by_cuid(data['cuid'])
            if not comment_info:
                return jsonify({'message': 'Media comment not found (may already be deleted).'}), 200

            # Delete the comment
            success = delete_media_comment(data['cuid'])

            if success:
                return jsonify({'message': 'Media comment deleted successfully.'}), 200
            else:
                return jsonify({'error': 'Failed to delete media comment.'}), 500

        elif action_type == 'mention_removal_media_comment':
            print("Processing federated action: mention_removal_media_comment")
            
            media_comment_cuid = data.get('media_comment_cuid')
            removed_mention = data.get('removed_mention')
            actor_puid = data.get('actor_puid')
            updated_content = data.get('updated_content')
            
            if not all([media_comment_cuid, removed_mention, actor_puid]):
                return jsonify({'error': 'Missing required fields for mention_removal_media_comment'}), 400
            
            from db_queries.media import get_media_comment_by_cuid
            comment = get_media_comment_by_cuid(media_comment_cuid)
            if not comment:
                return jsonify({'error': 'Media comment not found'}), 404
            
            # Update the media comment content directly with the new content
            db = get_db()
            cursor = db.cursor()
            cursor.execute("""
                UPDATE media_comments SET content = ?
                WHERE cuid = ?
            """, (updated_content, media_comment_cuid))
            db.commit()
            
            print(f"federation_inbox: Processed mention_removal_media_comment for @{removed_mention} from media comment {media_comment_cuid}")
            return jsonify({'message': 'Mention removed successfully'}), 200

        # --- NEW: HANDLE PROFILE UPDATE ---
        elif action_type == 'profile_update':
            print("Processing federated action: profile_update")
            
            # 1. Validate payload
            puid = data.get('puid')
            display_name = data.get('display_name')
            profile_picture_path = data.get('profile_picture_path')
            user_hostname = data.get('hostname') # The user's home node

            if not all([puid, display_name, user_hostname]):
                 missing = [f for f in ['puid', 'display_name', 'hostname'] if not data.get(f)]
                 return jsonify({'error': f"Missing one or more required fields for profile_update action: {', '.join(missing)}"}), 400

            # 2. Get or create a stub for this remote user.
            # We must ensure the stub exists to update it.
            remote_user_stub = get_or_create_remote_user(
                puid=puid,
                display_name=display_name,
                hostname=user_hostname,
                profile_picture_path=profile_picture_path
            )

            if not remote_user_stub:
                return jsonify({'error': f'Failed to get or create remote user stub for PUID {puid}.'}), 500

            # 3. Update the details
            if update_remote_user_details(puid, display_name, profile_picture_path):
                print(f"Successfully updated profile for remote user {puid} from {user_hostname}.")
                return jsonify({'message': 'Profile update received and processed.'}), 200
            else:
                print(f"Failed to update profile for remote user {puid}. update_remote_user_details returned False.")
                return jsonify({'error': 'Failed to update remote user profile locally.'}), 500
        # --- END NEW BLOCK ---

        # --- NEW: Privacy Action Handlers ---
        
        elif action_type == 'tag_removal':
            print("Processing federated action: tag_removal")
            
            post_cuid = data.get('post_cuid')
            removed_user_puid = data.get('removed_user_puid')
            actor_puid = data.get('actor_puid')
            
            if not all([post_cuid, removed_user_puid, actor_puid]):
                return jsonify({'error': 'Missing required fields for tag_removal'}), 400
            
            post = get_post_by_cuid(post_cuid)
            if not post:
                return jsonify({'error': 'Post not found'}), 404
            
            # Update the post to remove the tag
            from db_queries.posts import remove_user_tag_from_post
            if remove_user_tag_from_post(post_cuid, removed_user_puid):
                print(f"federation_inbox: Processed tag_removal for user {removed_user_puid} from post {post_cuid}")
                return jsonify({'message': 'Tag removed successfully'}), 200
            else:
                return jsonify({'error': 'Failed to remove tag'}), 500
        
        elif action_type == 'mention_removal_post':
            print("Processing federated action: mention_removal_post")
            
            post_cuid = data.get('post_cuid')
            removed_mention = data.get('removed_mention')
            actor_puid = data.get('actor_puid')
            updated_content = data.get('updated_content')
            
            if not all([post_cuid, removed_mention, actor_puid]):
                return jsonify({'error': 'Missing required fields for mention_removal_post'}), 400
            
            post = get_post_by_cuid(post_cuid)
            if not post:
                return jsonify({'error': 'Post not found'}), 404
            
            # Update the post content directly with the new content
            db = get_db()
            cursor = db.cursor()
            cursor.execute("UPDATE posts SET content = ? WHERE cuid = ?", (updated_content, post_cuid))
            db.commit()
            
            print(f"federation_inbox: Processed mention_removal_post for @{removed_mention} from post {post_cuid}")
            return jsonify({'message': 'Mention removed successfully'}), 200
        
        elif action_type == 'mention_removal_comment':
            print("Processing federated action: mention_removal_comment")
            
            comment_cuid = data.get('comment_cuid')
            removed_mention = data.get('removed_mention')
            actor_puid = data.get('actor_puid')
            updated_content = data.get('updated_content')
            
            if not all([comment_cuid, removed_mention, actor_puid]):
                return jsonify({'error': 'Missing required fields for mention_removal_comment'}), 400
            
            comment_info = get_comment_by_cuid(comment_cuid)
            if not comment_info:
                return jsonify({'error': 'Comment not found'}), 404
            
            # Update the comment content directly with the new content
            db = get_db()
            cursor = db.cursor()
            cursor.execute("UPDATE comments SET content = ? WHERE cuid = ?", (updated_content, comment_cuid))
            db.commit()
            
            print(f"federation_inbox: Processed mention_removal_comment for @{removed_mention} from comment {comment_cuid}")
            return jsonify({'message': 'Mention removed successfully'}), 200
        
        elif action_type == 'media_tags_update':
            print("Processing federated action: media_tags_update")
            
            muid = data.get('muid')
            tagged_user_puids = data.get('tagged_user_puids', [])
            actor_puid = data.get('actor_puid')
            
            if not all([muid, actor_puid is not None]):
                return jsonify({'error': 'Missing required fields for media_tags_update'}), 400
            
            from db_queries.media import get_media_by_muid
            media = get_media_by_muid(muid)
            if not media:
                return jsonify({'error': 'Media not found'}), 404
            
            # Update the media tags
            db = get_db()
            cursor = db.cursor()
            
            tagged_json = json.dumps(tagged_user_puids) if tagged_user_puids else None
            cursor.execute("""
                UPDATE post_media 
                SET tagged_user_puids = ? 
                WHERE muid = ?
            """, (tagged_json, muid))
            db.commit()
            
            print(f"federation_inbox: Updated tags for media {muid}")
            return jsonify({'message': 'Media tags updated successfully'}), 200
        
        elif action_type == 'media_tag_removal':
            print("Processing federated action: media_tag_removal")
            
            muid = data.get('muid')
            removed_user_puid = data.get('removed_user_puid')
            
            if not all([muid, removed_user_puid]):
                return jsonify({'error': 'Missing required fields for media_tag_removal'}), 400
            
            from db_queries.media import get_media_by_muid
            media = get_media_by_muid(muid)
            if not media:
                return jsonify({'error': 'Media not found'}), 404
            
            # Remove the tag
            db = get_db()
            cursor = db.cursor()
            
            cursor.execute("SELECT tagged_user_puids FROM post_media WHERE muid = ?", (muid,))
            result = cursor.fetchone()
            
            if result and result['tagged_user_puids']:
                try:
                    tagged_puids = json.loads(result['tagged_user_puids'])
                    if removed_user_puid in tagged_puids:
                        tagged_puids.remove(removed_user_puid)
                        new_tagged_json = json.dumps(tagged_puids) if tagged_puids else None
                        cursor.execute("UPDATE post_media SET tagged_user_puids = ? WHERE muid = ?", 
                                     (new_tagged_json, muid))
                        db.commit()
                except (json.JSONDecodeError, TypeError):
                    pass
            
            print(f"federation_inbox: Removed tag for user {removed_user_puid} from media {muid}")
            return jsonify({'message': 'Media tag removed successfully'}), 200
        
        # --- END Privacy Action Handlers ---

        # --- Poll Actions ---
        elif action_type == 'poll_create':
            # Create poll for a federated post
            print(f"🔔 federation_inbox: Received poll_create action for post {data.get('post_cuid')}")
            print(f"🔔 Poll data received: {data.get('poll')}")
            
            if 'post_cuid' not in data or 'poll' not in data:
                print(f"❌ federation_inbox: Missing required fields for poll_create")
                return jsonify({'error': 'Missing required fields for poll_create'}), 400
            
            from db_queries.polls import create_poll
            
            post = get_post_by_cuid(data['post_cuid'])
            if not post:
                print(f"❌ federation_inbox: Post {data['post_cuid']} not found for poll creation")
                return jsonify({'error': 'Post not found'}), 404
            
            print(f"✅ federation_inbox: Post found with ID {post['id']}")
            
            poll_data = data['poll']
            options = [opt['option_text'] for opt in poll_data.get('options', [])]
            
            print(f"🔔 federation_inbox: Creating poll with {len(options)} options")
            
            if len(options) >= 2:
                poll_id = create_poll(
                    post_id=post['id'],
                    options=options,
                    allow_multiple_answers=poll_data.get('allow_multiple_answers', False),
                    allow_add_options=poll_data.get('allow_add_options', False)
                )
                if poll_id:
                    print(f"✅ federation_inbox: Poll created successfully with ID {poll_id}")
                else:
                    print(f"❌ federation_inbox: create_poll returned None - poll creation failed")
                    return jsonify({'error': 'Failed to create poll in database'}), 500
            else:
                print(f"❌ federation_inbox: Not enough options ({len(options)}) to create poll")
            
            return jsonify({'message': 'Poll created successfully'}), 200
        
        elif action_type == 'poll_vote':
            # Record a vote on a poll from a remote user
            if 'post_cuid' not in data or 'option_text' not in data or 'voter_puid' not in data:
                return jsonify({'error': 'Missing required fields for poll_vote'}), 400
            
            from db_queries.polls import get_poll_by_post_id, vote_on_poll, get_poll_option_by_text

            
            post = get_post_by_cuid(data['post_cuid'])
            if not post:
                return jsonify({'error': 'Post not found'}), 404
            
            voter = get_user_by_puid(data['voter_puid'])
            if not voter:
                # Try to get or create remote user stub
                voter = get_or_create_remote_user(
                    puid=data['voter_puid'],
                    display_name=data.get('voter_display_name', 'Unknown'),
                    hostname=remote_hostname
                )
            
            if not voter:
                return jsonify({'error': 'Voter not found'}), 404
            
            poll = get_poll_by_post_id(post['id'])
            if not poll:
                return jsonify({'error': 'Poll not found'}), 404
            
            # Find option by text (since IDs differ across nodes)
            option = get_poll_option_by_text(poll['id'], data['option_text'])
            if not option:
                return jsonify({'error': 'Poll option not found'}), 404
            
            vote_on_poll(option['id'], voter['id'])
            return jsonify({'message': 'Vote recorded'}), 200
        
        elif action_type == 'poll_unvote':
            # Remove a vote from a remote user
            if 'post_cuid' not in data or 'option_text' not in data or 'voter_puid' not in data:
                return jsonify({'error': 'Missing required fields for poll_unvote'}), 400
            
            from db_queries.polls import get_poll_by_post_id, remove_vote_from_poll, get_poll_option_by_text

            
            post = get_post_by_cuid(data['post_cuid'])
            if not post:
                return jsonify({'error': 'Post not found'}), 404
            
            voter = get_user_by_puid(data['voter_puid'])
            if not voter:
                return jsonify({'error': 'Voter not found'}), 404
            
            poll = get_poll_by_post_id(post['id'])
            if not poll:
                return jsonify({'error': 'Poll not found'}), 404
            
            option = get_poll_option_by_text(poll['id'], data['option_text'])
            if not option:
                return jsonify({'error': 'Poll option not found'}), 404
            
            remove_vote_from_poll(option['id'], voter['id'])
            return jsonify({'message': 'Vote removed'}), 200
        
        elif action_type == 'poll_option_add':
            # Add a user-contributed option from remote node
            if 'post_cuid' not in data or 'option_text' not in data or 'creator_puid' not in data:
                return jsonify({'error': 'Missing required fields for poll_option_add'}), 400
            
            from db_queries.polls import get_poll_by_post_id, add_poll_option, get_poll_option_by_text

            
            post = get_post_by_cuid(data['post_cuid'])
            if not post:
                return jsonify({'error': 'Post not found'}), 404
            
            poll = get_poll_by_post_id(post['id'])
            if not poll or not poll['allow_add_options']:
                return jsonify({'error': 'Adding options not allowed'}), 403
            
            # Check if option already exists (prevent duplicates)
            existing_option = get_poll_option_by_text(poll['id'], data['option_text'])
            if existing_option:
                return jsonify({'message': 'Option already exists'}), 200
            
            # Get or create remote user
            creator = get_user_by_puid(data['creator_puid'])
            if not creator:
                creator = get_or_create_remote_user(
                    puid=data['creator_puid'],
                    display_name=data.get('creator_display_name', 'Unknown'),
                    hostname=remote_hostname
                )
            
            if not creator:
                return jsonify({'error': 'Creator not found'}), 404
            
            add_poll_option(poll['id'], data['option_text'], creator['id'])
            return jsonify({'message': 'Option added'}), 200
        
        elif action_type == 'poll_option_delete':
            # Delete a user-added option from remote node
            if 'post_cuid' not in data or 'option_text' not in data:
                return jsonify({'error': 'Missing required fields for poll_option_delete'}), 400
            
            from db_queries.polls import get_poll_by_post_id, get_poll_option_by_text
            
            post = get_post_by_cuid(data['post_cuid'])
            if not post:
                return jsonify({'error': 'Post not found'}), 404
            
            poll = get_poll_by_post_id(post['id'])
            if not poll:
                return jsonify({'error': 'Poll not found'}), 404
            
            option = get_poll_option_by_text(poll['id'], data['option_text'])
            if not option:
                return jsonify({'message': 'Option already deleted'}), 200
            
            # Delete the option
            db = get_db()
            cursor = db.cursor()
            cursor.execute("DELETE FROM poll_options WHERE id = ?", (option['id'],))
            db.commit()
            
            return jsonify({'message': 'Option deleted'}), 200

        else:
            return jsonify({'error': f'Unsupported action type: {action_type}'}), 400

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'An internal error occurred: {str(e)}'}), 500

@federation_bp.route('/federation/api/v1/receive_notification', methods=['POST'])
@signature_required
def receive_notification():
    """Receives a generic notification from a federated node (supports both posts and media)."""
    try:
        data = request.get_json()
        if not data:
            raise ValueError("Request body must be valid JSON.")

        notified_puid = data.get('notified_puid')
        actor_data = data.get('actor')
        type = data.get('type')
        post_cuid = data.get('post_cuid')
        comment_cuid = data.get('comment_cuid')
        group_puid = data.get('group_puid')
        event_puid = data.get('event_puid')
        muid = data.get('muid')  # NEW: For media notifications
        media_comment_cuid = data.get('media_comment_cuid')  # NEW: For media comment notifications

        # Convert PUIDs to local IDs
        group_id = None
        if group_puid:
            group = get_group_by_puid(group_puid)
            if group:
                group_id = group['id']

        event_id = None
        if event_puid:
            from db_queries.events import get_event_by_puid
            event = get_event_by_puid(event_puid)
            if event:
                event_id = event['id']

        # Validate required fields - either post_cuid OR muid must be present
        if not notified_puid or not actor_data or not type:
            raise ValueError("Missing required fields in payload (notified_puid, actor, type).")
        
        if not post_cuid and not muid:
            raise ValueError("Either post_cuid or muid must be provided.")

        notified_user = get_user_by_puid(notified_puid)
        if not notified_user or notified_user['hostname'] is not None:
            return jsonify({'error': 'Notified user is not a valid local user.'}), 404

        actor = get_or_create_remote_user(
            puid=actor_data['puid'],
            display_name=actor_data['display_name'],
            hostname=actor_data['hostname'],
            profile_picture_path=actor_data.get('profile_picture_path')
        )
        if not actor:
            return jsonify({'error': 'Could not process remote actor.'}), 500

        # Handle post-based notifications
        post_id = None
        if post_cuid:
            post = get_post_by_cuid(post_cuid)
            if not post:
                # Post might not have arrived yet. Acknowledge.
                print(f"WARN: Notification received for unknown post {post_cuid}. Skipping.")
                return jsonify({'message': 'Notification acknowledged, post not found locally yet.'}), 200
            post_id = post['id']

        comment_id = None
        if comment_cuid:
            comment_info = get_comment_by_cuid(comment_cuid)
            if comment_info:
                comment_id = comment_info['comment_id']

        # Handle media-based notifications
        media_id = None
        media_comment_id = None
        
        if muid:
            from db_queries.media import get_media_by_muid
            media = get_media_by_muid(muid)
            if not media:
                print(f"WARN: Notification received for unknown media {muid}. Skipping.")
                return jsonify({'message': 'Notification acknowledged, media not found locally yet.'}), 200
            media_id = media['id']
        
        if media_comment_cuid:
            from db_queries.media import get_media_comment_by_cuid
            media_comment = get_media_comment_by_cuid(media_comment_cuid)
            if media_comment:
                media_comment_id = media_comment['comment_id']

        create_notification(
            user_id=notified_user['id'],
            actor_id=actor['id'],
            type=type,
            post_id=post_id,
            comment_id=comment_id,
            group_id=group_id,
            event_id=event_id,
            media_id=media_id,  # NEW: Support for media notifications
            media_comment_id=media_comment_id  # NEW: Support for media comment notifications
        )

        return jsonify({'message': 'Notification received and processed.'}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'An internal error occurred: {str(e)}'}), 500


@federation_bp.route('/create_remote_post', methods=['POST'])
def create_remote_post():
    """
    Allows a federated user to create a post on a local user's timeline.
    """
    if not session.get('is_federated_viewer'):
        flash('Your secure session has expired. Please go back to your own feed and navigate to this profile again.', 'danger')
        return redirect(request.referrer or '/')

    viewer_puid = session.get('federated_viewer_puid')
    author = get_user_by_puid(viewer_puid)
    if not author:
        flash('Could not identify you as an authenticated remote user.', 'danger')
        return redirect(request.referrer or '/')

    profile_puid = request.form.get('profile_puid')
    profile_user = get_user_by_puid(profile_puid)
    if not profile_user or profile_user['hostname'] is not None:
        flash('The profile you are trying to post on is not a valid local user.', 'danger')
        return redirect(request.referrer or '/')

    if not is_friends_with(author['id'], profile_user['id']):
        flash('You can only post on the timeline of your friends.', 'danger')
        return redirect(url_for('main.user_profile', puid=profile_puid))

    content = request.form['content']
    selected_media_files_json = request.form.get('selected_media_files', '[]')
    media_files_for_db = json.loads(selected_media_files_json)
    privacy_setting = request.form.get('privacy_setting', 'friends')
    
    # PARENTAL CONTROL CHECK: Prevent children from making public posts
    from db_queries.parental_controls import requires_parental_approval
    
    if requires_parental_approval(author['id']) and privacy_setting == 'public':
        flash('You cannot create public posts while parental controls are active.', 'warning')
        return redirect(request.referrer or '/')

    # NEW: Get tagged users and location
    tagged_user_puids_json = request.form.get('tagged_users', '[]')
    tagged_user_puids = json.loads(tagged_user_puids_json) if tagged_user_puids_json else []
    location = request.form.get('location', '').strip() or None

    if privacy_setting == 'local':
        flash('You cannot create a "Local Only" post on a remote profile.', 'warning')
        return redirect(url_for('main.user_profile', puid=profile_puid))
    
    # NEW: Get poll data if provided
    poll_data_json = request.form.get('poll_data', '')
    poll_data = None
    if poll_data_json:
        try:
            poll_data = json.loads(poll_data_json)
            if poll_data and not content.strip():
                flash("You can't create a poll without text in your post.", 'warning')
                return redirect(url_for('main.user_profile', puid=profile_puid))
        except json.JSONDecodeError:
            poll_data = None

    post_cuid = add_post(
        user_id=author['id'],
        profile_user_id=profile_user['id'],
        content=content,
        privacy_setting=privacy_setting,
        media_files=media_files_for_db,
        author_hostname=author['hostname'],
        tagged_user_puids=tagged_user_puids,  # NEW
        location=location,
        poll_data=poll_data  # NEW
    )

    if post_cuid:
        from utils.federation_utils import distribute_post
        distribute_post(post_cuid)
        if poll_data:
            from utils.federation_utils import distribute_poll_data
            time.sleep(0.5)
            distribute_poll_data(post_cuid)
        flash('Post created successfully!', 'success')
    else:
        flash('Failed to create post.', 'danger')

    return redirect(url_for('main.user_profile', puid=profile_puid))

@federation_bp.route('/federation/api/v1/create_parental_approval', methods=['POST'])
@signature_required
def create_parental_approval():
    """
    Receives a request from a remote node to create a parental approval request
    for a local user who attempted an action while visiting that node.
    """
    from db_queries.parental_controls import requires_parental_approval, create_approval_request, get_all_parent_ids
    from db_queries.notifications import create_notification
    from db_queries.users import get_user_by_puid
    
    try:
        data = request.get_json(force=True)
        user_puid = data.get('user_puid')
        approval_type = data.get('approval_type')
        target_puid = data.get('target_puid')
        target_hostname = data.get('target_hostname')
        request_data_dict = data.get('request_data', {})
        
        if not all([user_puid, approval_type, target_puid, target_hostname]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Find the local user
        user = get_user_by_puid(user_puid)
        if not user or user.get('hostname') is not None:
            return jsonify({'error': 'User is not a local user on this node'}), 404
        
        # Verify they actually require parental approval
        if not requires_parental_approval(user['id']):
            return jsonify({'error': 'User does not require parental approval'}), 400
        
        # Create the approval request
        import json as json_module
        request_data = json_module.dumps(request_data_dict)
        
        approval_id = create_approval_request(
            user['id'],
            approval_type,
            target_puid,
            target_hostname,
            request_data
        )
        
        if approval_id:
            # Notify all parents
            parent_ids = get_all_parent_ids(user['id'])
            for parent_id in parent_ids:
                create_notification(parent_id, user['id'], 'parental_approval_needed')
            
            return jsonify({'message': 'Approval request created successfully'}), 200
        else:
            return jsonify({'error': 'Failed to create approval request'}), 500
            
    except Exception as e:
        print(f"ERROR in create_parental_approval: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'An internal error occurred: {str(e)}'}), 500