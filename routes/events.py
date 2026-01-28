# routes/events.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from db import get_db
from db_queries.users import get_user_by_username, get_user_by_puid
from db_queries.groups import get_group_by_puid
# MODIFICATION: Added get_or_create_remote_event_stub
from db_queries.events import (create_event, get_event_by_puid, get_event_attendees,
                               respond_to_event, get_events_for_user, update_event_picture_path,
                               update_event_details, cancel_event, get_friends_to_invite_to_event,
                               invite_friend_to_event, get_posts_for_event, get_or_create_remote_event_stub,
                               get_discoverable_public_events) # Make sure get_discoverable_public_events is imported
from utils.federation_utils import distribute_post, get_remote_node_api_url, distribute_event_invite, distribute_post_to_single_node
from db_queries.posts import get_posts_for_feed, add_post, get_post_by_cuid
# MODIFICATION: Import get_all_connected_nodes
from db_queries.federation import get_node_by_hostname, get_or_create_remote_user, get_all_connected_nodes
from db_queries.settings import get_user_settings
from db_queries.notifications import get_unread_notification_count
import os
import base64
import traceback
from datetime import datetime
import hmac
import hashlib
import json
import requests
import time
from datetime import datetime, timedelta

events_bp = Blueprint('events', __name__, url_prefix='/events')

# --- START FIX: Copy helper functions from db_queries/events.py ---
# Helper for date formatting
def suffix(d):
    return 'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')

# Locale-independent day and month names
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

def process_event_list(events):
    """
    Helper function to convert datetime strings in a list of event dicts
    into real datetime objects AND add creator display information.
    """
    from db_queries.users import get_user_by_puid  # Import here to avoid circular dependency
    
    processed = []
    for event_dict in events:
        try:
            # Make a copy to avoid modifying the original dict during iteration
            event = event_dict.copy()
            
            # Parse datetimes
            if event.get('event_datetime') and isinstance(event.get('event_datetime'), str):
                event['event_datetime'] = datetime.strptime(event['event_datetime'], '%Y-%m-%d %H:%M:%S')
            if event.get('event_end_datetime') and isinstance(event.get('event_end_datetime'), str):
                event['event_end_datetime'] = datetime.strptime(event['event_end_datetime'], '%Y-%m-%d %H:%M:%S')
            
            # Add creator information if not already present
            if not event.get('creator_display_name') and event.get('created_by_user_puid'):
                creator = get_user_by_puid(event['created_by_user_puid'])
                if creator:
                    event['creator_display_name'] = creator['display_name']
                    event['creator_hostname'] = creator.get('hostname')
                else:
                    # Fallback if creator not found
                    event['creator_display_name'] = f"User {event['created_by_user_puid'][:8]}"
                    event['creator_hostname'] = event.get('hostname')
            
            processed.append(event)
        except (ValueError, TypeError) as e:
            print(f"Warning: Could not parse datetime for event {event_dict.get('puid')}: {e}")
            processed.append(event_dict) # Keep original if parsing fails
    return processed


@events_bp.route('/')
def events_home():
    """
    MODIFICATION: This route now renders the main index.html "shell"
    and tells the client-side router to load the "My Events" content.
    """
    if 'username' not in session:
        flash('Please log in to access this page.', 'danger')
        return redirect(url_for('auth.login'))

    current_user = get_user_by_username(session['username'])
    if not current_user:
        flash('User not found.', 'danger')
        return redirect(url_for('main.index'))
    
    # NEW: Fetch all the data needed for the header/sidebar, just like index()
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

    # NEW: Pass the URL for the "My Events" content to load
    initial_content_url = url_for('events.get_events_content')

    return render_template('index.html',
                           username=current_username,
                           user_media_path=user_media_path,
                           current_user_puid=current_user_puid,
                           current_user_id=current_user['id'],
                           current_user_profile=current_user_profile,
                           viewer_home_url=viewer_home_url,
                           viewer_puid_for_js=current_user_puid,
                           initial_content_url=initial_content_url)


