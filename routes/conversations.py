# routes/conversations.py
# Contains routes for managing direct messaging conversations.

from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
import os
import base64
import traceback

from db_queries.users import get_user_by_username, get_user_by_puid, get_user_by_id
from db_queries.settings import get_user_settings
from db_queries.conversations import (
    get_or_create_conversation_between_users,
    get_conversation_by_conv_uid,
    get_conversation_by_id,
    get_conversations_for_user,
    get_messages_for_conversation,
    send_message,
    edit_message,
    delete_message,
    is_user_in_conversation,
    mark_conversation_as_read,
    archive_conversation_for_user,
    unarchive_conversation_for_user,
    add_media_to_message,
    get_pending_message_requests_for_user,
    accept_message_request,
    decline_message_request,
    create_message_request,
    can_user_message,
    conversation_requires_request,
    block_user_from_dms,
    unblock_user_from_dms,
    is_user_blocked_from_dms,
    get_blocked_users_for_dms,
    get_conversation_participants,
    get_unread_message_count_for_user,
    get_unread_conversation_count_for_user,
    invite_participant,
    remove_participant,
    leave_conversation,
    hide_conversation_for_user,
    update_conversation_picture,
    get_request_status_for_conversation,
    get_message_by_msg_uid
)
from utils.federation_utils import (
    distribute_dm_conversation,
    distribute_dm_message,
    distribute_dm_edit,
    distribute_dm_delete,
    distribute_dm_participant_update
)

conversations_bp = Blueprint('conversations', __name__)

# =============================================================================
# AUTHENTICATION HELPER
# =============================================================================

def get_current_user():
    """
    Gets the current authenticated user.
    Supports both regular users and federated viewers.
    
    Returns:
        dict: User data or None if not authenticated
    """
    if session.get('is_federated_viewer'):
        return get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        return get_user_by_username(session['username'])
    return None


# =============================================================================
# MAIN MESSAGING PAGE
# =============================================================================

@conversations_bp.route('/messages/')
def messages_page():
    """
    Main messages page - serves the SPA shell with messages content loaded.
    Handles direct navigation and refresh.
    """
    current_user = get_current_user()
    if not current_user:
        flash('Please log in to access messages.', 'danger')
        return redirect(url_for('auth.login'))

    from flask import current_app
    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'
    viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"

    initial_content_url = url_for('conversations.messages_page_api')
    user_settings = get_user_settings(current_user['id'])

    return render_template('index.html',
                           username=current_user.get('username'),
                           user_media_path=current_user.get('media_path'),
                           current_user_puid=current_user.get('puid'),
                           current_user_id=current_user['id'],
                           current_user_profile=current_user,
                           viewer_home_url=viewer_home_url,
                           viewer_puid_for_js=current_user.get('puid'),
                           initial_content_url=initial_content_url,
                           user_settings=user_settings)


@conversations_bp.route('/messages/<conv_uid>')
def conversation_page(conv_uid):
    current_user = get_current_user()
    if not current_user:
        flash('Please log in to access messages.', 'danger')
        return redirect(url_for('auth.login'))

    conversation = get_conversation_by_conv_uid(conv_uid)
    if not conversation:
        flash('Conversation not found.', 'danger')
        return redirect(url_for('conversations.messages_page'))

    if not is_user_in_conversation(current_user['id'], conversation['id']):
        flash('You do not have access to this conversation.', 'danger')
        return redirect(url_for('conversations.messages_page'))

    messages = get_messages_for_conversation(conversation['id'])
    participants = get_conversation_participants(conversation['id'])
    mark_conversation_as_read(conversation['id'], current_user['id'])

    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'
    viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"
    user_settings = get_user_settings(current_user['id'])

    from db_queries.notifications import get_unread_notification_count
    unread_notification_count = get_unread_notification_count(current_user['id'])
    unread_messages_count = get_unread_conversation_count_for_user(current_user['id'])
    is_creator = (conversation['created_by_user_id'] == current_user['id'])
    blocked_users = get_blocked_users_for_dms(current_user['id'])
    blocked_puids = {u['puid'] for u in blocked_users}

    # For 1:1 conversations, expose the other participant's puid and block state
    other_participants = [p for p in participants if p['user_id'] != current_user['id']]
    one_to_one_other_puid = other_participants[0]['puid'] if len(other_participants) == 1 else None
    one_to_one_is_blocked = one_to_one_other_puid in blocked_puids if one_to_one_other_puid else False

    return render_template('conversation.html',
                           conversation=conversation,
                           messages=messages,
                           participants=participants,
                           blocked_puids=blocked_puids,
                           one_to_one_other_puid=one_to_one_other_puid,
                           one_to_one_is_blocked=one_to_one_is_blocked,
                           current_user=current_user,
                           # Variables index.html needs:
                           username=current_user.get('username'),
                           user_media_path=current_user.get('media_path'),
                           current_user_puid=current_user.get('puid'),
                           current_user_id=current_user['id'],
                           current_user_profile=current_user,
                           viewer_home_url=viewer_home_url,
                           viewer_puid=current_user.get('puid'),        # ← ADD THIS
                           current_viewer_data=current_user,
                           viewer_puid_for_js=current_user.get('puid'),
                           user_settings=user_settings,
                           is_single_post_view=True,  # Disables SPA router
                           viewer_token=None,
                           is_federated_viewer=False,
                           initial_content_url=None,
                           unread_notification_count=unread_notification_count,
                           unread_messages_count=unread_messages_count,
                           is_creator=is_creator,
                           current_user_requires_parental_approval=False)

