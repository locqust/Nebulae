# routes/parental.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from db_queries.users import get_user_by_username, get_user_by_id, get_user_by_puid
from db_queries.parental_controls import (
    get_children_for_parent, 
    get_pending_approvals_for_parent,
    get_pending_approvals_for_child,
    approve_request, 
    deny_request,
    get_approval_request_by_id,
    get_parent_user_id
)
from db_queries.friends import send_friend_request_db
from db_queries.notifications import get_unread_notification_count, create_notification
from db_queries.hidden_items import get_hidden_items
from datetime import datetime
import json
import hmac
import hashlib
import requests

parental_bp = Blueprint('parental', __name__)

@parental_bp.route('/parental/')
def parental_dashboard():
    """
    MODIFICATION: This route now renders the main index.html "shell"
    and tells the client-side router to load the parental dashboard content.
    """
    if 'username' not in session:
        flash('Please log in to access parental controls.', 'danger')
        return redirect(url_for('auth.login'))
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        flash('User not found.', 'danger')
        return redirect(url_for('main.index'))
    
    # Check if user is actually a parent
    from db_queries.parental_controls import get_children_for_parent
    children = get_children_for_parent(current_user['id'])
    if not children:
        flash('You do not have parental control access.', 'danger')
        return redirect(url_for('main.index'))
    
    # Fetch all the data needed for the header/sidebar, just like index()
    user_media_path = current_user['media_path']
    current_user_puid = current_user['puid']
    current_user_profile = current_user
    
    viewer_home_url = None
    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'
    viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"
    
    # Pass the URL for the parental dashboard content to load
    initial_content_url = url_for('parental.get_parental_dashboard_content')
    
    return render_template('index.html',
                           username=session.get('username'),
                           user_media_path=user_media_path,
                           current_user_puid=current_user_puid,
                           current_user_id=current_user['id'],
                           current_user_profile=current_user_profile,
                           viewer_home_url=viewer_home_url,
                           viewer_puid_for_js=current_user_puid,
                           initial_content_url=initial_content_url)


