# utils/federation_utils.py
import hmac
import hashlib
import json
import requests
from functools import wraps
from flask import request, jsonify, g, current_app
import threading
import traceback
# MODIFICATION: Import get_all_connected_nodes
from db_queries.federation import get_node_by_hostname, get_all_connected_nodes


def get_remote_node_api_url(node_hostname, endpoint, insecure_mode):
    """
    Constructs the full API URL for a remote node.
    """
    protocol = "http" if insecure_mode else "https"
    return f"{protocol}://{node_hostname}{endpoint}"

def signature_required(f):
    """
    A decorator to protect federation API endpoints. It ensures that incoming
    requests are from a known, connected node and are correctly signed.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Import moved inside to potentially help with circular dependencies if routes import this
        from db_queries.federation import get_node_by_hostname

        remote_hostname = request.headers.get('X-Node-Hostname')
        signature_header = request.headers.get('X-Node-Signature')

        if not remote_hostname or not signature_header:
            return jsonify({'error': 'Missing federation headers'}), 401

        node = get_node_by_hostname(remote_hostname)
        if not node or node['status'] != 'connected' or not node['shared_secret']:
            return jsonify({'error': 'Unknown or not-connected node'}), 403

        request_body = request.get_data()
        expected_signature = hmac.new(
            node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, signature_header):
            return jsonify({'error': 'Invalid signature'}), 403

        return f(*args, **kwargs)
    return decorated_function

def _send_single_request(method, url, data, headers, verify_ssl):
    """
    Target function for a thread to send a single HTTP request.
    This function contains the actual network call and error handling.
    """
    try:
        response = requests.request(
            method, url, data=data, headers=headers, timeout=10, verify=verify_ssl
        )
        response.raise_for_status()
        print(f"SUCCESS: Sent federated {method} request to {url}, status {response.status_code}")
    except requests.RequestException as e:
        print(f"ERROR: Failed to send federated {method} request to {url}: {e}")
        if e.response is not None:
            print(f"Remote server response status: {e.response.status_code}")
            print(f"Remote server response body: {e.response.text}")
    except Exception:
        print(f"ERROR: An unexpected error occurred in the background thread for {url}:")
        traceback.print_exc()


def _send_federated_request(method, endpoint, payload, nodes_to_notify):
    """
    A helper function to send a signed request to a list of nodes in the background.
    """
    # Import moved inside
    from db_queries.federation import get_node_by_hostname

    if not nodes_to_notify:
        return

    request_body = json.dumps(payload, sort_keys=True).encode('utf-8')

    for hostname in nodes_to_notify:
        node = get_node_by_hostname(hostname)
        if not node or node['status'] != 'connected' or not node['shared_secret']:
            print(f"Skipping federation to {hostname}: Node not connected or missing secret.")
            continue

        shared_secret = node['shared_secret']
        signature = hmac.new(
            shared_secret.encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        headers = {
            'Content-Type': 'application/json',
            'X-Node-Hostname': current_app.config.get('NODE_HOSTNAME'),
            'X-Node-Signature': signature
        }

        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        api_url = get_remote_node_api_url(hostname, endpoint, insecure_mode)
        verify_ssl = not insecure_mode

        # Run each request in its own background thread
        thread = threading.Thread(
            target=_send_single_request,
            args=(method, api_url, request_body, headers, verify_ssl)
        )
        thread.daemon = True # Allows main thread to exit even if background threads are running
        thread.start()


def _get_post_recipient_nodes(post):
    """
    Gets a unique list of remote node hostnames to notify for any post.
    Handles special distribution for public event announcements.
    """
    from db_queries.friends import get_friends_list
    from db_queries.groups import get_group_members
    from utils.text_processing import extract_mentions
    from db_queries.followers import get_followers
    from db_queries.events import get_event_attendees
    # MODIFICATION: get_all_connected_nodes is already imported at top

    recipient_nodes = set()
    own_hostname = current_app.config.get('NODE_HOSTNAME')

    # --- START MODIFICATION: Public Event Announcement Distribution ---
    is_public_event_announcement = False
    # Check if the post has event data and no content
    if post.get('event_id') and \
       post.get('content') is None and \
       post.get('author', {}).get('user_type') == 'public_page' and \
       post.get('event', {}).get('is_public'): # Check the embedded event object
           is_public_event_announcement = True

    if is_public_event_announcement:
        # Send to ALL connected nodes
        print(f"Post {post['cuid']} is a public event announcement. Distributing to all connected nodes.")
        connected_nodes = get_all_connected_nodes()
        for node in connected_nodes:
            if node['status'] == 'connected' and node.get('hostname') and node['hostname'] != own_hostname:
                recipient_nodes.add(node['hostname'])
        
        # Also include all remote attendees' nodes (e.g., if they were invited by a follower on another node)
        attendees = get_event_attendees(post['event_id'])
        for attendee in attendees:
             if attendee.get('hostname') and attendee.get('hostname') != own_hostname:
                 recipient_nodes.add(attendee.get('hostname'))
    # --- END MODIFICATION ---
    else:
        # --- Existing Logic for Other Post Types ---
        if post.get('group_id'):
            # Get the group to check if it's a remote stub
            from db_queries.groups import get_group_by_id
            group = get_group_by_id(post['group_id'])
            
            if group and group.get('hostname') and group['hostname'] != own_hostname:
                # This is a remote group stub - send to the group's origin node
                recipient_nodes.add(group['hostname'])
            else:
                # This is a local group - send to all remote members
                group_members = get_group_members(post['group_id'])
                for member_row in group_members:
                    member = dict(member_row)
                    if member.get('hostname') and member.get('hostname') != own_hostname:
                        recipient_nodes.add(member.get('hostname'))
        elif post.get('event_id'):
            # Get the event to check if it's a remote stub
            from db_queries.events import get_event_by_id
            event = get_event_by_id(post['event_id'])
            
            if event and event.get('hostname') and event['hostname'] != own_hostname:
                # This is a remote event stub - send to the event's origin node
                recipient_nodes.add(event['hostname'])
            else:
                # This is a local event - send to all remote attendees
                attendees = get_event_attendees(post['event_id'])
                for attendee in attendees:
                    if attendee.get('hostname') and attendee.get('hostname') != own_hostname:
                        recipient_nodes.add(attendee.get('hostname'))
        else: # Profile posts
            author_id = post.get('user_id')
            author_user_type = post.get('author', {}).get('user_type')
            profile_owner_id = post.get('profile_user_id')

            if author_user_type == 'public_page':
                followers_list = get_followers(author_id)
                for follower_row in followers_list:
                    follower = dict(follower_row)
                    if follower.get('hostname') and follower.get('hostname') != own_hostname:
                        recipient_nodes.add(follower.get('hostname'))
            else: # Regular user or admin posts
                # Target friends of the profile owner OR the author if it's their own profile
                target_user_id = profile_owner_id if profile_owner_id and profile_owner_id != author_id else author_id
                if target_user_id:
                    friends_list = get_friends_list(target_user_id)
                    for friend_row in friends_list:
                        friend = dict(friend_row)
                        if friend.get('hostname') and friend.get('hostname') != own_hostname:
                            recipient_nodes.add(friend.get('hostname'))

            # Always add profile owner's node if they are remote
            profile_owner = post.get('profile_owner')
            if profile_owner and profile_owner.get('hostname') and profile_owner.get('hostname') != own_hostname:
                recipient_nodes.add(profile_owner.get('hostname'))

        # Mentions (for non-reposts)
        if not post.get('is_repost') and post.get('content'):
            mentioned_users = extract_mentions(post.get('content'))
            for user in mentioned_users:
                if user.get('hostname') and user.get('hostname') != own_hostname:
                    recipient_nodes.add(user.get('hostname'))

        # Original author (for reposts)
        if post.get('is_repost') and post.get('original_post'):
            original_author_hostname = post['original_post']['author'].get('hostname')
            if original_author_hostname and original_author_hostname != own_hostname:
                recipient_nodes.add(original_author_hostname)

        # Post author (always add if remote)
        author = post.get('author')
        if author and author.get('hostname') and author.get('hostname') != own_hostname:
            recipient_nodes.add(author.get('hostname'))
        # --- End Existing Logic ---

    recipient_nodes.discard(None)

    return list(recipient_nodes)


def _get_comment_recipient_nodes(post, commenting_user, comment_content=None, parent_comment_id=None):
    """
    Centralized logic to determine which nodes should be notified about a comment activity (create, update, delete).
    """
    from db_queries.comments import get_comment_by_internal_id
    # MODIFICATION: Added get_user_by_puid
    from db_queries.users import get_user_by_id, get_user_by_puid
    from utils.text_processing import extract_mentions
    from db_queries.friends import get_friends_list
    from db_queries.groups import get_group_members
    from db_queries.events import get_event_attendees
    # MODIFICATION: Added get_followers
    from db_queries.followers import get_followers

    potential_recipients = set()
    own_hostname = current_app.config.get('NODE_HOSTNAME')

    post_context = post.get('original_post', post) # Use original post if it's a repost

    # 1. Post Author
    post_author_hostname = post_context['author'].get('hostname')
    if post_author_hostname:
        potential_recipients.add(post_author_hostname)
    
    # 2. Context Recipients (Group members, Event attendees, Profile owner/friends)
    if post_context.get('group_id'):
        group_members = get_group_members(post_context['group_id'])
        for member_row in group_members:
            member = dict(member_row)
            if member.get('hostname'):
                potential_recipients.add(member.get('hostname'))
    elif post_context.get('event_id'):
        attendees = get_event_attendees(post_context['event_id'])
        for attendee in attendees:
            if attendee.get('hostname'):
                potential_recipients.add(attendee.get('hostname'))
    else: # Profile Post
        # --- NEW LOGIC FOR PUBLIC PAGES ---
        if post_context['author'].get('user_type') == 'public_page':
            # The author of the post is the public page
            page_author = get_user_by_puid(post_context['author']['puid'])
            if page_author:
                followers_list = get_followers(page_author['id'])
                for follower_row in followers_list:
                    follower = dict(follower_row)
                    if follower.get('hostname') and follower.get('hostname') != own_hostname:
                        potential_recipients.add(follower.get('hostname'))
        # --- END NEW LOGIC ---
        
        # --- Existing logic for regular user profile posts ---
        # This can run alongside the public page logic
        profile_owner = post_context.get('profile_owner') or {}
        profile_owner_hostname = profile_owner.get('hostname')
        if profile_owner_hostname:
            potential_recipients.add(profile_owner_hostname)

        # Friends of profile owner (for wall posts)
        profile_user_id = post_context.get('profile_user_id')
        if profile_user_id:
            # This logic is for wall posts on *another user's* profile.
            friends_list = get_friends_list(profile_user_id)
            for friend_row in friends_list:
                friend = dict(friend_row)
                # Only add if friend is remote
                if friend.get('hostname'):
                    potential_recipients.add(friend.get('hostname'))
    
    # 3. Mentions in the comment
    if comment_content:
        mentioned_users = extract_mentions(comment_content)
        for user in mentioned_users:
            if user.get('hostname'):
                potential_recipients.add(user.get('hostname'))

    # 4. Parent Comment Author (if it's a reply)
    if parent_comment_id:
        parent_comment = get_comment_by_internal_id(parent_comment_id)
        if parent_comment:
            parent_author = get_user_by_id(parent_comment['user_id'])
            if parent_author and parent_author.get('hostname'):
                potential_recipients.add(parent_author.get('hostname'))

    # 5. Reposter (if commenting on a repost)
    if post.get('is_repost'):
        reposter_hostname = post['author'].get('hostname')
        if reposter_hostname:
            potential_recipients.add(reposter_hostname)

    # Combine potential recipients
    nodes_to_notify = set(potential_recipients)

    # Always include the commenter's node if they are remote
    commenter_hostname = commenting_user.get('hostname')
    if commenter_hostname:
        nodes_to_notify.add(commenter_hostname)
    
    # Exclude own node and None values
    nodes_to_notify.discard(own_hostname)
    nodes_to_notify.discard(None)
    
    return list(nodes_to_notify)

def _get_event_recipient_nodes(event):
    """
    Gets a unique list of remote node hostnames to notify for event actions.
    """
    from db_queries.events import get_event_attendees
    
    recipient_nodes = set()
    own_hostname = current_app.config.get('NODE_HOSTNAME')

    attendees = get_event_attendees(event['id'])
    for attendee in attendees:
        if attendee.get('hostname') and attendee.get('hostname') != own_hostname:
            recipient_nodes.add(attendee.get('hostname'))

    # Also notify the event's origin node if it's different and not already included
    origin_hostname = event.get('hostname')
    if origin_hostname and origin_hostname != own_hostname:
        recipient_nodes.add(origin_hostname)


    recipient_nodes.discard(None)
    return list(recipient_nodes)

def _get_post_payload(post):
    """Generates the full payload for a post to be federated."""
    from utils.text_processing import extract_mentions, extract_everyone_mention

    author = post['author']
    author_data = {
        'puid': author['puid'],
        'display_name': author['display_name'],
        'hostname': author.get('hostname') or current_app.config.get('NODE_HOSTNAME'),
        'profile_picture_path': author.get('profile_picture_path'),
        'user_type': author.get('user_type')
    }

    post_payload = {
        'type': 'post_create',
        'cuid': post['cuid'],
        'author_data': author_data,
        'profile_puid': post.get('profile_owner', {}).get('puid') if post.get('profile_owner') else None,
        'timestamp': post['timestamp'],
        'privacy_setting': post['privacy_setting'],
        'nu_id': post['nu_id'],
        'is_repost': post.get('is_repost', False),
        'comments_disabled': post.get('comments_disabled', False) # NEW: Add this line
    }

    if post.get('is_repost'):
        if post.get('original_post'):
            post_payload['original_post_cuid'] = post['original_post']['cuid']
    else:
        post_payload['content'] = post['content']
        post_payload['media_files'] = post.get('media_files', [])
        # Extract mentions only if content exists
        post_payload['mentioned_puids'] = [u['puid'] for u in extract_mentions(post['content'])] if post.get('content') else []
        
        # NEW: Add tagged users and location
        import json
        post_payload['tagged_user_puids'] = json.loads(post.get('tagged_user_puids', '[]')) if post.get('tagged_user_puids') else []
        post_payload['location'] = post.get('location')

               # NEW: Add @everyone flag for groups
        if post.get('group'):
            post_payload['has_everyone_mention'] = extract_everyone_mention(post.get('content'), 'group')
        
        # NEW: Add @everyone flag for events
        if post.get('event'):
            post_payload['has_everyone_mention'] = extract_everyone_mention(post.get('content'), 'event')
        
        group_data = None
        if post.get('group'):
            group = post['group']
            group_data = {
                'puid': group.get('puid'),
                'name': group.get('name'),
                'description': group.get('description'),
                'profile_picture_path': group.get('profile_picture_path'),
                # Add group's hostname for remote stubs
                'hostname': group.get('hostname')
            }
        post_payload['group_data'] = group_data
    
    if post.get('event'):
        event = post['event']
        # Ensure datetimes are strings
        event_datetime_str = event['event_datetime'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(event.get('event_datetime'), 'strftime') else str(event.get('event_datetime'))
        event_end_datetime_str = None
        if event.get('event_end_datetime'):
            event_end_datetime_str = event['event_end_datetime'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(event.get('event_end_datetime'), 'strftime') else str(event.get('event_end_datetime'))

        post_payload['event_data'] = {
            'puid': event.get('puid'),
            'created_by_user_puid': event.get('created_by_user_puid'),
            'source_type': event.get('source_type'),
            'source_puid': event.get('source_puid'),
            'title': event.get('title'),
            'event_datetime': event_datetime_str,
            'event_end_datetime': event_end_datetime_str,
            'location': event.get('location'),
            'details': event.get('details'),
            'is_public': event.get('is_public'),
            'hostname': event.get('hostname') or current_app.config.get('NODE_HOSTNAME'), 
            'profile_picture_path': event.get('profile_picture_path')
        }
    
    return post_payload

def distribute_post(post_cuid):
    """
    Distributes a NEW post (or repost) to all relevant remote nodes.
    """
    from db_queries.posts import get_post_by_cuid

    post = get_post_by_cuid(post_cuid)
    
    # MODIFICATION: Check for public event announcement
    is_public_event_announcement = (
        post and post.get('event_id') and post.get('content') is None and
        post.get('author', {}).get('user_type') == 'public_page' and
        post.get('event', {}).get('is_public')
    )
    
    # Don't distribute local-only posts unless it's a public event announcement
    if not post or (post['privacy_setting'] == 'local' and not is_public_event_announcement):
        return

    nodes_to_notify = _get_post_recipient_nodes(post)

    if not nodes_to_notify:
        print(f"distribute_post: No remote nodes to notify for post {post_cuid}.")
        return

    post_payload = _get_post_payload(post)
    print(f"distribute_post: Sending post {post_cuid} ({post_payload.get('type')}) to nodes: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', post_payload, nodes_to_notify)

def distribute_post_to_single_node(post_cuid, hostname):
    """Distributes a post to a single specified remote node."""
    from db_queries.posts import get_post_by_cuid
    
    post = get_post_by_cuid(post_cuid)
    if not post or not hostname:
        return
        
    post_payload = _get_post_payload(post)
    print(f"distribute_post_to_single_node: Sending post {post_cuid} to node: {hostname}")
    _send_federated_request('POST', '/federation/inbox', post_payload, [hostname])


def distribute_post_update(post_cuid, old_privacy_setting=None):
    """
    Distributes an UPDATED post to relevant remote nodes. Reposts cannot be updated.
    Handles both privacy escalation (sending to more nodes) and de-escalation (deleting from some nodes).
    
    Args:
        post_cuid: The CUID of the post being updated
        old_privacy_setting: The previous privacy setting (if privacy changed)
    """
    from db_queries.posts import get_post_by_cuid
    from db_queries.federation import get_all_connected_nodes
    from utils.text_processing import extract_mentions
    from db_queries.friends import get_friends_list
    from db_queries.users import get_user_by_puid

    post = get_post_by_cuid(post_cuid)
    if not post or post.get('is_repost'):
        return

    new_privacy = post['privacy_setting']
    
    # If privacy changed, we need special handling
    if old_privacy_setting and old_privacy_setting != new_privacy:
        print(f"distribute_post_update: Privacy changed from {old_privacy_setting} to {new_privacy}")
        
        # Get post author for friend calculations
        post_author = get_user_by_puid(post['author']['puid'])
        if not post_author:
            return
        
        # Calculate old recipients (who had the post before)
        old_recipients = set()
        if old_privacy_setting == 'public':
            all_nodes = get_all_connected_nodes()
            local_hostname = current_app.config.get('NODE_HOSTNAME')
            old_recipients = {node['hostname'] for node in all_nodes if node['status'] == 'connected' and node['hostname'] != local_hostname}
        elif old_privacy_setting == 'friends':
            friends = get_friends_list(post_author['id'])
            old_recipients = {
                friend['hostname'] for friend in friends 
                if friend.get('hostname') and friend['hostname'] != current_app.config.get('NODE_HOSTNAME')
            }
        # old_privacy_setting == 'local' → old_recipients is empty set
        
        # Calculate new recipients (who should have the post now)
        new_recipients = set()
        if new_privacy == 'public':
            all_nodes = get_all_connected_nodes()
            local_hostname = current_app.config.get('NODE_HOSTNAME')
            new_recipients = {node['hostname'] for node in all_nodes if node['status'] == 'connected' and node['hostname'] != local_hostname}
        elif new_privacy == 'friends':
            friends = get_friends_list(post_author['id'])
            new_recipients = {
                friend['hostname'] for friend in friends 
                if friend.get('hostname') and friend['hostname'] != current_app.config.get('NODE_HOSTNAME')
            }
        # new_privacy == 'local' → new_recipients is empty set
        
        # Nodes that should receive DELETE (had it before, shouldn't have it now)
        nodes_to_delete = old_recipients - new_recipients
        
        # Nodes that should receive UPDATE (should have it now)
        nodes_to_update = new_recipients
        
        # Send DELETE to nodes that should no longer have access
        if nodes_to_delete:
            delete_payload = {
                'type': 'post_delete',
                'cuid': post['cuid']
            }
            print(f"distribute_post_update: Sending DELETE (privacy de-escalation) to {len(nodes_to_delete)} nodes: {nodes_to_delete}")
            _send_federated_request('DELETE', '/federation/inbox', delete_payload, nodes_to_delete)
        
        # For nodes that should have the post, determine if they need CREATE or UPDATE
        if nodes_to_update:
            # Nodes that are NEW (didn't have it before) need CREATE
            nodes_to_create = nodes_to_update - old_recipients
            # Nodes that ALREADY had it need UPDATE
            nodes_to_really_update = nodes_to_update & old_recipients
            
            # Send CREATE to new nodes (privacy escalation)
            if nodes_to_create:
                post_payload = _get_post_payload(post)
                print(f"distribute_post_update: Sending CREATE (privacy escalation) to {len(nodes_to_create)} new nodes: {nodes_to_create}")
                _send_federated_request('POST', '/federation/inbox', post_payload, nodes_to_create)
                
                # Wait for post to be created on remote nodes before sending comments
                import time
                time.sleep(0.5)  # 500ms delay to allow post creation to complete
                
                # NEW: Also send all existing comments to new nodes
                print(f"distribute_post_update: Distributing existing comments for post {post_cuid} to new nodes")
                _distribute_existing_comments_to_nodes(post_cuid, nodes_to_create)
            
            # Send UPDATE to nodes that already had the post
            if nodes_to_really_update:
                mentioned_puids = [u['puid'] for u in extract_mentions(post['content'])] if post.get('content') else []
                
                import json
                tagged_puids = post.get('tagged_user_puids')
                if tagged_puids and isinstance(tagged_puids, str):
                    try:
                        tagged_puids = json.loads(tagged_puids)
                    except (json.JSONDecodeError, TypeError):
                        tagged_puids = None
                
                update_payload = {
                    'type': 'post_update',
                    'cuid': post['cuid'],
                    'content': post['content'],
                    'privacy_setting': post['privacy_setting'],
                    'media_files': post.get('media_files', []),
                    'mentioned_puids': mentioned_puids,
                    'tagged_user_puids': tagged_puids,
                    'location': post.get('location')
                }
                print(f"distribute_post_update: Sending UPDATE to {len(nodes_to_really_update)} existing nodes: {nodes_to_really_update}")
                _send_federated_request('PUT', '/federation/inbox', update_payload, nodes_to_really_update)
        
        return
    
    # No privacy change - normal update flow
    if new_privacy == 'local':
        return  # Don't distribute local posts
    
    nodes_to_notify = _get_post_recipient_nodes(post)
    
    if not nodes_to_notify:
        print(f"distribute_post_update: No remote nodes to notify for {post_cuid}")
        return
        
    mentioned_puids = [u['puid'] for u in extract_mentions(post['content'])] if post.get('content') else []

    import json
    tagged_puids = post.get('tagged_user_puids')
    if tagged_puids and isinstance(tagged_puids, str):
        try:
            tagged_puids = json.loads(tagged_puids)
        except (json.JSONDecodeError, TypeError):
            tagged_puids = None    

    post_payload = {
        'type': 'post_update',
        'cuid': post['cuid'],
        'content': post['content'],
        'privacy_setting': post['privacy_setting'],
        'media_files': post.get('media_files', []),
        'mentioned_puids': mentioned_puids,
        'tagged_user_puids': tagged_puids,
        'location': post.get('location')
    }
    print(f"distribute_post_update: Sending update for {post_cuid} to nodes: {nodes_to_notify}")
    _send_federated_request('PUT', '/federation/inbox', post_payload, nodes_to_notify)

def _distribute_existing_comments_to_nodes(post_cuid, nodes):
    """
    Distributes all existing comments for a post to specific nodes.
    Used when privacy escalation makes a post visible to new nodes.
    
    Args:
        post_cuid: The CUID of the post
        nodes: Set of hostnames to send comments to
    """
    from db_queries.comments import get_comments_for_post
    from db_queries.posts import get_post_by_cuid
    
    if not nodes:
        return
    
    post = get_post_by_cuid(post_cuid)
    if not post:
        return
    
    # Get all comments for this post (including replies)
    all_comments = get_comments_for_post(post['id'], viewer_user_id=None)
    
    if not all_comments:
        print(f"_distribute_existing_comments_to_nodes: No comments to distribute for post {post_cuid}")
        return
    
    print(f"_distribute_existing_comments_to_nodes: Found {len(all_comments)} top-level comments for post {post_cuid}")
    
    # Flatten the comment tree (get all comments including nested replies)
    def flatten_comments(comments):
        """Recursively flatten comment tree"""
        flat = []
        for comment in comments:
            flat.append(comment)
            if comment.get('replies'):
                flat.extend(flatten_comments(comment['replies']))
        return flat
    
    all_comments_flat = flatten_comments(all_comments)
    print(f"_distribute_existing_comments_to_nodes: Total comments (including replies): {len(all_comments_flat)}")
    
    # Build comment payloads
    for comment in all_comments_flat:
        # Get parent CUID if this is a reply
        parent_cuid = None
        if comment.get('parent_comment_id'):
            from db_queries.comments import get_comment_by_internal_id
            parent_comment = get_comment_by_internal_id(comment['parent_comment_id'])
            if parent_comment:
                parent_cuid = parent_comment.get('cuid')
        
        # Build author data
        author_data = {
            'puid': comment['puid'],
            'display_name': comment['display_name'],
            'hostname': comment.get('hostname') or current_app.config.get('NODE_HOSTNAME'),
            'profile_picture_path': comment.get('profile_picture_path')
        }
        
        # Build comment payload
        comment_payload = {
            'type': 'comment_create',
            'cuid': comment['cuid'],
            'post_cuid': post_cuid,
            'author_data': author_data,
            'content': comment['content'],
            'timestamp': comment['timestamp'],
            'parent_cuid': parent_cuid,
            'nu_id': comment['nu_id'],
            'media_files': comment.get('media_files', [])
        }
        
        # Send to new nodes
        _send_federated_request('POST', '/federation/inbox', comment_payload, nodes)
    
    print(f"_distribute_existing_comments_to_nodes: Sent {len(all_comments_flat)} comments to {len(nodes)} new nodes")

def distribute_post_delete(post):
    """
    Distributes a DELETE action for a post to relevant remote nodes.
    """
    # MODIFICATION: Check for public event announcement
    is_public_event_announcement = (
        post and post.get('event_id') and post.get('content') is None and
        post.get('author', {}).get('user_type') == 'public_page' and
        post.get('event', {}).get('is_public')
    )
    
    # Allow deletion distribution even for 'local' if it's a repost or event announcement
    if not post or (post['privacy_setting'] == 'local' and not post.get('is_repost') and not is_public_event_announcement):
        return

    nodes_to_notify = _get_post_recipient_nodes(post)

    if not nodes_to_notify:
        return

    delete_payload = {
        'type': 'post_delete',
        'cuid': post['cuid']
    }
    print(f"distribute_post_delete: Sending delete for {post['cuid']} to nodes: {nodes_to_notify}")
    _send_federated_request('DELETE', '/federation/inbox', delete_payload, nodes_to_notify)

def distribute_comment(comment_cuid):
    """
    Distributes a NEW comment or reply to all relevant remote nodes.
    """
    from db_queries.comments import get_comment_by_cuid, get_comment_by_internal_id
    from db_queries.posts import get_post_by_cuid
    from db_queries.users import get_user_by_id

    comment_info = get_comment_by_cuid(comment_cuid)
    if not comment_info: return

    comment = get_comment_by_internal_id(comment_info['comment_id'])
    post = get_post_by_cuid(comment_info['post_cuid'])
    
    if not comment or not post or post.get('privacy_setting') == 'local': return

    commenting_user = get_user_by_id(comment['user_id'])
    if not commenting_user: return

    nodes_to_notify = _get_comment_recipient_nodes(post, commenting_user, comment['content'], comment.get('parent_comment_id'))

    if not nodes_to_notify:
        print(f"distribute_comment: No remote nodes to notify for comment {comment_cuid}.")
        return

    parent_cuid = None
    if comment.get('parent_comment_id'):
        parent_comment = get_comment_by_internal_id(comment['parent_comment_id'])
        if parent_comment:
            parent_cuid = parent_comment.get('cuid')

    author_data = {
        'puid': commenting_user['puid'],
        'display_name': commenting_user['display_name'],
        'hostname': commenting_user.get('hostname') or current_app.config.get('NODE_HOSTNAME'),
        'profile_picture_path': commenting_user.get('profile_picture_path')
    }

    comment_payload = {
        'type': 'comment_create',
        'cuid': comment['cuid'],
        'post_cuid': post['cuid'],
        'author_data': author_data,
        'content': comment['content'],
        'timestamp': comment['timestamp'],
        'parent_cuid': parent_cuid,
        'nu_id': comment['nu_id'],
        'media_files': comment.get('media_files', [])
    }
    
    print(f"distribute_comment: Sending comment {comment_cuid} to nodes: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', comment_payload, nodes_to_notify)

def distribute_comment_update(comment_cuid):
    """
    Distributes an UPDATED comment to all relevant remote nodes.
    """
    from db_queries.comments import get_comment_by_cuid, get_comment_by_internal_id
    from db_queries.posts import get_post_by_cuid
    from db_queries.users import get_user_by_id

    comment_info = get_comment_by_cuid(comment_cuid)
    if not comment_info: return

    comment = get_comment_by_internal_id(comment_info['comment_id'])
    post = get_post_by_cuid(comment_info['post_cuid'])
    
    if not comment or not post or post.get('privacy_setting') == 'local': return

    commenting_user = get_user_by_id(comment['user_id'])
    if not commenting_user: return

    nodes_to_notify = _get_comment_recipient_nodes(post, commenting_user, comment['content'], comment.get('parent_comment_id'))

    if not nodes_to_notify:
        print(f"distribute_comment_update: No remote nodes to notify for comment {comment_cuid}.")
        return

    update_payload = {
        'type': 'comment_update',
        'cuid': comment['cuid'],
        'post_cuid': post['cuid'],
        'content': comment['content'],
        'media_files': comment.get('media_files', [])
    }

    print(f"distribute_comment_update: Sending update for comment {comment_cuid} to nodes: {nodes_to_notify}")
    _send_federated_request('PUT', '/federation/inbox', update_payload, nodes_to_notify)

def distribute_comment_delete(comment, post):
    """
    Distributes a DELETE action for a comment to relevant remote nodes.
    Requires the full comment and post objects *before* deletion.
    """
    from db_queries.users import get_user_by_id

    if not comment or not post or post.get('privacy_setting') == 'local':
        return

    commenting_user = get_user_by_id(comment['user_id'])
    if not commenting_user:
        return

    nodes_to_notify = _get_comment_recipient_nodes(post, commenting_user)

    if not nodes_to_notify:
        print(f"distribute_comment_delete: No remote nodes to notify for comment {comment['cuid']}.")
        return

    delete_payload = {
        'type': 'comment_delete',
        'cuid': comment['cuid'],
        'post_cuid': post['cuid']
    }

    print(f"distribute_comment_delete: Sending delete for comment {comment['cuid']} to nodes: {nodes_to_notify}")
    _send_federated_request('DELETE', '/federation/inbox', delete_payload, nodes_to_notify)

def _get_media_comment_recipient_nodes(media_item, commenting_user, comment_content=None, parent_comment_id=None):
    """
    Determines which nodes should be notified about a media comment activity.
    Similar to _get_comment_recipient_nodes but for media items.
    """
    from db_queries.users import get_user_by_id, get_user_by_puid
    from db_queries.media import get_media_comment_by_internal_id
    from utils.text_processing import extract_mentions
    from db_queries.posts import get_post_by_cuid
    from db import get_db
    
    potential_recipients = set()
    own_hostname = current_app.config.get('NODE_HOSTNAME')
    
    # Get the parent post for this media
    post_id = media_item.get('post_id')
    if not post_id:
        return []
    
    # Get post by querying database directly since there's no get_post_by_id
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT cuid FROM posts WHERE id = ?", (post_id,))
    post_row = cursor.fetchone()
    
    if not post_row:
        return []
    
    post = get_post_by_cuid(post_row['cuid'])
    if not post or post.get('privacy_setting') == 'local':
        return []
    
    # 1. Media/Post Author
    post_author_puid = post.get('author_puid')
    if post_author_puid:
        post_author = get_user_by_puid(post_author_puid)
        if post_author and post_author.get('hostname'):
            potential_recipients.add(post_author.get('hostname'))
    
    # 2. Tagged Users in the media
    if media_item.get('tagged_user_puids'):
        import json
        try:
            tagged_puids = json.loads(media_item['tagged_user_puids']) if isinstance(media_item['tagged_user_puids'], str) else media_item['tagged_user_puids']
            for puid in tagged_puids:
                tagged_user = get_user_by_puid(puid)
                if tagged_user and tagged_user.get('hostname'):
                    potential_recipients.add(tagged_user.get('hostname'))
        except (json.JSONDecodeError, TypeError):
            pass
    
    # 3. Mentioned Users in comment content
    if comment_content:
        mentioned_users = extract_mentions(comment_content)
        for user in mentioned_users:
            if user.get('hostname'):
                potential_recipients.add(user.get('hostname'))
    
    # 4. Parent Comment Author (if it's a reply)
    if parent_comment_id:
        parent_comment = get_media_comment_by_internal_id(parent_comment_id)
        if parent_comment:
            parent_author = get_user_by_id(parent_comment['user_id'])
            if parent_author and parent_author.get('hostname'):
                potential_recipients.add(parent_author.get('hostname'))
    
    # 5. Get all nodes that have the post (most important!)
    # Use the same logic as distribute_comment
    nodes_to_notify = _get_post_recipient_nodes(post)
    for node in nodes_to_notify:
        potential_recipients.add(node)
    
    # Always include the commenter's node if they are remote
    commenter_hostname = commenting_user.get('hostname')
    if commenter_hostname:
        potential_recipients.add(commenter_hostname)
    
    # Exclude own node and None values
    potential_recipients.discard(own_hostname)
    potential_recipients.discard(None)
    
    return list(potential_recipients)


def distribute_media_comment(media_comment_cuid):
    """
    Distributes a NEW media comment or reply to all relevant remote nodes.
    """
    from db_queries.media import get_media_comment_by_cuid, get_media_comment_by_internal_id, get_media_by_muid
    from db_queries.users import get_user_by_id
    
    comment_info = get_media_comment_by_cuid(media_comment_cuid)
    if not comment_info:
        return
    
    comment = get_media_comment_by_internal_id(comment_info['comment_id'])
    if not comment:
        return
    
    # Get the media item
    media_id = comment.get('media_id')
    if not media_id:
        return
    
    from db import get_db
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT muid, post_id, tagged_user_puids FROM post_media WHERE id = ?", (media_id,))
    media_row = cursor.fetchone()
    
    if not media_row:
        return
    
    media_item = dict(media_row)
    
    commenting_user = get_user_by_id(comment['user_id'])
    if not commenting_user:
        return
    
    nodes_to_notify = _get_media_comment_recipient_nodes(
        media_item, 
        commenting_user, 
        comment['content'], 
        comment.get('parent_comment_id')
    )
    
    if not nodes_to_notify:
        print(f"distribute_media_comment: No remote nodes to notify for media comment {media_comment_cuid}.")
        return
    
    parent_cuid = None
    if comment.get('parent_comment_id'):
        parent_comment = get_media_comment_by_internal_id(comment['parent_comment_id'])
        if parent_comment:
            parent_cuid = parent_comment.get('cuid')
    
    author_data = {
        'puid': commenting_user['puid'],
        'display_name': commenting_user['display_name'],
        'hostname': commenting_user.get('hostname') or current_app.config.get('NODE_HOSTNAME'),
        'profile_picture_path': commenting_user.get('profile_picture_path')
    }
    
    comment_payload = {
        'type': 'media_comment_create',
        'cuid': comment['cuid'],
        'muid': media_item['muid'],
        'author_data': author_data,
        'content': comment['content'],
        'timestamp': comment['timestamp'],
        'parent_cuid': parent_cuid,
        'nu_id': comment['nu_id'],
        'media_files': comment.get('media_files', [])
    }
    
    print(f"distribute_media_comment: Sending media comment {media_comment_cuid} to nodes: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', comment_payload, nodes_to_notify)


def distribute_media_comment_update(media_comment_cuid):
    """
    Distributes an UPDATED media comment to all relevant remote nodes.
    """
    from db_queries.media import get_media_comment_by_cuid, get_media_comment_by_internal_id
    from db_queries.users import get_user_by_id
    from db import get_db
    
    comment_info = get_media_comment_by_cuid(media_comment_cuid)
    if not comment_info:
        return
    
    comment = get_media_comment_by_internal_id(comment_info['comment_id'])
    if not comment:
        return
    
    # Get the media item
    media_id = comment.get('media_id')
    if not media_id:
        return
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT muid, post_id, tagged_user_puids FROM post_media WHERE id = ?", (media_id,))
    media_row = cursor.fetchone()
    
    if not media_row:
        return
    
    media_item = dict(media_row)
    
    commenting_user = get_user_by_id(comment['user_id'])
    if not commenting_user:
        return
    
    nodes_to_notify = _get_media_comment_recipient_nodes(media_item, commenting_user, comment['content'], comment.get('parent_comment_id'))
    
    if not nodes_to_notify:
        print(f"distribute_media_comment_update: No remote nodes to notify for media comment {media_comment_cuid}.")
        return
    
    update_payload = {
        'type': 'media_comment_update',
        'cuid': comment['cuid'],
        'muid': media_item['muid'],
        'content': comment['content'],
        'media_files': comment.get('media_files', [])
    }
    
    print(f"distribute_media_comment_update: Sending update for media comment {media_comment_cuid} to nodes: {nodes_to_notify}")
    _send_federated_request('PUT', '/federation/inbox', update_payload, nodes_to_notify)


def distribute_media_comment_delete(comment, media_item):
    """
    Distributes a DELETE action for a media comment to relevant remote nodes.
    Requires the full comment and media_item objects *before* deletion.
    """
    from db_queries.users import get_user_by_id
    
    if not comment or not media_item:
        return
    
    commenting_user = get_user_by_id(comment['user_id'])
    if not commenting_user:
        return
    
    nodes_to_notify = _get_media_comment_recipient_nodes(media_item, commenting_user)
    
    if not nodes_to_notify:
        print(f"distribute_media_comment_delete: No remote nodes to notify for media comment {comment['cuid']}.")
        return
    
    delete_payload = {
        'type': 'media_comment_delete',
        'cuid': comment['cuid'],
        'muid': media_item['muid']
    }
    
    print(f"distribute_media_comment_delete: Sending delete for media comment {comment['cuid']} to nodes: {nodes_to_notify}")
    _send_federated_request('DELETE', '/federation/inbox', delete_payload, nodes_to_notify)

def distribute_event_invite(event, invitee_puid):
    """
    Distributes an event invitation to a remote user.
    """
    from db_queries.users import get_user_by_puid
    from db_queries.groups import get_group_by_puid

    invitee = get_user_by_puid(invitee_puid)
    if not invitee or not invitee.get('hostname'):
        return

    nodes_to_notify = [invitee.get('hostname')]
    
    # Ensure datetimes are strings
    event_datetime_str = event['event_datetime'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(event.get('event_datetime'), 'strftime') else str(event.get('event_datetime'))
    event_end_datetime_str = None
    if event.get('event_end_datetime'):
         event_end_datetime_str = event['event_end_datetime'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(event.get('event_end_datetime'), 'strftime') else str(event.get('event_end_datetime'))

    # Get creator display name
    creator = get_user_by_puid(event['created_by_user_puid'])
    creator_display_name = creator.get('display_name') if creator else None
    
    # Get group name if this is a group event
    group_name = None
    if event.get('source_type') == 'group' and event.get('source_puid'):
        group = get_group_by_puid(event['source_puid'])
        group_name = group.get('name') if group else None

    event_payload = {
        'type': 'event_invite',
        'puid': event['puid'],
        'created_by_user_puid': event['created_by_user_puid'],
        'creator_display_name': creator_display_name,
        'source_type': event['source_type'],
        'source_puid': event['source_puid'],
        'group_name': group_name,
        'title': event['title'],
        'event_datetime': event_datetime_str,
        'event_end_datetime': event_end_datetime_str,
        'location': event['location'],
        'details': event['details'],
        'is_public': event['is_public'],
        'hostname': current_app.config.get('NODE_HOSTNAME'),
        'profile_picture_path': event.get('profile_picture_path'),
        'invitee_puid': invitee_puid
    }
    print(f"distribute_event_invite: Sending invite for event {event['puid']} to {invitee_puid} via node {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', event_payload, nodes_to_notify)

def distribute_event_update(event_puid, actor):
    from db_queries.events import get_event_by_puid
    
    event = get_event_by_puid(event_puid)
    if not event:
        return

    nodes_to_notify = _get_event_recipient_nodes(event)
    if not nodes_to_notify:
        return

    if not actor:
        return # Actor required

    # Ensure datetimes are strings
    event_datetime_str = event['event_datetime'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(event.get('event_datetime'), 'strftime') else str(event.get('event_datetime'))
    event_end_datetime_str = event['event_end_datetime'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(event.get('event_end_datetime'), 'strftime') else str(event.get('event_end_datetime')) if event.get('event_end_datetime') else None

    actor_data = {
        'puid': actor['puid'],
        'display_name': actor['display_name'],
        'hostname': actor.get('hostname') or current_app.config.get('NODE_HOSTNAME'),
        'profile_picture_path': actor.get('profile_picture_path')
    }

    payload = {
        'type': 'event_update',
        'puid': event['puid'],
        'title': event['title'],
        'event_datetime': event_datetime_str,
        'event_end_datetime': event_end_datetime_str,
        'location': event['location'],
        'details': event['details'],
        'profile_picture_path': event.get('profile_picture_path'),
        'actor_data': actor_data
    }
    print(f"distribute_event_update: Sending update for {event_puid} to nodes: {nodes_to_notify}")
    _send_federated_request('PUT', '/federation/inbox', payload, nodes_to_notify)

def distribute_event_cancel(event_puid, actor):
    from db_queries.events import get_event_by_puid

    event = get_event_by_puid(event_puid)
    if not event:
        return

    nodes_to_notify = _get_event_recipient_nodes(event)
    if not nodes_to_notify:
        return

    if not actor:
        return # Actor required

    payload = {
        'type': 'event_cancel',
        'puid': event['puid'],
        'actor_puid': actor['puid']
    }
    print(f"distribute_event_cancel: Sending cancel for {event_puid} to nodes: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', payload, nodes_to_notify)

def distribute_event_response(event_puid, responder_puid, response):
    from db_queries.events import get_event_by_puid
    
    event = get_event_by_puid(event_puid)
    if not event or not event.get('hostname'): # Only distribute responses *back* to the origin node
        return
        
    nodes_to_notify = [event.get('hostname')]

    payload = {
        'type': 'event_response',
        'event_puid': event_puid,
        'responder_puid': responder_puid,
        'response': response
    }
    print(f"distribute_event_response: Sending response '{response}' for {event_puid} by {responder_puid} to node: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', payload, nodes_to_notify)

# NEW: Function to distribute comment status updates
def distribute_post_comment_status_update(post_cuid, actor):
    """
    Distributes a post's comment status (e.g., comments disabled) to relevant nodes.
    """
    from db_queries.posts import get_post_by_cuid

    post = get_post_by_cuid(post_cuid)
    # Don't distribute for local-only posts
    if not post or post['privacy_setting'] == 'local':
        return

    nodes_to_notify = _get_post_recipient_nodes(post)
    if not nodes_to_notify:
        return

    if not actor:
        return # Actor required

    actor_data = {
        'puid': actor['puid'],
        'display_name': actor['display_name'],
        'hostname': actor.get('hostname') or current_app.config.get('NODE_HOSTNAME'),
        'profile_picture_path': actor.get('profile_picture_path')
    }
    
    payload = {
        'type': 'post_comment_status_update',
        'cuid': post['cuid'],
        'comments_disabled': post.get('comments_disabled', False),
        'actor_data': actor_data # To log who made the change
    }
    print(f"distribute_post_comment_status_update: Sending comments_disabled={post.get('comments_disabled')} for {post_cuid} to nodes: {nodes_to_notify}")
    _send_federated_request('PUT', '/federation/inbox', payload, nodes_to_notify)

# --- NEW: FUNCTION TO DISTRIBUTE PROFILE UPDATES ---
def distribute_profile_update(puid, display_name, profile_picture_path):
    """
    Distributes a local user's profile update (display name, profile pic)
    to all remote nodes where they have friends.
    """
    # Import locally to avoid circular dependency
    from db_queries.users import get_user_by_puid
    from db_queries.friends import get_friends_list
    
    # 1. Get the user object
    user = get_user_by_puid(puid)
    if not user or user.get('hostname') is not None:
        print(f"distribute_profile_update: Skipping, user {puid} is not local or not found.")
        return

    # 2. Get all friends of this user
    friends = get_friends_list(user['id'])
    
    # 3. Filter for remote friends and group by hostname
    remote_nodes_to_notify = set()
    for friend in friends:
        if friend.get('hostname') and friend['hostname'] != current_app.config.get('NODE_HOSTNAME'):
            remote_nodes_to_notify.add(friend['hostname'])

    if not remote_nodes_to_notify:
        print(f"distribute_profile_update: No remote friends to notify for user {puid}.")
        return

    # 4. Construct the payload
    payload = {
        'type': 'profile_update',
        'puid': puid,
        'display_name': display_name,
        'profile_picture_path': profile_picture_path,
        'hostname': current_app.config.get('NODE_HOSTNAME') # The user's home node
    }
    
    # 5. Send the request
    print(f"distribute_profile_update: Sending profile update for {puid} to nodes: {list(remote_nodes_to_notify)}")
    _send_federated_request('PUT', '/federation/inbox', payload, list(remote_nodes_to_notify))

def distribute_tag_removal(post_cuid, removed_user_puid, actor_puid):
    """
    Distributes a tag removal action to relevant remote nodes.
    
    Args:
        post_cuid: The post CUID
        removed_user_puid: PUID of the user being untagged
        actor_puid: PUID of the user performing the action (usually same as removed_user_puid)
    """
    from db_queries.posts import get_post_by_cuid
    
    post = get_post_by_cuid(post_cuid)
    if not post or post['privacy_setting'] == 'local':
        return
    
    nodes_to_notify = _get_post_recipient_nodes(post)
    if not nodes_to_notify:
        print(f"distribute_tag_removal: No remote nodes to notify for post {post_cuid}.")
        return
    
    payload = {
        'type': 'tag_removal',
        'post_cuid': post_cuid,
        'removed_user_puid': removed_user_puid,
        'actor_puid': actor_puid
    }
    
    print(f"distribute_tag_removal: Sending tag removal for user {removed_user_puid} from post {post_cuid} to nodes: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', payload, nodes_to_notify)


def distribute_mention_removal_post(post_cuid, removed_mention, actor_puid):
    """
    Distributes a mention removal from a post to relevant remote nodes.
    
    Args:
        post_cuid: The post CUID
        removed_mention: The display name that was removed (e.g., "Emma Smith")
        actor_puid: PUID of the user performing the action
    """
    from db_queries.posts import get_post_by_cuid
    
    post = get_post_by_cuid(post_cuid)
    if not post or post['privacy_setting'] == 'local':
        return
    
    nodes_to_notify = _get_post_recipient_nodes(post)
    if not nodes_to_notify:
        print(f"distribute_mention_removal_post: No remote nodes to notify for post {post_cuid}.")
        return
    
    payload = {
        'type': 'mention_removal_post',
        'post_cuid': post_cuid,
        'removed_mention': removed_mention,
        'actor_puid': actor_puid,
        'updated_content': post['content']  # Send the new content after removal
    }
    
    print(f"distribute_mention_removal_post: Sending mention removal for @{removed_mention} from post {post_cuid} to nodes: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', payload, nodes_to_notify)


def distribute_mention_removal_comment(comment_cuid, removed_mention, actor_puid):
    """
    Distributes a mention removal from a comment to relevant remote nodes.
    
    Args:
        comment_cuid: The comment CUID
        removed_mention: The display name that was removed (e.g., "Emma Smith")
        actor_puid: PUID of the user performing the action
    """
    from db_queries.comments import get_comment_by_cuid, get_comment_by_internal_id
    from db_queries.posts import get_post_by_cuid
    
    comment_info = get_comment_by_cuid(comment_cuid)
    if not comment_info:
        return
    
    comment = get_comment_by_internal_id(comment_info['comment_id'])
    post = get_post_by_cuid(comment_info['post_cuid'])
    
    if not comment or not post or post['privacy_setting'] == 'local':
        return
    
    from db_queries.users import get_user_by_id
    commenting_user = get_user_by_id(comment['user_id'])
    if not commenting_user:
        return
    
    nodes_to_notify = _get_comment_recipient_nodes(post, commenting_user)
    if not nodes_to_notify:
        print(f"distribute_mention_removal_comment: No remote nodes to notify for comment {comment_cuid}.")
        return
    
    payload = {
        'type': 'mention_removal_comment',
        'comment_cuid': comment_cuid,
        'post_cuid': post['cuid'],
        'removed_mention': removed_mention,
        'actor_puid': actor_puid,
        'updated_content': comment['content']  # Send the new content after removal
    }
    
    print(f"distribute_mention_removal_comment: Sending mention removal for @{removed_mention} from comment {comment_cuid} to nodes: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', payload, nodes_to_notify)

def distribute_mention_removal_media_comment(media_comment_cuid, removed_mention, actor_puid):
    """
    Distributes a mention removal from a media comment to relevant remote nodes.
    
    Args:
        media_comment_cuid: The media comment CUID
        removed_mention: The display name that was removed (e.g., "Emma Smith")
        actor_puid: PUID of the user performing the action
    """
    from db_queries.media import get_media_comment_by_cuid, get_media_comment_by_internal_id
    from db_queries.users import get_user_by_id
    from db import get_db
    
    comment_info = get_media_comment_by_cuid(media_comment_cuid)
    if not comment_info:
        return
    
    comment = get_media_comment_by_internal_id(comment_info['comment_id'])
    if not comment:
        return
    
    # Get the media item
    media_id = comment.get('media_id')
    if not media_id:
        return
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT muid, post_id, tagged_user_puids FROM post_media WHERE id = ?", (media_id,))
    media_row = cursor.fetchone()
    
    if not media_row:
        return
    
    media_item = dict(media_row)
    
    commenting_user = get_user_by_id(comment['user_id'])
    if not commenting_user:
        return
    
    nodes_to_notify = _get_media_comment_recipient_nodes(media_item, commenting_user)
    if not nodes_to_notify:
        print(f"distribute_mention_removal_media_comment: No remote nodes to notify for media comment {media_comment_cuid}.")
        return
    
    payload = {
        'type': 'mention_removal_media_comment',
        'media_comment_cuid': media_comment_cuid,
        'removed_mention': removed_mention,
        'actor_puid': actor_puid,
        'updated_content': comment['content']  # Send the new content after removal
    }
    
    print(f"distribute_mention_removal_media_comment: Sending mention removal for @{removed_mention} from media comment {media_comment_cuid} to nodes: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', payload, nodes_to_notify)

def distribute_media_tags(muid, tagged_user_puids, actor_puid):
    """
    Distributes media tags to all relevant remote nodes.
    
    Args:
        muid: The MUID of the media item
        tagged_user_puids: List of PUIDs that are tagged
        actor_puid: PUID of the user performing the tagging
    """
    from db_queries.media import get_media_by_muid
    from db_queries.posts import get_post_by_cuid
    from db import get_db
    
    # Get the media item
    media = get_media_by_muid(muid)
    if not media:
        return
    
    # Get the parent post
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT cuid FROM posts WHERE id = ?", (media['post_id'],))
    post_row = cursor.fetchone()
    if not post_row:
        return
    
    post = get_post_by_cuid(post_row['cuid'])
    if not post or post.get('privacy_setting') == 'local':
        return
    
    # Get all nodes that have this post
    nodes_to_notify = _get_post_recipient_nodes(post)
    if not nodes_to_notify:
        print(f"distribute_media_tags: No remote nodes to notify for media {muid}.")
        return
    
    payload = {
        'type': 'media_tags_update',
        'muid': muid,
        'tagged_user_puids': tagged_user_puids,
        'actor_puid': actor_puid
    }
    
    print(f"distribute_media_tags: Sending tag update for media {muid} to nodes: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', payload, nodes_to_notify)


def distribute_media_tag_removal(muid, removed_user_puid):
    """
    Distributes a single tag removal from a media item to relevant remote nodes.
    
    Args:
        muid: The MUID of the media item
        removed_user_puid: PUID of the user being untagged
    """
    from db_queries.media import get_media_by_muid
    from db_queries.posts import get_post_by_cuid
    from db import get_db
    
    # Get the media item
    media = get_media_by_muid(muid)
    if not media:
        return
    
    # Get the parent post
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT cuid FROM posts WHERE id = ?", (media['post_id'],))
    post_row = cursor.fetchone()
    if not post_row:
        return
    
    post = get_post_by_cuid(post_row['cuid'])
    if not post or post.get('privacy_setting') == 'local':
        return
    
    # Get all nodes that have this post
    nodes_to_notify = _get_post_recipient_nodes(post)
    if not nodes_to_notify:
        print(f"distribute_media_tag_removal: No remote nodes to notify for media {muid}.")
        return
    
    payload = {
        'type': 'media_tag_removal',
        'muid': muid,
        'removed_user_puid': removed_user_puid
    }
    
    print(f"distribute_media_tag_removal: Sending tag removal for user {removed_user_puid} from media {muid} to nodes: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', payload, nodes_to_notify)

def distribute_poll_data(post_cuid):
    """
    Distributes poll data for a federated post.
    Called after distribute_post to send poll information.
    """
    from db_queries.posts import get_post_by_cuid
    from db_queries.polls import get_poll_by_post_id
    
    post = get_post_by_cuid(post_cuid)
    if not post:
        return
    
    poll = get_poll_by_post_id(post['id'])
    if not poll:
        return
    
    # Get nodes using the same logic as posts
    nodes_to_notify = _get_post_recipient_nodes(post)
    if not nodes_to_notify:
        print(f"distribute_poll_data: No remote nodes to notify for post {post_cuid}.")
        return
    
    # Prepare poll data payload
    poll_payload = {
        'type': 'poll_create',
        'post_cuid': post_cuid,
        'poll': {
            'allow_multiple_answers': poll['allow_multiple_answers'],
            'allow_add_options': poll['allow_add_options'],
            'options': [
                {
                    'option_text': opt['option_text'],
                    'display_order': opt['display_order']
                }
                for opt in poll['options']
                if opt['created_by_user_id'] is None  # Only send original options
            ]
        }
    }
    print(f"distribute_poll_data: Poll payload = {poll_payload}")
    print(f"distribute_poll_data: Sending poll for post {post_cuid} to nodes: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', poll_payload, nodes_to_notify)


def distribute_poll_vote(post_cuid, option_id, voter_puid, is_adding):
    """
    Distributes a poll vote to the origin node and connected nodes.
    """
    from db_queries.posts import get_post_by_cuid
    from db_queries.polls import get_poll_by_post_id
    
    post = get_post_by_cuid(post_cuid)
    if not post:
        return
    
    poll = get_poll_by_post_id(post['id'])
    if not poll:
        return
    
    # Find the option
    option = next((opt for opt in poll['options'] if opt['id'] == option_id), None)
    if not option:
        return
    
    # Get nodes using the same logic as posts
    nodes_to_notify = _get_post_recipient_nodes(post)
    if not nodes_to_notify:
        return
    
    vote_payload = {
        'type': 'poll_vote' if is_adding else 'poll_unvote',
        'post_cuid': post_cuid,
        'option_text': option['option_text'],
        'voter_puid': voter_puid
    }
    
    print(f"distribute_poll_vote: Sending {'vote' if is_adding else 'unvote'} for post {post_cuid} to nodes: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', vote_payload, nodes_to_notify)


def distribute_poll_option_add(post_cuid, option_text, creator_puid):
    """
    Distributes a user-added poll option.
    """
    from db_queries.posts import get_post_by_cuid
    
    post = get_post_by_cuid(post_cuid)
    if not post:
        return
    
    nodes_to_notify = _get_post_recipient_nodes(post)
    if not nodes_to_notify:
        return
    
    option_payload = {
        'type': 'poll_option_add',
        'post_cuid': post_cuid,
        'option_text': option_text,
        'creator_puid': creator_puid
    }
    
    print(f"distribute_poll_option_add: Sending option add for post {post_cuid} to nodes: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', option_payload, nodes_to_notify)


def distribute_poll_option_delete(post_cuid, option_text):
    """
    Distributes a poll option deletion.
    """
    from db_queries.posts import get_post_by_cuid
    
    post = get_post_by_cuid(post_cuid)
    if not post:
        return
    
    nodes_to_notify = _get_post_recipient_nodes(post)
    if not nodes_to_notify:
        return
    
    delete_payload = {
        'type': 'poll_option_delete',
        'post_cuid': post_cuid,
        'option_text': option_text
    }
    
    print(f"distribute_poll_option_delete: Sending option delete for post {post_cuid} to nodes: {nodes_to_notify}")
    _send_federated_request('POST', '/federation/inbox', delete_payload, nodes_to_notify)