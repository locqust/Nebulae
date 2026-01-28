# routes/friends.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
import sys
import requests
import hmac
import hashlib
import traceback
import json
from urllib.parse import urlencode # Import urlencode for query parameters

# Import database functions from the new query modules
from db import get_db
# MODIFICATION: Import the new search function
from db_queries.users import get_user_id_by_username, get_user_by_username, get_user_by_puid, get_user_by_id, search_discoverable_local_users
from db_queries.friends import (send_friend_request_db, accept_friend_request_db, reject_friend_request_db,
                                unfriend_db, get_pending_friend_requests, get_outgoing_friend_requests,
                                get_friends_list, is_friends_with, get_friendship_status,
                                snooze_friend, unsnooze_friend, block_friend, unblock_friend, get_friend_request_by_id,
                                get_friendship_details, get_friend_relationship, get_blocked_friends_list) # Added friendship details
# NEW: Import follower queries
from db_queries.followers import is_following, get_following_pages
from db_queries.federation import get_all_connected_nodes, get_node_by_hostname, get_or_create_remote_user, notify_remote_node_of_unfriend
# NEW: Import profile, settings, and media queries
from db_queries.profiles import get_profile_info_for_user, get_family_relationships_for_user
from db_queries.settings import get_user_settings
from db_queries.posts import get_media_for_user_gallery, get_muid_by_media_path
# NEW: Import notification query
from db_queries.notifications import get_unread_notification_count
from db_queries.followers import is_following, get_following_pages, get_followers
from db_queries.hidden_items import get_hidden_items


# Import federation utilities from the renamed file
from utils.federation_utils import get_remote_node_api_url

friends_bp = Blueprint('friends', __name__)

