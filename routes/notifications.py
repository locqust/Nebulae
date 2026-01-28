# routes/notifications.py
from flask import Blueprint, jsonify, session, redirect, url_for, flash, current_app, request
from datetime import datetime

# CIRCULAR IMPORT FIX: Imports are moved inside the functions that use them
# to break the import cycle that occurs at application startup.

notifications_bp = Blueprint('notifications', __name__)

@notifications_bp.before_request
def login_required():
    """Ensures a user is logged in before accessing any notification routes."""
    if 'username' not in session:
        # For API endpoints, returning JSON is more appropriate than redirecting.
        return jsonify({'error': 'Authentication required'}), 401

@notifications_bp.route('/notifications', methods=['GET'])
def get_notifications():
    """API endpoint to fetch all notifications for the current user."""
    # Imports are moved here to be executed only when the route is called.
    from db_queries.users import get_user_id_by_username
    from db_queries.notifications import get_notifications_for_user
    # GROUP FEDERATION FIX: Import get_group_by_id to fetch full group object
    from db_queries.groups import get_group_by_id
    # FEDERATION FIX: Import get_event_by_puid for event notifications
    from db_queries.events import get_event_by_puid
    # GROUP FEDERATION FIX: Import the helper function directly
    from app import inject_user_data_functions

    user_id = get_user_id_by_username(session['username'])
    if not user_id:
        return jsonify({'error': 'User not found'}), 404
        
    notifications_raw = get_notifications_for_user(user_id)
    
    # Get the URL generation functions from the context processor
    url_helpers = inject_user_data_functions()
    federated_group_profile_url = url_helpers['federated_group_profile_url']
    federated_event_profile_url = url_helpers['federated_event_profile_url']


    notifications = []
    for row in notifications_raw:
        n = dict(row)
        
        actor_pic_path = n.get('actor_profile_picture_path')

        # Build actor profile picture URL
        if n.get('actor_hostname') and actor_pic_path:
            insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
            protocol = "http" if insecure_mode else "https"
            n['actor_profile_picture_url'] = f"{protocol}://{n['actor_hostname']}/profile_pictures/{actor_pic_path}"
        elif actor_pic_path:
            n['actor_profile_picture_url'] = url_for('main.serve_profile_picture', filename=actor_pic_path, _external=True)
        else:
            n['actor_profile_picture_url'] = url_for('static', filename='images/default_avatar.png', _external=True)

        # Build notification link URL and text based on type
        n['url'] = url_for('main.user_profile', puid=n['actor_puid']) # Default link to the actor's profile
        
        if n['type'] == 'comment': n['text'] = f"<strong>{n['actor_display_name']}</strong> commented on your post."
        elif n['type'] == 'reply': n['text'] = f"<strong>{n['actor_display_name']}</strong> replied to your comment."
        elif n['type'] == 'mention': n['text'] = f"<strong>{n['actor_display_name']}</strong> mentioned you."
        elif n['type'] == 'tagged_in_post':
            # NEW: Notification for being tagged in a post
            n['text'] = f"<strong>{n['actor_display_name']}</strong> tagged you in a post."
        elif n['type'] == 'everyone_mention':
            # Show different message based on whether it's a group or event
            if n.get('group_name'):
                n['text'] = f"<strong>{n['actor_display_name']}</strong> mentioned everyone in <strong>{n['group_name']}</strong>."
            elif n.get('event_title'):
                n['text'] = f"<strong>{n['actor_display_name']}</strong> mentioned everyone in <strong>{n['event_title']}</strong>."
            else:
                n['text'] = f"<strong>{n['actor_display_name']}</strong> mentioned everyone."
        elif n['type'] == 'wall_post': n['text'] = f"<strong>{n['actor_display_name']}</strong> posted on your timeline."
        elif n['type'] == 'friend_request': n['text'] = f"<strong>{n['actor_display_name']}</strong> sent you a friend request."
        elif n['type'] == 'friend_accept': n['text'] = f"<strong>{n['actor_display_name']}</strong> accepted your friend request."
        elif n['type'] == 'birthday': n['text'] = f"It's <strong>{n['actor_display_name']}</strong>'s birthday today! Wish them well."
        elif n['type'] == 'group_request_accepted': n['text'] = f"Your request to join <strong>{n['group_name']}</strong> was accepted."
        elif n['type'] == 'group_request_rejected': n['text'] = f"Your request to join <strong>{n['group_name']}</strong> was rejected."
        elif n['type'] == 'group_post': n['text'] = f"<strong>{n['actor_display_name']}</strong> posted in <strong>{n['group_name']}</strong>."
        elif n['type'] == 'group_invite': n['text'] = f"<strong>{n['actor_display_name']}</strong> has invited you to join <strong>{n['group_name']}</strong>."
        elif n['type'] == 'repost': n['text'] = f"<strong>{n['actor_display_name']}</strong> shared your post."
        elif n['type'] == 'tagged_in_media': n['text'] = f"<strong>{n['actor_display_name']}</strong> tagged you in a some media."
        elif n['type'] == 'page_post': n['text'] = f"<strong>{n['actor_display_name']}</strong> has made a new post."
        elif n['type'] == 'event_invite':
            if n.get('event_is_public'):
                n['text'] = f"<strong>{n['actor_display_name']}</strong> created the public event: <strong>{n['event_title']}</strong>."
            elif n.get('event_group_name'):
                n['text'] = f"<strong>{n['actor_display_name']}</strong> invited you to the group event: <strong>{n['event_title']}</strong> in <strong>{n['event_group_name']}</strong>."
            else:
                n['text'] = f"<strong>{n['actor_display_name']}</strong> invited you to the event: <strong>{n['event_title']}</strong>."
        elif n['type'] == 'event_update':
             n['text'] = f"<strong>{n['actor_display_name']}</strong> updated the event: <strong>{n['event_title']}</strong>."
        elif n['type'] == 'event_cancelled':
            if n.get('event_group_name'):
                n['text'] = f"The group event <strong>{n['event_title']}</strong> in <strong>{n['event_group_name']}</strong> has been cancelled by <strong>{n['actor_display_name']}</strong>."
            elif n.get('event_is_public'):
                n['text'] = f"The public event <strong>{n['event_title']}</strong> has been cancelled by <strong>{n['actor_display_name']}</strong>."
            else:
                n['text'] = f"The event <strong>{n['event_title']}</strong> has been cancelled by <strong>{n['actor_display_name']}</strong>."
        elif n['type'] == 'event_post':
            n['text'] = f"<strong>{n['actor_display_name']}</strong> posted in the event: <strong>{n['event_title']}</strong>."
        elif n['type'] == 'tagged_in_media':
            n['text'] = f"<strong>{n['actor_display_name']}</strong> tagged you in a photo or video."
        elif n['type'] == 'media_comment':
            n['text'] = f"<strong>{n['actor_display_name']}</strong> commented on your media."
        elif n['type'] == 'media_mention':
            n['text'] = f"<strong>{n['actor_display_name']}</strong> mentioned you in a media comment."
        elif n['type'] == 'media_reply':
            n['text'] = f"<strong>{n['actor_display_name']}</strong> replied to your media comment."
        elif n['type'] == 'tagged_media_comment':
            n['text'] = f"<strong>{n['actor_display_name']}</strong> commented on a photo or video you're tagged in."
        elif n['type'] == 'parental_approval_needed': 
            n['text'] = f"<strong>{n['actor_display_name']}</strong> needs your approval for a remote action."
        elif n['type'] == 'parental_approval_approved': 
            n['text'] = f"<strong>{n['actor_display_name']}</strong> approved your request."
        elif n['type'] == 'parental_approval_denied': 
            n['text'] = f"<strong>{n['actor_display_name']}</strong> denied your request."
        else: n['text'] = 'New notification.'
        
        if n['type'] in ['comment', 'reply', 'mention', 'everyone_mention', 'wall_post', 'group_post', 'repost', 'page_post', 'event_update', 'event_post']:
            if n.get('comment_cuid'):
                n['url'] = url_for('main.view_comment', cuid=n['comment_cuid'])
            elif n.get('post_cuid'):
                n['url'] = url_for('main.view_post', cuid=n['post_cuid'])
        elif n['type'] == 'friend_request':
            n['url'] = url_for('friends.friends_list')
        elif n['type'] == 'friend_accept':
            n['url'] = url_for('main.user_profile', puid=n['actor_puid'])
        elif n['type'] in ['group_request_accepted', 'group_request_rejected', 'group_invite']:
            if n.get('group_id'):
                group = get_group_by_id(n['group_id'])
                if group:
                    n['url'] = federated_group_profile_url(dict(group))
        elif n['type'] in ['event_invite', 'event_cancelled', 'event_post']:
            if n.get('event_puid'):
                # FEDERATION: Use the new helper function for event URLs
                event_obj = {'puid': n['event_puid'], 'hostname': n.get('event_hostname')}
                n['url'] = federated_event_profile_url(event_obj)
        elif n['type'] in ['tagged_in_media', 'media_comment', 'media_mention', 'media_reply', 'tagged_media_comment']:
            if n.get('media_muid'):
                n['url'] = url_for('main.view_media', muid=n['media_muid'])
        elif n['type'] == 'parental_approval_needed':
            # Parent needs to approve - go to dashboard
            n['url'] = url_for('parental.parental_dashboard')
        elif n['type'] in ['parental_approval_approved', 'parental_approval_denied']:
            # Child gets result - go to home
            n['url'] = url_for('main.index')

        notifications.append(n)
    
    return jsonify(notifications)