@conversations_bp.route('/api/page/messages')
def messages_page_api():
    """
    API endpoint to get messages page content for SPA router.
    Returns HTML partial (not full page).
    """
    current_user = get_current_user()
    if not current_user:
        return '<p class="text-center p-8 text-red-500">Please log in to access messages.</p>', 401
    
    # Get user's conversations
    conversations = get_conversations_for_user(current_user['id'])
    
    # Get pending message requests
    pending_requests = get_pending_message_requests_for_user(current_user['id'])
    
    return render_template('_messages_content.html',
                         conversations=conversations,
                         pending_requests=pending_requests,
                         current_user=current_user)

# =============================================================================
# API: CONVERSATION LIST
# =============================================================================

@conversations_bp.route('/api/conversations', methods=['GET'])
def get_conversations_api():
    """
    API endpoint to get user's conversations.
    
    Query params:
        include_archived: Include archived conversations (default: false)
    
    Returns:
        JSON: List of conversations with metadata
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    include_archived = request.args.get('include_archived', 'false').lower() == 'true'
    
    conversations = get_conversations_for_user(current_user['id'], include_archived)
    
    return jsonify({
        'conversations': conversations,
        'unread_count': sum(c['unread_count'] for c in conversations)
    }), 200


@conversations_bp.route('/api/conversations/unread_count', methods=['GET'])
def get_unread_count_api():
    """
    API endpoint to get total unread message count for badge display.
    
    Returns:
        JSON: {'unread_count': int}
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    unread_count = get_unread_conversation_count_for_user(current_user['id'])
    
    return jsonify({'unread_count': unread_count}), 200


# =============================================================================
# API: START CONVERSATION
# =============================================================================