@friends_bp.route('/get_discoverable_users')
def get_discoverable_users():
    """
    Fetches discoverable users and public pages, both local and remote.
    Accepts an optional 'search_term' query parameter to filter results (for local users only).
    """
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    current_user_id = get_user_id_by_username(session['username'])
    if not current_user_id:
        return jsonify({'error': 'Current user not found'}), 404
    
    # Get hidden items for current user
    hidden_user_ids = get_hidden_items(current_user_id, 'user')
    hidden_page_ids = get_hidden_items(current_user_id, 'page')
    hidden_ids = hidden_user_ids | hidden_page_ids  # Combine sets

    search_term = request.args.get('search_term', None) # Get search term from query params
    discoverable_profiles = []
    added_puids = set() # Keep track of added PUIDs to prevent duplicates

    # --- Local User Search/Discovery ---
    local_node_hostname = current_app.config.get('NODE_HOSTNAME') or request.host.split(':')[0]
    local_profiles_to_process = []

    if search_term:
        print(f"DEBUG: Searching local users for: {search_term}")
        local_profiles_to_process = search_discoverable_local_users(search_term, current_user_id)
    else:
        # Existing logic to fetch all local discoverable users when no search term
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            SELECT id, puid, username, display_name, profile_picture_path, user_type, hostname
            FROM users
            WHERE user_type IN ('user', 'public_page', 'admin')
              AND username != 'admin'
              AND hostname IS NULL
        """)
        all_local_profiles_raw = cursor.fetchall()
        for profile_row in all_local_profiles_raw:
            profile = dict(profile_row)
            if profile['id'] == current_user_id: continue # Skip self
            is_related = False
            if profile['user_type'] in ['user', 'admin']:
                friendship_status_result = get_friendship_status(current_user_id, profile['id'])
                friendship_status = friendship_status_result[0] if isinstance(friendship_status_result, tuple) else friendship_status_result
                if friendship_status != 'not_friends': is_related = True
            elif profile['user_type'] == 'public_page':
                if is_following(current_user_id, profile['id']): is_related = True
            if not is_related:
                local_profiles_to_process.append(profile)

    # Process local results
    for profile in local_profiles_to_process:
        # Skip if hidden by user
        if profile['id'] in hidden_ids:
            continue
        if profile['puid'] not in added_puids:
            profile['node_hostname'] = local_node_hostname
            profile['node_nickname'] = 'Local'
            discoverable_profiles.append(profile)
            added_puids.add(profile['puid'])
            print(f"DEBUG: Added local profile {profile['puid']} ({profile.get('display_name')})")

    # --- Federated User Discovery (No Remote Search) ---
    # Only fetch remote users if there's NO search term
    if not search_term:
        connected_nodes = get_all_connected_nodes()
        print(f"DEBUG: Found {len(connected_nodes)} connected nodes for discovery.")
        for node in connected_nodes:
                # Only discover users from FULL connections, not targeted subscriptions
            if node['status'] != 'connected' or not node['shared_secret']:
                continue
            if node.get('connection_type') == 'targeted':
                continue  # Skip targeted subscriptions for user discovery

            print(f"DEBUG: Attempting to fetch all discoverable users from node {node['hostname']}")
            try:
                insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
                verify_ssl = not insecure_mode
                endpoint = '/federation/api/v1/discover_users'
                # --- REVERTED: No query parameters sent for remote discovery ---
                remote_url = get_remote_node_api_url(node['hostname'], endpoint, insecure_mode)
                print(f"DEBUG: Requesting URL: {remote_url}")
                # --- END REVERTED ---

                if not local_node_hostname:
                    print("ERROR: NODE_HOSTNAME is not configured. Federation calls will likely fail.")
                    continue

                request_body = b'' # GET request body is empty
                signature = hmac.new(node['shared_secret'].encode('utf-8'), msg=request_body, digestmod=hashlib.sha256).hexdigest()
                headers = {'X-Node-Hostname': local_node_hostname, 'X-Node-Signature': signature}

                response = requests.get(remote_url, headers=headers, timeout=5, verify=verify_ssl)
                response.raise_for_status()
                remote_profiles_data = response.json()
                print(f"DEBUG: Received from {node['hostname']}: {json.dumps(remote_profiles_data, indent=2)}")

                profiles_list = []
                if isinstance(remote_profiles_data, list):
                    profiles_list = remote_profiles_data
                elif isinstance(remote_profiles_data, dict) and 'users' in remote_profiles_data and isinstance(remote_profiles_data['users'], list):
                    profiles_list = remote_profiles_data['users']
                else:
                    print(f"WARN: Unexpected response format from {node['hostname']}: {type(remote_profiles_data)}")

                print(f"DEBUG: Processing profiles_list (length {len(profiles_list)}) from {node['hostname']}")

                for profile_data in profiles_list:
                    remote_profile_puid = profile_data.get('puid')
                    if not remote_profile_puid:
                        print(f"WARN: Skipping profile data with missing PUID from {node['hostname']}")
                        continue

                    if remote_profile_puid in added_puids:
                        print(f"DEBUG: Skipping duplicate profile {remote_profile_puid} received from {node['hostname']}.")
                        continue

                    current_user_puid_obj = get_user_by_id(current_user_id)
                    current_user_puid = current_user_puid_obj['puid'] if current_user_puid_obj else None

                    if not current_user_puid:
                         print("ERROR: Could not get PUID for current user. Skipping self-check.")
                    elif remote_profile_puid == current_user_puid:
                        print(f"DEBUG: Skipping own profile {remote_profile_puid} received from {node['hostname']}")
                        continue
                    
                    # --- FEDERATION FIX: Check for the received profile's origin hostname ---
                    origin_hostname = profile_data.get('hostname')

                    # If the origin_hostname is our own, skip it.
                    if origin_hostname == local_node_hostname:
                        continue

                    print(f"DEBUG: Checking remote profile: {profile_data.get('display_name')} ({remote_profile_puid}) from {origin_hostname or node['hostname']}")
                    
                    # --- BUG FIX: Determine the correct local stub type ---
                    # If the incoming profile is a 'public_page', we save it as 'public_page'.
                    # If it's anything else (like 'user'), we save it as 'remote'.
                    remote_type = profile_data.get('user_type')
                    print(f"DEBUG: Profile {profile_data.get('display_name')} has user_type: {remote_type}")
                    local_stub_type = 'public_page' if remote_type == 'public_page' else 'remote'
                    print(f"DEBUG: Setting local_stub_type to: {local_stub_type}")
                    # --- END BUG FIX ---

                    remote_user_stub = get_or_create_remote_user(
                        puid=remote_profile_puid,
                        display_name=profile_data.get('display_name'),
                        hostname=origin_hostname or node['hostname'], # Use origin_hostname!
                        profile_picture_path=profile_data.get('profile_picture_path'),
                        user_type=local_stub_type # <-- Use the corrected local_stub_type
                    )
                    
                    # --- KEYERROR FIX: Determine hostname and nickname upfront ---
                    effective_hostname = ""
                    effective_nickname = ""
                    if origin_hostname:
                        origin_node = get_node_by_hostname(origin_hostname)
                        effective_hostname = origin_hostname
                        effective_nickname = origin_node['nickname'] if origin_node else origin_hostname
                    else:
                        effective_hostname = node['hostname']
                        effective_nickname = node['nickname'] or node['hostname']
                    # --- END KEYERROR FIX ---

                    is_related = False
                    if remote_user_stub:
                        print(f"DEBUG: Found/Created local record for {remote_profile_puid}. Type: {remote_user_stub['user_type']}")
                        if remote_user_stub['user_type'] in ['user', 'remote', 'admin']:
                            friendship_status, _ = get_friendship_status(current_user_id, remote_user_stub['id'])
                            print(f"DEBUG: Friendship status with {remote_profile_puid}: {friendship_status}")
                            if friendship_status in ['friends', 'pending_sent', 'pending_received']: is_related = True
                        elif remote_user_stub['user_type'] == 'public_page':
                            is_following_status = is_following(current_user_id, remote_user_stub['id'])
                            print(f"DEBUG: Following status with {remote_profile_puid}: {is_following_status}")
                            if is_following_status: is_related = True
                    else:
                        print(f"DEBUG: Could not get/create local record for {remote_profile_puid}.")

                    print(f"DEBUG: Profile {remote_profile_puid} is_related = {is_related}")

                    # Skip if hidden by user
                    if remote_user_stub and remote_user_stub['id'] in hidden_ids:
                        print(f"DEBUG: Skipping hidden profile {remote_profile_puid}.")
                        continue

                    if not is_related:
                        # --- FEDERATION FIX ---
                        # Add the determined values to the dict
                        profile_data['node_hostname'] = effective_hostname
                        profile_data['node_nickname'] = effective_nickname
                        
                        discoverable_profiles.append(profile_data)
                        added_puids.add(remote_profile_puid)
                        # Use the new variable here
                        print(f"DEBUG: Added remote profile {remote_profile_puid} ({profile_data.get('display_name')}) from {effective_hostname} to discoverable list.")
                    else:
                        # Use the new variable here
                        print(f"DEBUG: Skipping related profile {remote_profile_puid} from {effective_hostname}.")

            except requests.exceptions.RequestException as e:
                print(f"ERROR: Could not fetch users from node {node['hostname']}: {e}")
            except Exception as e:
                print(f"ERROR: An unexpected error occurred while fetching from {node['hostname']}: {e}")
                traceback.print_exc()

    print(f"DEBUG: Returning {len(discoverable_profiles)} discoverable profiles.")
    return jsonify(discoverable_profiles)


@friends_bp.route('/send_friend_request/<puid>', methods=['POST'])
def send_friend_request_route(puid):
    """
    Allows a logged-in user to send a friend request to a user (local or remote) using their PUID.
    """
    if 'username' not in session:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': 'Authentication required.'}), 401
        flash('Please log in to send friend requests.', 'danger')
        return redirect(url_for('auth.login'))

    sender_user = get_user_by_username(session['username'])
    receiver_user = get_user_by_puid(puid)

    if not sender_user or not receiver_user:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': 'Sender or receiver user not found.'}), 404
        flash('Sender or receiver user not found.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    # NEW: Check if receiver is remote and handle accordingly
    if receiver_user['hostname'] is not None:
        # NEW: PARENTAL CONTROL CHECK - Intercept remote friend requests for under-16 users
        from db_queries.parental_controls import requires_parental_approval, create_approval_request, get_parent_user_id
        from db_queries.notifications import create_notification
        
        if requires_parental_approval(sender_user['id']):
            # Create approval request instead of sending directly
            request_data = json.dumps({
                'receiver_puid': receiver_user['puid'],
                'receiver_display_name': receiver_user.get('display_name', 'Unknown'),
                'receiver_hostname': receiver_user.get('hostname')
            })
            
            approval_id = create_approval_request(
                sender_user['id'],
                'friend_request_out',
                receiver_user['puid'],
                receiver_user.get('hostname'),
                request_data
            )
            
            if approval_id:
                # Get parent info for notification
                parent_id = get_parent_user_id(sender_user['id'])
                if parent_id:
                    create_notification(parent_id, sender_user['id'], 'parental_approval_needed')
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'status': 'info', 
                        'message': 'Friend request pending parental approval.',
                        'requires_approval': True
                    }), 200
                else:
                    flash('Friend request pending parental approval.', 'info')
                    return redirect(url_for('main.user_profile', puid=puid))
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'status': 'error', 'message': 'Failed to create approval request.'}), 500
                else:
                    flash('Failed to create approval request.', 'danger')
                    return redirect(url_for('main.user_profile', puid=puid))
        
        # Remote user - send via federation (existing code continues below)
        try:
            sender_hostname = current_app.config.get('NODE_HOSTNAME')
            node = get_node_by_hostname(receiver_user['hostname'])
            
            if not node or node['status'] != 'connected' or not node['shared_secret']:
                flash('Cannot send request: Remote node is not connected.', 'danger')
                return redirect(url_for('main.user_profile', puid=puid))

            insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
            verify_ssl = not insecure_mode

            remote_url = get_remote_node_api_url(
                receiver_user['hostname'],
                '/federation/api/v1/receive_friend_request',
                insecure_mode
            )

            payload = {
                "sender_puid": sender_user['puid'],
                "sender_hostname": sender_hostname,
                "sender_display_name": sender_user['display_name'],
                "sender_profile_picture_path": sender_user['profile_picture_path'],
                "receiver_puid": receiver_user['puid']
            }

            request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
            signature = hmac.new(
                node['shared_secret'].encode('utf-8'),
                msg=request_body,
                digestmod=hashlib.sha256
            ).hexdigest()

            headers = {
                'X-Node-Hostname': sender_hostname,
                'X-Node-Signature': signature,
                'Content-Type': 'application/json'
            }

            response = requests.post(remote_url, data=request_body, headers=headers, timeout=10, verify=verify_ssl)
            response.raise_for_status()
            response_data = response.json()

            if response.status_code == 200 and response_data.get('status') in ['success', 'info']:
                # Create local outgoing request record
                send_friend_request_db(sender_user['id'], receiver_user['id'])
                flash(f'Friend request sent to {receiver_user["display_name"]}!', 'success')
            else:
                flash(response_data.get('message', 'Failed to send friend request.'), 'danger')

        except Exception as e:
            print(f"ERROR sending remote friend request: {e}")
            traceback.print_exc()
            flash(f'Failed to send friend request: {str(e)}', 'danger')

        # FEDERATED VIEWER FIX: Check if referrer is from remote domain
        referrer = request.referrer
        local_hostname = current_app.config.get('NODE_HOSTNAME')
        
        if referrer and local_hostname:
            from urllib.parse import urlparse
            referrer_host = urlparse(referrer).netloc
            if referrer_host and referrer_host != local_hostname and not referrer_host.startswith('localhost'):
                return redirect(url_for('friends.friends_list'))
        
        return redirect(url_for('main.user_profile', puid=puid))

    # PARENTAL CONTROL CHECK for federated viewers sending friend requests  
    # Check if the sender is a federated viewer who requires parental approval
    if session.get('is_federated_viewer'):
        from db_queries.federation import check_remote_user_parental_controls, notify_home_node_of_friend_request_attempt
        
        if check_remote_user_parental_controls(sender_user):
            # Notify their home node to create an approval request
            success = notify_home_node_of_friend_request_attempt(sender_user, receiver_user)
            
            if success:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'status': 'info',
                        'message': 'Friend request sent to your parent for approval.',
                        'requires_approval': True
                    }), 200
                else:
                    flash('Friend request sent to your parent for approval.', 'info')
                    return redirect(url_for('main.user_profile', puid=puid))
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'status': 'error', 'message': 'Failed to send approval request to your home node.'}), 500
                else:
                    flash('Failed to send approval request to your home node.', 'danger')
                    return redirect(url_for('main.user_profile', puid=puid))

    # Local user logic (unchanged)
    sender_id = sender_user['id']
    receiver_id = receiver_user['id']

    if sender_id == receiver_id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': 'You cannot send a friend request to yourself.'}), 400
        flash('You cannot send a friend request to yourself.', 'warning')
        return redirect(url_for('main.user_profile', puid=puid))

    if is_friends_with(sender_id, receiver_id):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'info', 'message': f'You are already friends with {receiver_user["display_name"]}.'}), 200
        flash(f'You are already friends with {receiver_user["display_name"]}.', 'info')
        return redirect(url_for('main.user_profile', puid=puid))

    success, error_type = send_friend_request_db(sender_id, receiver_id)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if success:
            return jsonify({'status': 'success', 'message': f'Friend request sent to {receiver_user["display_name"]}!'}), 200
        elif error_type == 'exists':
             return jsonify({'status': 'info', 'message': 'A friend request already exists.'}), 200
        else:
            return jsonify({'status': 'error', 'message': f'Failed to send friend request to {receiver_user["display_name"]}.'}), 500
    else:
        if success:
            flash(f'Friend request sent to {receiver_user["display_name"]}!', 'success')
        else:
            flash(f'Failed to send friend request to {receiver_user["display_name"]}.', 'danger')
        return redirect(url_for('main.user_profile', puid=puid))


@friends_bp.route('/send_remote_request', methods=['POST'])
def send_remote_request_proxy():
    """
    Acts as a proxy to send a friend request from a local user to a remote user.
    """
    if 'username' not in session:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json()
    target_puid = data.get('target_puid')
    target_hostname = data.get('target_hostname')
    target_display_name = data.get('target_display_name')

    if not target_puid or not target_hostname:
        return jsonify({'error': 'Missing target user PUID or hostname'}), 400

    sender = get_user_by_username(session['username'])
    if not sender:
        return jsonify({'error': 'Could not identify sender.'}), 401

    # NEW: PARENTAL CONTROL CHECK - Intercept remote friend requests for users requiring approval
    print(f"DEBUG: Checking parental approval for user {sender['username']} (ID: {sender['id']})")
    from db_queries.parental_controls import requires_parental_approval, create_approval_request, get_all_parent_ids
    from db_queries.notifications import create_notification
    
    needs_approval = requires_parental_approval(sender['id'])
    print(f"DEBUG: Requires approval: {needs_approval}")
    
    if needs_approval:
        # Create approval request instead of sending directly
        request_data = json.dumps({
            'target_puid': target_puid,
            'target_display_name': target_display_name,
            'target_hostname': target_hostname
        })
        
        approval_id = create_approval_request(
            sender['id'],
            'friend_request_out',
            target_puid,
            target_hostname,
            request_data
        )
        
        print(f"DEBUG: Created approval request with ID: {approval_id}")
        
        if approval_id:
            # Get ALL parents for notification (supports multiple parents)
            parent_ids = get_all_parent_ids(sender['id'])
            print(f"DEBUG: Found {len(parent_ids)} parent(s) for user {sender['username']}: {parent_ids}")
            
            # Notify all parents
            for parent_id in parent_ids:
                notification_id = create_notification(parent_id, sender['id'], 'parental_approval_needed')
                print(f"DEBUG: Created notification {notification_id} for parent {parent_id}")
            
            return jsonify({
                'status': 'info', 
                'message': 'Friend request pending parental approval.'
            }), 200
        else:
            return jsonify({
                'status': 'error', 
                'message': 'Failed to create approval request.'
            }), 500
    
    # If no parental approval needed, continue with normal flow...
    sender_puid = sender['puid']
    sender_display_name = sender['display_name']
    sender_profile_picture_path = sender['profile_picture_path']
    sender_hostname = current_app.config.get('NODE_HOSTNAME')

    if not sender_hostname:
        return jsonify({'error': 'NODE_HOSTNAME is not configured on this server.'}), 500

    node = get_node_by_hostname(target_hostname)
    if not node or node['status'] != 'connected' or not node['shared_secret']:
        return jsonify({'error': 'Cannot send request: Node is not connected or is unknown.'}), 400

    try:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        verify_ssl = not insecure_mode

        remote_url = get_remote_node_api_url(
            target_hostname,
            '/federation/api/v1/receive_friend_request',
            insecure_mode
        )

        payload = {
            "sender_puid": sender_puid,
            "sender_hostname": sender_hostname,
            "sender_display_name": sender_display_name,
            "sender_profile_picture_path": sender_profile_picture_path,
            "receiver_puid": target_puid
        }

        request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        headers = {
            'X-Node-Hostname': sender_hostname,
            'X-Node-Signature': signature,
            'Content-Type': 'application/json'
        }

        response = requests.post(remote_url, data=request_body, headers=headers, timeout=10, verify=verify_ssl)
        response.raise_for_status()

        response_data = response.json()

        if response.status_code == 200 and response_data.get('status') in ['success', 'info']:
            remote_user = get_user_by_puid(target_puid)
            if not remote_user:
                display_name_to_use = target_display_name or f"User {target_puid[:8]}"
                # PRIVACY FIX: Updated to new function signature without username (was using positional args)
                remote_user = get_or_create_remote_user(
                    puid=target_puid,
                    display_name=display_name_to_use,
                    hostname=target_hostname,
                    profile_picture_path=None
                )

            if remote_user:
                send_friend_request_db(sender['id'], remote_user['id'])
            else:
                print(f"WARN: Could not create local outgoing friend request record for remote user {target_puid}")

        return jsonify(response_data), response.status_code

    except requests.exceptions.RequestException as e:
        print(f"ERROR proxying friend request to {target_hostname}: {e}")
        return jsonify({'error': f'Failed to connect to the remote node: {e}'}), 500
    except Exception as e:
        print(f"ERROR in send_remote_request_proxy: {e}")
        traceback.print_exc()
        return jsonify({'error': 'An unexpected error occurred.'}), 500


@friends_bp.route('/accept_friend_request/<int:request_id>', methods=['POST'])
def accept_friend_request_route(request_id):
    """Allows a logged-in user to accept a friend request."""
    if 'username' not in session:
        flash('Please log in to manage friend requests.', 'danger')
        return redirect(url_for('auth.login'))

    current_user = get_user_by_username(session['username'])
    if not current_user:
        flash('Current user not found.', 'danger')
        return redirect(url_for('auth.login'))

    # SECURITY FIX: Verify the request exists and belongs to current user
    friend_request = get_friend_request_by_id(request_id)
    
    if not friend_request or friend_request['receiver_id'] != current_user['id']:
        flash('Unauthorized to accept this friend request.', 'danger')
        return redirect(url_for('friends.friends_list'))

    if accept_friend_request_db(request_id, notify_remote=True):
        flash('Friend request accepted!', 'success')
    else:
        flash('Failed to accept friend request.', 'danger')

    # FEDERATED VIEWER FIX: Check if referrer is from remote domain
    referrer = request.referrer
    local_hostname = current_app.config.get('NODE_HOSTNAME')
    
    if referrer and local_hostname:
        from urllib.parse import urlparse
        referrer_host = urlparse(referrer).netloc
        if referrer_host and referrer_host != local_hostname and not referrer_host.startswith('localhost'):
            return redirect(url_for('friends.friends_list'))

    return redirect(url_for('friends.friends_list'))

@friends_bp.route('/reject_friend_request/<int:request_id>', methods=['POST'])
def reject_friend_request_route(request_id):
    """Allows a logged-in user to reject a friend request."""
    if 'username' not in session:
        flash('Please log in to manage friend requests.', 'danger')
        return redirect(url_for('auth.login'))

    current_user = get_user_by_username(session['username'])
    if not current_user:
        flash('Current user not found.', 'danger')
        return redirect(url_for('auth.login'))

    friend_request = get_friend_request_by_id(request_id)

    if not friend_request or friend_request['receiver_id'] != current_user['id']:
        flash('Unauthorized to reject this friend request.', 'danger')
        return redirect(url_for('friends.friends_list'))

    if reject_friend_request_db(request_id):
        flash('Friend request rejected.', 'info')
    else:
        flash('Failed to reject friend request.', 'danger')

    # FEDERATED VIEWER FIX: Check if referrer is from remote domain
    referrer = request.referrer
    local_hostname = current_app.config.get('NODE_HOSTNAME')
    
    if referrer and local_hostname:
        from urllib.parse import urlparse
        referrer_host = urlparse(referrer).netloc
        if referrer_host and referrer_host != local_hostname and not referrer_host.startswith('localhost'):
            return redirect(url_for('friends.friends_list'))

    return redirect(url_for('friends.friends_list'))

@friends_bp.route('/unfriend/<puid>', methods=['POST'])
def unfriend_route(puid):
    """Allows a logged-in user to unfriend another user by their PUID."""
    if 'username' not in session:
        flash('Please log in to unfriend users.', 'danger')
        return redirect(url_for('auth.login'))

    current_user = get_user_by_username(session['username'])
    target_user = get_user_by_puid(puid)

    if not current_user or not target_user:
        flash('User not found.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    # PARENTAL CONTROL CHECK: Prevent unfriending if parent-child relationship exists
    from db_queries.parental_controls import is_parent_child_relationship
    
    if is_parent_child_relationship(current_user['id'], target_user['id']):
        flash('Cannot unfriend: This user is your parent/child guardian.', 'warning')
        return redirect(request.referrer or url_for('main.index'))

    # If the target user is remote, notify their node
    if target_user.get('hostname'):
        notify_remote_node_of_unfriend(current_user, target_user)

    if unfriend_db(current_user['id'], target_user['id']):
        flash(f'You have unfriended {target_user["display_name"]}.', 'success')
    else:
        flash(f'Failed to unfriend {target_user["display_name"]}.', 'danger')

    # FEDERATED VIEWER FIX: Don't redirect to remote referrers
    referrer = request.referrer
    local_hostname = current_app.config.get('NODE_HOSTNAME')

    # Check if referrer is from a different domain
    if referrer and local_hostname:
        from urllib.parse import urlparse
        referrer_host = urlparse(referrer).netloc
        # If referrer is from a different host, redirect to local friends page or profile instead
        if referrer_host and referrer_host != local_hostname and not referrer_host.startswith('localhost'):
            # For most actions, redirect to friends list or user profile
            return redirect(url_for('friends.friends_list'))  # or appropriate local page

    return redirect(referrer or url_for('main.index'))

@friends_bp.route('/accept_friend_request_by_puid/<sender_puid>', methods=['POST'])
def accept_friend_request_by_puid_route(sender_puid):
    """Allows a logged-in user to accept a friend request by sender PUID (for federated viewers)."""
    if 'username' not in session:
        flash('Please log in to manage friend requests.', 'danger')
        return redirect(url_for('auth.login'))

    current_user = get_user_by_username(session['username'])
    if not current_user:
        flash('Current user not found.', 'danger')
        return redirect(url_for('auth.login'))

    # Get the sender by PUID
    sender_user = get_user_by_puid(sender_puid)
    if not sender_user:
        flash('Sender user not found.', 'danger')
        return redirect(url_for('friends.friends_list'))

    # Find the friend request by sender and receiver IDs
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id FROM friend_requests 
        WHERE sender_id = ? AND receiver_id = ? AND status = 'pending'
    """, (sender_user['id'], current_user['id']))
    
    friend_request = cursor.fetchone()
    
    if not friend_request:
        flash('No pending friend request found from this user.', 'danger')
        return redirect(url_for('friends.friends_list'))

    request_id = friend_request['id']

    if accept_friend_request_db(request_id, notify_remote=True):
        flash('Friend request accepted!', 'success')
    else:
        flash('Failed to accept friend request.', 'danger')

    # FEDERATED VIEWER FIX: Check if referrer is from remote domain
    referrer = request.referrer
    local_hostname = current_app.config.get('NODE_HOSTNAME')
    
    if referrer and local_hostname:
        from urllib.parse import urlparse
        referrer_host = urlparse(referrer).netloc
        if referrer_host and referrer_host != local_hostname and not referrer_host.startswith('localhost'):
            return redirect(url_for('friends.friends_list'))

    return redirect(url_for('friends.friends_list'))


