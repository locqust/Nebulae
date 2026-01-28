# db_queries/notifications.py
# Contains functions for creating and managing notifications.

import sqlite3
from datetime import datetime
from db import get_db
from .friends import get_friends_list
# NEW: Import functions to get user settings and send emails
from .settings import get_user_settings
from .users import get_user_by_id
from utils.email_utils import send_email
from utils.email_templates import get_email_template, get_notification_content
from db_queries.groups import get_group_by_id
# Try to import push notification utilities
try:
    from utils.push_utils import send_push_notification
    PUSH_AVAILABLE = True
except ImportError:
    PUSH_AVAILABLE = False
    print("Push notification dependencies not available")

def create_notification(user_id, actor_id, type, post_id=None, comment_id=None, group_id=None, event_id=None, media_id=None, media_comment_id=None):
    """
    Creates a new notification and sends an email if the user has opted in.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO notifications (user_id, actor_id, type, post_id, comment_id, group_id, event_id, media_id, media_comment_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, actor_id, type, post_id, comment_id, group_id, event_id, media_id, media_comment_id))
        db.commit()
    except sqlite3.Error as e:
        print(f"ERROR: Could not create notification: {e}")
        return # Exit if the notification can't be created

    # --- NEW: Email Sending Logic ---
    # After successfully creating the in-app notification, check if an email should be sent.
    user_settings = get_user_settings(user_id)
    
    # First, check if email notifications are enabled globally for the user and if they have an address set.
    if user_settings.get('email_notifications_enabled') == 'True' and user_settings.get('user_email_address'):
        recipient_email = user_settings.get('user_email_address')
        recipient_user = get_user_by_id(user_id)
        actor = get_user_by_id(actor_id)
        actor_name = actor.get('display_name') if actor else 'Someone'

        # Map notification types to settings and email subjects
        notification_mapping = {
            'friend_request': ('email_on_friend_request', f"New Friend Request from {actor_name}"),
            'friend_accept': ('email_on_friend_accept', f"{actor_name} Accepted Your Friend Request"),
            'wall_post': ('email_on_wall_post', f"{actor_name} Posted on Your Wall"),
            'mention': ('email_on_mention', f"{actor_name} Mentioned You"),
            'everyone_mention': ('email_on_mention', f"{actor_name} Mentioned Everyone"),
            'event_invite': ('email_on_event_invite', f"Event Invitation from {actor_name}"),
            'event_update': ('email_on_event_update', "Event Update"),
            'event_cancelled': ('email_on_event_update', "Event Cancelled"),
            'tagged_in_post': ('email_on_post_tag', f"{actor_name} Tagged You in a Post"),
            'tagged_in_media': ('email_on_media_tag', f"{actor_name} Tagged You in Media"),
            'media_mention': ('email_on_media_mention', f"{actor_name} Mentioned You in Media"),
            'group_post': ('email_on_group_post', f"New Post in Group"),
            'group_request_accepted': ('email_on_group_join', "Group Join Request Accepted"),
            'parental_approval_needed': ('email_on_parental_approval', f"Approval Needed from {actor_name}"),
            'parental_approval_approved': ('email_on_parental_approval', "Your Request Was Approved"),
            'parental_approval_denied': ('email_on_parental_approval', "Your Request Was Denied")
        }

        # Check if the current notification type is one we should send emails for
        if type in notification_mapping:
            setting_key, email_subject = notification_mapping[type]
            
            # Check if the user has enabled this specific notification type
            if user_settings.get(setting_key) == 'True':
                # Gather additional context for the email
                kwargs = {'actor_puid': actor.get('puid') if actor else None}
                
                # Get post CUID if post_id provided
                if post_id:
                    cursor.execute("SELECT cuid FROM posts WHERE id = ?", (post_id,))
                    post_row = cursor.fetchone()
                    if post_row:
                        kwargs['post_cuid'] = post_row['cuid']
                
                # Get group info if group_id provided
                if group_id:
                    group = get_group_by_id(group_id)
                    if group:
                        kwargs['group_puid'] = group.get('puid')
                        kwargs['group_name'] = group.get('name')
                
                # Get event info if event_id provided
                if event_id:
                    cursor.execute("SELECT puid, title, event_datetime, event_end_datetime, location, details FROM events WHERE id = ?", (event_id,))
                    event_row = cursor.fetchone()
                    if event_row:
                        kwargs['event_puid'] = event_row['puid']
                        kwargs['event_title'] = event_row['title']
                        
                        # Format the datetime nicely for the email
                        if event_row['event_datetime']:
                            from datetime import datetime
                            try:
                                event_dt = datetime.strptime(event_row['event_datetime'], '%Y-%m-%d %H:%M:%S')
                                kwargs['event_datetime'] = event_dt.strftime('%A, %B %d, %Y at %I:%M %p')
                            except:
                                kwargs['event_datetime'] = event_row['event_datetime']
                        
                        kwargs['event_location'] = event_row['location']
                        kwargs['event_details'] = event_row['details']
                
                # Get media info if media_id provided
                if media_id:
                    cursor.execute("SELECT muid, media_file_path FROM post_media WHERE id = ?", (media_id,))
                    media_row = cursor.fetchone()
                    if media_row:
                        kwargs['muid'] = media_row['muid']
                        # Extract filename from media_file_path
                        import os
                        if media_row['media_file_path']:
                            kwargs['media_filename'] = os.path.basename(media_row['media_file_path'])
                        else:
                            kwargs['media_filename'] = 'Media file'
                
                # Generate notification-specific content
                main_content, button_text, button_url, preview_html = get_notification_content(
                    type, 
                    actor_name,
                    **kwargs
                )
                
                # Generate preview text (first line without HTML)
                import re
                preview_text = re.sub('<[^<]+?>', '', main_content).strip()
                
                # Generate full HTML email
                html_body = get_email_template(
                    username=recipient_user.get('display_name') or recipient_user.get('username'),
                    subject=email_subject,
                    preview_text=preview_text,
                    main_content=main_content,
                    action_button_text=button_text,
                    action_button_url=button_url,
                    preview_content=preview_html
                )
                
                # Send the email
                send_email(
                    recipient=recipient_email,
                    subject=f"Nebulae - {email_subject}",
                    body_html=html_body
                )

    # ============================================================================
    # NEW: Push Notification Logic
    # Send push notifications when the app is closed/backgrounded
    # ============================================================================
    if PUSH_AVAILABLE:
        try:
            # Get actor info for notification
            actor = get_user_by_id(actor_id)
            actor_name = actor.get('display_name') if actor else 'Someone'
            
            # Create notification text and URL
            notification_text = _get_notification_text(type, actor_name)
            notification_url = _get_notification_url(
                type, post_id, comment_id, group_id, event_id, 
                media_id, media_comment_id, actor.get('puid') if actor else None
            )
            
            # Get icon URL for the notification
            icon_url = None
            if actor and actor.get('profile_picture_path'):
                if actor.get('hostname'):
                    # Federated user - need full URL
                    from flask import current_app
                    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
                    protocol = 'http' if insecure_mode else 'https'
                    icon_url = f"{protocol}://{actor['hostname']}/profile_pictures/{actor['profile_picture_path']}"
                else:
                    # Local user - relative path is fine
                    icon_url = f"/profile_pictures/{actor['profile_picture_path']}"
            
            # Send push notification (will only be delivered if app is closed/backgrounded)
            send_push_notification(
                user_id=user_id,
                title='NODE',
                body=notification_text,
                url=notification_url,
                icon_url=icon_url
            )
            
        except Exception as e:
            # Don't fail notification creation if push fails
            print(f"Error sending push notification: {e}")
            import traceback
            traceback.print_exc()

# ============================================================================
# Helper functions for push notifications
# ============================================================================

def _get_notification_text(notification_type, actor_name):
    """
    Generate notification text based on type.
    Used for push notifications.
    """
    texts = {
        'comment': f'{actor_name} commented on your post',
        'reply': f'{actor_name} replied to your comment',
        'mention': f'{actor_name} mentioned you',
        'everyone_mention': f'{actor_name} mentioned everyone',
        'wall_post': f'{actor_name} posted on your profile',
        'friend_request': f'{actor_name} sent you a friend request',
        'friend_accept': f'{actor_name} accepted your friend request',
        'birthday': f"It's {actor_name}'s birthday!",
        'group_request_accepted': f'Your request to join a group was accepted',
        'group_request_rejected': f'Your request to join a group was rejected',
        'group_invite': f'{actor_name} invited you to a group',
        'group_post': f'{actor_name} posted in a group',
        'event_invite': f'{actor_name} invited you to an event',
        'event_update': f'An event has been updated',
        'event_cancelled': f'An event has been cancelled',
        'event_post': f'{actor_name} posted in an event',
        'repost': f'{actor_name} reposted your post',
        'page_post': f'{actor_name} posted on a page',
        'tagged_in_post': f'{actor_name} tagged you in a post',
        'tagged_in_media': f'{actor_name} tagged you in a photo',
        'media_comment': f'{actor_name} commented on a photo',
        'media_mention': f'{actor_name} mentioned you in a photo comment',
        'parental_approval_needed': f'{actor_name} needs parental approval',
        'parental_approval_approved': f'{actor_name} approved your request',
        'parental_approval_denied': f'{actor_name} denied your request'
    }
    return texts.get(notification_type, 'You have a new notification')


def _get_notification_url(notification_type, post_id, comment_id, group_id, event_id, media_id, media_comment_id, actor_puid):
    """
    Generate notification URL based on type.
    Used for push notifications.
    """
    from flask import url_for
    from db_queries.comments import get_comment_by_internal_id
    from db_queries.media import get_media_comment_by_internal_id
    from db import get_db
    
    # Comment-related notifications - go to the comment
    if comment_id:
        comment = get_comment_by_internal_id(comment_id)
        if comment:
            return url_for('main.view_comment', cuid=comment['cuid'], _external=False)
    
    # Media comment notifications
    if media_comment_id:
        media_comment = get_media_comment_by_internal_id(media_comment_id)
        if media_comment:
            return url_for('main.view_media_comment', cuid=media_comment['cuid'], _external=False)
    
    # Post-related notifications - go to the post (QUERY DIRECTLY - no helper function)
    if post_id:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT cuid FROM posts WHERE id = ?", (post_id,))
        post_row = cursor.fetchone()
        if post_row:
            return url_for('main.view_post', cuid=post_row['cuid'], _external=False)
    
    # Group-related notifications - go to the group
    if group_id:
        from db_queries.groups import get_group_by_id
        group = get_group_by_id(group_id)
        if group:
            return url_for('groups.group_profile', puid=group['puid'], _external=False)
    
    # Event-related notifications - go to the event (QUERY DIRECTLY - no helper function)
    if event_id:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT puid FROM events WHERE id = ?", (event_id,))
        event_row = cursor.fetchone()
        if event_row:
            return url_for('events.event_profile', puid=event_row['puid'], _external=False)
    
    # NEW: Parental approval notifications - go to parental dashboard
    if notification_type in ['parental_approval_needed', 'parental_approval_approved', 'parental_approval_denied']:
        # For parents needing to approve - go to dashboard
        if notification_type == 'parental_approval_needed':
            return url_for('parental.parental_dashboard', _external=False)
        # For children getting results - go to their profile (or could go to home)
        else:
            return url_for('main.index', _external=False)

    # Friend request notifications - go to friends list
    if notification_type in ['friend_request', 'friend_accept']:
        return url_for('friends.friends_list', _external=False)
    
    # Birthday notifications - go to the person's profile
    if notification_type == 'birthday' and actor_puid:
        return url_for('main.user_profile', puid=actor_puid, _external=False)
    
    # Default to actor's profile if available
    if actor_puid:
        return url_for('main.user_profile', puid=actor_puid, _external=False)
    
    # Fallback to home
    return url_for('main.index', _external=False)

def get_notifications_for_user(user_id):
    """Retrieves all notifications for a user, including necessary CUIDs and profile picture paths."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT 
            n.id, n.type, n.is_read, n.timestamp, n.post_id, n.comment_id, n.group_id,
            a.username as actor_username, a.display_name as actor_display_name,
            a.profile_picture_path as actor_profile_picture_path,
            a.hostname as actor_hostname, a.puid as actor_puid,
            p_owner.puid as post_profile_puid,
            p.cuid as post_cuid,
            c.cuid as comment_cuid,
            g.name as group_name, g.puid as group_puid,
            e.title as event_title, e.puid as event_puid,
            e.is_public as event_is_public,
            e.hostname as event_hostname,
            event_group.name as event_group_name,
            pm.muid as media_muid,
            mc.cuid as media_comment_cuid
        FROM notifications n
        JOIN users a ON n.actor_id = a.id
        LEFT JOIN posts p ON n.post_id = p.id
        LEFT JOIN comments c ON n.comment_id = c.id
        LEFT JOIN users p_owner ON p.profile_user_id = p_owner.id
        LEFT JOIN groups g ON n.group_id = g.id
        LEFT JOIN events e ON n.event_id = e.id
        LEFT JOIN groups event_group ON e.source_type = 'group' AND e.source_puid = event_group.puid
        LEFT JOIN post_media pm ON n.media_id = pm.id
        LEFT JOIN media_comments mc ON n.media_comment_id = mc.id
        WHERE n.user_id = ?
        ORDER BY n.timestamp DESC
    """, (user_id,))
    return cursor.fetchall()

def get_unread_notification_count(user_id):
    """Gets the count of unread notifications for a user."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (user_id,))
    return cursor.fetchone()[0]