@conversations_bp.route('/api/conversations/start', methods=['POST'])
def start_conversation():
    """
    API endpoint to start a new conversation with one or more users.
    
    JSON body:
        {
            "user_puids": ["puid1", "puid2", ...],  // List of user PUIDs to message
            "initial_message": "Optional first message text"
        }
    
    Returns:
        JSON: Conversation data with conv_uid
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.get_json()
    if not data or 'user_puids' not in data:
        return jsonify({'error': 'user_puids required'}), 400
    
    user_puids = data['user_puids']
    if not isinstance(user_puids, list) or len(user_puids) == 0:
        return jsonify({'error': 'user_puids must be a non-empty list'}), 400
    
    # Get user IDs from PUIDs
    participant_ids = [current_user['id']]
    for puid in user_puids:
        user = get_user_by_puid(puid)
        if not user:
            return jsonify({'error': f'User not found: {puid}'}), 404
        
        # Check if user can message this person
        can_message, reason = can_user_message(current_user['id'], user['id'])
        if not can_message:
            return jsonify({'error': reason}), 403
        
        participant_ids.append(user['id'])
    
    # Remove duplicates
    participant_ids = list(set(participant_ids))
    
    # ── PARENTAL CONTROLS CHECK ──────────────────────────────────────────────
    # Rule 1: Federated viewer (remote child visiting this node) attempting to DM
    # a local user — notify their home node to create the approval request there.
    # We ALWAYS delegate to the home node — it's the only place with the actual
    # parental controls record. The home node will return 400 if no approval is
    # needed (non-child user), in which case we fall through to normal processing.
    if session.get('is_federated_viewer') and current_user.get('hostname'):
        from db_queries.federation import notify_home_node_of_dm_start_attempt
        local_hostname = current_app.config.get('NODE_HOSTNAME')
        local_targets = [get_user_by_puid(p) for p in user_puids]
        for target in local_targets:
            if target:
                result = notify_home_node_of_dm_start_attempt(current_user, target, local_hostname)
                if result is True:
                    # Home node confirmed approval is pending — stop here
                    return jsonify({
                        'status': 'pending_parental_approval',
                        'message': 'This conversation needs a parent\'s approval before it can start.'
                    }), 202
                elif result is False:
                    # Home node said no approval needed (non-child) OR call failed —
                    # fall through to normal DM processing below
                    pass

    # Rule 2: Local child user attempting to DM a remote user — create approval locally.
    from db_queries.parental_controls import requires_parental_approval, create_approval_request, get_all_parent_ids
    from db_queries.notifications import create_notification

    if requires_parental_approval(current_user['id']):
        # Check if any target user is remote (non-local)
        remote_targets = [u for u in [get_user_by_puid(p) for p in user_puids]
                          if u and u.get('hostname')]
        if remote_targets:
            import json as _json
            for remote_user in remote_targets:
                approval_id = create_approval_request(
                    child_user_id=current_user['id'],
                    approval_type='dm_start_out',
                    target_puid=remote_user['puid'],
                    target_hostname=remote_user['hostname'],
                    request_data=_json.dumps({
                        'target_display_name': remote_user.get('display_name', 'Unknown'),
                        'target_puid': remote_user['puid'],
                        'target_hostname': remote_user['hostname'],
                    })
                )
                if approval_id:
                    for parent_id in get_all_parent_ids(current_user['id']):
                        create_notification(parent_id, current_user['id'], 'parental_approval_needed')
            return jsonify({
                'status': 'pending_parental_approval',
                'message': 'This conversation needs a parent\'s approval before it can start.'
            }), 202
    # ── END PARENTAL CONTROLS CHECK ─────────────────────────────────────────

    # Check if conversation already exists
    conversation = get_or_create_conversation_between_users(participant_ids)
    if not conversation:
        return jsonify({'error': 'Failed to create conversation'}), 500
    
    # For 1:1 conversations with non-friends, check if message request is needed
    if len(participant_ids) == 2:
        other_user_id = [uid for uid in participant_ids if uid != current_user['id']][0]
        
        if conversation_requires_request(current_user['id'], other_user_id):
            # Check existing request status — don't allow re-requesting if already pending
            existing_status = get_request_status_for_conversation(conversation['id'], other_user_id)
            if existing_status == 'pending':
                return jsonify({
                    'status': 'request_sent',
                    'message': 'A message request is already pending',
                    'conv_uid': conversation['conv_uid']
                }), 200
            
            # Check if recipient is under parental controls and sender is remote
            from db_queries.parental_controls import requires_parental_approval, create_approval_request, get_all_parent_ids
            from db_queries.notifications import create_notification
            other_user = get_user_by_id(other_user_id)
            sender_is_remote = bool(current_user.get('hostname'))
            if other_user and requires_parental_approval(other_user['id']) and sender_is_remote:
                import json as _json
                approval_id = create_approval_request(
                    child_user_id=other_user['id'],
                    approval_type='dm_start_in',
                    target_puid=current_user['puid'],
                    target_hostname=current_user.get('hostname'),
                    request_data=_json.dumps({
                        'sender_display_name': current_user.get('display_name', 'Unknown'),
                        'sender_puid': current_user['puid'],
                        'sender_hostname': current_user.get('hostname'),
                        'conv_uid': conversation['conv_uid'],
                    })
                )
                if approval_id:
                    for parent_id in get_all_parent_ids(other_user['id']):
                        create_notification(parent_id, other_user['id'], 'parental_approval_needed')
                    # Hide the conversation from the child until a parent approves it
                    hide_conversation_for_user(conversation['id'], other_user['id'])
                return jsonify({
                    'status': 'pending_parental_approval',
                    'message': 'Message request requires parental approval.'
                }), 202

            # Normal message request path (handles new + re-request after decline)

            # TARGETED SUBSCRIPTION: If the recipient is on a remote node we're not
            # yet connected to, establish a targeted subscription now. Without this,
            # distribute_dm_conversation has nowhere to send the request, and the
            # remote user never knows they've been messaged. A conversation without
            # federation is just a very lonely diary.
            if other_user and other_user.get('hostname'):
                from db_queries.federation import get_node_by_hostname, get_or_create_dm_targeted_subscription
                _node = get_node_by_hostname(other_user['hostname'])
                if not _node or _node.get('status') != 'connected' or not _node.get('shared_secret'):
                    _node = get_or_create_dm_targeted_subscription(
                        other_user['hostname'],
                        other_user['puid'],
                        other_user.get('display_name', 'Unknown')
                    )
                    if not _node:
                        return jsonify({'error': 'Unable to reach the remote node. Please try again later.'}), 500

            request_created = create_message_request(
                conversation['id'],
                current_user['id'],
                other_user_id
            )
            
            if request_created:
                # Distribute the conversation so the remote node receives the request
                distribute_dm_conversation(conversation['conv_uid'])
                return jsonify({
                    'status': 'request_sent',
                    'message': 'Message request sent',
                    'conv_uid': conversation['conv_uid']
                }), 200
    
    # Send initial message if provided
    initial_message = data.get('initial_message')
    if initial_message and initial_message.strip():
        message = send_message(conversation['id'], current_user['id'], initial_message.strip())
        if not message:
            return jsonify({'error': 'Failed to send initial message'}), 500
    
    # Distribute conversation to remote participants' nodes (fire and forget)
    distribute_dm_conversation(conversation['conv_uid'])

    return jsonify({
        'status': 'success',
        'conv_uid': conversation['conv_uid'],
        'conversation': conversation
    }), 201


# =============================================================================
# API: SEND MESSAGE
# =============================================================================

@conversations_bp.route('/api/conversations/<conv_uid>/messages', methods=['POST'])
def send_message_api(conv_uid):
    """
    API endpoint to send a message in a conversation.
    
    JSON body:
        {
            "content": "Message text",
            "media_files": ["file1.jpg", "file2.png"]  // Optional, from uploads
        }
    
    Returns:
        JSON: Created message data
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Get conversation
    conversation = get_conversation_by_conv_uid(conv_uid)
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404
    
    # Verify user is a participant
    if not is_user_in_conversation(current_user['id'], conversation['id']):
        return jsonify({'error': 'You are not a participant in this conversation'}), 403
    
    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({'error': 'Message content required'}), 400
    
    content = data['content'].strip()
    if not content:
        return jsonify({'error': 'Message content cannot be empty'}), 400
    
    reply_to_msg_uid = data.get('reply_to_msg_uid') or None

    # Send message
    message = send_message(conversation['id'], current_user['id'], content, reply_to_msg_uid=reply_to_msg_uid)
    if not message:
        return jsonify({'error': 'Failed to send message'}), 500
    
    # Add media files if provided
    local_hostname = current_app.config.get('NODE_HOSTNAME')
    media_files = data.get('media_files', [])
    if media_files:
        for media_path in media_files:
            add_media_to_message(message['id'], media_path, origin_hostname=local_hostname)
    
    # Build payload in request context, pass to thread
    distribute_dm_message(conv_uid, message['msg_uid'])

    return jsonify({
        'status': 'success',
        'message': message
    }), 201


