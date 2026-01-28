# routes/groups.py
import os
import base64
import traceback
import json
import requests
import hmac
import hashlib
import time

from flask import (Blueprint, render_template, request, redirect, url_for,
                   session, flash, jsonify, current_app)

# The url_prefix is handled in app.py during blueprint registration.
# Removing it from here for clarity and to avoid confusion.
groups_bp = Blueprint('groups', __name__)

# Import federation utilities from the new query modules
from utils.federation_utils import get_remote_node_api_url
# NEW: Import settings query to pass settings to remote nodes
from db_queries.settings import get_user_settings
from db_queries.settings import get_user_settings
from db_queries.notifications import get_unread_notification_count
from db_queries.hidden_items import get_hidden_items


@groups_bp.route('/<puid>')
def group_profile(puid):
    """Displays a group's profile page, now with federation support."""
    # Imports moved inside function
    from db_queries.groups import (get_group_by_puid, get_group_members, is_user_group_member,
                                   is_user_group_admin, is_user_group_moderator_or_admin,
                                   get_user_join_request_status, get_pending_join_requests,
                                   get_group_profile_info, get_friends_in_group)
    from db_queries.users import get_user_by_username, get_user_by_puid
    from db_queries.posts import (get_muid_by_media_path, get_posts_for_group, filter_comments,
                                  get_media_for_group_gallery)
    from db_queries.friends import get_snoozed_friends, get_who_blocked_user
    from db_queries.federation import get_node_by_hostname

    # FEDERATION FIX: Handle incoming viewer tokens to establish a federated session.
    viewer_token = request.args.get('viewer_token')
    
    # --- START BUG FIX ---
    # We must catch the token, store it in the session, and redirect to establish the session
    # *before* trying to render the page. This mimics the working logic in main.py.
    if viewer_token:
        session['viewer_token'] = viewer_token
        # Redirect to the same page without the token in the URL
        return redirect(url_for('groups.group_profile', puid=puid))
    # --- END BUG FIX ---

    group = get_group_by_puid(puid)
    if not group:
        flash('Group not found.', 'danger')
        return redirect(url_for('main.index'))

    # FEDERATION FIX: Redirect local users to the remote node when they try to view a remote group.
    # This part of the logic remains the same.
    current_viewer_is_local = 'username' in session and not session.get('is_federated_viewer')
    if group.get('hostname') and current_viewer_is_local:
        local_viewer = get_user_by_username(session['username'])
        remote_hostname = group['hostname']
        node = get_node_by_hostname(remote_hostname)

        if not node or not node['shared_secret']:
            flash(f'Cannot view remote group: Your node is not securely connected to {remote_hostname}.', 'danger')
            return redirect(request.referrer or url_for('main.index'))

        try:
            insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
            verify_ssl = not insecure_mode

            token_request_url = get_remote_node_api_url(
                remote_hostname,
                '/federation/api/v1/request_viewer_token',
                insecure_mode
            )

            # DARK MODE FIX: Get the local viewer's settings to send them to the remote node.
            local_viewer_settings = get_user_settings(local_viewer['id'])

            # The target is the group, but the endpoint is generic for any PUID
            payload = {
                'viewer_puid': local_viewer['puid'],
                'target_puid': puid,
                'viewer_settings': local_viewer_settings # Add settings to the payload
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

            response = requests.post(token_request_url, data=request_body, headers=headers, timeout=10,
                                     verify=verify_ssl)
            response.raise_for_status()

            token_data = response.json()
            new_viewer_token = token_data.get('viewer_token')

            if not new_viewer_token:
                raise Exception("Failed to retrieve a viewer token from the remote node.")

            protocol = 'http' if insecure_mode else 'https'
            remote_group_url = f"{protocol}://{remote_hostname}/group/{puid}"
            return redirect(f"{remote_group_url}?viewer_token={new_viewer_token}")

        except requests.exceptions.RequestException as e:
            flash(f"Error connecting to remote node: {e}", "danger")
            return redirect(request.referrer or url_for('main.index'))
        except Exception as e:
            flash(f"An error occurred while trying to view the remote group: {e}", "danger")
            traceback.print_exc()
            return redirect(request.referrer or url_for('main.index'))

    # ====================================================================
    # HEADER BAR FIX: Initialize viewer context variables
    # ====================================================================
    current_user = None
    current_viewer_id = None  # NEW: Added for clarity
    current_user_id = None
    is_federated_viewer = False  # NEW: Initialize explicitly
    viewer_home_url = None
    viewer_puid = None  # NEW: Added for header
    current_viewer_data = None  # NEW: Added for header
    viewer_is_admin = False
    
    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'
    
    # NEW: Get default user settings
    user_settings = get_user_settings(None)
    
    # ====================================================================
    # HEADER BAR FIX: Determine viewer context (federated or local)
    # ====================================================================
    if session.get('is_federated_viewer'):
        is_federated_viewer = True
        viewer_puid = session.get('federated_viewer_puid')
        current_user = get_user_by_puid(viewer_puid)
        if current_user:
            current_viewer_id = current_user['id']
            current_user_id = current_user['id']
            current_viewer_data = current_user  # NEW: Set for header
            viewer_home_url = f"{protocol}://{current_user['hostname']}"
            # NEW: Update settings with federated viewer's preferences
            if session.get('federated_viewer_settings'):
                user_settings.update(session.get('federated_viewer_settings'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
        if current_user:
            current_viewer_id = current_user['id']
            current_user_id = current_user['id']
            viewer_puid = current_user['puid']  # NEW: Set for header
            current_viewer_data = current_user  # NEW: Set for header
            viewer_is_admin = (current_user['user_type'] == 'admin')
            viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"
            # NEW: Get user-specific settings
            user_settings = get_user_settings(current_viewer_id)

    # Group membership and permissions
    is_member = False
    is_group_admin = False
    is_moderator_or_admin = False
    join_request_status = None
    pending_requests = []
    group_posts = []
    snoozed_friend_ids = set()
    viewer_blocked_by_map = {}

    if current_user:
        is_member = is_user_group_member(current_user['id'], group['id'])
        is_group_admin = is_user_group_admin(current_user['id'], group['id'])
        is_moderator_or_admin = is_user_group_moderator_or_admin(current_user['id'], group['id'])
        if not is_member:
            join_request_status = get_user_join_request_status(current_user['id'], group['id'])
        if is_moderator_or_admin:
            pending_requests = get_pending_join_requests(group['id'])

        snoozed_friend_ids = get_snoozed_friends(current_user['id'])
        viewer_blocked_by_map = get_who_blocked_user(current_user['id'])

    # Fetch group posts
    raw_group_posts = get_posts_for_group(
        group_puid=puid,
        viewer_user_id=current_user['id'] if current_user else None,
        is_member=is_member,
        viewer_is_admin=is_group_admin or session.get('is_admin', False),
        page=1,
        limit=20
    )

    # Filter snoozed/blocked content from posts and their comments
    for post in raw_group_posts:
        post['comments'] = filter_comments(post.get('comments', []), snoozed_friend_ids, viewer_blocked_by_map)
        group_posts.append(post)

    # Data for Sidebar
    members_full_list = get_group_members(group['id'])
    members_count = len(members_full_list)

    # THIS IS THE FIX: Fetch group_profile_info
    group_profile_info = get_group_profile_info(group['id'], is_member, is_group_admin)

    # Check if viewer can see members list based on privacy settings
    show_members_info = group_profile_info.get('show_members', {})
    can_view_members = is_member or is_group_admin

    if not can_view_members:
        # Check if members list is public
        if show_members_info.get('privacy_public'):
            can_view_members = True

    # Only show members list if viewer has permission
    if can_view_members:
        members = members_full_list
    else:
        members = []

    friends_in_group = []
    if current_user and is_member:
        friends_in_group = get_friends_in_group(current_user['id'], group['id'])

    group['profile_picture_muid'] = get_muid_by_media_path(
        group.get('original_profile_picture_path')
    )

    user_media_path = current_user.get('media_path') if current_user else None

    # Get media for the gallery
    all_gallery_media = get_media_for_group_gallery(puid, current_user_id, is_member,
                                                    is_group_admin or session.get('is_admin', False))
    latest_gallery_media = all_gallery_media[:10]

    # ====================================================================
    # HEADER BAR FIX: Get unread notification count
    # ====================================================================
    unread_count = 0
    if current_viewer_id and not is_federated_viewer:
        unread_count = get_unread_notification_count(current_viewer_id)

    # ====================================================================
    # FEDERATION FIX: Add hostname to group object for federated viewers
    # ====================================================================
    # For federated viewers, add hostname to group object so JavaScript knows it's remote
    if is_federated_viewer and current_user:
        # The group is local to this node, but remote from the viewer's perspective
        # Add the current node's hostname so JavaScript treats it as a remote group
        group = dict(group)  # Convert to dict if it's a Row object
        group['hostname'] = current_app.config.get('NODE_HOSTNAME')

    from db_queries.parental_controls import requires_parental_approval
    
    # Add to context
    current_user_requires_parental_approval = requires_parental_approval(current_user_id) if current_user_id else False

    # ====================================================================
    # HEADER BAR FIX: Updated return statement with all required variables
    # ====================================================================
    return render_template('group_profile.html',
                           group=group,
                           members=members,
                           is_member=is_member,
                           is_group_admin=is_group_admin,
                           is_moderator_or_admin=is_moderator_or_admin,
                           is_viewer_group_moderator=is_moderator_or_admin,
                           join_request_status=join_request_status,
                           pending_requests=pending_requests,
                           current_user_puid=current_user['puid'] if current_user else None,
                           current_user_id=current_user_id,
                           group_info=group_profile_info,
                           friends_in_group=friends_in_group,
                           user_media_path=user_media_path,
                           viewer_home_url=viewer_home_url,
                           group_posts=group_posts,
                           latest_gallery_media=latest_gallery_media,
                           total_media_count=len(all_gallery_media),
                           viewer_token=session.pop('viewer_token', None),
                           is_federated_viewer=is_federated_viewer,
                           # ===== NEW: Added these 5 variables for header bar =====
                           current_viewer_data=current_viewer_data,
                           viewer_puid=viewer_puid,
                           user_settings=user_settings,
                           unread_notification_count=unread_count,
                           members_count=members_count,
                           viewer_puid_for_js=viewer_puid,
                           current_user_requires_parental_approval=current_user_requires_parental_approval)


@groups_bp.route('/<puid>/gallery')
def group_media_gallery(puid):
    """Displays a group's full media gallery."""
    # --- START: Import ALL necessary functions ---
    from db_queries.groups import (get_group_by_puid, get_group_members, is_user_group_member,
                                   is_user_group_admin, is_user_group_moderator_or_admin,
                                   get_user_join_request_status, get_pending_join_requests,
                                   get_group_profile_info, get_friends_in_group)
    from db_queries.users import get_user_by_username, get_user_by_puid
    from db_queries.posts import get_muid_by_media_path, get_media_for_group_gallery
    from db_queries.settings import get_user_settings
    from db_queries.notifications import get_unread_notification_count
    # --- END: Import ALL necessary functions ---

    group = get_group_by_puid(puid)
    if not group:
        flash('Group not found.', 'danger')
        return redirect(url_for('main.index'))

    # --- START: Viewer Context Logic ---
    current_user = None
    current_viewer_id = None
    current_user_id = None
    is_federated_viewer = False
    viewer_home_url = None
    viewer_puid = None
    current_viewer_data = None
    viewer_is_admin = False
    
    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'
    
    user_settings = get_user_settings(None)
    
    if session.get('is_federated_viewer'):
        is_federated_viewer = True
        viewer_puid = session.get('federated_viewer_puid')
        current_user = get_user_by_puid(viewer_puid)
        if current_user:
            current_viewer_id = current_user['id']
            current_user_id = current_user['id']
            current_viewer_data = current_user
            viewer_home_url = f"{protocol}://{current_user['hostname']}"
            if session.get('federated_viewer_settings'):
                user_settings.update(session.get('federated_viewer_settings'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
        if current_user:
            current_viewer_id = current_user['id']
            current_user_id = current_user['id']
            viewer_puid = current_user['puid']
            current_viewer_data = current_user
            viewer_is_admin = (current_user['user_type'] == 'admin')
            viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"
            user_settings = get_user_settings(current_viewer_id)
    # --- END: Viewer Context Logic ---

    # --- START: Permissions & Sidebar Data Logic ---
    is_member = False
    is_group_admin = False
    is_moderator_or_admin = False
    join_request_status = None
    pending_requests = []

    if current_user:
        is_member = is_user_group_member(current_user['id'], group['id'])
        is_group_admin = is_user_group_admin(current_user['id'], group['id'])
        is_moderator_or_admin = is_user_group_moderator_or_admin(current_user['id'], group['id'])
        if not is_member:
            join_request_status = get_user_join_request_status(current_user['id'], group['id'])
        if is_moderator_or_admin:
            pending_requests = get_pending_join_requests(group['id'])

    # Data for Sidebar
    members_full_list = get_group_members(group['id'])
    members_count = len(members_full_list)

    # THIS IS THE FIX: Fetch group_profile_info
    group_profile_info = get_group_profile_info(group['id'], is_member, is_group_admin)

    # Check if viewer can see members list based on privacy settings
    show_members_info = group_profile_info.get('show_members', {})
    can_view_members = is_member or is_group_admin

    if not can_view_members:
        # Check if members list is public
        if show_members_info.get('privacy_public'):
            can_view_members = True

    # Only show members list if viewer has permission
    if can_view_members:
        members = members_full_list
    else:
        members = []

    friends_in_group = []
    if current_user and is_member:
        friends_in_group = get_friends_in_group(current_user['id'], group['id'])

    group['profile_picture_muid'] = get_muid_by_media_path(
        group.get('original_profile_picture_path')
    )

    # Get media for BOTH the gallery page AND the sidebar
    all_gallery_media = get_media_for_group_gallery(puid, current_user_id, is_member,
                                                    is_group_admin or session.get('is_admin', False) or viewer_is_admin)
    latest_gallery_media = all_gallery_media[:10] # For sidebar
    total_media_count = len(all_gallery_media) # For sidebar
    # --- END: Permissions & Sidebar Data Logic ---

    # --- START: Header Data Logic ---
    unread_count = 0
    if current_viewer_id and not is_federated_viewer:
        unread_count = get_unread_notification_count(current_viewer_id)
    # --- END: Header Data Logic ---

    # ====================================================================
    # FEDERATION FIX: Add hostname to group object for federated viewers
    # ====================================================================
    # For federated viewers, add hostname to group object so JavaScript knows it's remote
    if is_federated_viewer and current_user:
        # The group is local to this node, but remote from the viewer's perspective
        # Add the current node's hostname so JavaScript treats it as a remote group
        group = dict(group)  # Convert to dict if it's a Row object
        group['hostname'] = current_app.config.get('NODE_HOSTNAME')

    # --- FINAL RENDER (with all variables) ---
    return render_template('group_media_gallery.html',
                           group=group,
                           all_media=all_gallery_media, # For main content
                           # --- All the missing sidebar/header variables ---
                           members=members,
                           is_member=is_member,
                           is_group_admin=is_group_admin,
                           is_moderator_or_admin=is_moderator_or_admin,
                           join_request_status=join_request_status,
                           pending_requests=pending_requests,
                           current_user_puid=current_user['puid'] if current_user else None,
                           current_user_id=current_user_id,
                           group_info=group_profile_info, # <-- THE FIX
                           friends_in_group=friends_in_group,
                           viewer_home_url=viewer_home_url,
                           latest_gallery_media=latest_gallery_media, # For sidebar
                           total_media_count=total_media_count, # For sidebar
                           viewer_token=session.pop('viewer_token', None),
                           is_federated_viewer=is_federated_viewer,
                           current_viewer_data=current_viewer_data,
                           viewer_puid=viewer_puid,
                           user_settings=user_settings,
                           unread_notification_count=unread_count,
                           members_count=members_count,
                           viewer_puid_for_js=viewer_puid)


@groups_bp.route('/<puid>/create_post', methods=['POST'])
def create_group_post(puid):
    """
    Handles the creation of a new post within a group by both local and remote users.
    """
    from db_queries.groups import get_group_by_puid, is_user_group_member
    from db_queries.users import get_user_by_username, get_user_by_puid
    from db_queries.posts import add_post
    from utils.federation_utils import distribute_post

    # FEDERATION FIX: Identify the user based on their session type.
    current_user = None
    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if not viewer_puid:
            flash('Your secure session has expired. Please go back to your home node and navigate to this group again.',
                  'danger')
            return redirect(request.referrer or url_for('main.index'))
        current_user = get_user_by_puid(viewer_puid)
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
    else:
        flash('Please log in to post in groups.', 'danger')
        return redirect(url_for('auth.login'))

    if not current_user:
        flash('Could not identify you as an authenticated user.', 'danger')
        return redirect(url_for('auth.login'))

    group = get_group_by_puid(puid)
    if not group:
        flash('Group not found.', 'danger')
        return redirect(url_for('main.index'))

    # This membership check now works for both local and remote users.
    if not is_user_group_member(current_user['id'], group['id']):
        flash('You must be a member of this group to post.', 'danger')
        return redirect(url_for('groups.group_profile', puid=puid))

    content = request.form.get('content')
    selected_media_files_json = request.form.get('selected_media_files', '[]')
    media_files_for_db = json.loads(selected_media_files_json) if selected_media_files_json else []
    privacy_setting = request.form.get('privacy_setting', 'group')
    
    # PARENTAL CONTROL CHECK: Prevent children from making public posts in groups
    from db_queries.parental_controls import requires_parental_approval
    
    if requires_parental_approval(current_user['id']) and privacy_setting == 'public':
        flash('You cannot create public posts while parental controls are active.', 'warning')
        return redirect(url_for('groups.group_profile', puid=puid))

    # NEW: Get tagged users and location
    tagged_user_puids_json = request.form.get('tagged_users', '[]')
    tagged_user_puids = json.loads(tagged_user_puids_json) if tagged_user_puids_json else []
    location = request.form.get('location', '').strip() or None

    if not content and not media_files_for_db:
        flash('Post content or media cannot be empty.', 'danger')
        return redirect(url_for('groups.group_profile', puid=puid))

    # NEW: Get poll data if provided
    poll_data_json = request.form.get('poll_data', '')
    poll_data = None
    if poll_data_json:
        try:
            poll_data = json.loads(poll_data_json)
            if poll_data and not content.strip():
                flash("You can't create a poll without text in your post.", 'danger')
                return redirect(url_for('groups.group_profile', puid=puid))
        except json.JSONDecodeError:
            poll_data = None

    try:
        # The add_post function is called with the user's ID (local or remote stub)
        # and their hostname if they are a remote user.
        post_cuid = add_post(
            user_id=current_user['id'],
            profile_user_id=None,
            content=content,
            privacy_setting=privacy_setting,
            media_files=media_files_for_db,
            group_puid=puid,
            author_hostname=current_user.get('hostname'),
            tagged_user_puids=tagged_user_puids,  # NEW
            location=location,
            poll_data=poll_data
        )

        if post_cuid:
            distribute_post(post_cuid)
            if poll_data:
                from utils.federation_utils import distribute_poll_data
                time.sleep(0.5)
                distribute_poll_data(post_cuid)
            flash('Post created successfully!', 'success')
        else:
            flash('Failed to create post.', 'danger')
    except Exception as e:
        flash(f'An error occurred: {e}', 'danger')
        traceback.print_exc()

    return redirect(url_for('groups.group_profile', puid=puid))


@groups_bp.route('/my_groups/') # <-- MODIFICATION: Added trailing slash
def my_groups():
    """
    MODIFICATION: This route now renders the main index.html "shell"
    and tells the client-side router to load the "My Groups" content.
    """
    # Imports moved inside function
    from db_queries.users import get_user_by_username

    if 'username' not in session:
        flash('Please log in to view your groups.', 'danger')
        return redirect(url_for('auth.login'))

    current_user = get_user_by_username(session['username'])
    if not current_user:
        flash('User not found.', 'danger')
        return redirect(url_for('main.index'))

    # NEW: Fetch all the data needed for the header/sidebar, just like index()
    user_media_path = current_user['media_path']
    current_user_puid = current_user['puid']
    current_user_profile = current_user
    
    viewer_home_url = None
    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'
    viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"

    # NEW: Pass the URL for the "My Groups" content to load
    initial_content_url = url_for('groups.get_my_groups_content')

    return render_template('index.html',
                           username=session.get('username'),
                           user_media_path=user_media_path,
                           current_user_puid=current_user_puid,
                           current_user_id=current_user['id'],
                           current_user_profile=current_user_profile,
                           viewer_home_url=viewer_home_url,
                           viewer_puid_for_js=current_user_puid,
                           initial_content_url=initial_content_url)


@groups_bp.route('/api/page/my_groups')
def get_my_groups_content():
    """
    API endpoint to fetch the HTML for the "My Groups" content.
    """
    from db_queries.groups import get_user_groups, get_user_outgoing_join_requests
    from db_queries.users import get_user_by_username

    if 'username' not in session:
        # API route should return error, not redirect
        return jsonify({'error': 'Authentication required.'}), 401

    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found.'}), 404

    groups = get_user_groups(current_user['id'])
    outgoing_requests = get_user_outgoing_join_requests(current_user['id'])

    # Render the *partial* template
    return render_template('_my_groups_content.html', 
                           groups=groups, 
                           pending_requests=outgoing_requests)


@groups_bp.route('/discover')
def discover_groups_api():
    """API endpoint to get discoverable groups, including from remote nodes."""
    # Import locally to avoid circular dependencies
    from app import inject_user_data_functions
    from db_queries.groups import get_all_groups, is_user_group_member, get_user_join_request_status, get_or_create_remote_group_stub
    from db_queries.users import get_user_by_username
    from db_queries.federation import get_all_connected_nodes, get_node_by_hostname

    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'Current user not found'}), 404
    
    # Get hidden groups for current user
    hidden_group_ids = get_hidden_items(current_user['id'], 'group')

    # Get the URL generation helper function
    url_helpers = inject_user_data_functions()
    federated_group_profile_url = url_helpers['federated_group_profile_url']

    local_groups = get_all_groups()
    discoverable_groups = []
    added_puids = set() # Keep track of added PUIDs to prevent duplicates
    local_hostname = current_app.config.get('NODE_HOSTNAME')

    for group in local_groups:
        # BUG FIX: Exclude remote group stubs from the local discovery list.
        if group['is_remote']:
            continue

        # Skip if hidden by user
        if group['id'] in hidden_group_ids:
            continue

        is_member = is_user_group_member(current_user['id'], group['id'])
        join_status = get_user_join_request_status(current_user['id'], group['id'])
        if not is_member and join_status != 'pending':
            group['node_hostname'] = local_hostname
            group['node_nickname'] = 'Local'
            # FEATURE: Add the pre-generated profile URL
            group['profile_url'] = federated_group_profile_url(group)
            discoverable_groups.append(group)
            added_puids.add(group['puid'])

    connected_nodes = get_all_connected_nodes()
    for node in connected_nodes:
        if node['status'] != 'connected' or not node['shared_secret']:
            continue

        try:
            insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
            verify_ssl = not insecure_mode

            remote_url = get_remote_node_api_url(
                node['hostname'],
                '/federation/api/v1/discover_groups',
                insecure_mode
            )

            if not local_hostname:
                print("ERROR: NODE_HOSTNAME is not configured. Federation calls will likely fail.")
                continue

            request_body = b''
            signature = hmac.new(
                node['shared_secret'].encode('utf-8'),
                msg=request_body,
                digestmod=hashlib.sha256
            ).hexdigest()

            headers = {
                'X-Node-Hostname': local_hostname,
                'X-Node-Signature': signature
            }

            response = requests.get(remote_url, headers=headers, timeout=5, verify=verify_ssl)
            response.raise_for_status()

            remote_groups_data = response.json()

            for group_data in remote_groups_data:
                remote_group_puid = group_data.get('puid')
                if not remote_group_puid:
                    print(f"WARN: Skipping group data with missing PUID from {node['hostname']}")
                    continue

                if remote_group_puid in added_puids:
                    print(f"DEBUG: Skipping duplicate group {remote_group_puid} received from {node['hostname']}.")
                    continue
                
                # --- FEDERATION FIX: Check for the group's *true* origin hostname ---
                origin_hostname = group_data.get('hostname')
                
                # If the origin_hostname is our own, skip it.
                if origin_hostname == local_hostname:
                    continue

                # The hostname we will create the stub with is the *origin* hostname,
                # not the node we are currently querying.
                stub_hostname = origin_hostname or node['hostname']

                print(f"DEBUG: Checking remote group: {group_data.get('name')} ({remote_group_puid}) from {stub_hostname}")

                # We must create a local stub for the remote group to check relationships
                group_stub = get_or_create_remote_group_stub(
                    puid=remote_group_puid,
                    name=group_data.get('name'),
                    description=group_data.get('description'),
                    profile_picture_path=group_data.get('profile_picture_path'),
                    hostname=stub_hostname # Use the correct origin hostname!
                )

                is_related = False
                if group_stub:
                    is_member = is_user_group_member(current_user['id'], group_stub['id'])
                    join_status = get_user_join_request_status(current_user['id'], group_stub['id'])
                    if is_member or join_status == 'pending':
                        is_related = True
                else:
                    print(f"DEBUG: Could not get/create local stub for {remote_group_puid}.")

                print(f"DEBUG: Group {remote_group_puid} is_related = {is_related}")

                # Skip if hidden by user
                if group_stub and group_stub['id'] in hidden_group_ids:
                    print(f"DEBUG: Skipping hidden group {remote_group_puid}.")
                    continue

                if not is_related:
                    # --- FEDERATION FIX ---
                    # Now that the stub is created (or existed) with the correct origin hostname,
                    # we can build the profile card for the UI.
                    
                    if origin_hostname:
                        # This group is from a *different* node (Node A) that Node B told us about.
                        # We need to find *our* connection details for Node A, if any.
                        origin_node = get_node_by_hostname(origin_hostname)
                        group_data['node_hostname'] = origin_hostname
                        # Use the nickname *we* have for Node A, or just Node A's hostname
                        group_data['node_nickname'] = origin_node['nickname'] if origin_node else origin_hostname
                    else:
                        # This group is local to Node B. Use Node B's info.
                        group_data['node_hostname'] = node['hostname']
                        group_data['node_nickname'] = node['nickname'] or node['hostname']
                    
                    # FEATURE: Add the pre-generated profile URL for remote groups
                    group_data['profile_url'] = federated_group_profile_url(group_data)
                    discoverable_groups.append(group_data)
                    added_puids.add(remote_group_puid)
                    print(f"DEBUG: Added remote group {remote_group_puid} ({group_data.get('name')}) from {group_data['node_hostname']} to discoverable list.")
                else:
                    print(f"DEBUG: Skipping related group {remote_group_puid} from {stub_hostname}.")

        except requests.exceptions.RequestException as e:
            print(f"ERROR: Could not fetch groups from node {node['hostname']}: {e}")
        except Exception as e:
            print(f"ERROR: An unexpected error occurred while fetching groups from {node['hostname']}: {e}")

    return jsonify(discoverable_groups)


def send_remote_group_join_request(group_data, sender):
    """
    Acts as a proxy to send a join request from a user to a remote group after creating a local stub.
    Supports both local users and federated viewers.
    """
    from db_queries.federation import get_node_by_hostname, get_or_create_targeted_subscription
    from db_queries.groups import get_or_create_remote_group_stub, send_join_request

    if not sender:
        return jsonify({'error': 'Could not identify sender.'}), 401

    group_hostname = group_data.get('node_hostname')
    group_puid = group_data.get('puid')
    group_name = group_data.get('name', 'Unknown Group')
    
    # TARGETED SUBSCRIPTION: Check for connection and create targeted subscription if needed
    node = get_node_by_hostname(group_hostname)
    if not node or node['status'] != 'connected' or not node['shared_secret']:
        # No connection exists, create a targeted subscription
        print(f"No connection to {group_hostname}, creating targeted subscription for group {group_name}")
        node = get_or_create_targeted_subscription(
            group_hostname,
            'group',
            group_puid,
            group_name
        )
        
        if not node:
            return jsonify({'error': 'Unable to establish connection to the remote node. Please try again later.'}), 500

    # Create the local stub for the remote group
    group_stub = get_or_create_remote_group_stub(
        puid=group_data.get('puid'),
        name=group_data.get('name'),
        description=group_data.get('description'),
        profile_picture_path=group_data.get('profile_picture_path'),
        hostname=group_hostname
    )

    if not group_stub:
        return jsonify({'error': 'Failed to create a local record for the remote group.'}), 500

    # Create the local 'pending' join request record
    send_join_request(group_stub['id'], sender['id'])

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
            "group_puid": group_data.get('puid'),
            "requester_data": {
                "puid": sender['puid'],
                "display_name": sender['display_name'],
                "profile_picture_path": sender['profile_picture_path'],
                "hostname": local_hostname
            },
            # NEW: Include join request responses
            "rules_agreed": group_data.get('rules_agreed', False),
            "question_responses": group_data.get('question_responses', {})
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

        return jsonify(response.json()), response.status_code

    except requests.exceptions.RequestException as e:
        print(f"ERROR proxying group join request to {group_hostname}: {e}")
        return jsonify({'error': f'Failed to connect to the remote node: {e}'}), 500
    except Exception as e:
        print(f"ERROR in send_remote_group_join_request: {e}")
        traceback.print_exc()
        return jsonify({'error': 'An unexpected error occurred.'}), 500


@groups_bp.route('/join/<puid>', methods=['POST'])
def join_group(puid):
    """Sends a request to join a group, handling remote groups."""
    from db_queries.groups import get_group_by_puid, send_join_request
    from db_queries.users import get_user_by_username, get_user_by_puid

    # Correctly identify the user from either a local or federated session
    current_user = None
    is_federated_viewer = session.get('is_federated_viewer', False)
    
    if 'username' in session:
        current_user = get_user_by_username(session['username'])
    elif is_federated_viewer:
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))

    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json()

    # PARENTAL CONTROL CHECK - Intercept remote group join requests for users requiring approval
    # Only check if this is a remote group (has hostname)
    group_hostname = None
    if data:
        group_hostname = data.get('hostname') or data.get('node_hostname')
    
    if not is_federated_viewer and group_hostname and group_hostname != current_app.config.get('NODE_HOSTNAME'):
        # This is a local user trying to join a remote group
        from db_queries.parental_controls import requires_parental_approval, create_approval_request, get_all_parent_ids
        from db_queries.notifications import create_notification
        
        if requires_parental_approval(current_user['id']):
            # Get group info for the approval request
            group_info = data if data else {}
            
            request_data = json.dumps({
                'group_puid': puid,
                'group_name': group_info.get('name', 'Unknown Group'),
                'group_hostname': group_hostname,
                'rules_agreed': data.get('rules_agreed', False),
                'question_responses': data.get('question_responses', {})
            })
            
            approval_id = create_approval_request(
                current_user['id'],
                'group_join_remote',
                puid,
                group_hostname,
                request_data
            )
            
            if approval_id:
                # Get ALL parents for notification
                parent_ids = get_all_parent_ids(current_user['id'])
                
                # Notify all parents
                for parent_id in parent_ids:
                    create_notification(parent_id, current_user['id'], 'parental_approval_needed')
                
                return jsonify({
                    'status': 'info',
                    'message': 'Group join request pending parental approval.'
                }), 200
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to create approval request.'
                }), 500
    
    # Extract join request responses
    rules_agreed = data.get('rules_agreed', False)
    question_responses = data.get('question_responses', {})

    # The group object from the group_profile page has a 'hostname' key,
    # while the one from the discover modal has 'node_hostname'.
    group_hostname = None
    if data:
        group_hostname = data.get('hostname') or data.get('node_hostname')

    # Only proxy when a LOCAL user is joining a REMOTE group
    # Federated viewers join directly on the node they're visiting
    if not is_federated_viewer and group_hostname and group_hostname != current_app.config.get('NODE_HOSTNAME'):
        # Local user joining a remote group - proxy through their home node
        data['node_hostname'] = group_hostname
        data['rules_agreed'] = rules_agreed
        data['question_responses'] = question_responses
        return send_remote_group_join_request(data, current_user)

    # Handle as a local join (local user + local group, OR federated viewer + any group)
    group = get_group_by_puid(puid)
    if not group:
        return jsonify({'error': 'Group not found'}), 404

    # PARENTAL CONTROL CHECK for federated viewers
    # If a federated viewer requires parental approval, notify their home node
    if is_federated_viewer and current_user.get('hostname'):
        # Check if this federated user requires parental approval on their home node
        from db_queries.federation import check_remote_user_parental_controls
        
        requires_approval = check_remote_user_parental_controls(current_user)
        
        if requires_approval:
            # Notify the user's home node to create an approval request
            from db_queries.federation import notify_home_node_of_group_join_attempt
            
            success = notify_home_node_of_group_join_attempt(
                current_user,
                group,
                rules_agreed,
                question_responses
            )
            
            if success:
                return jsonify({
                    'status': 'info',
                    'message': 'Group join request sent to your parent for approval.'
                }), 200
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to send approval request to your home node.'
                }), 500

    # Pass rules_agreed and question_responses to send_join_request
    success, message = send_join_request(
        group['id'], 
        current_user['id'],
        rules_agreed=rules_agreed,
        question_responses=question_responses
    )

    if success:
        # FEDERATION FIX: If this is a federated user, notify their home node
        if current_user.get('hostname'):
            from db_queries.federation import notify_remote_node_of_group_join_request
            notify_remote_node_of_group_join_request(current_user, group)
        
        return jsonify({'status': 'success', 'message': message})
    else:
        return jsonify({'status': 'error', 'message': message}), 500