@parental_bp.route('/parental/api/page/dashboard')
def get_parental_dashboard_content():
    """
    API endpoint to fetch the HTML for the parental dashboard content.
    """
    if 'username' not in session:
        return jsonify({'error': 'Authentication required.'}), 401
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found.'}), 404
    
    # Get children this parent monitors
    children = get_children_for_parent(current_user['id'])
    
    # Add pending count for each child
    from db_queries.parental_controls import get_pending_approvals_count_for_child
    for child in children:
        child['pending_count'] = get_pending_approvals_count_for_child(child['id'])
    
    # Get pending approval requests
    approvals = get_pending_approvals_for_parent(current_user['id'])
    
    # Parse the JSON request_data and enrich with target user info
    from db_queries.users import get_user_by_puid
    for approval in approvals:
        # DEBUG: Print the raw approval data
        print(f"DEBUG: Processing approval ID {approval.get('id')}")
        print(f"DEBUG: approval_type = {approval.get('approval_type')}")
        print(f"DEBUG: target_puid (column) = {approval.get('target_puid')}")
        print(f"DEBUG: request_data (raw) = {approval.get('request_data')}")
        
        if approval.get('request_data'):
            try:
                approval['request_data_parsed'] = json.loads(approval['request_data'])
                print(f"DEBUG: request_data_parsed = {approval['request_data_parsed']}")
                
                # Format event datetime for display
                if approval['approval_type'] == 'event_invite':
                    event_datetime_str = approval['request_data_parsed'].get('event_datetime')
                    event_end_datetime_str = approval['request_data_parsed'].get('event_end_datetime')
                    
                    if event_datetime_str:
                        try:
                            # Helper function for date suffix
                            def suffix(d):
                                return 'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')
                            
                            event_dt = datetime.strptime(event_datetime_str, '%Y-%m-%d %H:%M:%S')
                            event_end_dt = None
                            if event_end_datetime_str:
                                event_end_dt = datetime.strptime(event_end_datetime_str, '%Y-%m-%d %H:%M:%S')
                            
                            # Format like the event cards do
                            day_with_suffix = str(event_dt.day) + suffix(event_dt.day)
                            start_str = event_dt.strftime(f'%A, {day_with_suffix} %B %Y at %H:%M')
                            
                            if event_end_dt:
                                if event_dt.date() == event_end_dt.date():
                                    # Same day
                                    approval['formatted_event_datetime'] = f"{start_str} to {event_end_dt.strftime('%H:%M')}"
                                else:
                                    # Different days
                                    end_day_with_suffix = str(event_end_dt.day) + suffix(event_end_dt.day)
                                    end_str = event_end_dt.strftime(f'%A, {end_day_with_suffix} %B %Y at %H:%M')
                                    approval['formatted_event_datetime'] = f"{start_str} to {end_str}"
                            else:
                                approval['formatted_event_datetime'] = start_str
                                
                        except (ValueError, TypeError) as e:
                            print(f"Error formatting event datetime: {e}")
                            approval['formatted_event_datetime'] = event_datetime_str
                
                # Fetch target user information for OUTGOING friend requests
                if approval['approval_type'] == 'friend_request_out':
                    # Support both key formats: 'receiver_puid' (from send_friend_request_route) and 'target_puid' (from send_remote_request_proxy)
                    receiver_puid = approval['request_data_parsed'].get('receiver_puid') or approval['request_data_parsed'].get('target_puid')
                    print(f"DEBUG: Outgoing request - puid from parsed = {receiver_puid}")
                    
                    if receiver_puid:
                        target_user = get_user_by_puid(receiver_puid)
                        print(f"DEBUG: Found target_user = {target_user}")
                        
                        if target_user:
                            approval['target_user'] = target_user
                            
                            # Build profile picture URL for remote users
                            if target_user.get('hostname') and target_user.get('profile_picture_path'):
                                insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
                                protocol = 'http' if insecure_mode else 'https'
                                approval['target_profile_picture_url'] = f"{protocol}://{target_user['hostname']}/profile_pictures/{target_user['profile_picture_path']}"
                            elif target_user.get('profile_picture_path'):
                                approval['target_profile_picture_url'] = url_for('main.serve_profile_picture', filename=target_user['profile_picture_path'])
                            else:
                                approval['target_profile_picture_url'] = url_for('static', filename='images/default_avatar.png')
                            
                            print(f"DEBUG: Set target_profile_picture_url = {approval.get('target_profile_picture_url')}")
                
                # Fetch target user information for INCOMING friend requests
                elif approval['approval_type'] == 'friend_request_in':
                    sender_puid = approval['request_data_parsed'].get('sender_puid')
                    if sender_puid:
                        sender_user = get_user_by_puid(sender_puid)
                        if sender_user:
                            approval['target_user'] = sender_user
                            
                            # Build profile picture URL for remote users
                            if sender_user.get('hostname') and sender_user.get('profile_picture_path'):
                                insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
                                protocol = 'http' if insecure_mode else 'https'
                                approval['target_profile_picture_url'] = f"{protocol}://{sender_user['hostname']}/profile_pictures/{sender_user['profile_picture_path']}"
                            elif sender_user.get('profile_picture_path'):
                                approval['target_profile_picture_url'] = url_for('main.serve_profile_picture', filename=sender_user['profile_picture_path'])
                            else:
                                approval['target_profile_picture_url'] = url_for('static', filename='images/default_avatar.png')
                        
            except (ValueError, TypeError) as e:
                print(f"DEBUG: Error parsing request_data: {e}")
                approval['request_data_parsed'] = {}
        else:
            approval['request_data_parsed'] = {}
    
    # DEBUG: Print what we're sending to template
    for approval in approvals:
        print(f"DEBUG FINAL: ID={approval.get('id')}, has target_user={bool(approval.get('target_user'))}, has pic_url={bool(approval.get('target_profile_picture_url'))}")
    
    # Render the *partial* template
    return render_template('_parental_dashboard_content.html',
                         children=children,
                         approvals=approvals)