# =============================================================================
# API: GET MESSAGES
# =============================================================================

@conversations_bp.route('/api/conversations/<conv_uid>/messages', methods=['GET'])
def get_messages_api(conv_uid):
    """
    API endpoint to get messages for a conversation.
    
    Query params:
        limit: Number of messages to return (default: 50)
        before: Timestamp to get messages before (for pagination)
    
    Returns:
        JSON: List of messages
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Get conversation
    conversation = get_conversation_by_conv_uid(conv_uid)
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404
    
    # Verify user is a participant
    if not is_user_in_conversation(current_user['id'], conversation['id']):
        return jsonify({'error': 'You are not a participant in this conversation'}), 403
    
    # Get pagination params
    limit = int(request.args.get('limit', 50))
    before_timestamp = request.args.get('before')
    
    # Get messages
    messages = get_messages_for_conversation(conversation['id'], limit, before_timestamp)
    
    # Mark conversation as read
    mark_conversation_as_read(conversation['id'], current_user['id'])
    
    return jsonify({
        'messages': messages,
        'has_more': len(messages) == limit
    }), 200


# =============================================================================
# API: EDIT MESSAGE
# =============================================================================

@conversations_bp.route('/api/messages/<msg_uid>', methods=['PUT'])
def edit_message_api(msg_uid):
    """
    API endpoint to edit a message.
    
    JSON body:
        {
            "content": "Updated message text"
        }
    
    Returns:
        JSON: Success status
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({'error': 'Message content required'}), 400
    
    new_content = data['content'].strip()
    if not new_content:
        return jsonify({'error': 'Message content cannot be empty'}), 400
    
    # Edit message (function checks ownership internally)
    # Verify ownership before editing
    msg = get_message_by_msg_uid(msg_uid)
    if not msg:
        return jsonify({'error': 'Message not found'}), 404
    if msg['sender_id'] != current_user['id']:
        return jsonify({'error': 'You can only edit your own messages'}), 403

    success = edit_message(msg_uid, new_content, current_user['id'])
    if not success:
        return jsonify({'error': 'Failed to edit message'}), 500

    # Distribute edit to remote participants (fire and forget)
    conversation = get_conversation_by_id(msg['conversation_id'])
    if conversation:
        distribute_dm_edit(conversation['conv_uid'], msg_uid, new_content)

    return jsonify({'status': 'success'}), 200


# =============================================================================
# API: DELETE MESSAGE
# =============================================================================