@groups_bp.route('/join_settings/<puid>', methods=['GET'])
def get_join_settings(puid):
    """Gets the join rules and questions for a group."""
    from db_queries.groups import get_group_by_puid, get_group_join_settings, is_user_group_member
    from db_queries.users import get_user_by_username, get_user_by_puid
    from db_queries.federation import get_node_by_hostname
    
    group = get_group_by_puid(puid)
    if not group:
        return jsonify({'error': 'Group not found'}), 404
    
    # Get current user (local or federated)
    current_user = None
    if 'username' in session:
        current_user = get_user_by_username(session['username'])
    elif session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    
    # If group is remote and user is local, proxy the request to the remote node
    if group.get('hostname') and 'username' in session:
        remote_hostname = group['hostname']
        node = get_node_by_hostname(remote_hostname)
        
        if not node or not node['shared_secret']:
            return jsonify({'error': f'Not connected to {remote_hostname}'}), 503
        
        try:
            insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
            verify_ssl = not insecure_mode
            local_hostname = current_app.config.get('NODE_HOSTNAME')
            
            remote_url = get_remote_node_api_url(
                remote_hostname,
                f'/federation/api/v1/group_join_settings/{puid}',
                insecure_mode
            )
            
            # Create empty payload for GET-style request
            request_body = b''
            signature = hmac.new(
                node['shared_secret'].encode('utf-8'),
                msg=request_body,
                digestmod=hashlib.sha256
            ).hexdigest()
            
            headers = {
                'X-Node-Hostname': local_hostname,
                'X-Node-Signature': signature
            }
            
            response = requests.get(remote_url, headers=headers, timeout=10, verify=verify_ssl)
            response.raise_for_status()
            
            return jsonify(response.json()), response.status_code
            
        except requests.exceptions.RequestException as e:
            print(f"ERROR fetching join settings from {remote_hostname}: {e}")
            return jsonify({'error': f'Failed to connect to remote node: {e}'}), 500
        except Exception as e:
            print(f"ERROR in get_join_settings proxy: {e}")
            traceback.print_exc()
            return jsonify({'error': 'An unexpected error occurred'}), 500
    
    # For local groups (or remote users viewing local groups), continue with existing logic
    # Check if user is a member
    is_member = False
    if current_user:
        is_member = is_user_group_member(current_user['id'], group['id'])
    
    settings = get_group_join_settings(group['id'])
    
    # Apply privacy filtering
    # If rules are members-only and user is not a member, hide them
    if not settings.get('join_rules_public') and not is_member:
        settings['join_rules'] = None
    
    # Questions are always shown to everyone (so they can answer before joining)
    # Rules can be hidden if privacy is set to members-only
    
    return jsonify(settings)