@notifications_bp.route('/notifications/mark_read/<int:notification_id>', methods=['POST'])
def mark_as_read(notification_id):
    """API endpoint to mark a single notification as read."""
    from db_queries.users import get_user_id_by_username
    from db_queries.notifications import mark_notification_as_read

    user_id = get_user_id_by_username(session['username'])
    if not user_id:
        return jsonify({'error': 'User not found'}), 404

    if mark_notification_as_read(notification_id, user_id):
        return jsonify({'message': 'Notification marked as read'}), 200
    else:
        return jsonify({'error': 'Notification not found or you do not have permission to mark it as read'}), 404

@notifications_bp.route('/notifications/mark_all_read', methods=['POST'])
def mark_all_as_read():
    """API endpoint to mark all notifications for the current user as read."""
    from db_queries.users import get_user_id_by_username
    from db_queries.notifications import mark_all_notifications_as_read
    
    user_id = get_user_id_by_username(session['username'])
    if not user_id:
        return jsonify({'error': 'User not found'}), 404
        
    if mark_all_notifications_as_read(user_id):
        return jsonify({'message': 'All notifications marked as read'}), 200
    else:
        return jsonify({'error': 'Failed to mark all notifications as read'}), 500

@notifications_bp.route('/notifications/check_new', methods=['GET'])
def check_new_notifications():
    """
    API endpoint to check for new notifications since a given timestamp.
    Returns count and list of new notifications.
    Query params: since_timestamp (ISO format datetime string)
    """
    from db_queries.users import get_user_id_by_username
    from db_queries.notifications import get_notifications_for_user
    from db_queries.groups import get_group_by_id
    from db_queries.events import get_event_by_puid
    from app import inject_user_data_functions
    from datetime import datetime
    
    user_id = get_user_id_by_username(session['username'])
    if not user_id:
        return jsonify({'error': 'User not found'}), 404
    
    # Get timestamp from query params
    since_timestamp = request.args.get('since_timestamp')
    if not since_timestamp:
        return jsonify({'error': 'since_timestamp parameter required'}), 400
    
    # Fetch all notifications
    notifications_raw = get_notifications_for_user(user_id)
    
    # Get the URL generation functions from the context processor
    url_helpers = inject_user_data_functions()
    federated_group_profile_url = url_helpers['federated_group_profile_url']
    federated_event_profile_url = url_helpers['federated_event_profile_url']
    
    new_notifications = []
    unread_count = 0
    
    for row in notifications_raw:
        n = dict(row)
        
        # Count unread notifications
        if not n['is_read']:
            unread_count += 1
        
        # Only include notifications created after the given timestamp
        try:
            # SQLite format: "2025-09-03 22:06:45"
            notification_dt = datetime.strptime(n['timestamp'], '%Y-%m-%d %H:%M:%S')
            
            # JavaScript ISO format: "2025-12-02T21:27:30.471Z"
            since_dt = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
            # Convert to naive datetime (remove timezone) for comparison
            since_dt = since_dt.replace(tzinfo=None)
            
            # Only include notifications created after the given timestamp
            if notification_dt > since_dt:
                actor_pic_path = n.get('actor_profile_picture_path')
                
                # Build actor profile picture URL
                if n.get('actor_hostname') and actor_pic_path:
                    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
                    protocol = "http" if insecure_mode else "https"
                    n['actor_profile_picture_url'] = f"{protocol}://{n['actor_hostname']}/profile_pictures/{actor_pic_path}"
                elif actor_pic_path:
                    n['actor_profile_picture_url'] = url_for('main.serve_profile_picture', filename=actor_pic_path, _external=True)
                else:
                    n['actor_profile_picture_url'] = url_for('static', filename='images/default_avatar.png', _external=True)
                
                # Build notification text and URL
                n['url'] = url_for('main.user_profile', puid=n['actor_puid'])
                
                if n['type'] == 'comment':
                    n['text'] = f"{n['actor_display_name']} commented on your post."
                elif n['type'] == 'reply':
                    n['text'] = f"{n['actor_display_name']} replied to your comment."
                elif n['type'] == 'mention':
                    n['text'] = f"{n['actor_display_name']} mentioned you in a post or comment."
                elif n['type'] == 'everyone_mention':
                    # Show different message based on whether it's a group or event
                    if n.get('group_name'):
                        n['text'] = f"{n['actor_display_name']} mentioned everyone in {n.get('group_name')}."
                    elif n.get('event_title'):
                        n['text'] = f"{n['actor_display_name']} mentioned everyone in {n.get('event_title')}."
                    else:
                        n['text'] = f"{n['actor_display_name']} mentioned everyone."
                elif n['type'] == 'wall_post':
                    n['text'] = f"{n['actor_display_name']} posted on your timeline."
                elif n['type'] == 'friend_request':
                    n['text'] = f"{n['actor_display_name']} sent you a friend request."
                    n['url'] = url_for('friends.friends_list')
                elif n['type'] == 'friend_accept':
                    n['text'] = f"{n['actor_display_name']} accepted your friend request."
                elif n['type'] == 'birthday':
                    n['text'] = f"It's {n['actor_display_name']}'s birthday today!"
                elif n['type'] == 'group_request_accepted':
                    n['text'] = f"Your request to join {n.get('group_name', 'a group')} has been accepted."
                    if n.get('group_id'):
                        group = get_group_by_id(n['group_id'])
                        if group:
                            n['url'] = federated_group_profile_url(dict(group))
                elif n['type'] == 'group_request_rejected':
                    n['text'] = f"Your request to join {n.get('group_name', 'a group')} has been rejected."
                elif n['type'] == 'group_post':
                    n['text'] = f"{n['actor_display_name']} posted in {n.get('group_name', 'a group')}."
                elif n['type'] == 'group_invite':
                    n['text'] = f"{n['actor_display_name']} invited you to join {n.get('group_name', 'a group')}."
                    if n.get('group_id'):
                        group = get_group_by_id(n['group_id'])
                        if group:
                            n['url'] = federated_group_profile_url(dict(group))
                elif n['type'] == 'repost':
                    n['text'] = f"{n['actor_display_name']} reposted your post."
                elif n['type'] == 'page_post':
                    n['text'] = f"{n['actor_display_name']} posted an update."
                elif n['type'] == 'follow':
                    n['text'] = f"{n['actor_display_name']} followed you."
                elif n['type'] == 'event_invite':
                    n['text'] = f"{n['actor_display_name']} invited you to {n.get('event_title', 'an event')}."
                    if n.get('event_puid'):
                        event_obj = {'puid': n['event_puid'], 'hostname': n.get('event_hostname')}
                        n['url'] = federated_event_profile_url(event_obj)
                elif n['type'] == 'event_update':
                    n['text'] = f"The event {n.get('event_title', 'an event')} has been updated by {n['actor_display_name']}."
                    if n.get('event_puid'):
                        event_obj = {'puid': n['event_puid'], 'hostname': n.get('event_hostname')}
                        n['url'] = federated_event_profile_url(event_obj)
                elif n['type'] == 'event_cancelled':
                    if n.get('event_is_public'):
                        n['text'] = f"The public event {n['event_title']} has been cancelled by {n['actor_display_name']}."
                    else:
                        n['text'] = f"The event {n['event_title']} has been cancelled by {n['actor_display_name']}."
                elif n['type'] == 'event_post':
                    n['text'] = f"{n['actor_display_name']} posted in {n.get('event_title', 'an event')}."
                    if n.get('event_puid'):
                        event_obj = {'puid': n['event_puid'], 'hostname': n.get('event_hostname')}
                        n['url'] = federated_event_profile_url(event_obj)
                elif n['type'] == 'parental_approval_needed':
                    n['text'] = f"{n['actor_display_name']} needs your approval for a remote action."
                    n['url'] = url_for('parental.parental_dashboard')
                elif n['type'] == 'parental_approval_approved':
                    n['text'] = f"{n['actor_display_name']} approved your request."
                    n['url'] = url_for('main.index')
                elif n['type'] == 'parental_approval_denied':
                    n['text'] = f"{n['actor_display_name']} denied your request."
                    n['url'] = url_for('main.index')
                else:
                    n['text'] = 'New notification.'
                
                # Build URLs for comments/posts
                if n['type'] in ['comment', 'reply', 'mention', 'everyone_mention', 'wall_post', 'group_post', 'repost', 'page_post', 'event_update', 'event_post']:
                    if n.get('comment_cuid'):
                        n['url'] = url_for('main.view_comment', cuid=n['comment_cuid'])
                    elif n.get('post_cuid'):
                        n['url'] = url_for('main.view_post', cuid=n['post_cuid'])
                
                new_notifications.append(n)
        except Exception as e:
            print(f"Error processing notification timestamp: {e}")
            continue
    
    return jsonify({
        'new_notifications': new_notifications,
        'unread_count': unread_count
    })