@conversations_bp.route('/api/messages/<msg_uid>', methods=['DELETE'])
def delete_message_api(msg_uid):
    """
    API endpoint to delete a message (soft delete).
    
    Returns:
        JSON: Success status
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Delete message (function checks ownership internally)
    # Verify ownership before deleting
    msg = get_message_by_msg_uid(msg_uid)
    if not msg:
        return jsonify({'error': 'Message not found'}), 404
    if msg['sender_id'] != current_user['id']:
        return jsonify({'error': 'You can only delete your own messages'}), 403

    success = delete_message(msg_uid, current_user['id'])
    if not success:
        return jsonify({'error': 'Failed to delete message'}), 500

    # Distribute soft-delete to remote participants (fire and forget)
    conversation = get_conversation_by_id(msg['conversation_id'])
    if conversation:
        distribute_dm_delete(conversation['conv_uid'], msg_uid)

    return jsonify({'status': 'success'}), 200

# =============================================================================
# API: CHECK NEW MESSAGES
# =============================================================================

@conversations_bp.route('/api/messages/check_new', methods=['GET'])
def check_new_messages():
    """
    Polls for new messages since a given timestamp.
    Returns unread count, new message previews for toasts, and
    whether the current conversation has new messages.
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    since_timestamp = request.args.get('since_timestamp')
    current_conv_uid = request.args.get('conv_uid')  # if user is in a conversation view

    if not since_timestamp:
        return jsonify({'error': 'since_timestamp required'}), 400

    from db_queries.conversations import get_new_messages_since, get_unread_message_count_for_user, get_unread_conversation_count_for_user, get_updated_messages_since
    from datetime import datetime

    # Normalize the JS ISO timestamp to SQLite format (same pattern as notifications endpoint)
    try:
        since_dt = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
        since_timestamp_normalized = since_dt.replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, AttributeError):
        since_timestamp_normalized = since_timestamp

    unread_count = get_unread_conversation_count_for_user(current_user['id'])
    new_messages = get_new_messages_since(current_user['id'], since_timestamp_normalized)

    # Build toast-friendly previews, excluding messages sent by the current user
    new_previews = []
    current_conv_has_new = False

    for msg in new_messages:
        if msg.get('message_type') == 'system':
            # System messages don't toast but DO trigger a refresh if we're viewing that conversation
            if current_conv_uid and msg['conv_uid'] == current_conv_uid:
                current_conv_has_new = True
            continue
        if msg['sender_id'] == current_user['id']:
            continue  # Don't toast your own messages

        # Only show conv_name if there's a custom title, or it's a group chat (3+ participants)
        # For 1:1s with no title, conv_name is omitted to avoid "Emma in Emma: hi"
        participant_names = msg.get('participant_names') or ''
        conv_title = msg.get('conv_title')
        is_group = ',' in participant_names  # GROUP_CONCAT uses comma separator
        conv_name = conv_title or (participant_names if is_group else None)

        preview = {
            'conv_uid': msg['conv_uid'],
            'sender_name': msg['display_name'],
            'conv_name': conv_name,
            'preview': msg['content'][:60] + '...' if len(msg.get('content') or '') > 60 else msg.get('content', ''),
            'url': f"/conversations/messages/{msg['conv_uid']}"
        }
        new_previews.append(preview)
        if current_conv_uid and msg['conv_uid'] == current_conv_uid:
            current_conv_has_new = True

    # Check for edits/deletes in the current conversation
    updated_messages = []
    if current_conv_uid:
        conversation = get_conversation_by_conv_uid(current_conv_uid)
        if conversation:
            updated_messages = get_updated_messages_since(
                conversation['id'], since_timestamp_normalized
            )

    from db_queries.conversations import get_pending_message_requests_for_user
    pending_requests = get_pending_message_requests_for_user(current_user['id'])
    pending_request_count = len(pending_requests)

    return jsonify({
        'unread_count': unread_count,
        'new_messages': new_previews,
        'current_conv_has_new': current_conv_has_new,
        'updated_messages': updated_messages,
        'pending_request_count': pending_request_count
    }), 200
# =============================================================================
# API: ARCHIVE/UNARCHIVE
# =============================================================================

@conversations_bp.route('/api/conversations/<conv_uid>/archive', methods=['POST'])
def archive_conversation_api(conv_uid):
    """
    API endpoint to archive a conversation.
    
    Returns:
        JSON: Success status
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    conversation = get_conversation_by_conv_uid(conv_uid)
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404
    
    success = archive_conversation_for_user(conversation['id'], current_user['id'])
    if not success:
        return jsonify({'error': 'Failed to archive conversation'}), 500
    
    return jsonify({'status': 'success'}), 200


@conversations_bp.route('/api/conversations/<conv_uid>/unarchive', methods=['POST'])
def unarchive_conversation_api(conv_uid):
    """
    API endpoint to unarchive a conversation.
    
    Returns:
        JSON: Success status
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    conversation = get_conversation_by_conv_uid(conv_uid)
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404
    
    success = unarchive_conversation_for_user(conversation['id'], current_user['id'])
    if not success:
        return jsonify({'error': 'Failed to unarchive conversation'}), 500
    
    return jsonify({'status': 'success'}), 200

# =============================================================================
# API: LEAVE CONVERSATION
# =============================================================================

@conversations_bp.route('/api/conversations/<conv_uid>/leave', methods=['POST'])
def leave_conversation_api(conv_uid):
    """
    Soft-leaves a conversation. Stamps left_at, hides from user's list.
    Others see the user as greyed out / left in participants.
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    conversation = get_conversation_by_conv_uid(conv_uid)
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404

    if not is_user_in_conversation(current_user['id'], conversation['id']):
        return jsonify({'error': 'You are not in this conversation'}), 403

    success = leave_conversation(conversation['id'], current_user['id'])
    if not success:
        return jsonify({'error': 'Failed to leave conversation'}), 500

    # Distribute leave event to remote nodes
    distribute_dm_participant_update(conv_uid, 'leave', current_user['id'], current_user['puid'], current_user.get('hostname'), current_user['display_name'])

    return jsonify({'status': 'success'}), 200


# =============================================================================
# API: HIDE CONVERSATION (delete for myself)
# =============================================================================

@conversations_bp.route('/api/conversations/<conv_uid>/hide', methods=['POST'])
def hide_conversation_api(conv_uid):
    """
    Hides a conversation from the user's list without leaving.
    Reappears automatically if a new message arrives.
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    conversation = get_conversation_by_conv_uid(conv_uid)
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404

    success = hide_conversation_for_user(conversation['id'], current_user['id'])
    if not success:
        return jsonify({'error': 'Failed to hide conversation'}), 500

    return jsonify({'status': 'success'}), 200