@groups_bp.route('/invite_friends/<group_puid>', methods=['GET'])
def invite_friends(group_puid):
    """API endpoint to get a list of friends who can be invited to the group."""
    from db_queries.groups import get_group_by_puid, get_friends_to_invite
    from db_queries.users import get_user_by_username

    if 'username' not in session:
        return jsonify({'error': 'Authentication required'}), 401

    current_user = get_user_by_username(session['username'])
    group = get_group_by_puid(group_puid)

    if not current_user or not group:
        return jsonify({'error': 'User or group not found'}), 404

    friends = get_friends_to_invite(current_user['id'], group['id'])

    return jsonify(friends)

@groups_bp.route('/invite/<group_puid>/<user_puid>', methods=['POST'])
def send_invite_route(group_puid, user_puid):
    """API endpoint to send a group invitation from the current user to another user."""
    from db_queries.groups import get_group_by_puid, send_group_invite
    from db_queries.users import get_user_by_username, get_user_by_puid

    if 'username' not in session:
        return jsonify({'error': 'Authentication required'}), 401

    sender = get_user_by_username(session['username'])
    group = get_group_by_puid(group_puid)
    receiver = get_user_by_puid(user_puid)

    if not all([sender, group, receiver]):
        return jsonify({'error': 'Invalid sender, group, or receiver.'}), 404

    success, message = send_group_invite(group['id'], sender['id'], receiver['id'])

    if success:
        return jsonify({'status': 'success', 'message': message}), 200
    else:
        return jsonify({'status': 'error', 'message': message}), 400