@parental_bp.route('/parental/approve/<int:approval_id>', methods=['POST'])
def approve_request_route(approval_id):
    """Approves a parental approval request and executes the action."""
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    
    user = get_user_by_username(session['username'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get the approval request
    approval = get_approval_request_by_id(approval_id)
    if not approval:
        return jsonify({'error': 'Approval request not found'}), 404
    
    # Verify this parent has authority over this child
    parent_id = get_parent_user_id(approval['child_user_id'])
    if parent_id != user['id']:
        return jsonify({'error': 'You do not have authority over this child'}), 403
    
    # Mark as approved
    if not approve_request(approval_id, user['id']):
        return jsonify({'error': 'Failed to approve request'}), 500
    
    # Execute the approved action
    try:
        request_data = json.loads(approval['request_data'])
        child_user = get_user_by_id(approval['child_user_id'])
        
        if approval['approval_type'] == 'friend_request_out':
            # Send the friend request on behalf of the child
            from db_queries.federation import get_node_by_hostname, get_or_create_remote_user
            from utils.federation_utils import get_remote_node_api_url
            
            receiver_puid = approval['target_puid']
            receiver_hostname = approval['target_hostname']
            
            # Create/get remote user stub
            receiver = get_or_create_remote_user(
                puid=receiver_puid,
                display_name=request_data.get('receiver_display_name', 'Unknown'),
                hostname=receiver_hostname,
                profile_picture_path=None
            )
            
            # Send federated friend request
            origin_node = get_node_by_hostname(receiver_hostname)
            if origin_node:
                insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
                verify_ssl = not insecure_mode
                sender_hostname = current_app.config.get('NODE_HOSTNAME')
                
                api_url = get_remote_node_api_url(
                    receiver_hostname,
                    '/federation/api/v1/receive_friend_request',
                    insecure_mode
                )
                
                payload = {
                    'sender_puid': child_user['puid'],
                    'sender_hostname': sender_hostname,
                    'sender_display_name': child_user['display_name'],
                    'sender_profile_picture_path': child_user.get('profile_picture_path'),
                    'receiver_puid': receiver_puid
                }
                
                request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
                signature = hmac.new(
                    origin_node['shared_secret'].encode('utf-8'),
                    msg=request_body,
                    digestmod=hashlib.sha256
                ).hexdigest()
                
                headers = {
                    'X-Node-Hostname': sender_hostname,
                    'X-Node-Signature': signature,
                    'Content-Type': 'application/json'
                }
                
                response = requests.post(api_url, data=request_body, headers=headers, timeout=10, verify=verify_ssl)
                response.raise_for_status()
                
                if response.status_code == 200:
                    # Also store locally as outgoing request
                    send_friend_request_db(child_user['id'], receiver['id'])
                    
                    # Notify child that request was approved and sent
                    create_notification(child_user['id'], user['id'], 'parental_approval_approved')
                    
                    return jsonify({'message': 'Friend request approved and sent'}), 200
                else:
                    return jsonify({'error': 'Failed to send friend request to remote node'}), 500
        
        elif approval['approval_type'] == 'friend_request_in':
            # Approve an incoming friend request - add it to the child's pending requests
            
            sender_puid = approval['target_puid']
            sender_user = get_user_by_puid(sender_puid)
            
            if sender_user:
                # Create the friend request in the database so it appears in child's pending requests
                success, error_type = send_friend_request_db(sender_user['id'], child_user['id'])
                
                if success:
                    # Notify child that the request was approved and is now in their pending list
                    create_notification(child_user['id'], user['id'], 'parental_approval_approved')
                    # Also create the standard friend request notification for the child
                    create_notification(child_user['id'], sender_user['id'], 'friend_request')
                    
                    return jsonify({'message': 'Incoming friend request approved and added to pending requests'}), 200
                elif error_type == 'exists':
                    # Request already exists somehow
                    return jsonify({'message': 'Friend request already exists'}), 200
                else:
                    return jsonify({'error': 'Failed to process incoming friend request'}), 500
            else:
                return jsonify({'error': 'Sender user not found'}), 404
        
        elif approval['approval_type'] == 'group_join_remote':
            # Approve a remote group join request
            from db_queries.groups import get_group_by_puid, send_join_request, get_or_create_remote_group_stub
            from db_queries.federation import get_node_by_hostname, get_or_create_targeted_subscription
            from utils.federation_utils import get_remote_node_api_url
            import requests
            
            group_puid = approval['target_puid']
            group_hostname = approval['target_hostname']
            
            # Get/create the group stub
            request_data_parsed = json.loads(approval['request_data'])
            group_stub = get_or_create_remote_group_stub(
                puid=group_puid,
                name=request_data_parsed.get('group_name', 'Unknown Group'),
                description=None,
                profile_picture_path=None,
                hostname=group_hostname
            )
            
            if not group_stub:
                return jsonify({'error': 'Failed to create group stub'}), 500
            
            # Create local pending join request
            send_join_request(group_stub['id'], child_user['id'],
                            rules_agreed=request_data_parsed.get('rules_agreed', False),
                            question_responses=request_data_parsed.get('question_responses', {}))
            
            # Get connection to remote node
            node = get_node_by_hostname(group_hostname)
            if not node or node['status'] != 'connected' or not node['shared_secret']:
                # Try to create targeted subscription
                node = get_or_create_targeted_subscription(
                    group_hostname,
                    'group',
                    group_puid,
                    request_data_parsed.get('group_name', 'Unknown Group')
                )
                
                if not node:
                    return jsonify({'error': 'Unable to connect to remote node'}), 500
            
            try:
                insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
                verify_ssl = not insecure_mode
                local_hostname = current_app.config.get('NODE_HOSTNAME')
                
                remote_url = get_remote_node_api_url(
                    group_hostname,
                    '/federation/api/v1/receive_group_join_request',
                    insecure_mode
                )
                
                payload = {
                    "group_puid": group_puid,
                    "requester_data": {
                        "puid": child_user['puid'],
                        "display_name": child_user['display_name'],
                        "profile_picture_path": child_user['profile_picture_path'],
                        "hostname": local_hostname
                    },
                    "rules_agreed": request_data_parsed.get('rules_agreed', False),
                    "question_responses": request_data_parsed.get('question_responses', {})
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
                
                if response.status_code == 200:
                    # Notify child that request was approved and sent
                    create_notification(child_user['id'], user['id'], 'parental_approval_approved')
                    return jsonify({'message': 'Group join request approved and sent'}), 200
                else:
                    return jsonify({'error': 'Failed to send group join request to remote node'}), 500
                    
            except requests.exceptions.RequestException as e:
                print(f"ERROR sending approved group join request: {e}")
                return jsonify({'error': f'Failed to connect to remote node: {e}'}), 500
        
        elif approval['approval_type'] == 'event_invite':
            # Approve an event invitation - create the event stub and add the child as invited
            request_data_parsed = json.loads(approval['request_data'])
            
            # Parse the event datetime
            try:
                event_datetime = datetime.strptime(request_data_parsed['event_datetime'], '%Y-%m-%d %H:%M:%S')
                event_end_datetime = None
                if request_data_parsed.get('event_end_datetime'):
                    event_end_datetime = datetime.strptime(request_data_parsed['event_end_datetime'], '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid event date format'}), 400
            
            # Create or get the remote event stub
            from db_queries.events import get_or_create_remote_event_stub, invite_friend_to_event
            
            event_stub = get_or_create_remote_event_stub(
                puid=request_data_parsed['event_puid'],
                created_by_user_puid=request_data_parsed['creator_puid'],
                source_type=request_data_parsed['source_type'],
                source_puid=request_data_parsed['source_puid'],
                title=request_data_parsed['event_title'],
                event_datetime=event_datetime,
                event_end_datetime=event_end_datetime,
                location=request_data_parsed.get('location'),
                details=request_data_parsed.get('details'),
                is_public=request_data_parsed.get('is_public', False),
                hostname=approval['target_hostname'],
                profile_picture_path=request_data_parsed.get('profile_picture_path')
            )
            
            if event_stub:
                # Create stub for the inviter
                from db_queries.federation import get_or_create_remote_user
                inviter = get_or_create_remote_user(
                    puid=request_data_parsed['creator_puid'],
                    display_name=f"User from {approval['target_hostname']}",
                    hostname=approval['target_hostname'],
                    profile_picture_path=request_data_parsed.get('profile_picture_path')
                )
                
                if inviter:
                    # Add child to event as 'invited'
                    success = invite_friend_to_event(event_stub['id'], inviter['id'], child_user['puid'])
                    
                    if success:
                        # Notify child that invitation was approved
                        create_notification(child_user['id'], user['id'], 'parental_approval_approved')
                        return jsonify({'message': 'Event invitation approved'}), 200
                    else:
                        return jsonify({'error': 'Failed to add child to event'}), 500

        elif approval['approval_type'] == 'post_tag':
            # Approve a post tag - add child to tagged users and create notification
            request_data_parsed = json.loads(approval['request_data'])
            post_cuid = request_data_parsed.get('post_cuid')
            tagger_puid = request_data_parsed.get('tagger_puid')
            
            if not post_cuid or not tagger_puid:
                return jsonify({'error': 'Invalid post tag data'}), 400
            
            # Get the post to verify it still exists
            from db_queries.posts import get_post_by_cuid
            post = get_post_by_cuid(post_cuid)
            
            if not post:
                return jsonify({'error': 'Post no longer exists'}), 404
            
            # Get the tagger's internal ID
            tagger_user = get_user_by_puid(tagger_puid)
            if not tagger_user:
                return jsonify({'error': 'Tagger user not found'}), 404
            
            # Add child to the post's tagged_user_puids
            from db import get_db as get_db_direct
            db_temp = get_db_direct()
            cursor_temp = db_temp.cursor()
            
            cursor_temp.execute("SELECT tagged_user_puids FROM posts WHERE cuid = ?", (post_cuid,))
            post_row = cursor_temp.fetchone()
            
            if post_row:
                current_tags = json.loads(post_row['tagged_user_puids']) if post_row['tagged_user_puids'] else []
                
                # Add child's PUID if not already there
                if child_user['puid'] not in current_tags:
                    current_tags.append(child_user['puid'])
                    cursor_temp.execute("""
                        UPDATE posts 
                        SET tagged_user_puids = ?
                        WHERE cuid = ?
                    """, (json.dumps(current_tags), post_cuid))
                    db_temp.commit()
            
            # Create the notification for the child
            create_notification(
                child_user['id'],
                tagger_user['id'],
                'tagged_in_post',
                post['id'],
                group_id=request_data_parsed.get('group_id'),
                event_id=request_data_parsed.get('event_id')
            )
            
            # Notify child that the tag was approved
            create_notification(child_user['id'], user['id'], 'parental_approval_approved')
            return jsonify({'message': 'Post tag approved'}), 200
            
        elif approval['approval_type'] == 'media_tag':
            # Approve a media tag - add child to tagged users and create notification
            request_data_parsed = json.loads(approval['request_data'])
            muid = request_data_parsed.get('muid')
            tagger_puid = request_data_parsed.get('tagger_puid')
            
            if not muid or not tagger_puid:
                return jsonify({'error': 'Invalid media tag data'}), 400
            
            # Get the media to verify it still exists
            from db_queries.media import get_media_by_muid
            media = get_media_by_muid(muid)
            
            if not media:
                return jsonify({'error': 'Media no longer exists'}), 404
            
            # Get the tagger's internal ID
            tagger_user = get_user_by_puid(tagger_puid)
            if not tagger_user:
                return jsonify({'error': 'Tagger user not found'}), 404
            
            # Add child to the media's tagged_user_puids
            from db import get_db as get_db_direct
            db_temp = get_db_direct()
            cursor_temp = db_temp.cursor()
            
            cursor_temp.execute("SELECT tagged_user_puids FROM post_media WHERE muid = ?", (muid,))
            media_row = cursor_temp.fetchone()
            
            if media_row:
                current_tags = json.loads(media_row['tagged_user_puids']) if media_row['tagged_user_puids'] else []
                
                # Add child's PUID if not already there
                if child_user['puid'] not in current_tags:
                    current_tags.append(child_user['puid'])
                    cursor_temp.execute("""
                        UPDATE post_media 
                        SET tagged_user_puids = ?
                        WHERE muid = ?
                    """, (json.dumps(current_tags), muid))
                    db_temp.commit()
            
            # Get the parent post info for group/event context
            from db_queries.posts import get_post_by_cuid
            parent_post = get_post_by_cuid(media['post_cuid']) if media.get('post_cuid') else None
            
            # Create the notification for the child
            create_notification(
                child_user['id'],
                tagger_user['id'],
                'tagged_in_media',
                post_id=None,
                media_id=media['id'],
                group_id=parent_post['group_id'] if parent_post else None,
                event_id=parent_post['event_id'] if parent_post else None
            )
            
            # Notify child that the tag was approved
            create_notification(child_user['id'], user['id'], 'parental_approval_approved')
            return jsonify({'message': 'Media tag approved'}), 200
         
        return jsonify({'error': f'Unknown approval type: {approval["approval_type"]}'}), 400
    
    except Exception as e:
        print(f"Error executing approved action: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to execute approved action'}), 500

@parental_bp.route('/parental/deny/<int:approval_id>', methods=['POST'])
def deny_request_route(approval_id):
    """Denies a parental approval request."""
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 403
    
    user = get_user_by_username(session['username'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get the approval request
    approval = get_approval_request_by_id(approval_id)
    if not approval:
        return jsonify({'error': 'Approval request not found'}), 404
    
    # Verify this parent has authority over this child
    parent_id = get_parent_user_id(approval['child_user_id'])
    if parent_id != user['id']:
        return jsonify({'error': 'You do not have authority over this child'}), 403
    
    # Mark as denied
    if deny_request(approval_id, user['id']):
        # Notify child that request was denied
        create_notification(approval['child_user_id'], user['id'], 'parental_approval_denied')
        
        # If this is an incoming friend request, notify the remote node of rejection
        if approval['approval_type'] == 'friend_request_in':
            from db_queries.users import get_user_by_puid
            from db_queries.federation import notify_remote_node_of_rejection
            
            child_user = get_user_by_id(approval['child_user_id'])
            sender_puid = approval['target_puid']
            sender_user = get_user_by_puid(sender_puid)
            
            if sender_user and child_user:
                # Notify remote node that the request was rejected
                notify_remote_node_of_rejection(sender_user, child_user)
        
        return jsonify({'message': 'Request denied'}), 200
    else:
        return jsonify({'error': 'Failed to deny request'}), 500
    
@parental_bp.route('/parental/api/badge_count')
def get_badge_count():
    """API endpoint to get the current pending approvals count for badge."""
    if 'username' not in session:
        return jsonify({'count': 0}), 200
    
    from db_queries.parental_controls import get_pending_approvals_count_for_parent
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'count': 0}), 200
    
    count = get_pending_approvals_count_for_parent(current_user['id'])
    return jsonify({'count': count}), 200