# =============================================================================
# API: INVITE PARTICIPANT
# =============================================================================

@conversations_bp.route('/api/conversations/<conv_uid>/invite', methods=['POST'])
def invite_participant_api(conv_uid):
    """
    Invites a user (by puid) to a conversation, or re-invites someone who left.
    Any active participant can do this.

    JSON body: { "user_puid": "abc123" }
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    conversation = get_conversation_by_conv_uid(conv_uid)
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404

    if not is_user_in_conversation(current_user['id'], conversation['id']):
        return jsonify({'error': 'You are not in this conversation'}), 403

    data = request.get_json()
    user_puid = (data or {}).get('user_puid')
    if not user_puid:
        return jsonify({'error': 'user_puid required'}), 400

    from db_queries.users import get_user_by_puid
    target_user = get_user_by_puid(user_puid)
    if not target_user:
        return jsonify({'error': 'User not found'}), 404

    success = invite_participant(conversation['id'], target_user['id'], current_user['id'])
    if not success:
        return jsonify({'error': 'Could not invite user — they may already be active in this conversation'}), 400

    # Distribute participant add to remote nodes
    distribute_dm_participant_update(conv_uid, 'add', current_user['id'], target_user['puid'], target_user.get('hostname'), target_user['display_name'])

    return jsonify({'status': 'success'}), 200


# =============================================================================
# API: REMOVE PARTICIPANT
# =============================================================================

@conversations_bp.route('/api/conversations/<conv_uid>/remove_participant', methods=['POST'])
def remove_participant_api(conv_uid):
    """
    Creator removes a participant from a conversation.

    JSON body: { "user_puid": "abc123" }
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    conversation = get_conversation_by_conv_uid(conv_uid)
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404

    if conversation['created_by_user_id'] != current_user['id']:
        return jsonify({'error': 'Only the conversation creator can remove participants'}), 403

    data = request.get_json()
    user_puid = (data or {}).get('user_puid')
    if not user_puid:
        return jsonify({'error': 'user_puid required'}), 400

    from db_queries.users import get_user_by_puid
    target_user = get_user_by_puid(user_puid)
    if not target_user:
        return jsonify({'error': 'User not found'}), 404

    if target_user['id'] == current_user['id']:
        return jsonify({'error': 'Use Leave conversation to remove yourself'}), 400

    success = remove_participant(conversation['id'], target_user['id'], current_user['id'])
    if not success:
        return jsonify({'error': 'Could not remove participant'}), 400

    # Distribute participant removal to remote nodes
    distribute_dm_participant_update(conv_uid, 'remove', current_user['id'], target_user['puid'], target_user.get('hostname'), target_user['display_name'])

    return jsonify({'status': 'success'}), 200

# =============================================================================
# API: RENAME CONVERSATION
# =============================================================================

@conversations_bp.route('/api/conversations/<conv_uid>/rename', methods=['POST'])
def rename_conversation_api(conv_uid):
    """
    API endpoint to rename a conversation. Only the creator can do this.

    JSON body:
        { "title": "New name" }

    Returns:
        JSON: Success status
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json()
    if data is None:
        return jsonify({'error': 'JSON body required'}), 400

    new_title = (data.get('title') or '').strip()
    # Allow empty string to clear the title — max 100 chars
    if len(new_title) > 100:
        return jsonify({'error': 'Conversation name must be 100 characters or fewer'}), 400

    from db_queries.conversations import rename_conversation
    success = rename_conversation(conv_uid, new_title or None, current_user['id'])
    if not success:
        return jsonify({'error': 'Failed to rename conversation. Only the conversation creator can do this.'}), 403

    # Federate the rename to all remote participant nodes
    distribute_dm_conversation(conv_uid)

    return jsonify({'status': 'success', 'title': new_title or None}), 200

# =============================================================================
# API: MESSAGE REQUESTS
# =============================================================================

@conversations_bp.route('/api/message_requests', methods=['GET'])
def get_message_requests_api():
    """
    API endpoint to get pending message requests.
    
    Returns:
        JSON: List of pending requests
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    requests = get_pending_message_requests_for_user(current_user['id'])
    
    return jsonify({'requests': requests}), 200