@friends_bp.route('/reject_friend_request_by_puid/<sender_puid>', methods=['POST'])
def reject_friend_request_by_puid_route(sender_puid):
    """Allows a logged-in user to reject a friend request by sender PUID (for federated viewers)."""
    if 'username' not in session:
        flash('Please log in to manage friend requests.', 'danger')
        return redirect(url_for('auth.login'))

    current_user = get_user_by_username(session['username'])
    if not current_user:
        flash('Current user not found.', 'danger')
        return redirect(url_for('auth.login'))

    # Get the sender by PUID
    sender_user = get_user_by_puid(sender_puid)
    if not sender_user:
        flash('Sender user not found.', 'danger')
        return redirect(url_for('friends.friends_list'))

    # Find the friend request by sender and receiver IDs
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id FROM friend_requests 
        WHERE sender_id = ? AND receiver_id = ? AND status = 'pending'
    """, (sender_user['id'], current_user['id']))
    
    friend_request = cursor.fetchone()
    
    if not friend_request:
        flash('No pending friend request found from this user.', 'danger')
        return redirect(url_for('friends.friends_list'))

    request_id = friend_request['id']

    if reject_friend_request_db(request_id):
        flash('Friend request rejected.', 'info')
    else:
        flash('Failed to reject friend request.', 'danger')

    # FEDERATED VIEWER FIX: Check if referrer is from remote domain
    referrer = request.referrer
    local_hostname = current_app.config.get('NODE_HOSTNAME')
    
    if referrer and local_hostname:
        from urllib.parse import urlparse
        referrer_host = urlparse(referrer).netloc
        if referrer_host and referrer_host != local_hostname and not referrer_host.startswith('localhost'):
            return redirect(url_for('friends.friends_list'))

    return redirect(url_for('friends.friends_list'))

@friends_bp.route('/')
def friends_list():
    """
    MODIFICATION: This route now renders the main index.html "shell"
    and tells the client-side router to load the friends content.
    """
    if 'username' not in session or session.get('is_admin'):
        flash('Please log in to view your friends list.', 'danger')
        return redirect(url_for('auth.login'))

    current_user_id = get_user_id_by_username(session['username'])
    if not current_user_id:
        flash('User not found.', 'danger')
        return redirect(url_for('main.index'))

    # NEW: Fetch all the data needed for the header/sidebar, just like index() does
    current_username = session.get('username')
    user_data = get_user_by_username(current_username)
    user_media_path = None
    current_user_puid = None
    current_user_profile = None
    viewer_home_url = None
    
    if user_data:
        user_media_path = user_data['media_path']
        current_user_puid = user_data['puid']
        current_user_profile = user_data
        
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"

    # NEW: Pass the URL for the friends content to load
    initial_content_url = url_for('friends.get_friends_content')

    return render_template('index.html',
                           username=current_username,
                           user_media_path=user_media_path,
                           current_user_puid=current_user_puid,
                           current_user_id=current_user_id,
                           current_user_profile=current_user_profile,
                           viewer_home_url=viewer_home_url,
                           viewer_puid_for_js=current_user_puid,
                           initial_content_url=initial_content_url)


@friends_bp.route('/api/page/connections')
def get_friends_content():
    """
    API endpoint to fetch the HTML for the "My Connections" content.
    """
    if 'username' not in session or session.get('is_admin'):
        flash('Please log in to view your friends list.', 'danger')
        return redirect(url_for('auth.login'))
    
    current_user_id = get_user_id_by_username(session['username'])
    if not current_user_id:
        flash('User not found.', 'danger')
        return redirect(url_for('main.index'))
    
    # Get the full user object
    current_user = get_user_by_username(session['username'])
    if not current_user:
        flash('User not found.', 'danger')
        return redirect(url_for('main.index'))
    
    # Get friends OR followers depending on user type
    if current_user['user_type'] == 'public_page':
        friends = get_followers(current_user_id)
        # Public pages don't have friend requests or blocking
        followed_pages = []
        pending_incoming_requests = []
        pending_outgoing_requests = []
        blocked_friends = []
    else:
        friends = get_friends_list(current_user_id)
        # Get pages this user follows
        followed_pages = get_following_pages(current_user_id)
        # Get pending friend requests
        pending_incoming_requests = get_pending_friend_requests(current_user_id)
        pending_outgoing_requests = get_outgoing_friend_requests(current_user_id)
        # Get blocked friends - need to import the new function
        from db_queries.friends import get_blocked_friends_list
        blocked_friends = get_blocked_friends_list(current_user_id)
    
    # Render the *partial* template
    return render_template('_friends_content.html',
                           profile_user=current_user,
                           friends=friends,
                           followed_pages=followed_pages,
                           pending_incoming_requests=pending_incoming_requests,
                           pending_outgoing_requests=pending_outgoing_requests,
                           blocked_friends=blocked_friends,
                           is_owner=True)


@friends_bp.route('/snooze_friend/<puid>', methods=['POST'])
def snooze_friend_route(puid):
    """Snoozes a friend for 30 days."""
    if 'username' not in session:
        flash('Please log in to perform this action.', 'danger')
        return redirect(url_for('auth.login'))

    current_user = get_user_by_username(session['username'])
    target_user = get_user_by_puid(puid)

    if not current_user or not target_user:
        flash('User not found.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    # PARENTAL CONTROL CHECK: Prevent snoozing if parent-child relationship exists
    from db_queries.parental_controls import is_parent_child_relationship
    
    if is_parent_child_relationship(current_user['id'], target_user['id']):
        flash('Cannot snooze: This user is your parent/child guardian.', 'warning')
        return redirect(request.referrer or url_for('main.index'))

    if snooze_friend(current_user['id'], target_user['id']):
        flash(f'You have snoozed {target_user["display_name"]} for 30 days.', 'success')
    else:
        flash(f'Failed to snooze {target_user["display_name"]}.', 'danger')

    referrer = request.referrer
    local_hostname = current_app.config.get('NODE_HOSTNAME')

    # Check if referrer is from a different domain
    if referrer and local_hostname:
        from urllib.parse import urlparse
        referrer_host = urlparse(referrer).netloc
        # If referrer is from a different host, redirect to local friends page or profile instead
        if referrer_host and referrer_host != local_hostname and not referrer_host.startswith('localhost'):
            # For most actions, redirect to friends list or user profile
            return redirect(url_for('friends.friends_list'))  # or appropriate local page

    return redirect(referrer or url_for('main.index'))

@friends_bp.route('/unsnooze_friend/<puid>', methods=['POST'])
def unsnooze_friend_route(puid):
    """Unsnoozes a friend."""
    if 'username' not in session:
        flash('Please log in to perform this action.', 'danger')
        return redirect(url_for('auth.login'))

    current_user = get_user_by_username(session['username'])
    target_user = get_user_by_puid(puid)

    if not current_user or not target_user:
        flash('User not found.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    # PARENTAL CONTROL CHECK: Prevent unsnoozing if parent-child relationship exists
    from db_queries.parental_controls import is_parent_child_relationship
    
    if is_parent_child_relationship(current_user['id'], target_user['id']):
        flash('Cannot unsnooze: This user is your parent/child guardian.', 'warning')
        return redirect(request.referrer or url_for('main.index'))

    if unsnooze_friend(current_user['id'], target_user['id']):
        flash(f'You have unsnoozed {target_user["display_name"]}.', 'success')
    else:
        flash(f'Failed to unsnooze {target_user["display_name"]}.', 'danger')

    referrer = request.referrer
    local_hostname = current_app.config.get('NODE_HOSTNAME')

    # Check if referrer is from a different domain
    if referrer and local_hostname:
        from urllib.parse import urlparse
        referrer_host = urlparse(referrer).netloc
        # If referrer is from a different host, redirect to local friends page or profile instead
        if referrer_host and referrer_host != local_hostname and not referrer_host.startswith('localhost'):
            # For most actions, redirect to friends list or user profile
            return redirect(url_for('friends.friends_list'))  # or appropriate local page

    return redirect(referrer or url_for('main.index'))

@friends_bp.route('/block_friend/<puid>', methods=['POST'])
def block_friend_route(puid):
    """Blocks a friend."""
    if 'username' not in session:
        flash('Please log in to perform this action.', 'danger')
        return redirect(url_for('auth.login'))

    current_user = get_user_by_username(session['username'])
    target_user = get_user_by_puid(puid)

    if not current_user or not target_user:
        flash('User not found.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    # PARENTAL CONTROL CHECK: Prevent blocking if parent-child relationship exists
    from db_queries.parental_controls import is_parent_child_relationship
    
    if is_parent_child_relationship(current_user['id'], target_user['id']):
        flash('Cannot block: This user is your parent/child guardian.', 'warning')
        return redirect(request.referrer or url_for('main.index'))

    if block_friend(current_user['id'], target_user['id']):
        flash(f'You have blocked {target_user["display_name"]}.', 'success')
    else:
        flash(f'Failed to block {target_user["display_name"]}.', 'danger')

    referrer = request.referrer
    local_hostname = current_app.config.get('NODE_HOSTNAME')

    # Check if referrer is from a different domain
    if referrer and local_hostname:
        from urllib.parse import urlparse
        referrer_host = urlparse(referrer).netloc
        # If referrer is from a different host, redirect to local friends page or profile instead
        if referrer_host and referrer_host != local_hostname and not referrer_host.startswith('localhost'):
            # For most actions, redirect to friends list or user profile
            return redirect(url_for('friends.friends_list'))  # or appropriate local page

    return redirect(referrer or url_for('main.index'))

@friends_bp.route('/unblock_friend/<puid>', methods=['POST'])
def unblock_friend_route(puid):
    """Unblocks a friend."""
    if 'username' not in session:
        flash('Please log in to perform this action.', 'danger')
        return redirect(url_for('auth.login'))

    current_user = get_user_by_username(session['username'])
    target_user = get_user_by_puid(puid)

    if not current_user or not target_user:
        flash('User not found.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    # PARENTAL CONTROL CHECK: Prevent unblocking if parent-child relationship exists
    from db_queries.parental_controls import is_parent_child_relationship
    
    if is_parent_child_relationship(current_user['id'], target_user['id']):
        flash('Cannot unblock: This user is your parent/child guardian.', 'warning')
        return redirect(request.referrer or url_for('main.index'))

    if unblock_friend(current_user['id'], target_user['id']):
        flash(f'You have unblocked {target_user["display_name"]}.', 'success')
    else:
        flash(f'Failed to unblock {target_user["display_name"]}.', 'danger')

    referrer = request.referrer
    local_hostname = current_app.config.get('NODE_HOSTNAME')

    # Check if referrer is from a different domain
    if referrer and local_hostname:
        from urllib.parse import urlparse
        referrer_host = urlparse(referrer).netloc
        # If referrer is from a different host, redirect to local friends page or profile instead
        if referrer_host and referrer_host != local_hostname and not referrer_host.startswith('localhost'):
            # For most actions, redirect to friends list or user profile
            return redirect(url_for('friends.friends_list'))  # or appropriate local page

    return redirect(referrer or url_for('main.index'))


@friends_bp.route('/user/<puid>')
def view_user_friends(puid):
    """
    Displays the friends list for a specific user (identified by PUID).
    Similar to media_gallery but for friends.
    """
    # --- START: Added Full Context ---
    if 'username' not in session and not session.get('is_federated_viewer'):
        flash('Please log in to view this page.', 'danger')
        return redirect(url_for('auth.login'))

    profile_user = get_user_by_puid(puid)
    if not profile_user:
        flash('User not found.', 'danger')
        return redirect(url_for('main.index'))

    current_viewer_id = None
    viewer_is_admin = False
    is_federated_viewer = False
    viewer_home_url = None
    viewer_puid = None
    current_viewer_data = None

    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'
    
    user_settings = get_user_settings(None) # Default settings

    if session.get('is_federated_viewer'):
        is_federated_viewer = True
        viewer_puid = session.get('federated_viewer_puid')
        federated_viewer = get_user_by_puid(viewer_puid)
        if federated_viewer:
            current_viewer_id = federated_viewer['id']
            viewer_home_url = f"{protocol}://{federated_viewer['hostname']}"
            current_viewer_data = federated_viewer
            if session.get('federated_viewer_settings'):
                user_settings.update(session.get('federated_viewer_settings'))
    elif 'username' in session:
        current_viewer = get_user_by_username(session['username'])
        if current_viewer:
            current_viewer_id = current_viewer['id']
            viewer_is_admin = (current_viewer['user_type'] == 'admin')
            viewer_puid = current_viewer['puid']
            viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"
            current_viewer_data = current_viewer
            user_settings = get_user_settings(current_viewer_id) # Get user-specific settings

    is_owner = (current_viewer_id == profile_user['id']) if current_viewer_id else False

    friendship_status_result = get_friendship_status(current_viewer_id, profile_user['id'])
    friendship_status = friendship_status_result[0] if isinstance(friendship_status_result, tuple) else friendship_status_result
    incoming_request_id = friendship_status_result[1] if isinstance(friendship_status_result, tuple) else None

    friendship_date = None
    relationship_info = None
    if friendship_status == 'friends':
        friendship_date = get_friendship_details(current_viewer_id, profile_user['id'])
        relationship_info = get_friend_relationship(current_viewer_id, profile_user['id'])

    # Permission check
    if profile_user['user_type'] == 'public_page':
        # For public pages, check show_friends privacy settings
        profile_info_for_check = get_profile_info_for_user(profile_user['id'], current_viewer_id, viewer_is_admin)
        show_friends_info = profile_info_for_check.get('show_friends', {})
        
        can_view = is_owner or viewer_is_admin
        
        if not can_view:
            # Check if viewer meets any of the privacy criteria
            if show_friends_info.get('privacy_public'):
                can_view = True
            elif show_friends_info.get('privacy_friends'):
                # For public pages, privacy_friends means "followers only"
                # Check if viewer follows this page
                from db_queries.followers import is_following
                if current_viewer_id and is_following(current_viewer_id, profile_user['id']):
                    can_view = True
    else:
        # For regular users, check show_friends privacy settings
        profile_info_for_check = get_profile_info_for_user(profile_user['id'], current_viewer_id, viewer_is_admin)
        show_friends_info = profile_info_for_check.get('show_friends', {})
        
        can_view = is_owner or viewer_is_admin
        
        if not can_view:
            # Check if viewer meets any of the privacy criteria
            if show_friends_info.get('privacy_public'):
                can_view = True
            elif show_friends_info.get('privacy_local') and not is_federated_viewer:
                can_view = True
            elif show_friends_info.get('privacy_friends') and friendship_status == 'friends':
                can_view = True

    if not can_view:
        flash('You do not have permission to view this user\'s friends list.', 'danger')
        return redirect(url_for('main.user_profile', puid=puid))

    # --- Data for the sidebar (MOVED UP - need this first) ---
    profile_info = get_profile_info_for_user(profile_user['id'], current_viewer_id, viewer_is_admin)
    family_relationships = get_family_relationships_for_user(profile_user['id'], current_viewer_id, viewer_is_admin)
    all_gallery_media = get_media_for_user_gallery(profile_user['puid'], current_viewer_id, viewer_is_admin)
    
    profile_picture_muid = get_muid_by_media_path(profile_user.get('original_profile_picture_path'))
    profile_user['profile_picture_muid'] = profile_picture_muid
    
    latest_gallery_media = all_gallery_media[:9]
    total_media_count = len(all_gallery_media)
    # --- End data for sidebar ---

    # Get friends OR followers depending on user type
    if profile_user['user_type'] == 'public_page':
        from db_queries.followers import get_followers, is_following
        # Always fetch to get count
        followers_full_list = get_followers(profile_user['id'])
        followers_count = len(followers_full_list)
        following = is_following(current_viewer_id, profile_user['id']) if current_viewer_id else False
        
        # Check privacy for followers list
        show_friends_info = profile_info.get('show_friends', {})
        can_view_followers = is_owner or viewer_is_admin
        
        if not can_view_followers:
            if show_friends_info.get('privacy_public'):
                can_view_followers = True
            elif show_friends_info.get('privacy_friends') and following:
                can_view_followers = True
        
        friends = followers_full_list if can_view_followers else []
        friends_count = followers_count  # For consistency in template
    else:
        # Always fetch to get count
        friends_full_list = get_friends_list(profile_user['id'])
        friends_count = len(friends_full_list)
        following = False  # Not applicable for regular users
        
        # Check privacy for friends list
        show_friends_info = profile_info.get('show_friends', {})
        can_view_friends = is_owner or viewer_is_admin
        
        if not can_view_friends:
            if show_friends_info.get('privacy_public'):
                can_view_friends = True
            elif show_friends_info.get('privacy_local') and not is_federated_viewer:
                can_view_friends = True
            elif show_friends_info.get('privacy_friends') and friendship_status == 'friends':
                can_view_friends = True
        
        friends = friends_full_list if can_view_friends else []

    # NEW: Get followed pages for the *profile user*
    followed_pages = get_following_pages(profile_user['id'])
    # --- End data for sidebar ---

    # NEW: Get unread notification count for the VIEWER
    unread_count = 0
    if current_viewer_id and not is_federated_viewer:
        unread_count = get_unread_notification_count(current_viewer_id)

    return render_template('user_friends.html',
                           profile_user=profile_user,
                           friends=friends,
                           following=following,
                           followed_pages=followed_pages, # NEW: Pass followed pages
                           is_owner=is_owner,
                           # --- Added all missing context variables ---
                           profile_info=profile_info,
                           family_relationships=family_relationships,
                           latest_gallery_media=latest_gallery_media,
                           total_media_count=total_media_count,
                           current_viewer_data=current_viewer_data,
                           current_user_id=current_viewer_id,
                           viewer_puid=viewer_puid,
                           viewer_home_url=viewer_home_url,
                           is_federated_viewer=is_federated_viewer,
                           user_settings=user_settings,
                           viewer_token=session.pop('viewer_token', None),
                           friendship_status=friendship_status,
                           incoming_request_id=incoming_request_id,
                           friendship_date=friendship_date,
                           relationship_info=relationship_info,
                           user_media_path=current_viewer_data.get('media_path') if current_viewer_data else None,
                           viewer_puid_for_js=viewer_puid,
                           friends_count=friends_count,
                           unread_notification_count=unread_count #FIX: Use the fetched count
                           )

@friends_bp.route('/page/<puid>')
def view_page_followers(puid):
    """
    Displays the followers list for a specific public page (identified by PUID).
    Similar to view_user_friends but for public pages showing their followers.
    """
    # --- START: Added Full Context ---
    if 'username' not in session and not session.get('is_federated_viewer'):
        flash('Please log in to view this page.', 'danger')
        return redirect(url_for('auth.login'))

    profile_user = get_user_by_puid(puid)
    if not profile_user:
        flash('Page not found.', 'danger')
        return redirect(url_for('main.index'))
    
    if profile_user['user_type'] != 'public_page':
        flash('This page is not a public page.', 'danger')
        return redirect(url_for('main.user_profile', puid=puid))

    current_viewer_id = None
    viewer_is_admin = False
    is_federated_viewer = False
    viewer_home_url = None
    viewer_puid = None
    current_viewer_data = None

    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'
    
    user_settings = get_user_settings(None) # Default settings

    if session.get('is_federated_viewer'):
        is_federated_viewer = True
        viewer_puid = session.get('federated_viewer_puid')
        federated_viewer = get_user_by_puid(viewer_puid)
        if federated_viewer:
            current_viewer_id = federated_viewer['id']
            viewer_home_url = f"{protocol}://{federated_viewer['hostname']}"
            current_viewer_data = federated_viewer
            if session.get('federated_viewer_settings'):
                user_settings.update(session.get('federated_viewer_settings'))
    elif 'username' in session:
        current_viewer = get_user_by_username(session['username'])
        if current_viewer:
            current_viewer_id = current_viewer['id']
            viewer_is_admin = (current_viewer['user_type'] == 'admin')
            viewer_puid = current_viewer['puid']
            viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"
            current_viewer_data = current_viewer
            user_settings = get_user_settings(current_viewer_id) # Get user-specific settings

    is_owner = (current_viewer_id == profile_user['id']) if current_viewer_id else False

    # For public pages, anyone can view the followers list
    # (Unlike user profiles where you need to be friends)
    
    # Import the get_followers function from followers queries
    from db_queries.followers import get_followers
    
    # Get the followers list for the *profile page*
    followers = get_followers(profile_user['id'])

    # --- Data for the sidebar ---
    profile_info = get_profile_info_for_user(profile_user['id'], current_viewer_id, viewer_is_admin)
    all_gallery_media = get_media_for_user_gallery(profile_user['puid'], current_viewer_id, viewer_is_admin)
    
    profile_picture_muid = get_muid_by_media_path(profile_user.get('original_profile_picture_path'))
    profile_user['profile_picture_muid'] = profile_picture_muid
    
    latest_gallery_media = all_gallery_media[:9]
    total_media_count = len(all_gallery_media)
    # --- End data for sidebar ---

    # NEW: Get unread notification count for the VIEWER
    unread_count = 0
    if current_viewer_id and not is_federated_viewer:
        unread_count = get_unread_notification_count(current_viewer_id)

    # Check if viewer is following this page
    following = is_following(current_viewer_id, profile_user['id']) if current_viewer_id else False

    return render_template('page_followers.html',
                           profile_user=profile_user,
                           followers=followers,
                           is_owner=is_owner,
                           following=following,
                           # --- Added all missing context variables ---
                           profile_info=profile_info,
                           latest_gallery_media=latest_gallery_media,
                           total_media_count=total_media_count,
                           current_viewer_data=current_viewer_data,
                           current_user_id=current_viewer_id,
                           viewer_puid=viewer_puid,
                           viewer_home_url=viewer_home_url,
                           is_federated_viewer=is_federated_viewer,
                           user_settings=user_settings,
                           viewer_token=session.pop('viewer_token', None),
                           user_media_path=current_viewer_data.get('media_path') if current_viewer_data else None,
                           viewer_puid_for_js=viewer_puid,
                           unread_notification_count=unread_count
                           )


@friends_bp.route('/api/friends_list')
def friends_list_api():
    """
    API endpoint to get current user's friends list for tagging in posts.
    Returns a JSON array of friends with their PUIDs, display names, and profile pictures.
    """
    from flask import jsonify
    
    if 'username' not in session or session.get('is_admin'):
        return jsonify({'error': 'Authentication required'}), 401
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    
    friends = get_friends_list(current_user['id'])
    
    # Get insecure mode setting
    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = "http" if insecure_mode else "https"
    
    # Format for frontend
    friends_data = []
    for friend in friends:
        friend_data = {
            'puid': friend['puid'],
            'display_name': friend['display_name'],
            'hostname': friend.get('hostname')
        }
        
        # Build full profile picture URL
        if friend.get('profile_picture_path'):
            if friend.get('hostname'):
                # Remote friend - use full URL with correct protocol
                friend_data['profile_picture_url'] = f"{protocol}://{friend['hostname']}/profile_pictures/{friend['profile_picture_path']}"
            else:
                # Local friend - use relative path
                friend_data['profile_picture_url'] = f"/profile_pictures/{friend['profile_picture_path']}"
        else:
            friend_data['profile_picture_url'] = None
        
        friends_data.append(friend_data)
    
    return jsonify({'friends': friends_data})