@events_bp.route('/api/page/my_events')
def get_events_content():
    """
    API endpoint to fetch the HTML for the "My Events" content.
    Contains the logic previously in events_home.
    """
    if 'username' not in session:
        return jsonify({'error': 'Authentication required.'}), 401

    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found.'}), 404
    
    # --- Federated Discovery Logic ---
    connected_nodes = get_all_connected_nodes()
    local_hostname = current_app.config.get('NODE_HOSTNAME')
    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    verify_ssl = not insecure_mode

    for node in connected_nodes:
        if node['status'] != 'connected' or not node['shared_secret']:
            continue
        try:
            remote_url = get_remote_node_api_url(
                node['hostname'],
                '/federation/api/v1/discover_public_events',
                insecure_mode
            )
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
            remote_events_data = response.json()

            for event_data in remote_events_data:
                event_puid = event_data.get('puid')
                if not event_puid or event_data.get('hostname') == local_hostname:
                    continue
                try:
                    event_datetime = datetime.strptime(event_data['event_datetime'], '%Y-%m-%d %H:%M:%S')
                    event_end_datetime = None
                    if event_data.get('event_end_datetime'):
                        event_end_datetime = datetime.strptime(event_data['event_end_datetime'], '%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    print(f"WARN: Skipping remote event {event_puid} from {node['hostname']} due to invalid date format.")
                    continue

                get_or_create_remote_event_stub(
                    puid=event_puid,
                    created_by_user_puid=event_data.get('created_by_user_puid'),
                    source_type=event_data.get('source_type'),
                    source_puid=event_data.get('source_puid'),
                    title=event_data.get('title'),
                    event_datetime=event_datetime,
                    event_end_datetime=event_end_datetime,
                    location=event_data.get('location'),
                    details=event_data.get('details'),
                    is_public=event_data.get('is_public', False),
                    hostname=event_data.get('hostname'),
                    profile_picture_path=event_data.get('profile_picture_path')
                )
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Could not fetch public events from node {node['hostname']}: {e}")
        except Exception as e:
            print(f"ERROR: An unexpected error occurred while fetching from {node['hostname']}: {e}")
            traceback.print_exc()
    
    # --- End Federated Discovery ---

    user_events = get_events_for_user(current_user['puid'])

    # Render the *partial* template
    # get_events_for_user *already* processes the datetimes, so this is safe.
    return render_template('_my_events_content.html', 
                           my_upcoming=user_events['my_upcoming'],
                           invitations=user_events['invitations'],
                           discover_public=user_events['discover_public'],
                           past=user_events['past'],
                           current_user_puid=current_user['puid'])


# NEW: API route specifically for the 'Discover' tab content
@events_bp.route('/api/page/discover_public')
def get_discover_public_content():
    """
    API endpoint to fetch the HTML for the "Discover Public Events" content.
    This is called by events.js when switching to the Discover tab.
    """
    if 'username' not in session:
        return jsonify({'error': 'Authentication required.'}), 401
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found.'}), 404

    # Run federated discovery
    connected_nodes = get_all_connected_nodes()
    local_hostname = current_app.config.get('NODE_HOSTNAME')
    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    verify_ssl = not insecure_mode

    for node in connected_nodes:
        if node['status'] != 'connected' or not node['shared_secret']:
            continue
        try:
            remote_url = get_remote_node_api_url(
                node['hostname'],
                '/federation/api/v1/discover_public_events',
                insecure_mode
            )
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
            remote_events_data = response.json()

            for event_data in remote_events_data:
                event_puid = event_data.get('puid')
                if not event_puid or event_data.get('hostname') == local_hostname:
                    continue
                try:
                    event_datetime = datetime.strptime(event_data['event_datetime'], '%Y-%m-%d %H:%M:%S')
                    event_end_datetime = None
                    if event_data.get('event_end_datetime'):
                        event_end_datetime = datetime.strptime(event_data['event_end_datetime'], '%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    print(f"WARN: Skipping remote event {event_puid} from {node['hostname']} due to invalid date format.")
                    continue

                get_or_create_remote_event_stub(
                    puid=event_puid,
                    created_by_user_puid=event_data.get('created_by_user_puid'),
                    source_type=event_data.get('source_type'),
                    source_puid=event_data.get('source_puid'),
                    title=event_data.get('title'),
                    event_datetime=event_datetime,
                    event_end_datetime=event_end_datetime,
                    location=event_data.get('location'),
                    details=event_data.get('details'),
                    is_public=event_data.get('is_public', False),
                    hostname=event_data.get('hostname'),
                    profile_picture_path=event_data.get('profile_picture_path')
                )
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Could not fetch public events from node {node['hostname']}: {e}")
        except Exception as e:
            print(f"ERROR: An unexpected error occurred while fetching from {node['hostname']}: {e}")
            traceback.print_exc()

    # Get all discoverable public events (local + stubs)
    discover_public_events_raw = get_discoverable_public_events()
    
    # --- START FIX: Process the list to convert strings to datetime objects ---
    discover_public_events = process_event_list(discover_public_events_raw)
    # --- END FIX ---
    
    # We just need to render the *content* of the tab pane
    return render_template(
        '_my_events_content.html', 
        discover_public=discover_public_events,
        # Pass dummy data for other tabs as they aren't being rendered here
        my_upcoming=[], 
        invitations=[], 
        past=[],
        current_user_puid=current_user['puid']
    )
# END NEW ROUTE


@events_bp.route('/<puid>')
def event_profile(puid):
# ... (rest of the file is unchanged) ...
    """Displays the profile for a single event."""
    viewer_token = request.args.get('viewer_token')
    
    current_user = None
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
    
    if not current_user and not viewer_token:
        flash('Please log in to view this page.', 'danger')
        return redirect(url_for('auth.login'))

    current_user_puid = current_user['puid'] if current_user else None
    current_user_id = current_user['id'] if current_user else None

    event = get_event_by_puid(puid, current_user_puid)
    
    if not event:
        flash('Event not found.', 'danger')
        return redirect(url_for('events.events_home'))
        
    current_viewer_is_local = not session.get('is_federated_viewer')

    # If a local user tries to view a remote event, redirect them with a viewer token
    if event.get('hostname') and current_viewer_is_local:
        if not current_user:
             flash('Please log in to view remote events.', 'danger')
             return redirect(url_for('auth.login'))
        local_viewer = get_user_by_username(session['username'])
        remote_hostname = event['hostname']
        node = get_node_by_hostname(remote_hostname)

        if not node or not node['shared_secret']:
            flash(f'Cannot view remote event: Your node is not securely connected to {remote_hostname}.', 'danger')
            return redirect(request.referrer or url_for('main.index'))

        try:
            insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
            
            token_request_url = get_remote_node_api_url(remote_hostname, '/federation/api/v1/request_viewer_token', insecure_mode)
            
            local_viewer_settings = get_user_settings(local_viewer['id'])

            payload = {
                'viewer_puid': local_viewer['puid'], 
                'target_puid': puid,
                'viewer_settings': local_viewer_settings
            }
            request_body = json.dumps(payload, sort_keys=True).encode('utf-8')

            signature = hmac.new(node['shared_secret'].encode('utf-8'), msg=request_body, digestmod=hashlib.sha256).hexdigest()

            headers = {
                'X-Node-Hostname': current_app.config.get('NODE_HOSTNAME'),
                'X-Node-Signature': signature,
                'Content-Type': 'application/json'
            }

            response = requests.post(token_request_url, data=request_body, headers=headers, timeout=10, verify=not insecure_mode)
            response.raise_for_status()

            token_data = response.json()
            new_viewer_token = token_data.get('viewer_token')

            if not new_viewer_token:
                raise Exception("Failed to retrieve a viewer token from the remote node.")

            remote_event_url = get_remote_node_api_url(remote_hostname, f"/events/{puid}", insecure_mode)
            return redirect(f"{remote_event_url}?viewer_token={new_viewer_token}")

        except requests.exceptions.RequestException as e:
            flash(f"Error connecting to remote node: {e}", "danger")
            return redirect(request.referrer or url_for('main.index'))
        except Exception as e:
            flash(f"An error occurred while trying to view the remote event: {e}", "danger")
            traceback.print_exc()
            return redirect(request.referrer or url_for('main.index'))
        
    if event.get('event_datetime'):
        try:
            event['event_datetime'] = datetime.strptime(event['event_datetime'], '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            pass
            
    if event.get('event_end_datetime'):
        try:
            event['event_end_datetime'] = datetime.strptime(event['event_end_datetime'], '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            pass

    response_map = {'attending': 'going', 'tentative': 'interested', 'declined': 'declined', 'invited': 'invited'}
    event['user_status'] = response_map.get(event.get('viewer_response'))

    attendees = get_event_attendees(event['id'])
    
    event_posts = get_posts_for_event(
        event_id=event['id'],
        viewer_user_puid=current_user_puid,
        page=1,
        limit=20
    )
        
    is_creator = (current_user_puid == event['created_by_user_puid']) if current_user_puid else False
    
    creator = None
    creator_media_path = None
    creator_type = event.get('source_type')

    if is_creator and current_user:
        creator_media_path = current_user.get('media_path')

    # Get the creator object (which could be a user or a page)
    creator = get_user_by_puid(event['created_by_user_puid'])
    
    # If the source is a group, the 'creator' for display is the group
    if creator_type == 'group':
        creator = get_group_by_puid(event['source_puid'])

    
    event['creator'] = creator # This is now either the user, page, or group object
    event['creator_type'] = creator_type

    viewer_home_url = None
    if current_user:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        hostname = current_user.get('hostname') or current_app.config.get('NODE_HOSTNAME')
        viewer_home_url = f"{protocol}://{hostname}"

    # Get user settings for the template
    user_settings = get_user_settings(None)  # Default settings
    if session.get('is_federated_viewer'):
        if 'federated_viewer_settings' in session:
            user_settings.update(session.get('federated_viewer_settings'))
    else:
        current_viewer_id = current_user['id'] if current_user else None
        if current_viewer_id:
            user_settings = get_user_settings(current_viewer_id)
    
    # Get media gallery for sidebar (if needed in the future)
    # For now, we'll set these to empty/None since events don't have a media gallery yet
    latest_gallery_media = []
    total_media_count = 0
    
    # NEW: Variables needed for the header
    current_viewer_data = current_user  # The current viewer's user data
    viewer_puid = current_user_puid  # The viewer's PUID
    unread_count = 0
    if current_user_id:
        unread_count = get_unread_notification_count(current_user_id)
    
    from db_queries.parental_controls import requires_parental_approval
    
    # Add to context
    current_user_requires_parental_approval = requires_parental_approval(current_user_id) if current_user_id else False

    return render_template('event_profile.html', 
                           event=event,
                           attendees=attendees,
                           event_posts=event_posts,
                           current_user_puid=current_user_puid,
                           current_user_id=current_user_id,
                           is_creator=is_creator,
                           creator=creator, # Pass the creator object (user, page, or group)
                           creator_media_path=creator_media_path,
                           user_media_path=current_user.get('media_path') if current_user else None,
                           is_federated_viewer=session.get('is_federated_viewer', False),
                           viewer_home_url=viewer_home_url,
                           viewer_token=viewer_token,
                           user_settings=user_settings,
                           latest_gallery_media=latest_gallery_media,
                           total_media_count=total_media_count,
                           # NEW: Header variables
                           current_viewer_data=current_viewer_data,
                           viewer_puid=viewer_puid,
                           unread_notification_count=unread_count,
                           timedelta=timedelta,
                           viewer_puid_for_js=viewer_puid,
                           current_user_requires_parental_approval=current_user_requires_parental_approval)

@events_bp.route('/api/event/<puid>/posts')
def get_event_posts_api(puid):
    """
    API endpoint to fetch paginated posts for an event's timeline.
    Returns JSON with rendered HTML for each post.
    """
    # Imports
    from db_queries.events import get_event_by_puid
    from db_queries.users import get_user_by_username, get_user_by_puid
    from db_queries.events import get_posts_for_event
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
    
    # Get the event
    event = get_event_by_puid(puid)
    if not event:
        return jsonify({'error': 'Event not found'}), 404
    
    current_viewer_id = current_viewer['id']
    is_admin = (current_viewer.get('user_type') == 'admin')
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    # Validate parameters
    if page < 1:
        page = 1
    if limit < 1 or limit > 50:
        limit = 20
    
    # Get paginated posts
    # First get the event to get its ID
    posts = get_posts_for_event(
        event_id=event['id'],
        viewer_user_puid=current_viewer['puid'],
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

@events_bp.route('/api/event/<puid>/check_new')
def check_new_event_posts(puid):
    """
    Check if there are new posts in an event since a given timestamp.
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
    
    from db_queries.events import check_new_posts_in_event
    has_new = check_new_posts_in_event(puid, current_user_id, since_timestamp)
    
    return jsonify({'has_new_posts': has_new})

@events_bp.route('/<puid>/attendees')
def event_attendees(puid):
    """Displays all attendees for an event, grouped by response status."""
    viewer_token = request.args.get('viewer_token')
    
    current_user = None
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
    
    if not current_user and not viewer_token:
        flash('Please log in to view this page.', 'danger')
        return redirect(url_for('auth.login'))

    current_user_puid = current_user['puid'] if current_user else None
    current_user_id = current_user['id'] if current_user else None

    event = get_event_by_puid(puid, current_user_puid)
    
    if not event:
        flash('Event not found.', 'danger')
        return redirect(url_for('events.events_home'))
    
    # Get all attendees
    attendees = get_event_attendees(event['id'])
    
    # Get creator object
    creator = get_user_by_puid(event['created_by_user_puid'])
    if event.get('source_type') == 'group':
        creator = get_group_by_puid(event['source_puid'])
    
    event['creator'] = creator
    event['creator_type'] = event.get('source_type')
    
    # Parse event datetime
    if event.get('event_datetime'):
        try:
            event['event_datetime'] = datetime.strptime(event['event_datetime'], '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            pass
            
    if event.get('event_end_datetime'):
        try:
            event['event_end_datetime'] = datetime.strptime(event['event_end_datetime'], '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            pass
    
    viewer_home_url = None
    if current_user:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        hostname = current_user.get('hostname') or current_app.config.get('NODE_HOSTNAME')
        viewer_home_url = f"{protocol}://{hostname}"

    # Get user settings for the template
    user_settings = get_user_settings(None)  # Default settings
    if session.get('is_federated_viewer'):
        if 'federated_viewer_settings' in session:
            user_settings.update(session.get('federated_viewer_settings'))
    else:
        current_viewer_id = current_user['id'] if current_user else None
        if current_viewer_id:
            user_settings = get_user_settings(current_viewer_id)
    
    # Get media gallery for sidebar
    latest_gallery_media = []
    total_media_count = 0
    
    # Variables needed for the header
    current_viewer_data = current_user
    viewer_puid = current_user_puid
    unread_count = 0
    if current_user_id:
        unread_count = get_unread_notification_count(current_user_id)

    return render_template('event_attendees.html', 
                           event=event,
                           attendees=attendees,
                           creator=creator,
                           current_user_puid=current_user_puid,
                           current_user_id=current_user_id,
                           is_federated_viewer=session.get('is_federated_viewer', False),
                           viewer_home_url=viewer_home_url,
                           viewer_token=viewer_token,
                           user_settings=user_settings,
                           latest_gallery_media=latest_gallery_media,
                           total_media_count=total_media_count,
                           current_viewer_data=current_viewer_data,
                           viewer_puid=viewer_puid,
                           unread_notification_count=unread_count,
                           viewer_puid_for_js=viewer_puid)


@events_bp.route('/<puid>/gallery')
def event_media_gallery(puid):
    """Displays the full media gallery for an event."""
    viewer_token = request.args.get('viewer_token')
    
    current_user = None
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
    
    if not current_user and not viewer_token:
        flash('Please log in to view this page.', 'danger')
        return redirect(url_for('auth.login'))

    current_user_puid = current_user['puid'] if current_user else None
    current_user_id = current_user['id'] if current_user else None

    event = get_event_by_puid(puid, current_user_puid)
    
    if not event:
        flash('Event not found.', 'danger')
        return redirect(url_for('events.events_home'))
    
    # Get all attendees for the sidebar
    attendees = get_event_attendees(event['id'])
    
    # Get all media for this event
    # NOTE: You'll need to create this function in db_queries/events.py or db_queries/media.py
    # For now, using a similar pattern to groups
    db = get_db()
    cursor = db.cursor()
    
    # Query to get all media from posts in this event
    cursor.execute("""
        SELECT m.id, m.muid, m.media_file_path, m.media_type, m.alt_text, m.uploaded_at,
               u.username, u.puid, u.display_name, u.hostname as origin_hostname,
               p.cuid as post_cuid
        FROM media m
        JOIN users u ON m.user_id = u.id
        JOIN posts p ON m.post_id = p.id
        WHERE p.event_id = ?
        ORDER BY m.uploaded_at DESC
    """, (event['id'],))
    
    all_media = cursor.fetchall()
    
    # Get latest 10 for sidebar preview
    latest_gallery_media = all_media[:10] if all_media else []
    total_media_count = len(all_media)
    
    # Check if current user is the event creator
    is_creator = (current_user_puid == event['created_by_user_puid']) if current_user_puid else False
    creator_media_path = None
    if is_creator and current_user:
        creator_media_path = current_user.get('media_path')
    
    # Get creator object
    creator = get_user_by_puid(event['created_by_user_puid'])
    if event.get('source_type') == 'group':
        creator = get_group_by_puid(event['source_puid'])
    
    event['creator'] = creator
    event['creator_type'] = event.get('source_type')
    
    # Parse event datetime
    if event.get('event_datetime'):
        try:
            event['event_datetime'] = datetime.strptime(event['event_datetime'], '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            pass
            
    if event.get('event_end_datetime'):
        try:
            event['event_end_datetime'] = datetime.strptime(event['event_end_datetime'], '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            pass
    
    viewer_home_url = None
    if current_user:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        hostname = current_user.get('hostname') or current_app.config.get('NODE_HOSTNAME')
        viewer_home_url = f"{protocol}://{hostname}"

    # Get user settings for the template
    user_settings = get_user_settings(None)  # Default settings
    if session.get('is_federated_viewer'):
        if 'federated_viewer_settings' in session:
            user_settings.update(session.get('federated_viewer_settings'))
    else:
        current_viewer_id = current_user['id'] if current_user else None
        if current_viewer_id:
            user_settings = get_user_settings(current_viewer_id)
    
    # Variables needed for the header
    current_viewer_data = current_user
    viewer_puid = current_user_puid
    unread_count = 0
    if current_user_id:
        unread_count = get_unread_notification_count(current_user_id)

    return render_template('event_media_gallery.html', 
                           event=event,
                           attendees=attendees,
                           all_media=all_media,
                           latest_gallery_media=latest_gallery_media,
                           total_media_count=total_media_count,
                           creator=creator,
                           is_creator=is_creator,
                           creator_media_path=creator_media_path,
                           current_user_puid=current_user_puid,
                           current_user_id=current_user_id,
                           is_federated_viewer=session.get('is_federated_viewer', False),
                           viewer_home_url=viewer_home_url,
                           viewer_token=viewer_token,
                           user_settings=user_settings,
                           current_viewer_data=current_viewer_data,
                           viewer_puid=viewer_puid,
                           unread_notification_count=unread_count,
                           viewer_puid_for_js=viewer_puid)


@events_bp.route('/create', methods=['POST'])
def create_event_route():
    """API endpoint to create a new event."""
    if 'username' not in session:
        return jsonify({'error': 'Authentication required.'}), 401
    current_user = get_user_by_username(session['username'])
    data = request.get_json()

    source_type = data.get('source_type')
    source_puid = data.get('source_puid')
    title = data.get('title')
    event_date = data.get('event_date')
    event_time = data.get('event_time')
    location = data.get('location')
    details = data.get('details')
    is_public = data.get('is_public', False)
    
    event_end_date = data.get('event_end_date')
    event_end_time = data.get('event_end_time')

    if not all([source_type, source_puid, title, event_date, event_time, location]):
        return jsonify({'error': 'Missing required fields.'}), 400

    try:
        event_datetime_str = f"{event_date} {event_time}"
        event_datetime = datetime.strptime(event_datetime_str, '%Y-%m-%d %H:%M')
        
        event_end_datetime = None
        if event_end_time:
            end_date_str = event_end_date if event_end_date else event_date
            event_end_datetime_str = f"{end_date_str} {event_end_time}"
            event_end_datetime = datetime.strptime(event_end_datetime_str, '%Y-%m-%d %H:%M')

            if event_end_datetime <= event_datetime:
                return jsonify({'error': 'Event end time must be after the start time.'}), 400


    except ValueError:
        return jsonify({'error': 'Invalid date or time format.'}), 400

    event_puid, post_cuid = create_event(
        created_by_user=current_user, 
        source_type=source_type, 
        source_puid=source_puid, 
        title=title, 
        event_datetime=event_datetime,
        event_end_datetime=event_end_datetime,
        location=location, 
        details=details, 
        is_public=is_public,
        hostname=None
    )

    if event_puid:
        if post_cuid:
            # The general 'distribute_post' function correctly handles event announcement posts,
            # ensuring full event data is sent to prevent race conditions on remote nodes.
            distribute_post(post_cuid)
        event_url = url_for('events.event_profile', puid=event_puid)
        return jsonify({'message': 'Event created successfully!', 'event_url': event_url}), 201
    else:
        return jsonify({'error': 'Failed to create event.'}), 500

@events_bp.route('/<puid>/respond', methods=['POST'])
def respond_route(puid):
    """API endpoint for a user to respond to an event invitation."""
    current_user = None
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])

    if not current_user:
        return jsonify({'error': 'Authentication required.'}), 401
        
    data = request.get_json()
    response = data.get('response')

    if not response or response not in ['attending', 'tentative', 'declined']:
        return jsonify({'error': 'Invalid response.'}), 400

    success, message = respond_to_event(puid, current_user['puid'], response)

    if success:
        return jsonify({'message': message, 'new_response': response}), 200
    else:
        return jsonify({'error': message}), 500

@events_bp.route('/upload_picture/<puid>', methods=['POST'])
def upload_event_picture(puid):
    """Handles uploading a profile picture for an event."""
    current_user = get_user_by_username(session['username'])
    event = get_event_by_puid(puid)
    if not event or event['created_by_user_puid'] != current_user['puid']:
        flash('You do not have permission to modify this event.', 'danger')
        return redirect(url_for('events.event_profile', puid=puid))

    event_pic_dir = os.path.join(current_app.config['PROFILE_PICTURE_STORAGE_DIR'], 'event_pics', event['puid'])
    os.makedirs(event_pic_dir, exist_ok=True)

    cropped_image_data = request.form.get('cropped_image_data')
    original_image_path = request.form.get('original_image_path_from_browser')

    if cropped_image_data:
        try:
            header, encoded_data = cropped_image_data.split(',', 1)
            decoded_image = base64.b64decode(encoded_data)
            mime_type = header.split(';')[0].split(':')[1]
            file_extension = mime_type.split('/')[-1]
            filename = f"event_pic.{file_extension}"
            file_path = os.path.join(event_pic_dir, filename)

            with open(file_path, 'wb') as f:
                f.write(decoded_image)
            
            picture_path = os.path.join('event_pics', event['puid'], filename)
            update_event_picture_path(event['puid'], picture_path, original_image_path)
            
            # NEW: Distribute the event update to remote nodes so they get the new picture
            from utils.federation_utils import distribute_event_update
            distribute_event_update(event['puid'], current_user)
            
            flash('Event picture updated!', 'success')
        except Exception as e:
            flash(f"Error processing image: {e}", 'danger')
            traceback.print_exc()

    return redirect(url_for('events.event_profile', puid=puid))

@events_bp.route('/<puid>/edit', methods=['POST'])
def edit_event_route(puid):
    """Handles editing an event's details."""
    current_user = get_user_by_username(session['username'])
    event = get_event_by_puid(puid)
    if not event or event['created_by_user_puid'] != current_user['puid']:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    title = data.get('title')
    event_date = data.get('event_date')
    event_time = data.get('event_time')
    location = data.get('location')
    details = data.get('details')
    event_end_date = data.get('event_end_date')
    event_end_time = data.get('event_end_time')
    
    try:
        event_datetime = datetime.strptime(f"{event_date} {event_time}", '%Y-%m-%d %H:%M')
        
        event_end_datetime = None
        if event_end_time:
            end_date_str = event_end_date if event_end_date else event_date
            event_end_datetime_str = f"{end_date_str} {event_end_time}"
            event_end_datetime = datetime.strptime(event_end_datetime_str, '%Y-%m-%d %H:%M')
            if event_end_datetime <= event_datetime:
                return jsonify({'error': 'Event end time must be after the start time.'}), 400

    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid date or time format.'}), 400

    success, message = update_event_details(puid, title, event_datetime, location, details, current_user, event_end_datetime)
    if success and data.get('profile_picture_path'):
        from db_queries.events import update_event_picture_path
        update_event_picture_path(data['puid'], data['profile_picture_path'])
    if success:
        return jsonify({'message': message}), 200
    else:
        return jsonify({'error': message}), 500

@events_bp.route('/<puid>/cancel', methods=['POST'])
def cancel_event_route(puid):
    """Handles cancelling an event."""
    current_user = get_user_by_username(session['username'])
    if not current_user:
        flash('Could not identify user.', 'danger')
        return redirect(url_for('main.index'))
    
    success, message = cancel_event(puid, current_user['id'])
    
    flash(message, 'success' if success else 'danger')
    
    return redirect(url_for('events.event_profile', puid=puid))

@events_bp.route('/<puid>/invite_friends', methods=['GET'])
def get_invitable_friends_route(puid):
    """Gets a list of friends who can be invited to a user-created event."""
    current_user = get_user_by_username(session['username'])
    event = get_event_by_puid(puid)
    if not event or event['created_by_user_puid'] != current_user['puid']:
        return jsonify({'error': 'Unauthorized'}), 403

    invitable_friends = get_friends_to_invite_to_event(current_user['id'], event['id'])
    return jsonify(invitable_friends)

@events_bp.route('/<puid>/invite/<user_puid>', methods=['POST'])
def invite_friend_route(puid, user_puid):
    """Invites a specific friend to a user-created event."""
    current_user = get_user_by_username(session['username'])
    event = get_event_by_puid(puid)
    if not event or event['created_by_user_puid'] != current_user['puid']:
        return jsonify({'error': 'Unauthorized'}), 403

    invitee = get_user_by_puid(user_puid)
    if not invitee:
        return jsonify({'error': 'Invitee not found.'}), 404

    if invitee.get('hostname'):
        # This sends the event data to the remote node
        distribute_event_invite(event, user_puid)
        # This adds the remote user to the local attendee list
        invite_friend_to_event(event['id'], current_user['id'], user_puid)

        # BUG FIX: After inviting a remote user and adding them to the local attendee list,
        # we must now re-distribute the initial announcement post. The recipient logic
        # in distribute_post will now find the new remote attendee and send the post
        # to their node, solving the race condition.
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT cuid FROM posts WHERE event_id = ? AND content IS NULL AND is_repost = FALSE", (event['id'],))
        announcement_post_row = cursor.fetchone()
        if announcement_post_row:
            post_cuid = announcement_post_row['cuid']
            distribute_post_to_single_node(post_cuid, invitee.get('hostname'))

        return jsonify({'message': 'Remote invitation sent.'}), 200
    else:
        if invite_friend_to_event(event['id'], current_user['id'], user_puid):
            return jsonify({'message': 'Invitation sent.'}), 200
        else:
            return jsonify({'error': 'Failed to send invitation.'}), 500

@events_bp.route('/<event_puid>/create_post', methods=['POST'])
def create_event_post_route(event_puid):
    """
    Handles creation of a new post within an event's wall.
    This now correctly handles both local and remote users.
    """
    current_user = None
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])

    if not current_user:
        flash('Please log in to post in events.', 'danger')
        return redirect(url_for('auth.login'))
        
    event = get_event_by_puid(event_puid)
    if not event:
        flash('Event not found.', 'danger')
        return redirect(url_for('events.events_home'))

    content = request.form.get('content')
    selected_media_files_json = request.form.get('selected_media_files', '[]')
    media_files_for_db = json.loads(selected_media_files_json) if selected_media_files_json else []
    
    # NEW: Get tagged users and location
    tagged_user_puids_json = request.form.get('tagged_users', '[]')
    tagged_user_puids = json.loads(tagged_user_puids_json) if tagged_user_puids_json else []
    location = request.form.get('location', '').strip() or None

    # PARENTAL CONTROL CHECK: Prevent children from making public posts in events
    # (Event posts are 'event' privacy by default, but check for safety)
    from db_queries.parental_controls import requires_parental_approval
    
    privacy_setting = request.form.get('privacy_setting', 'event')
    if requires_parental_approval(current_user['id']) and privacy_setting == 'public':
        flash('You cannot create public posts while parental controls are active.', 'warning')
        return redirect(url_for('events.event_profile', puid=event_puid))

    # NEW: Get poll data if provided
    poll_data_json = request.form.get('poll_data', '')
    poll_data = None
    if poll_data_json:
        try:
            poll_data = json.loads(poll_data_json)
            if poll_data and not content.strip():
                flash("You can't create a poll without text in your post.", 'danger')
                return redirect(url_for('events.event_profile', puid=event_puid))
        except json.JSONDecodeError:
            poll_data = None

    try:
        post_cuid = add_post(
            user_id=current_user['id'],
            profile_user_id=None,
            content=content,
            privacy_setting='event',
            media_files=media_files_for_db,
            event_id=event['id'],
            author_hostname=current_user.get('hostname'),
            tagged_user_puids=tagged_user_puids,  # NEW
            location=location,
            poll_data=poll_data  # NEW
        )
        if post_cuid:
            # The general 'distribute_post' function is also used here for consistency and robustness.
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

    return redirect(url_for('events.event_profile', puid=event_puid))

@events_bp.route('/<puid>/export.ics')
def export_event_ics(puid):
    """Generates and returns an iCalendar (.ics) file for the event."""
    event = get_event_by_puid(puid)
    if not event:
        flash('Event not found.', 'danger')
        return redirect(url_for('events.events_home'))
    
    # Parse datetime objects if they're strings
    if isinstance(event.get('event_datetime'), str):
        event_datetime = datetime.strptime(event['event_datetime'], '%Y-%m-%d %H:%M:%S')
    else:
        event_datetime = event.get('event_datetime')
    
    event_end_datetime = None
    if event.get('event_end_datetime'):
        if isinstance(event['event_end_datetime'], str):
            event_end_datetime = datetime.strptime(event['event_end_datetime'], '%Y-%m-%d %H:%M:%S')
        else:
            event_end_datetime = event.get('event_end_datetime')
    
    # Default end time to 1 hour after start if not specified
    if not event_end_datetime:
        from datetime import timedelta
        event_end_datetime = event_datetime + timedelta(hours=1)
    
    # Format datetimes for iCalendar (UTC format: YYYYMMDDTHHMMSSZ)
    # We'll use local time without timezone conversion for simplicity
    dtstart = event_datetime.strftime('%Y%m%dT%H%M%S')
    dtend = event_end_datetime.strftime('%Y%m%dT%H%M%S')
    dtstamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    
    # Build the event URL
    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'
    event_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}{url_for('events.event_profile', puid=puid)}"
    
    # Clean and format description
    description = event.get('details', '').replace('\n', '\\n').replace(',', '\\,')
    location = event.get('location', '').replace('\n', '\\n').replace(',', '\\,')
    title = event.get('title', 'Event').replace('\n', '\\n').replace(',', '\\,')
    
    # Get creator info
    creator = get_user_by_puid(event.get('created_by_user_puid'))
    organizer_name = creator.get('display_name', 'Unknown') if creator else 'Unknown'
    organizer_name = organizer_name.replace(',', '\\,')
    
    # Generate UID (unique identifier for this event)
    uid = f"{event['puid']}@{current_app.config.get('NODE_HOSTNAME')}"
    
    # Build iCalendar content
    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//NODE Social//Event Calendar//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{dtstamp}
DTSTART:{dtstart}
DTEND:{dtend}
SUMMARY:{title}
DESCRIPTION:{description}
LOCATION:{location}
URL:{event_url}
ORGANIZER;CN={organizer_name}:MAILTO:noreply@{current_app.config.get('NODE_HOSTNAME')}
STATUS:{'CANCELLED' if event.get('is_cancelled') else 'CONFIRMED'}
SEQUENCE:0
END:VEVENT
END:VCALENDAR"""
    
    from flask import Response
    response = Response(ics_content, mimetype='text/calendar')
    response.headers['Content-Disposition'] = f'attachment; filename="{event["puid"]}.ics"'
    return response