@conversations_bp.route('/api/message_requests/<conv_uid>/accept', methods=['POST'])
def accept_message_request_api(conv_uid):
    """
    API endpoint to accept a message request.
    
    Returns:
        JSON: Success status
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    conversation = get_conversation_by_conv_uid(conv_uid)
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404
    
    success = accept_message_request(conversation['id'], current_user['id'])
    if not success:
        return jsonify({'error': 'Failed to accept message request'}), 500
    
    # Notify the requester their request was accepted
    from db_queries.notifications import create_notification
    from db import get_db
    db = get_db()
    row = db.cursor().execute("""
        SELECT requester_id FROM dm_requests 
        WHERE conversation_id = ? AND recipient_id = ?
    """, (conversation['id'], current_user['id'])).fetchone()
    if row:
        requester = get_user_by_id(row['requester_id'])
        if requester and requester.get('hostname'):
            from utils.federation_utils import notify_remote_node_of_dm_request_accepted
            notify_remote_node_of_dm_request_accepted(current_user, requester, conv_uid)
            # Push the conversation to the requester's node so it appears in their list
            distribute_dm_conversation(conv_uid)
        else:
            create_notification(row['requester_id'], current_user['id'], 'dm_request_accepted')

    return jsonify({'status': 'success'}), 200


@conversations_bp.route('/api/message_requests/<conv_uid>/decline', methods=['POST'])
def decline_message_request_api(conv_uid):
    """
    API endpoint to decline a message request.
    
    Returns:
        JSON: Success status
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    conversation = get_conversation_by_conv_uid(conv_uid)
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404
    
    success = decline_message_request(conversation['id'], current_user['id'])
    if not success:
        return jsonify({'error': 'Failed to decline message request'}), 500

    # Notify the requester their request was declined
    from db_queries.notifications import create_notification
    from db import get_db
    db = get_db()
    row = db.cursor().execute("""
        SELECT requester_id FROM dm_requests 
        WHERE conversation_id = ? AND recipient_id = ?
    """, (conversation['id'], current_user['id'])).fetchone()
    # AFTER:
    if row:
        requester = get_user_by_id(row['requester_id'])
        if requester and requester.get('hostname'):
            # Remote requester — federate the notification
            from utils.federation_utils import notify_remote_node_of_dm_request_declined
            notify_remote_node_of_dm_request_declined(current_user, requester, conv_uid)
        else:
            # Local requester — standard notification
            create_notification(row['requester_id'], current_user['id'], 'dm_request_declined')

    return jsonify({'status': 'success'}), 200

@conversations_bp.route('/api/message_requests/<conv_uid>/decline_and_block', methods=['POST'])
def decline_and_block_message_request_api(conv_uid):
    """
    API endpoint to decline a message request AND block the requester from future DMs.
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    conversation = get_conversation_by_conv_uid(conv_uid)
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404

    # Find the requester before we decline
    from db import get_db as _get_db
    db = _get_db()
    row = db.cursor().execute("""
        SELECT requester_id FROM dm_requests
        WHERE conversation_id = ? AND recipient_id = ? AND status = 'pending'
    """, (conversation['id'], current_user['id'])).fetchone()

    if not row:
        return jsonify({'error': 'No pending request found'}), 404

    requester = get_user_by_id(row['requester_id'])

    # Decline the request
    success = decline_message_request(conversation['id'], current_user['id'])
    if not success:
        return jsonify({'error': 'Failed to decline message request'}), 500

    # Block the requester
    if requester:
        block_user_from_dms(current_user['id'], requester['id'])

        # Notify them their request was declined (same as normal decline)
        if requester.get('hostname'):
            from utils.federation_utils import notify_remote_node_of_dm_request_declined
            notify_remote_node_of_dm_request_declined(current_user, requester, conv_uid)
        else:
            from db_queries.notifications import create_notification
            create_notification(row['requester_id'], current_user['id'], 'dm_request_declined')

    return jsonify({'status': 'success'}), 200

# =============================================================================
# API: BLOCKING
# =============================================================================

@conversations_bp.route('/api/block/<user_puid>', methods=['POST'])
def block_user_api(user_puid):
    """
    API endpoint to block a user from sending DMs.
    
    Returns:
        JSON: Success status
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    user_to_block = get_user_by_puid(user_puid)
    if not user_to_block:
        return jsonify({'error': 'User not found'}), 404
    
    if user_to_block['id'] == current_user['id']:
        return jsonify({'error': 'Cannot block yourself'}), 400
    
    success = block_user_from_dms(current_user['id'], user_to_block['id'])
    if not success:
        return jsonify({'error': 'User already blocked or error occurred'}), 400
    
    return jsonify({'status': 'success'}), 200