@groups_bp.route('/update_info/<puid>', methods=['POST'])
def update_group_info(puid):
    """Handles updates to the group's 'About' section info."""
    from db_queries.groups import get_group_by_puid, is_user_group_admin, update_group_profile_info_field
    from db_queries.users import get_user_by_username

    if 'username' not in session:
        return jsonify({'error': 'Authentication required'}), 401

    current_user = get_user_by_username(session['username'])
    group = get_group_by_puid(puid)

    if not current_user or not group:
        return jsonify({'error': 'User or Group not found'}), 404

    if not is_user_group_admin(current_user['id'], group['id']):
        return jsonify({'error': 'You do not have permission to edit this group.'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request data'}), 400

    profile_fields = data.get('profile_fields', {})
    for field_name, field_data in profile_fields.items():
        update_group_profile_info_field(
            group_id=group['id'],
            field_name=field_name,
            field_value=field_data.get('value'),
            privacy_public=1 if field_data.get('privacy_public') else 0,
            privacy_members_only=1 if field_data.get('privacy_members_only') else 0
        )

    return jsonify({'message': 'Group information updated successfully!'}), 200

@groups_bp.route('/update_join_settings/<puid>', methods=['POST'])
def update_join_settings_route(puid):
    """Updates the join rules and questions for a group (admin only)."""
    from db_queries.groups import get_group_by_puid, is_user_group_admin, update_group_join_settings, update_group_profile_info_field
    from db_queries.users import get_user_by_username

    if 'username' not in session:
        return jsonify({'error': 'Authentication required'}), 401

    current_user = get_user_by_username(session['username'])
    group = get_group_by_puid(puid)

    if not current_user or not group:
        return jsonify({'error': 'User or Group not found'}), 404

    if not is_user_group_admin(current_user['id'], group['id']):
        return jsonify({'error': 'You do not have permission to edit join settings.'}), 403

    data = request.get_json()
    join_rules = data.get('join_rules')
    join_questions = data.get('join_questions', [])
    
    # NEW: Get privacy settings for join_rules
    join_rules_public = data.get('join_rules_public', False)
    join_rules_members = data.get('join_rules_members', True)

    # Store join_rules in group_profile_info table with privacy settings
    update_group_profile_info_field(
        group_id=group['id'],
        field_name='join_rules',
        field_value=join_rules,
        privacy_public=1 if join_rules_public else 0,
        privacy_members_only=1 if join_rules_members else 0
    )
    
    # Store join_questions in groups table
    success, message = update_group_join_settings(group['id'], None, join_questions)
    
    if success:
        return jsonify({'message': 'Join settings updated successfully!'}), 200
    else:
        return jsonify({'error': message}), 500

# --- Group Admin Actions ---

@groups_bp.route('/<group_puid>/update_role/<user_puid>', methods=['POST'])
def update_member_role_route(group_puid, user_puid):
    """Updates a member's role in a group."""
    from db_queries.groups import get_group_by_puid, update_group_member_role
    from db_queries.users import get_user_by_username, get_user_by_puid

    if 'username' not in session:
        flash('Authentication required.', 'danger')
        return redirect(request.referrer)

    acting_user = get_user_by_username(session['username'])
    group = get_group_by_puid(group_puid)
    target_user = get_user_by_puid(user_puid)
    new_role = request.form.get('new_role')

    if not all([acting_user, group, target_user, new_role]):
        flash('Invalid request. User, group, or role not found.', 'danger')
        return redirect(request.referrer)

    if new_role not in ['admin', 'moderator', 'member']:
        flash('Invalid role specified.', 'danger')
        return redirect(request.referrer)

    success, message = update_group_member_role(group['id'], target_user['id'], new_role, acting_user['id'])
    flash(message, 'success' if success else 'danger')
    return redirect(request.referrer)


@groups_bp.route('/accept_request/<int:request_id>', methods=['POST'])
def accept_join_request_route(request_id):
    """Accepts a join request for a group."""
    # MODIFICATION: Import is_user_group_moderator_or_admin
    from db_queries.groups import get_join_request_by_id, is_user_group_admin, accept_join_request, is_user_group_moderator_or_admin
    from db_queries.users import get_user_by_username
    from db_queries.notifications import create_notification

    if 'username' not in session:
        flash('Authentication required.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    current_user = get_user_by_username(session['username'])
    request_data = get_join_request_by_id(request_id)

    if not request_data:
        flash('Join request not found.', 'danger')
        return redirect(request.referrer)

    # MODIFICATION: Allow moderators to accept requests
    if not is_user_group_moderator_or_admin(current_user['id'], request_data['group_id']):
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(request.referrer)

    success, message = accept_join_request(request_id)
    if success:
        # FEDERATION FIX: Only create local notification for local users
        # Remote users get notified via federation (handled in accept_join_request)
        if not request_data.get('hostname'):
            create_notification(
                user_id=request_data['user_id'],
                actor_id=current_user['id'],
                type='group_request_accepted',
                group_id=request_data['group_id']
            )

    flash(message, 'success' if success else 'danger')
    return redirect(request.referrer)


@groups_bp.route('/reject_request/<int:request_id>', methods=['POST'])
def reject_join_request_route(request_id):
    """Rejects a join request for a group."""
    # MODIFICATION: Import is_user_group_moderator_or_admin
    from db_queries.groups import get_join_request_by_id, is_user_group_admin, reject_join_request, is_user_group_moderator_or_admin
    from db_queries.users import get_user_by_username
    from db_queries.notifications import create_notification

    if 'username' not in session:
        flash('Authentication required.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    current_user = get_user_by_username(session['username'])
    request_data = get_join_request_by_id(request_id)

    if not request_data:
        flash('Join request not found.', 'danger')
        return redirect(request.referrer)

    # MODIFICATION: Allow moderators to reject requests
    if not is_user_group_moderator_or_admin(current_user['id'], request_data['group_id']):
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(request.referrer)

    success, message = reject_join_request(request_id)
    if success:
        create_notification(
            user_id=request_data['user_id'],
            actor_id=current_user['id'],
            type='group_request_rejected',
            group_id=request_data['group_id']
        )
    flash(message, 'info' if success else 'danger')
    return redirect(request.referrer)


@groups_bp.route('/<group_puid>/kick/<user_puid>', methods=['POST'])
def kick_member_route(group_puid, user_puid):
    """Kicks a member from a group."""
    from db_queries.groups import get_group_by_puid, is_user_group_moderator_or_admin, kick_group_member, is_user_group_admin
    from db_queries.users import get_user_by_username, get_user_by_puid
    from db import get_db

    if 'username' not in session:
        flash('Authentication required.', 'danger')
        return redirect(request.referrer)

    current_user = get_user_by_username(session['username'])
    group = get_group_by_puid(group_puid)
    member_to_kick = get_user_by_puid(user_puid)

    if not group or not member_to_kick:
        flash('Group or user not found.', 'danger')
        return redirect(request.referrer)

    if not is_user_group_moderator_or_admin(current_user['id'], group['id']):
        flash('You do not have permission to kick members.', 'danger')
        return redirect(request.referrer)

    # Safeguard: Prevent moderators from kicking other moderators or admins
    is_acting_user_admin = is_user_group_admin(current_user['id'], group['id'])
    if not is_acting_user_admin:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT role FROM group_members WHERE group_id = ? AND user_id = ?", (group['id'], member_to_kick['id']))
        target_member_row = cursor.fetchone()
        target_member = dict(target_member_row) if target_member_row else None
        if target_member and target_member['role'] in ['admin', 'moderator']:
            flash('Moderators cannot kick other moderators or admins.', 'danger')
            return redirect(request.referrer)

    success, message = kick_group_member(group['id'], member_to_kick['id'])
    flash(message, 'success' if success else 'danger')
    return redirect(request.referrer)


@groups_bp.route('/<group_puid>/ban/<user_puid>', methods=['POST'])
def ban_member_route(group_puid, user_puid):
    """Bans a member from a group."""
    from db_queries.groups import get_group_by_puid, is_user_group_moderator_or_admin, ban_group_member, is_user_group_admin
    from db_queries.users import get_user_by_username, get_user_by_puid
    from db import get_db

    if 'username' not in session:
        flash('Authentication required.', 'danger')
        return redirect(request.referrer)

    current_user = get_user_by_username(session['username'])
    group = get_group_by_puid(group_puid)
    member_to_ban = get_user_by_puid(user_puid)

    if not group or not member_to_ban:
        flash('Group or user not found.', 'danger')
        return redirect(request.referrer)

    if not is_user_group_moderator_or_admin(current_user['id'], group['id']):
        flash('You do not have permission to ban members.', 'danger')
        return redirect(request.referrer)

    # Safeguard: Prevent moderators from banning other moderators or admins
    is_acting_user_admin = is_user_group_admin(current_user['id'], group['id'])
    if not is_acting_user_admin:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT role FROM group_members WHERE group_id = ? AND user_id = ?", (group['id'], member_to_ban['id']))
        target_member_row = cursor.fetchone()
        target_member = dict(target_member_row) if target_member_row else None
        if target_member and target_member['role'] in ['admin', 'moderator']:
            flash('Moderators cannot ban other moderators or admins.', 'danger')
            return redirect(request.referrer)

    success, message = ban_group_member(group['id'], member_to_ban['id'])
    flash(message, 'success' if success else 'danger')
    return redirect(request.referrer)


@groups_bp.route('/<group_puid>/unban/<user_puid>', methods=['POST'])
def unban_member_route(group_puid, user_puid):
    """Unbans a member from a group."""
    from db_queries.groups import get_group_by_puid, is_user_group_moderator_or_admin, unban_group_member
    from db_queries.users import get_user_by_username, get_user_by_puid

    if 'username' not in session:
        flash('Authentication required.', 'danger')
        return redirect(request.referrer)

    current_user = get_user_by_username(session['username'])
    group = get_group_by_puid(group_puid)
    member_to_unban = get_user_by_puid(user_puid)

    if not group or not member_to_unban:
        flash('Group or user not found.', 'danger')
        return redirect(request.referrer)

    if not is_user_group_moderator_or_admin(current_user['id'], group['id']):
        flash('You do not have permission to unban members.', 'danger')
        return redirect(request.referrer)

    success, message = unban_group_member(group['id'], member_to_unban['id'])
    flash(message, 'success' if success else 'danger')
    return redirect(request.referrer)


@groups_bp.route('/<group_puid>/snooze/<user_puid>', methods=['POST'])
def snooze_member_route(group_puid, user_puid):
    """Snoozes a member in a group for 30 days."""
    from db_queries.groups import get_group_by_puid, is_user_group_moderator_or_admin, snooze_group_member, is_user_group_admin
    from db_queries.users import get_user_by_username, get_user_by_puid
    from db import get_db

    if 'username' not in session:
        flash('Authentication required.', 'danger')
        return redirect(request.referrer)

    current_user = get_user_by_username(session['username'])
    group = get_group_by_puid(group_puid)
    member_to_snooze = get_user_by_puid(user_puid)

    if not group or not member_to_snooze:
        flash('Group or user not found.', 'danger')
        return redirect(request.referrer)

    if not is_user_group_moderator_or_admin(current_user['id'], group['id']):
        flash('You do not have permission to snooze members.', 'danger')
        return redirect(request.referrer)

    # Safeguard: Prevent moderators from snoozing other moderators or admins
    is_acting_user_admin = is_user_group_admin(current_user['id'], group['id'])
    if not is_acting_user_admin:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT role FROM group_members WHERE group_id = ? AND user_id = ?", (group['id'], member_to_snooze['id']))
        target_member_row = cursor.fetchone()
        target_member = dict(target_member_row) if target_member_row else None
        if target_member and target_member['role'] in ['admin', 'moderator']:
            flash('Moderators cannot snooze other moderators or admins.', 'danger')
            return redirect(request.referrer)

    success, message = snooze_group_member(group['id'], member_to_snooze['id'])
    flash(message, 'success' if success else 'danger')
    return redirect(request.referrer)


@groups_bp.route('/<group_puid>/unsnooze/<user_puid>', methods=['POST'])
def unsnooze_member_route(group_puid, user_puid):
    """Unsnoozes a member in a group."""
    from db_queries.groups import get_group_by_puid, is_user_group_moderator_or_admin, unsnooze_group_member
    from db_queries.users import get_user_by_username, get_user_by_puid

    if 'username' not in session:
        flash('Authentication required.', 'danger')
        return redirect(request.referrer)

    current_user = get_user_by_username(session['username'])
    group = get_group_by_puid(group_puid)
    member_to_unsnooze = get_user_by_puid(user_puid)

    if not group or not member_to_unsnooze:
        flash('Group or user not found.', 'danger')
        return redirect(request.referrer)

    if not is_user_group_moderator_or_admin(current_user['id'], group['id']):
        flash('You do not have permission to unsnooze members.', 'danger')
        return redirect(request.referrer)

    success, message = unsnooze_group_member(group['id'], member_to_unsnooze['id'])
    flash(message, 'success' if success else 'danger')
    return redirect(request.referrer)


@groups_bp.route('/<puid>/upload_picture', methods=['POST'])
def upload_group_picture(puid):
    """Handles uploading a profile picture for a group by an admin."""
    from db_queries.groups import get_group_by_puid, is_user_group_admin, update_group_profile_picture_path
    from db_queries.users import get_user_by_username

    if 'username' not in session:
        flash('Please log in to upload a group picture.', 'danger')
        return redirect(url_for('auth.login'))

    current_user = get_user_by_username(session['username'])
    group = get_group_by_puid(puid)

    if not current_user or not group:
        flash('User or group not found.', 'danger')
        return redirect(url_for('main.index'))

    if not is_user_group_admin(current_user['id'], group['id']):
        flash('You do not have permission to change this group\'s picture.', 'danger')
        return redirect(url_for('groups.group_profile', puid=puid))

    profile_picture_path = None
    original_profile_picture_path = None

    group_profile_pic_dir = os.path.join(current_app.config['PROFILE_PICTURE_STORAGE_DIR'], 'group_pics',
                                         group['puid'])
    os.makedirs(group_profile_pic_dir, exist_ok=True)

    cropped_image_data = request.form.get('cropped_image_data')
    original_image_path_from_browser = request.form.get('original_image_path_from_browser')

    if cropped_image_data:
        try:
            header, encoded_data = cropped_image_data.split(',', 1)
            decoded_image = base64.b64decode(encoded_data)
            mime_type = header.split(';')[0].split(':')[1]
            file_extension = mime_type.split('/')[-1]
            standardized_filename = f"profile.{file_extension}"
            file_path = os.path.join(group_profile_pic_dir, standardized_filename)

            with open(file_path, 'wb') as f:
                f.write(decoded_image)

            profile_picture_path = os.path.join('group_pics', group['puid'], standardized_filename)
            flash('Group profile picture uploaded successfully!', 'success')

            if original_image_path_from_browser:
                original_profile_picture_path = original_image_path_from_browser

        except Exception as e:
            flash(f'Error processing image: {e}', 'danger')
            traceback.print_exc()
            return redirect(url_for('groups.group_profile', puid=puid))

    if profile_picture_path:
        update_group_profile_picture_path(
            group_puid=group['puid'],
            profile_picture_path=profile_picture_path,
            original_profile_picture_path=original_profile_picture_path,
            admin_puid=current_user['puid']
        )

    return redirect(url_for('groups.group_profile', puid=puid))


@groups_bp.route('/leave/<puid>', methods=['POST'])
def leave_group_route(puid):
    """Allows a user to leave a group."""
    from db_queries.groups import get_group_by_puid, leave_group
    from db_queries.users import get_user_by_username
    # Import the new federation function
    from db_queries.federation import notify_remote_node_of_leave_group

    if 'username' not in session:
        flash('Authentication required.', 'danger')
        return redirect(url_for('auth.login'))

    current_user = get_user_by_username(session['username'])
    group = get_group_by_puid(puid)

    if not current_user or not group:
        flash('User or Group not found.', 'danger')
        return redirect(url_for('groups.my_groups'))

    # If the group is remote, notify its home node that the user is leaving.
    # For remote groups, the membership only exists on the remote node.
    if group.get('hostname'):
        notify_remote_node_of_leave_group(current_user, group)
        flash('Successfully left the group.', 'success')
        return redirect(url_for('groups.my_groups'))

    # For local groups, remove the membership from the local database
    success, message = leave_group(group['id'], current_user['id'])

    flash(message, 'success' if success else 'danger')
    return redirect(url_for('groups.my_groups'))

@groups_bp.route('/api/group/<puid>/posts')
def get_group_posts_api(puid):
    """
    API endpoint to fetch paginated posts for a group's timeline.
    Returns JSON with rendered HTML for each post.
    """
    # Imports
    from db_queries.groups import get_group_by_puid, is_user_group_member
    from db_queries.users import get_user_by_username, get_user_by_puid
    from db_queries.posts import get_posts_for_group
    from flask import render_template, jsonify, session, request, current_app
    
    # Determine viewer
    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if not viewer_puid:
            return jsonify({'error': 'Unauthorized'}), 401
        current_viewer = get_user_by_puid(viewer_puid)
    elif 'username' in session:
        current_viewer = get_user_by_username(session['username'])
    else:
        return jsonify({'error': 'Authentication required'}), 401
    
    if not current_viewer:
        return jsonify({'error': 'Viewer not found'}), 404
    
    # Get the group
    group = get_group_by_puid(puid)
    if not group:
        return jsonify({'error': 'Group not found'}), 404
    
    current_viewer_id = current_viewer['id']
    is_admin = (current_viewer.get('user_type') == 'admin')
    is_member = is_user_group_member(current_viewer_id, group['id'])
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    # Validate parameters
    if page < 1:
        page = 1
    if limit < 1 or limit > 50:
        limit = 20
    
    # Get paginated posts
    posts = get_posts_for_group(
        group_puid=puid,
        viewer_user_id=current_viewer_id,
        is_member=is_member,
        viewer_is_admin=is_admin,
        page=page,
        limit=limit
    )
    
    # NEW: Get friend PUIDs for snooze/block actions in post menus
    friend_puids = set()
    if current_viewer_id:
        from db_queries.friends import get_all_friends_puid
        friend_puids = get_all_friends_puid(current_viewer_id)
    
    # Determine viewer info for templates
    is_federated_viewer = session.get('is_federated_viewer', False)
    if is_federated_viewer:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        viewer_home_url = f"{protocol}://{current_viewer.get('hostname')}"
    else:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"

    from db_queries.parental_controls import requires_parental_approval
    
    # Add to context
    current_user_requires_parental_approval = requires_parental_approval(current_viewer_id) if current_viewer_id else False

    
    # Render each post to HTML
    rendered_posts = []
    for post in posts:
        html = render_template('_post_template.html',
                             post=post,
                             current_user_id=current_viewer_id,
                             current_user_puid=current_viewer['puid'],
                             current_user=current_viewer,
                             is_admin=is_admin,
                             is_federated_viewer=is_federated_viewer,
                             viewer_home_url=viewer_home_url,
                             friend_puids=friend_puids,
                             current_user_requires_parental_approval=current_user_requires_parental_approval)
        rendered_posts.append(html)
    
    return jsonify({'posts': rendered_posts})

@groups_bp.route('/api/group/<puid>/check_new')
def check_new_group_posts(puid):
    """
    Check if there are new posts in a group since a given timestamp.
    """
    from db_queries.users import get_user_by_username
    
    since_timestamp = request.args.get('since')
    if not since_timestamp:
        return jsonify({'has_new_posts': False}), 400
    
    current_username = session.get('username')
    current_user_id = None
    
    if current_username:
        user_data = get_user_by_username(current_username)
        if user_data:
            current_user_id = user_data['id']
    
    from db_queries.groups import check_new_posts_in_group
    has_new = check_new_posts_in_group(puid, current_user_id, since_timestamp)
    
    return jsonify({'has_new_posts': has_new})

@groups_bp.route('/<puid>/members')
def group_members(puid):
    """
    Displays the members list for a specific group (identified by PUID).
    Similar to view_user_friends but for group members.
    """
    # Imports moved inside function
    from db_queries.groups import (get_group_by_puid, get_group_members, is_user_group_member,
                                   is_user_group_admin, is_user_group_moderator_or_admin,
                                   get_group_profile_info, get_friends_in_group)
    from db_queries.users import get_user_by_username, get_user_by_puid
    from db_queries.posts import get_muid_by_media_path, get_media_for_group_gallery
    from db_queries.settings import get_user_settings
    from db_queries.notifications import get_unread_notification_count

    # Check authentication
    if 'username' not in session and not session.get('is_federated_viewer'):
        flash('Please log in to view this page.', 'danger')
        return redirect(url_for('auth.login'))

    # Get the group
    group = get_group_by_puid(puid)
    if not group:
        flash('Group not found.', 'danger')
        return redirect(url_for('main.index'))

    # Initialize viewer context variables
    current_viewer_id = None
    current_user_id = None
    viewer_is_admin = False
    is_federated_viewer = False
    viewer_home_url = None
    viewer_puid = None
    current_viewer_data = None
    current_user = None

    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'
    
    user_settings = get_user_settings(None)  # Default settings

    # Determine viewer context (federated or local)
    if session.get('is_federated_viewer'):
        is_federated_viewer = True
        viewer_puid = session.get('federated_viewer_puid')
        federated_viewer = get_user_by_puid(viewer_puid)
        if federated_viewer:
            current_viewer_id = federated_viewer['id']
            current_user_id = federated_viewer['id']
            current_user = federated_viewer
            viewer_home_url = f"{protocol}://{federated_viewer['hostname']}"
            current_viewer_data = federated_viewer
            if session.get('federated_viewer_settings'):
                user_settings.update(session.get('federated_viewer_settings'))
    elif 'username' in session:
        current_viewer = get_user_by_username(session['username'])
        if current_viewer:
            current_viewer_id = current_viewer['id']
            current_user_id = current_viewer['id']
            current_user = current_viewer
            viewer_is_admin = (current_viewer['user_type'] == 'admin')
            viewer_puid = current_viewer['puid']
            viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"
            current_viewer_data = current_viewer
            user_settings = get_user_settings(current_viewer_id)

    # Check group membership and permissions
    is_member = is_user_group_member(current_viewer_id, group['id']) if current_viewer_id else False
    is_group_admin = is_user_group_admin(current_viewer_id, group['id']) if current_viewer_id else False
    is_moderator_or_admin = is_user_group_moderator_or_admin(current_viewer_id, group['id']) if current_viewer_id else False

    # Check if viewer can see the members list
    can_view = is_member or is_group_admin or viewer_is_admin
    
    if not can_view:
        flash('You do not have permission to view this group\'s members list.', 'danger')
        return redirect(url_for('groups.group_profile', puid=puid))

    # Get all group members
    members = get_group_members(group['id'])

    # Data for Sidebar
    members_full_list = get_group_members(group['id'])
    members_count = len(members_full_list)

    # THIS IS THE FIX: Fetch group_profile_info
    group_profile_info = get_group_profile_info(group['id'], is_member, is_group_admin)

    # Check if viewer can see members list based on privacy settings
    show_members_info = group_profile_info.get('show_members', {})
    can_view_members = is_member or is_group_admin

    if not can_view_members:
        # Check if members list is public
        if show_members_info.get('privacy_public'):
            can_view_members = True

    # Only show members list if viewer has permission
    if can_view_members:
        members = members_full_list
    else:
        members = []
    
    # Get friends in group (for the viewer)
    friends_in_group = []
    if current_user and is_member:
        friends_in_group = get_friends_in_group(current_user['id'], group['id'])
    
    # Get media for gallery preview
    all_gallery_media = get_media_for_group_gallery(puid, current_viewer_id, is_member,
                                                     is_group_admin or viewer_is_admin)
    
    group['profile_picture_muid'] = get_muid_by_media_path(
        group.get('original_profile_picture_path')
    )
    
    latest_gallery_media = all_gallery_media[:9]
    total_media_count = len(all_gallery_media)
    # --- End data for sidebar ---

    # Get unread notification count for the VIEWER
    unread_count = 0
    if current_viewer_id and not is_federated_viewer:
        unread_count = get_unread_notification_count(current_viewer_id)

    user_media_path = current_viewer_data.get('media_path') if current_viewer_data else None

    # ====================================================================
    # FEDERATION FIX: Add hostname to group object for federated viewers
    # ====================================================================
    # For federated viewers, add hostname to group object so JavaScript knows it's remote
    if is_federated_viewer and current_user:
        # The group is local to this node, but remote from the viewer's perspective
        # Add the current node's hostname so JavaScript treats it as a remote group
        group = dict(group)  # Convert to dict if it's a Row object
        group['hostname'] = current_app.config.get('NODE_HOSTNAME')

    return render_template('group_members.html',
                           group=group,
                           members=members,
                           is_member=is_member,
                           is_group_admin=is_group_admin,
                           is_moderator_or_admin=is_moderator_or_admin,
                           # --- Sidebar data ---
                           group_info=group_profile_info,
                           friends_in_group=friends_in_group,
                           latest_gallery_media=latest_gallery_media,
                           total_media_count=total_media_count,
                           # --- Viewer context (needed for header) ---
                           current_viewer_data=current_viewer_data,
                           current_user_id=current_viewer_id,
                           current_user_puid=viewer_puid,
                           viewer_puid=viewer_puid,
                           viewer_home_url=viewer_home_url,
                           is_federated_viewer=is_federated_viewer,
                           user_settings=user_settings,
                           viewer_token=session.pop('viewer_token', None),
                           user_media_path=user_media_path,
                           viewer_puid_for_js=viewer_puid,
                           members_count=members_count,
                           unread_notification_count=unread_count)