def mark_notification_as_read(notification_id, user_id):
    """Marks a single notification as read, ensuring ownership."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", (notification_id, user_id))
    db.commit()
    return cursor.rowcount > 0

def mark_all_notifications_as_read(user_id):
    """Marks all of a user's notifications as read."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))
    db.commit()
    return cursor.rowcount > 0

def trigger_birthday_notifications_for_user(user_id):
    """
    Creates birthday notifications for a specific user's friends.
    """
    db = get_db()
    birthday_user_id = user_id
    friends = get_friends_list(birthday_user_id)
    
    for friend in friends:
        friend_id = friend['id']
        cursor = db.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM notifications
            WHERE user_id = ? AND actor_id = ? AND type = 'birthday' AND date(timestamp) = date('now', 'utc')
        """, (friend_id, birthday_user_id))
        
        if cursor.fetchone()[0] == 0:
            create_notification(friend_id, birthday_user_id, 'birthday')
    
    db.commit()

def check_and_create_birthday_notifications():
    """
    Checks for user birthdays and creates notifications for their friends.
    Runs only once per day.
    """
    db = get_db()
    cursor = db.cursor()
    
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    
    cursor.execute("SELECT value FROM app_state WHERE key = 'last_birthday_check'")
    last_check = cursor.fetchone()
    if last_check and last_check['value'] == today_str:
        return
        
    today_month_day = datetime.utcnow().strftime('%m-%d')
    cursor.execute("""
        SELECT user_id FROM user_profile_info
        WHERE field_name = 'dob' AND substr(field_value, 6) = ? AND privacy_friends = 1
    """, (today_month_day,))
    
    birthday_users = cursor.fetchall()
    
    for user_row in birthday_users:
        trigger_birthday_notifications_for_user(user_row['user_id'])
            
    cursor.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('last_birthday_check', ?)", (today_str,))
    db.commit()
    print(f"Birthday notification check completed for {today_str}")