@conversations_bp.route('/api/unblock/<user_puid>', methods=['POST'])
def unblock_user_api(user_puid):
    """
    API endpoint to unblock a user from sending DMs.
    
    Returns:
        JSON: Success status
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    user_to_unblock = get_user_by_puid(user_puid)
    if not user_to_unblock:
        return jsonify({'error': 'User not found'}), 404
    
    success = unblock_user_from_dms(current_user['id'], user_to_unblock['id'])
    if not success:
        return jsonify({'error': 'User not blocked or error occurred'}), 400
    
    return jsonify({'status': 'success'}), 200


@conversations_bp.route('/api/blocked_users', methods=['GET'])
def get_blocked_users_api():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    blocked_users = get_blocked_users_for_dms(current_user['id'])

    # Build profile picture URLs server-side using the same logic as templates,
    # so the JS doesn't have to guess at URL construction.
    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'
    for user in blocked_users:
        if user.get('profile_picture_path'):
            if user.get('hostname'):
                user['profile_pic_url'] = f"{protocol}://{user['hostname']}/profile_pictures/{user['profile_picture_path']}"
            else:
                user['profile_pic_url'] = url_for('main.serve_profile_picture', filename=user['profile_picture_path'])
        else:
            user['profile_pic_url'] = None

    return jsonify({'blocked_users': blocked_users}), 200


# =============================================================================
# API: MEDIA UPLOAD FOR DMS
# =============================================================================

@conversations_bp.route('/api/upload_dm_media', methods=['POST'])
def upload_dm_media():
    """
    API endpoint to upload media files for direct messages.
    Uses user's uploads directory.
    
    Returns:
        JSON: List of uploaded file paths
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401
    
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files provided'}), 400
    
    # Get user's uploads directory
    user_uploads_path = current_user.get('uploads_path')
    if not user_uploads_path:
        return jsonify({'error': 'No uploads directory configured'}), 400
    
    uploads_base_dir = os.path.join(current_app.config['USER_UPLOADS_BASE_DIR'], user_uploads_path)
    
    # Create uploads directory if it doesn't exist
    dm_media_dir = os.path.join(uploads_base_dir, 'dm_media')
    if not os.path.exists(dm_media_dir):
        try:
            os.makedirs(dm_media_dir, exist_ok=True)
        except Exception as e:
            return jsonify({'error': f'Failed to create media directory: {e}'}), 500
    
    uploaded_files = []
    allowed_extensions = current_app.config.get('ALLOWED_MEDIA_EXTENSIONS', 
                                                 {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'webp'})
    
    for file in files:
        if file and file.filename:
            # Validate file extension
            file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            if file_extension not in allowed_extensions:
                continue
            
            # Secure filename
            filename = secure_filename(file.filename)
            
            # Generate unique filename to prevent collisions
            import uuid
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            
            # Save file
            file_path = os.path.join(dm_media_dir, unique_filename)
            try:
                file.save(file_path)
                # Return relative path from uploads directory
                relative_path = os.path.join('dm_media', unique_filename)
                uploaded_files.append(relative_path)
            except Exception as e:
                print(f"Error saving file: {e}")
                continue
    
    if not uploaded_files:
        return jsonify({'error': 'No valid files uploaded'}), 400
    
    return jsonify({
        'status': 'success',
        'files': uploaded_files
    }), 200

# =============================================================================
# API: GROUP PICTURE UPLOAD
# =============================================================================

@conversations_bp.route('/api/conversations/<conv_uid>/picture', methods=['POST'])
def upload_conversation_picture(conv_uid):
    """
    Uploads or updates the group picture for a conversation.
    Only the conversation creator can do this.
    Accepts cropped base64 image OR a path from the media browser.
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    conversation = get_conversation_by_conv_uid(conv_uid)
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404

    if conversation['created_by_user_id'] != current_user['id']:
        return jsonify({'error': 'Only the conversation creator can set the group picture'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    cropped_image_data = data.get('cropped_image_data')
    media_browser_path = data.get('media_browser_path')

    pic_dir = os.path.join(
        current_app.config['PROFILE_PICTURE_STORAGE_DIR'],
        'conv_pics', conv_uid
    )
    os.makedirs(pic_dir, exist_ok=True)

    picture_path = None

    if cropped_image_data:
        try:
            header, encoded_data = cropped_image_data.split(',', 1)
            decoded_image = base64.b64decode(encoded_data)
            mime_type = header.split(';')[0].split(':')[1]
            file_extension = mime_type.split('/')[-1]
            filename = f"conv_pic.{file_extension}"
            file_path = os.path.join(pic_dir, filename)
            with open(file_path, 'wb') as f:
                f.write(decoded_image)
            picture_path = os.path.join('conv_pics', conv_uid, filename)
        except Exception as e:
            traceback.print_exc()
            return jsonify({'error': f'Error processing image: {e}'}), 500

    elif media_browser_path:
        # User picked from their media library — copy it to conv_pics so it's stable
        try:
            from db_queries.users import get_user_by_id
            user = get_user_by_id(current_user['id'])
            src = os.path.join(
                current_app.config['USER_UPLOADS_BASE_DIR'],
                user['uploads_path'],
                media_browser_path
            )
            if not os.path.exists(src):
                return jsonify({'error': 'Source file not found'}), 404
            import shutil
            ext = os.path.splitext(media_browser_path)[1]
            dest_filename = f"conv_pic{ext}"
            shutil.copy2(src, os.path.join(pic_dir, dest_filename))
            picture_path = os.path.join('conv_pics', conv_uid, dest_filename)
        except Exception as e:
            traceback.print_exc()
            return jsonify({'error': f'Error copying image: {e}'}), 500

    if not picture_path:
        return jsonify({'error': 'No image data provided'}), 400

    local_hostname = current_app.config.get('NODE_HOSTNAME')
    success = update_conversation_picture(conv_uid, picture_path, local_hostname)
    if not success:
        return jsonify({'error': 'Failed to save picture path'}), 500

    picture_url = f"/profile_pictures/{picture_path}"
    
    # Federate the conversation update so remote nodes know about the new picture
    distribute_dm_conversation(conv_uid)
    
    return jsonify({'status': 'success', 'picture_url': picture_url}), 200