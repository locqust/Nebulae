# db_queries/posts.py
# Contains functions for managing posts and the main feed.

import uuid
from datetime import datetime
from flask import g, current_app
from db import get_db
from utils.text_processing import extract_mentions, extract_everyone_mention
from .users import get_user_by_id, get_user_by_puid
from .comments import get_comments_for_post, filter_comments
from .notifications import create_notification
from .friends import get_snoozed_friends, get_who_blocked_user, is_friends_with, get_friend_relationship, get_all_friends_puid
# CIRCULAR IMPORT FIX: Import federation functions inside functions where needed
from .groups import get_user_group_ids, get_group_by_puid, get_group_members
# NEW: Import follower queries
from .followers import get_following_pages, is_following
# BUG FIX: Import event queries to get event attendees
from .events import get_event_attendees
import sqlite3

# MODIFICATION: Added 'comments_disabled=False' to the function definition
# NEW: Added 'tagged_user_puids=None' and 'location=None' parameters
def add_post(user_id, profile_user_id, content, privacy_setting='local', media_files=None, nu_id=None, cuid=None, author_puid=None, profile_puid=None, group_puid=None, is_remote=False, author_hostname=None, is_repost=False, original_post_cuid=None, event_id=None, comments_disabled=False, tagged_user_puids=None, location=None, poll_data=None, timestamp=None):
    """Adds a new post or repost, links media, and creates notifications."""
    # CIRCULAR IMPORT FIX: Import federation functions here
    from .federation import send_remote_mention_notification, send_remote_notification
    
    db = get_db()
    cursor = db.cursor()

    if nu_id is None:
        nu_id = g.nu_id

    if cuid is None:
        cuid = str(uuid.uuid4())

    # A repost has no content of its own.
    if is_repost:
        content = None

    group_id = None
    if group_puid:
        group = get_group_by_puid(group_puid)
        if group:
            group_id = group['id']
        else:
            raise ValueError("Group not found for the given PUID.")
        # Group posts don't have a profile destination
        profile_puid = None
        profile_user_id = None

    origin_hostname = author_hostname if author_hostname else current_app.config.get('NODE_HOSTNAME')

    if not is_remote:
        author = get_user_by_id(user_id)
        if not author:
            raise ValueError("Invalid user_id for a local post.")
        author_puid = author['puid']

        if profile_user_id:
            profile_user = get_user_by_id(profile_user_id)
            if not profile_user:
                raise ValueError("Invalid profile_user_id for a local post.")
            profile_puid = profile_user['puid']
    else:
        if not author_puid:
            raise ValueError("author_puid is required for remote posts.")
        pass

    # NEW: Convert tagged_user_puids list to JSON string if provided
    import json
    tagged_puids_json = json.dumps(tagged_user_puids) if tagged_user_puids else None

    # Use provided timestamp or let database default to CURRENT_TIMESTAMP
    if timestamp:
        cursor.execute("""
            INSERT INTO posts (cuid, user_id, profile_user_id, author_puid, profile_puid, group_id, content, privacy_setting, nu_id, is_remote, is_repost, original_post_cuid, event_id, comments_disabled, tagged_user_puids, location, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (cuid, user_id, profile_user_id, author_puid, profile_puid, group_id, content, privacy_setting, nu_id, is_remote, is_repost, original_post_cuid, event_id, comments_disabled, tagged_puids_json, location, timestamp))
    else:
        cursor.execute("""
            INSERT INTO posts (cuid, user_id, profile_user_id, author_puid, profile_puid, group_id, content, privacy_setting, nu_id, is_remote, is_repost, original_post_cuid, event_id, comments_disabled, tagged_user_puids, location)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (cuid, user_id, profile_user_id, author_puid, profile_puid, group_id, content, privacy_setting, nu_id, is_remote, is_repost, original_post_cuid, event_id, comments_disabled, tagged_puids_json, location))
    post_id = cursor.lastrowid

    if media_files and not is_repost:
        for media_file_data in media_files:
            media_path = media_file_data.get('media_file_path')
            alt_text = media_file_data.get('alt_text')
            # NEW: Get MUID and tagged_user_puids from the media_file_data if present (for federation)
            muid = media_file_data.get('muid')
            tagged_user_puids_json = media_file_data.get('tagged_user_puids')
            media_origin_hostname = media_file_data.get('origin_hostname', origin_hostname)
            
            if media_path:
                # Generate new MUID only if not provided (i.e., for local posts)
                if not muid:
                    muid = str(uuid.uuid4())
                
                cursor.execute("""
                    INSERT INTO post_media (muid, post_id, media_file_path, alt_text, origin_hostname, tagged_user_puids) 
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (muid, post_id, media_path, alt_text, media_origin_hostname, tagged_user_puids_json))
    
    # NEW: Create poll if poll_data is provided
    if poll_data and not is_repost:
        #print(f"DEBUG: poll_data received: {poll_data}")  # ADD THIS
        from .polls import create_poll
        poll_options = poll_data.get('options', [])
        allow_multiple = poll_data.get('allow_multiple_answers', False)
        allow_add_options = poll_data.get('allow_add_options', False)
        
        #print(f"DEBUG: Creating poll with {len(poll_options)} options")  
        if poll_options and len(poll_options) >= 2:
            poll_id = create_poll(post_id, poll_options, allow_multiple, allow_add_options)
            print(f"DEBUG: Poll created with ID: {poll_id}")  
        else:
            print(f"DEBUG: Poll NOT created - insufficient options")

    # Extract and associate link previews
    if not is_repost and content:  # Only create previews for original posts with content
        try:
            from db_queries.link_previews import associate_link_previews_with_post
            associate_link_previews_with_post(post_id, content)
        except Exception as e:
            print(f"Error creating link previews for post: {e}")
            # Don't fail the post creation if link preview fails

    # Notification logic only runs for posts created directly on this node.
    if not is_remote and user_id:
        actor_id = user_id

        # If it's a repost, notify the original author
        if is_repost and original_post_cuid:
            original_post = get_post_by_cuid(original_post_cuid)
            if original_post:
                # The original post might itself be a repost, so we get the ultimate original author
                ultimate_original_post = original_post.get('original_post', original_post)
                original_author_puid = ultimate_original_post['author']['puid']
                original_author = get_user_by_puid(original_author_puid)

                # Only notify if the original author is a local user and not the one reposting
                if original_author and original_author['hostname'] is None and original_author['id'] != user_id:
                    create_notification(
                        user_id=original_author['id'],
                        actor_id=user_id,
                        type='repost',
                        post_id=post_id # Link notification to the new repost itself
                    )

        # Original post notification logic for mentions, etc.
        elif not is_repost:
            # If the author is a public page, notify their followers
            if author and author['user_type'] == 'public_page':
                from .followers import get_followers
                followers = get_followers(user_id)

                for follower in followers:
                    if follower['id'] != actor_id and follower.get('hostname') is None:
                        # If it's an event-related post...
                        if event_id:
                            # ...and it's the initial creation post (no content), send an invite.
                            if content is None:
                                create_notification(
                                    user_id=follower['id'],
                                    actor_id=actor_id,
                                    type='event_invite',
                                    post_id=post_id,
                                    event_id=event_id
                                )
                            # If it has content, it's a cancellation or update, which has its own notification logic. Do nothing here.

                        # If it's not an event post, it's a regular page post.
                        else:
                            create_notification(
                                user_id=follower['id'],
                                actor_id=actor_id,
                                type='page_post',
                                post_id=post_id
                            )

            if content:
                mentioned_users = extract_mentions(content)
                already_notified = {actor_id}

                for user in mentioned_users:
                    if user['id'] not in already_notified:
                        if user['hostname'] is None:
                            create_notification(user['id'], actor_id, 'mention', post_id, group_id=group_id)
                        else:
                            send_remote_mention_notification(user, actor_id, post_id, group_id=group_id)
                        already_notified.add(user['id'])

                # Handle @everyone/@all for groups
                if group_id is not None:
                    has_everyone_mention = extract_everyone_mention(content, 'group')
                    
                    if has_everyone_mention:
                        # Check if user has permission to use @everyone
                        from .groups import is_user_group_moderator_or_admin, get_group_by_id
                        if is_user_group_moderator_or_admin(actor_id, group_id):
                            # Notify ALL group members with everyone_mention type
                            members = get_group_members(group_id)
                            # Get group object to pass PUID to remote nodes
                            group = get_group_by_id(group_id)
                            group_puid = group['puid'] if group else None
                            
                            for member in members:
                                if member['id'] not in already_notified:
                                    if member['hostname'] is None:
                                        # Local user
                                        create_notification(member['id'], actor_id, 'everyone_mention', post_id, group_id=group_id)
                                    else:
                                        # Remote user - pass group_puid instead of group_id
                                        send_remote_notification(member, actor_id, 'everyone_mention', cuid, group_puid=group_puid)
                                    already_notified.add(member['id'])
                        # If user doesn't have permission, @everyone is treated as regular text (no notification)
                    else:
                        # Regular group post notifications (only if no @everyone)
                        members = get_group_members(group_id)
                        for member in members:
                            if member['id'] != actor_id and member['id'] not in already_notified and member['hostname'] is None:
                                create_notification(member['id'], actor_id, 'group_post', post_id, group_id=group_id)
                
                # Handle @everyone/@all for events
                elif event_id is not None:
                    has_everyone_mention = extract_everyone_mention(content, 'event')
                    
                    if has_everyone_mention:
                        # Check if user is the event organizer
                        from .events import get_event_by_id
                        event = get_event_by_id(event_id)
                        if event and event['created_by_user_puid'] == author_puid:
                            # Notify ALL event attendees with everyone_mention type
                            attendees = get_event_attendees(event_id)
                            for attendee in attendees:
                                if attendee['puid'] != author_puid:
                                    attendee_user = get_user_by_puid(attendee['puid'])
                                    if attendee_user and attendee_user['id'] not in already_notified:
                                        if attendee_user.get('hostname') is None:
                                            # Local user - notify directly
                                            create_notification(attendee_user['id'], actor_id, 'everyone_mention', post_id, event_id=event_id)
                                        # NOTE: Remote users will be notified via post distribution
                                        # to avoid duplicate notifications
                                        already_notified.add(attendee_user['id'])
                        # If user isn't the organizer, @everyone is treated as regular text
                    else:
                        # Regular event post notifications (non-@everyone posts)
                        from .events import get_event_by_id
                        event = get_event_by_id(event_id)
                        if event:
                            # Notify all attendees except the post author
                            attendees = get_event_attendees(event_id)
                            for attendee in attendees:
                                if attendee['puid'] != author_puid:
                                    attendee_user = get_user_by_puid(attendee['puid'])
                                    if attendee_user and attendee_user['id'] not in already_notified:
                                        if attendee_user.get('hostname') is None:
                                            # Local user - notify with 'event_post' type
                                            create_notification(attendee_user['id'], actor_id, 'event_post', post_id, event_id=event_id)
                                        # Remote users will be notified via federation
                                        already_notified.add(attendee_user['id'])
                
                # Wall post notifications (non-group, non-event posts)
                elif group_id is None and event_id is None and user_id != profile_user_id:
                    if profile_user_id and profile_user_id not in already_notified:
                        create_notification(profile_user_id, actor_id, 'wall_post', post_id)
                        already_notified.add(profile_user_id)

            # NEW: Handle tagged users with parental approval check
            if tagged_user_puids and not is_repost:
                approved_tags = []  # Track which tags were immediately approved
                pending_tags = []   # Track which tags need approval
                
                for tagged_puid in tagged_user_puids:
                    tagged_user = get_user_by_puid(tagged_puid)
                    if not tagged_user or tagged_user['id'] in already_notified:
                        continue
                    
                    if tagged_user['hostname'] is None:
                        # Local user - check parental approval
                        from .parental_controls import requires_parental_approval, create_approval_request, get_all_parent_ids
                        
                        if requires_parental_approval(tagged_user['id']):
                            # This tag needs approval - add to pending list
                            pending_tags.append(tagged_puid)
                            
                            # Create approval request
                            tagger_user = get_user_by_id(actor_id)
                            
                            # Get media info if this post has media
                            media_muids = []
                            if post_id:
                                db_temp = get_db()
                                cursor_temp = db_temp.cursor()
                                cursor_temp.execute("SELECT muid FROM post_media WHERE post_id = ?", (post_id,))
                                media_muids = [row['muid'] for row in cursor_temp.fetchall()]
                            
                            request_data = json.dumps({
                                'post_cuid': cuid,
                                'tagger_puid': tagger_user.get('puid') if tagger_user else None,
                                'tagger_display_name': tagger_user.get('display_name', 'Unknown') if tagger_user else 'Unknown',
                                'post_content': content,  # Full content so parent can review
                                'post_content_preview': content[:100] if content else '[No content]',
                                'has_media': len(media_muids) > 0,
                                'media_muids': media_muids,  # So parent can view the photos
                                'group_id': group_id,
                                'event_id': event_id
                            })
                            
                            approval_id = create_approval_request(
                                tagged_user['id'],
                                'post_tag',
                                cuid,
                                None,
                                request_data
                            )
                            
                            if approval_id:
                                # Notify all parents
                                parent_ids = get_all_parent_ids(tagged_user['id'])
                                for parent_id in parent_ids:
                                    create_notification(parent_id, tagged_user['id'], 'parental_approval_needed')
                        else:
                            # No parental approval needed - proceed normally
                            approved_tags.append(tagged_puid)
                            create_notification(
                                tagged_user['id'], 
                                actor_id, 
                                'tagged_in_post', 
                                post_id,
                                group_id=group_id,
                                event_id=event_id
                            )
                    else:
                        # Remote user - send federated notification
                        approved_tags.append(tagged_puid)
                        send_remote_notification(
                            tagged_user, 
                            actor_id, 
                            'tagged_in_post', 
                            cuid,
                            group_puid=group_puid if group_id else None,
                            event_puid=None
                        )
                    
                    already_notified.add(tagged_user['id'])
                
                # IMPORTANT: Update the post's tagged_user_puids to only include approved tags
                # Pending tags will be added later if/when approved
                if pending_tags:
                    # Remove pending tags from the post temporarily
                    cursor.execute("""
                        UPDATE posts 
                        SET tagged_user_puids = ?
                        WHERE id = ?
                    """, (json.dumps(approved_tags) if approved_tags else None, post_id))
                    db.commit()

    db.commit()
    return cuid

def get_post_by_cuid(cuid, viewer_user_puid=None):
    """
    Retrieves a single post by its CUID. If it's a repost, it also fetches the original post.
    Now includes the viewer's response to any associated event.
    """
    # CIRCULAR IMPORT FIX: Import get_event_by_puid locally within the function.
    from .events import get_event_by_puid
    db = get_db()
    cursor = db.cursor()

    # NEW: Get viewer_user_id from viewer_user_puid for comment filtering
    viewer_user_id = None
    if viewer_user_puid:
        viewer_user = get_user_by_puid(viewer_user_puid)
        if viewer_user:
            viewer_user_id = viewer_user['id']

    cursor.execute("""
        SELECT
            p.*,
            author.username AS author_username,
            author.puid AS author_puid,
            author.display_name AS author_display_name,
            author.user_type as author_user_type,
            author.profile_picture_path AS author_profile_picture_path,
            author.hostname AS author_hostname,
            profile_owner.username AS profile_owner_username,
            profile_owner.puid AS profile_owner_puid,
            profile_owner.display_name AS profile_owner_display_name,
            profile_owner.profile_picture_path AS profile_owner_profile_picture_path,
            profile_owner.hostname AS profile_owner_hostname,
            profile_owner.requires_parental_approval AS profile_owner_requires_parental_approval,
            g.id as group_id,
            g.name as group_name,
            g.puid as group_puid,
            g.description as group_description,
            g.profile_picture_path as group_profile_picture_path,
            g.hostname as group_hostname
        FROM posts p
        JOIN users author ON p.author_puid = author.puid
        LEFT JOIN users profile_owner ON p.profile_puid = profile_owner.puid
        LEFT JOIN groups g ON p.group_id = g.id
        WHERE p.cuid = ?
    """, (cuid,))

    post = cursor.fetchone()

    if post:
        post_dict = dict(post)

        post_dict['author'] = {
            'username': post_dict['author_username'],
            'puid': post_dict['author_puid'],
            'display_name': post_dict['author_display_name'],
            'user_type': post_dict['author_user_type'],
            'profile_picture_path': post_dict['author_profile_picture_path'],
            'hostname': post_dict['author_hostname']
        }

        if post_dict['profile_owner_puid']:
            post_dict['profile_owner'] = {
                'username': post_dict['profile_owner_username'],
                'puid': post_dict['profile_owner_puid'],
                'display_name': post_dict['profile_owner_display_name'],
                'profile_picture_path': post_dict['profile_owner_profile_picture_path'],
                'hostname': post_dict['profile_owner_hostname'],
                'requires_parental_approval': bool(post_dict.get('profile_owner_requires_parental_approval', 0))
            }
        else:
            post_dict['profile_owner'] = None

        if post_dict['group_puid']:
            post_dict['group'] = {
                'id': post_dict['group_id'],
                'name': post_dict['group_name'],
                'puid': post_dict['group_puid'],
                'description': post_dict['group_description'],
                'profile_picture_path': post_dict['group_profile_picture_path'],
                'hostname': post_dict['group_hostname']
            }
        else:
            post_dict['group'] = None

        # NEW: If this post is an event post, fetch the event data and embed it.
        if post_dict.get('event_id'):
            cursor.execute("SELECT puid FROM events WHERE id = ?", (post_dict['event_id'],))
            event_row = cursor.fetchone()
            if event_row:
                event_puid = event_row['puid']
                # BUG FIX: Pass the viewer_user_puid to get their response status for the event.
                post_dict['event'] = get_event_by_puid(event_puid, viewer_user_puid=viewer_user_puid)
        else:
            post_dict['event'] = None


        # If this post is a repost, fetch the original post data and embed it.
        if post_dict.get('is_repost') and post_dict.get('original_post_cuid'):
            # BUG FIX: Pass the viewer_user_puid down when fetching the original post as well.
            post_dict['original_post'] = get_post_by_cuid(post_dict['original_post_cuid'], viewer_user_puid=viewer_user_puid)
            post_dict['media_files'] = []
            post_dict['comments'] = get_comments_for_post(post['id'], viewer_user_id)
        else:
            # An original post gets its media and comments as usual.
            media_cursor = db.cursor()
            media_cursor.execute("SELECT id, muid, media_file_path, alt_text, origin_hostname FROM post_media WHERE post_id = ?", (post['id'],))
            post_dict['media_files'] = [dict(row) for row in media_cursor.fetchall()]
            post_dict['comments'] = get_comments_for_post(post['id'], viewer_user_id)
            # NEW: Get poll data if this post has a poll
            from .polls import get_poll_by_post_id
            post_dict['poll'] = get_poll_by_post_id(post['id'], viewer_user_id)
            #print(f"DEBUG get_post_by_cuid: Post {cuid} poll data: {post_dict['poll']}")

        # NEW: Get link previews for this post
            try:
                from db_queries.link_previews import get_link_previews_for_post
                post_dict['link_previews'] = get_link_previews_for_post(post['id'])
            except Exception as e:
                print(f"Error fetching link previews for post {cuid}: {e}")
                post_dict['link_previews'] = []

        return post_dict
    return None

def get_media_by_muid(muid):
    """Retrieves a media item by its MUID and finds the CUID of its parent post."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT pm.muid, p.cuid as post_cuid
        FROM post_media pm
        JOIN posts p ON pm.post_id = p.id
        WHERE pm.muid = ?
    """, (muid,))
    result = cursor.fetchone()
    return dict(result) if result else None

def disable_comments_for_post(cuid):
    """Sets the comments_disabled flag for a post to True."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE posts SET comments_disabled = TRUE WHERE cuid = ?", (cuid,))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error disabling comments for post {cuid}: {e}")
        db.rollback()
        return False

def update_post(cuid, content, privacy_setting, media_files=None, tagged_user_puids=None, location=None):
    """Updates an existing post by its CUID, its media, and handles new mentions."""
    # CIRCULAR IMPORT FIX: Import federation functions here
    from .federation import send_remote_mention_notification

    import json    
    db = get_db()
    cursor = db.cursor()

    original_post = get_post_by_cuid(cuid)
    if not original_post or original_post.get('is_repost'): # Cannot edit a repost
        return False

    post_id = original_post['id']
    original_content = original_post['content']
    group_id = original_post.get('group_id')

    # NEW: Handle tagged users with parental approval check
    if tagged_user_puids is None:
        # Keep existing tags
        tagged_puids_json = original_post.get('tagged_user_puids')
        newly_tagged_puids = []  # No new tags
    else:
        # Get existing tags to compare
        existing_tags = json.loads(original_post.get('tagged_user_puids', '[]')) if original_post.get('tagged_user_puids') else []
        
        # Find newly added tags (tags that weren't there before)
        newly_tagged_puids = [puid for puid in tagged_user_puids if puid not in existing_tags]
        
        # Process new tags for parental approval
        approved_new_tags = []
        pending_new_tags = []
        
        if newly_tagged_puids:
            from .parental_controls import requires_parental_approval, create_approval_request, get_all_parent_ids
            
            for tagged_puid in newly_tagged_puids:
                tagged_user = get_user_by_puid(tagged_puid)
                if not tagged_user:
                    continue
                
                if tagged_user['hostname'] is None:
                    # Local user - check parental approval
                    if requires_parental_approval(tagged_user['id']):
                        # This tag needs approval
                        pending_new_tags.append(tagged_puid)
                        
                        # Create approval request
                        tagger_user = get_user_by_id(original_post['user_id'])
                        
                        # Get media info if post has media
                        media_muids = []
                        cursor_temp = db.cursor()
                        cursor_temp.execute("SELECT muid FROM post_media WHERE post_id = ?", (post_id,))
                        media_muids = [row['muid'] for row in cursor_temp.fetchall()]
                        
                        request_data = json.dumps({
                            'post_cuid': cuid,
                            'tagger_puid': tagger_user.get('puid') if tagger_user else None,
                            'tagger_display_name': tagger_user.get('display_name', 'Unknown') if tagger_user else 'Unknown',
                            'post_content': content,
                            'post_content_preview': content[:100] if content else '[No content]',
                            'has_media': len(media_muids) > 0,
                            'media_muids': media_muids,
                            'group_id': group_id,
                            'event_id': original_post.get('event_id')
                        })
                        
                        approval_id = create_approval_request(
                            tagged_user['id'],
                            'post_tag',
                            cuid,
                            None,
                            request_data
                        )
                        
                        if approval_id:
                            # Notify all parents
                            parent_ids = get_all_parent_ids(tagged_user['id'])
                            for parent_id in parent_ids:
                                create_notification(parent_id, tagged_user['id'], 'parental_approval_needed')
                    else:
                        # No approval needed
                        approved_new_tags.append(tagged_puid)
                        
                        # Notify the newly tagged user
                        create_notification(
                            tagged_user['id'],
                            original_post['user_id'],
                            'tagged_in_post',
                            post_id,
                            group_id=group_id,
                            event_id=original_post.get('event_id')
                        )
                else:
                    # Remote user
                    approved_new_tags.append(tagged_puid)
                    from .federation import send_remote_notification
                    send_remote_notification(
                        tagged_user,
                        original_post['user_id'],
                        'tagged_in_post',
                        cuid,
                        group_puid=None,  # TODO: get group PUID if needed
                        event_puid=None
                    )
        
        # Combine: existing tags + approved new tags (pending tags are excluded)
        # Keep existing tags that weren't explicitly removed
        final_tags = list(set(existing_tags + approved_new_tags))
        
        # If user provided an explicit list, respect removals
        # (if they removed someone from the list, don't add them back)
        if set(tagged_user_puids) != set(existing_tags):
            # User made changes - use only their selections plus approved new ones
            final_tags = [puid for puid in final_tags if puid in tagged_user_puids or puid in existing_tags]
        
        tagged_puids_json = json.dumps(final_tags) if final_tags else None
    
    if location is None:
        # Keep existing location
        location = original_post.get('location')
    # else: use the provided location value (could be empty string to clear location)

    cursor.execute("""
        UPDATE posts 
        SET content = ?, 
            privacy_setting = ?,
            tagged_user_puids = ?,
            location = ?
        WHERE cuid = ?
    """, (content, privacy_setting, tagged_puids_json, location, cuid))

    origin_hostname = current_app.config.get('NODE_HOSTNAME')

    current_media_ids_cursor = db.cursor()
    current_media_ids_cursor.execute("SELECT id, media_file_path FROM post_media WHERE post_id = ?", (post_id,))
    current_media_map = {row['media_file_path']: row['id'] for row in current_media_ids_cursor.fetchall()}
    incoming_media_paths = {mf['media_file_path'] for mf in media_files} if media_files else set()
    media_to_delete_ids = [media_id for path, media_id in current_media_map.items() if path not in incoming_media_paths]
    if media_to_delete_ids:
        placeholders = ','.join('?' * len(media_to_delete_ids))
        cursor.execute(f"DELETE FROM post_media WHERE id IN ({placeholders})", media_to_delete_ids)
    if media_files:
        for media_file_data in media_files:
            media_path = media_file_data.get('media_file_path')
            alt_text = media_file_data.get('alt_text')
            if media_path in current_media_map:
                media_id = current_media_map[media_path]
                cursor.execute("UPDATE post_media SET alt_text = ? WHERE id = ?", (alt_text, media_id))
            else:
                muid = str(uuid.uuid4())
                cursor.execute("INSERT INTO post_media (muid, post_id, media_file_path, alt_text, origin_hostname) VALUES (?, ?, ?, ?, ?)",
                               (muid, post_id, media_path, alt_text, origin_hostname))

    actor_id = original_post['user_id']

    original_mentioned_users = extract_mentions(original_content)
    new_mentioned_users = extract_mentions(content)

    original_mentioned_ids = {u['id'] for u in original_mentioned_users}

    for user in new_mentioned_users:
        if user['id'] not in original_mentioned_ids and user['id'] != actor_id:
            if user['hostname'] is None: # Local user
                create_notification(user['id'], actor_id, 'mention', post_id, group_id=group_id)
            else: # Remote user
                send_remote_mention_notification(user, actor_id, post_id, group_id=group_id)

    # NEW: Regenerate link previews when content changes
    if content != original_content:
        try:
            from db_queries.link_previews import remove_link_previews_for_post, associate_link_previews_with_post
            remove_link_previews_for_post(post_id)
            associate_link_previews_with_post(post_id, content)
        except Exception as e:
            print(f"Error updating link previews for post: {e}")

    db.commit()
    return cursor.rowcount > 0

def delete_post(cuid):
    """
    Deletes a post by CUID. If it's an original post, it also deletes all of its reposts.
    If it's a repost, only the repost is deleted.
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id, is_repost FROM posts WHERE cuid = ?", (cuid,))
    post_row = cursor.fetchone()

    if not post_row:
        return False

    post_id = post_row['id']
    is_repost = post_row['is_repost']

    # Delete the specific post, its media, and comments
    cursor.execute("DELETE FROM post_media WHERE post_id = ?", (post_id,))
    cursor.execute("DELETE FROM comments WHERE post_id = ?", (post_id,))
    cursor.execute("DELETE FROM posts WHERE id = ?", (post_id,))

    # If the deleted post was an original post, also delete its reposts
    if not is_repost:
        cursor.execute("DELETE FROM posts WHERE original_post_cuid = ?", (cuid,))

    db.commit()
    # The returned rowcount might not be perfectly accurate if both deletes run,
    # but it serves to indicate success.
    return True

def get_posts_for_feed(current_user_id=None, current_user_is_admin=False, filter_type='everything', page=1, limit=20):
    """
    Retrieves posts for the feed, including local, friends', public, and group posts.
    
    Args:
        current_user_id: ID of the current user
        current_user_is_admin: Whether user is admin
        filter_type: Type of filter to apply
        page: Page number (1-indexed)
        limit: Number of posts per page
    
    Returns:
        List of post dictionaries
    """
    db = get_db()
    cursor = db.cursor()

    snoozed_friend_ids = set()
    viewer_blocked_by_map = {}
    member_of_group_ids = []
    followed_page_puids = []

    # BUG FIX: Get the current user object once at the beginning.
    current_user = None
    if current_user_id:
        current_user = get_user_by_id(current_user_id)
        if not current_user:
            return [] # Return empty if user not found, to prevent further errors.

        snoozed_friend_ids = get_snoozed_friends(current_user_id)
        viewer_blocked_by_map = get_who_blocked_user(current_user_id)
        member_of_group_ids = get_user_group_ids(current_user_id)
        followed_pages = get_following_pages(current_user_id)
        followed_page_puids = [page['puid'] for page in followed_pages]

    conditions = ["p.privacy_setting = 'public'"]
    params = []

    if current_user_id and current_user:
        if current_user_is_admin:
            conditions.append("p.privacy_setting IN ('local', 'friends', 'followers', 'event')")
        else:
            conditions.append("p.privacy_setting = 'local'")

            friend_puids = get_all_friends_puid(current_user_id)
            friend_puids.add(current_user['puid'])

            if friend_puids:
                placeholders = ','.join('?' * len(friend_puids))
                conditions.append(f"(p.privacy_setting = 'friends' AND p.profile_puid IN ({placeholders}))")
                params.extend(list(friend_puids))

            if followed_page_puids:
                page_placeholders = ','.join('?' * len(followed_page_puids))
                # This is the crucial line to add - it includes posts authored by followed pages with the 'followers' privacy setting.
                conditions.append(f"(p.privacy_setting = 'followers' AND p.author_puid IN ({page_placeholders}))")
                params.extend(followed_page_puids)

            # BUG FIX: If the current user is a public page, they should also see their own 'followers' posts in their feed.
            if current_user['user_type'] == 'public_page':
                conditions.append("(p.privacy_setting = 'followers' AND p.author_puid = ?)")
                params.append(current_user['puid'])

            # BUG FIX: Include event posts if the current user is an attendee (but not if they declined).
            cursor.execute("SELECT event_id FROM event_attendees WHERE user_puid = ? AND response != 'declined'", (current_user['puid'],))
            attended_event_ids = [row['event_id'] for row in cursor.fetchall()]
            if attended_event_ids:
                event_placeholders = ','.join('?' * len(attended_event_ids))
                conditions.append(f"(p.privacy_setting = 'event' AND p.event_id IN ({event_placeholders}))")
                params.extend(attended_event_ids)


        if member_of_group_ids:
            group_placeholders = ','.join('?' * len(member_of_group_ids))
            conditions.append(f"(p.privacy_setting = 'group' AND p.group_id IN ({group_placeholders}))")
            params.extend(member_of_group_ids)

    where_clause = ' OR '.join(f"({c})" for c in conditions)
    # Calculate offset for pagination
    offset = (page - 1) * limit

    query = f"SELECT p.cuid FROM posts p WHERE {where_clause} ORDER BY p.timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    #print(f"DEBUG get_posts_for_feed: Final query: {query}")
    #print(f"DEBUG get_posts_for_feed: Params: {params}")

    cursor.execute(query, params)
    post_cuids = [row['cuid'] for row in cursor.fetchall()]
    #print(f"DEBUG get_posts_for_feed: Found {len(post_cuids)} posts total")

    final_posts = []
    for cuid in post_cuids:
        # BUG FIX: Pass the current_user's PUID to get their event response status.
        viewer_puid = current_user['puid'] if current_user else None
        post = get_post_by_cuid(cuid, viewer_user_puid=viewer_puid)
        if not post:
            continue

        # NEW: Skip hidden posts
        if current_user_id and is_post_hidden_for_user(current_user_id, post['id']):
            continue

        author_puid = post['author'].get('puid')
        author_user = get_user_by_puid(author_puid)
        author_id = author_user['id'] if author_user else None

        if not current_user_is_admin and author_id:
            if author_id in snoozed_friend_ids:
                continue
            if author_id in viewer_blocked_by_map:
                blocked_at_ts = viewer_blocked_by_map[author_id]
                post_timestamp_str = post['timestamp'].split('.')[0]
                post_timestamp = datetime.strptime(post_timestamp_str, '%Y-%m-%d %H:%M:%S')
                if post_timestamp > blocked_at_ts:
                    continue

        if post.get('is_repost') and post.get('original_post'):
            post['original_post']['comments'] = filter_comments(post['original_post'].get('comments', []), snoozed_friend_ids, viewer_blocked_by_map)
        else:
            post['comments'] = filter_comments(post.get('comments', []), snoozed_friend_ids, viewer_blocked_by_map)

        final_posts.append(post)

    return final_posts

def get_posts_for_group(group_puid, viewer_user_id, is_member, viewer_is_admin, page=1, limit=20):
    """Retrieves posts for a specific group's timeline using PUID."""
    db = get_db()
    cursor = db.cursor()

    group = get_group_by_puid(group_puid)
    if not group:
        return []

    visible_privacy_levels = {'public'}
    if is_member or viewer_is_admin:
        visible_privacy_levels.add('group')
        # FIX: Also show event announcement posts on the group wall for members
        visible_privacy_levels.add('event')

    placeholders = ','.join('?' * len(visible_privacy_levels))
    offset = (page - 1) * limit
    
    # Build query with LIMIT and OFFSET
    query = f"SELECT cuid FROM posts WHERE group_id = ? AND privacy_setting IN ({placeholders}) ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    
    # Build params list: [group_id, privacy_levels..., limit, offset]
    params = [group['id']] + list(visible_privacy_levels) + [limit, offset]
    
    cursor.execute(query, params)
    post_cuids = [row['cuid'] for row in cursor.fetchall()]

    final_posts = []
    # BUG FIX: Pass viewer's PUID to get their event responses.
    viewer_puid = None
    if viewer_user_id:
        viewer_user = get_user_by_id(viewer_user_id)
        if viewer_user:
            viewer_puid = viewer_user['puid']

    for cuid in post_cuids:
        post = get_post_by_cuid(cuid, viewer_user_puid=viewer_puid)
        if post:
            # NEW: Skip hidden posts
            if viewer_user_id and is_post_hidden_for_user(viewer_user_id, post['id']):
                continue
            final_posts.append(post)

    return final_posts

def get_posts_for_profile_timeline(profile_user_puid, viewer_user_id, viewer_is_admin, page=1, limit=20):
    """Retrieves posts for a specific user's profile timeline using PUID."""
    db = get_db()
    cursor = db.cursor()

    profile_user_row = get_user_by_puid(profile_user_puid)
    if not profile_user_row:
        return []

    profile_user = dict(profile_user_row)
    profile_user_id = profile_user.get('id')

    viewer_is_blocked = False
    blocked_at_ts = None

    viewer_user = None
    if viewer_user_id:
        viewer_user = get_user_by_id(viewer_user_id)
        if not viewer_user:
            return [] # Should not happen, but a good safeguard.

    if profile_user_id and viewer_user_id:
        block_info = get_friend_relationship(profile_user_id, viewer_user_id)
        viewer_is_blocked = block_info and block_info['is_blocked']
        if viewer_is_blocked and block_info.get('blocked_at'):
            blocked_at_ts_str = block_info['blocked_at'].split('.')[0]
            blocked_at_ts = datetime.strptime(blocked_at_ts_str, '%Y-%m-%d %H:%M:%S')

    visible_privacy_levels = {'public'}

    # NEW: Check for 'followers' privacy if the profile is a public page and the viewer follows it.
    if viewer_user and profile_user['user_type'] == 'public_page' and is_following(viewer_user_id, profile_user_id):
        visible_privacy_levels.add('followers')

    if viewer_user and (viewer_user['puid'] == profile_user_puid or viewer_is_admin):
        visible_privacy_levels.update(['friends', 'local', 'followers']) # Owner/admin sees all their own posts
    elif viewer_user_id and profile_user_id and is_friends_with(viewer_user_id, profile_user_id):
        visible_privacy_levels.add('friends')
        if viewer_user and viewer_user['hostname'] is None:
            visible_privacy_levels.add('local')

    placeholders = ','.join('?' * len(visible_privacy_levels))
    offset = (page - 1) * limit
    
    # Build query with LIMIT and OFFSET
    # NEW: Include posts where user is tagged
    # Use json_each to check if profile_puid is in the tagged_user_puids JSON array
    query = f"""
        SELECT cuid FROM posts 
        WHERE (
            profile_puid = ? 
            OR (
                tagged_user_puids IS NOT NULL 
                AND tagged_user_puids != '[]'
                AND EXISTS (
                    SELECT 1 FROM json_each(tagged_user_puids) 
                    WHERE value = ?
                )
            )
        )
        AND privacy_setting IN ({placeholders}) 
        ORDER BY timestamp DESC 
        LIMIT ? OFFSET ?
    """
    
    # Build params list: [profile_puid, privacy_levels..., limit, offset]
    params = [profile_user_puid, profile_user_puid] + list(visible_privacy_levels) + [limit, offset]
    
    cursor.execute(query, params)
    raw_posts = cursor.fetchall()

    final_posts = []
    viewer_puid = viewer_user['puid'] if viewer_user else None
    for post_row in raw_posts:
        post = get_post_by_cuid(post_row['cuid'], viewer_user_puid=viewer_puid)
        if not post:
            continue

        # NEW: Skip hidden posts
        if viewer_user_id and is_post_hidden_for_user(viewer_user_id, post['id']):
            continue

        post_timestamp_str = post['timestamp'].split('.')[0]
        post_timestamp = datetime.strptime(post_timestamp_str, '%Y-%m-%d %H:%M:%S')

        if viewer_is_blocked and blocked_at_ts and post_timestamp > blocked_at_ts:
            continue

        final_posts.append(post)

    return final_posts

def get_media_for_user_gallery(profile_user_puid, viewer_user_id, viewer_is_admin):
    """Retrieves media from a user's posts AND media where user is tagged, respecting privacy settings."""
    from .media import get_tagged_media_for_user
    
    db = get_db()
    cursor = db.cursor()

    profile_user_row = get_user_by_puid(profile_user_puid)
    if not profile_user_row:
        return []

    profile_user = dict(profile_user_row)
    profile_user_id = profile_user.get('id')

    visible_privacy_levels = {'public'}
    if viewer_user_id and profile_user_id:
        viewer_user = get_user_by_id(viewer_user_id)

        # NEW: Check for 'followers' privacy if the profile is a public page and the viewer follows it.
        if viewer_user and profile_user['user_type'] == 'public_page' and is_following(viewer_user_id, profile_user_id):
            visible_privacy_levels.add('followers')

        if viewer_user and (viewer_user['puid'] == profile_user_puid or viewer_is_admin):
            visible_privacy_levels.update(['friends', 'local', 'followers'])
        elif is_friends_with(viewer_user_id, profile_user_id):
            visible_privacy_levels.add('friends')
            if viewer_user and viewer_user['hostname'] is None:
                visible_privacy_levels.add('local')

    placeholders = ','.join('?' for _ in visible_privacy_levels)
    
    # Get media from user's own posts
    query = f"""
        SELECT pm.id, pm.muid, pm.media_file_path, pm.alt_text, 
            u.hostname as origin_hostname, p.author_puid, p.timestamp, 
            u.username, u.puid, p.privacy_setting, p.cuid as post_cuid,
            strftime('%Y', p.timestamp) as year,
            strftime('%m', p.timestamp) as month
        FROM post_media pm
        JOIN posts p ON pm.post_id = p.id
        JOIN users u ON p.author_puid = u.puid
        WHERE p.author_puid = ? AND p.privacy_setting IN ({placeholders})
        ORDER BY p.timestamp DESC
    """

    params = [profile_user_puid] + list(visible_privacy_levels)
    cursor.execute(query, tuple(params))

    gallery_media = []
    for row in cursor.fetchall():
        # Correctly determine the media_type
        media_path_lower = row['media_file_path'].lower()
        media_type = 'other'
        if media_path_lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')):
            media_type = 'image'
        elif media_path_lower.endswith(('.mp4', '.mov', '.webm', '.avi', '.mkv')):
            media_type = 'video'
            
        gallery_media.append({
            'id': row['id'],
            'muid': row['muid'],
            'media_file_path': row['media_file_path'],
            'origin_hostname': row['origin_hostname'],
            'media_type': media_type,
            'alt_text': row['alt_text'],
            'username': row['username'],
            'puid': row['puid'],
            'post_cuid': row['post_cuid'],
            'timestamp': row['timestamp'],
            'year': row['year'],
            'month': row['month'],
            'is_tagged_photo': 0  # User's own media
        })
    
    # Get media where user is tagged
    tagged_media = get_tagged_media_for_user(profile_user_puid, viewer_user_id, viewer_is_admin)
    
    # Add is_tagged_photo flag to tagged media
    for media in tagged_media:
        media['is_tagged_photo'] = 1
    
    # Combine both lists
    gallery_media.extend(tagged_media)
    
    # Remove duplicates based on muid, keeping the first occurrence
    seen_muids = set()
    deduplicated_media = []
    for media in gallery_media:
        if media['muid'] not in seen_muids:
            seen_muids.add(media['muid'])
            deduplicated_media.append(media)
    
    # Sort by timestamp descending
    deduplicated_media.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return deduplicated_media

def get_media_for_group_gallery(group_puid, viewer_user_id, is_member, viewer_is_admin):
    """Retrieves all media from a group's posts, respecting privacy for the viewer."""
    db = get_db()
    cursor = db.cursor()

    group = get_group_by_puid(group_puid)
    if not group:
        return []

    visible_privacy_levels = {'public'}
    if is_member or viewer_is_admin:
        visible_privacy_levels.add('group')

    placeholders = ','.join('?' * len(visible_privacy_levels))
    query = f"""
        SELECT pm.id, pm.muid, pm.media_file_path, pm.alt_text, 
            u.hostname as origin_hostname, p.author_puid, p.timestamp, 
            u.username, u.puid, p.privacy_setting, p.cuid as post_cuid,
            strftime('%Y', p.timestamp) as year,
            strftime('%m', p.timestamp) as month
        FROM post_media pm
        JOIN posts p ON pm.post_id = p.id
        JOIN users u ON p.author_puid = u.puid
        WHERE p.group_id = ? AND p.privacy_setting IN ({placeholders})
        ORDER BY p.timestamp DESC
    """

    params = [group['id']] + list(visible_privacy_levels)
    cursor.execute(query, tuple(params))

    gallery_media = []
    for row in cursor.fetchall():
        # --- FIX: START ---
        # Correctly determine the media_type (Copied from get_media_for_user_gallery)
        media_path_lower = row['media_file_path'].lower()
        media_type = 'other' # Default
        if media_path_lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')):
            media_type = 'image'
        elif media_path_lower.endswith(('.mp4', '.mov', '.webm', '.avi', '.mkv')):
            media_type = 'video'
        # --- FIX: END ---
        
        gallery_media.append({
            'id': row['id'],
            'muid': row['muid'],
            'media_file_path': row['media_file_path'],
            'origin_hostname': row['origin_hostname'],
            'media_type': media_type, # Use the correctly determined media_type
            'alt_text': row['alt_text'],
            'username': row['username'],
            'puid': row['puid'],
            'post_cuid': row['post_cuid'],
            'timestamp': row['timestamp'],
            'year': row['year'],
            'month': row['month']
        })

    return gallery_media


def get_muid_by_media_path(media_file_path):
    """
    Retrieves the MUID for a given media file path.
    This is used to find the MUID for profile pictures selected from the gallery.
    """
    if not media_file_path:
        return None

    db = get_db()
    try:
        muid_row = db.execute(
            "SELECT muid FROM post_media WHERE media_file_path = ?",
            (media_file_path,)
        ).fetchone()
        return muid_row['muid'] if muid_row else None
    except sqlite3.OperationalError as e:
        print(f"Error querying post_media table in get_muid_by_media_path: {e}")
        return None


# --- NEW FUNCTION ---

def get_event_announcement_post(event_id):
    """
    Retrieves the CUID of the initial announcement post for a given event ID.
    Announcement posts are identified by having a non-null event_id, null content, and is_repost=False.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT cuid FROM posts
            WHERE event_id = ? AND content IS NULL AND is_repost = FALSE
            ORDER BY timestamp ASC
            LIMIT 1
        """, (event_id,))
        row = cursor.fetchone()
        return row['cuid'] if row else None
    except sqlite3.Error as e:
        print(f"Error fetching announcement post for event {event_id}: {e}")
        return None

def remove_user_tag_from_post(post_cuid, user_puid):
    """
    Removes a user's tag from a post.
    
    Args:
        post_cuid: The CUID of the post
        user_puid: The PUID of the user to untag
    
    Returns:
        bool: True if successful, False otherwise
    """
    import json
    db = get_db()
    cursor = db.cursor()
    
    # Get the post
    cursor.execute("SELECT tagged_user_puids FROM posts WHERE cuid = ?", (post_cuid,))
    result = cursor.fetchone()
    
    if not result or not result['tagged_user_puids']:
        return False
    
    # Parse the JSON array
    try:
        tagged_puids = json.loads(result['tagged_user_puids'])
    except (json.JSONDecodeError, TypeError):
        return False
    
    # Remove the user's PUID
    if user_puid in tagged_puids:
        tagged_puids.remove(user_puid)
        
        # Update the post
        new_tagged_json = json.dumps(tagged_puids) if tagged_puids else None
        cursor.execute("UPDATE posts SET tagged_user_puids = ? WHERE cuid = ?", 
                      (new_tagged_json, post_cuid))
        db.commit()
        return True
    
    return False

def remove_mention_from_post(post_cuid, user_display_name):
    """
    Removes @mentions of a specific user from a post's content.
    Converts @DisplayName to just DisplayName.
    
    Args:
        post_cuid: The CUID of the post
        user_display_name: The display name to remove mentions of
    
    Returns:
        bool: True if successful, False otherwise
    """
    import re
    db = get_db()
    cursor = db.cursor()
    
    # Get the post content
    cursor.execute("SELECT content FROM posts WHERE cuid = ?", (post_cuid,))
    result = cursor.fetchone()
    
    if not result or not result['content']:
        return False
    
    content = result['content']
    
    # Remove the @ symbol before the display name (case-insensitive)
    # Pattern: @DisplayName -> DisplayName
    pattern = r'@(' + re.escape(user_display_name) + r')\b'
    new_content = re.sub(pattern, r'\1', content, flags=re.IGNORECASE)
    
    # Only update if content actually changed
    if new_content != content:
        cursor.execute("UPDATE posts SET content = ? WHERE cuid = ?", (new_content, post_cuid))
        db.commit()
        return True
    
    return False

def hide_post_for_user(user_id, post_id):
    """
    Hides a post for a specific user.
    
    Args:
        user_id: The ID of the user hiding the post
        post_id: The ID of the post to hide
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO hidden_content (user_id, content_type, content_id)
            VALUES (?, 'post', ?)
        """, (user_id, post_id))
        db.commit()
        return True
    except Exception as e:
        print(f"Error hiding post: {e}")
        return False

def is_post_hidden_for_user(user_id, post_id):
    """
    Check if a post is hidden for a specific user.
    
    Args:
        user_id: The ID of the user
        post_id: The ID of the post
    
    Returns:
        bool: True if hidden, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT COUNT(*) as count FROM hidden_content
        WHERE user_id = ? AND content_type = 'post' AND content_id = ?
    """, (user_id, post_id))
    result = cursor.fetchone()
    return result['count'] > 0 if result else False

def get_hidden_post_ids_for_user(user_id):
    """
    Get all post IDs hidden by a specific user.
    
    Args:
        user_id: The ID of the user
    
    Returns:
        set: Set of post IDs that are hidden
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT content_id FROM hidden_content
        WHERE user_id = ? AND content_type = 'post'
    """, (user_id,))
    return {row['content_id'] for row in cursor.fetchall()}

def check_new_posts_in_feed(current_user_id, current_user_is_admin, since_timestamp):
    """
    Check if there are new posts in the feed since a given timestamp.
    """
    from datetime import datetime
    
    try:
        since_dt = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
    except (ValueError, AttributeError) as e:
        return False
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current user info
    current_user = get_user_by_id(current_user_id) if current_user_id else None
    if not current_user:
        return False
    
    # Build the same conditions as get_posts_for_feed
    conditions = []
    params = []
    
    # Always include public posts
    conditions.append("p.privacy_setting = 'public'")
    
    if current_user_id and current_user:
        if current_user_is_admin:
            conditions.append("p.privacy_setting IN ('local', 'friends', 'followers', 'event')")
        else:
            conditions.append("p.privacy_setting = 'local'")
            
            friend_puids = get_all_friends_puid(current_user_id)
            friend_puids.add(current_user['puid'])
            
            if friend_puids:
                placeholders = ','.join('?' * len(friend_puids))
                conditions.append(f"(p.privacy_setting = 'friends' AND p.profile_puid IN ({placeholders}))")
                params.extend(list(friend_puids))
            
            followed_pages = get_following_pages(current_user_id)
            followed_page_puids = [page['puid'] for page in followed_pages]
            
            if followed_page_puids:
                page_placeholders = ','.join('?' * len(followed_page_puids))
                conditions.append(f"(p.privacy_setting = 'followers' AND p.author_puid IN ({page_placeholders}))")
                params.extend(followed_page_puids)
            
            if current_user['user_type'] == 'public_page':
                conditions.append("(p.privacy_setting = 'followers' AND p.author_puid = ?)")
                params.append(current_user['puid'])
            
            cursor.execute("SELECT event_id FROM event_attendees WHERE user_puid = ? AND response != 'declined'", (current_user['puid'],))
            attended_event_ids = [row['event_id'] for row in cursor.fetchall()]
            if attended_event_ids:
                event_placeholders = ','.join('?' * len(attended_event_ids))
                conditions.append(f"(p.privacy_setting = 'event' AND p.event_id IN ({event_placeholders}))")
                params.extend(attended_event_ids)
        
        member_of_group_ids = get_user_group_ids(current_user_id)
        if member_of_group_ids:
            group_placeholders = ','.join('?' * len(member_of_group_ids))
            conditions.append(f"(p.privacy_setting = 'group' AND p.group_id IN ({group_placeholders}))")
            params.extend(member_of_group_ids)
    
    where_clause = ' OR '.join(f"({c})" for c in conditions)
    
    # FIXED: Use strftime with microseconds to keep full precision
    query = f"""
        SELECT 1 
        FROM posts p 
        WHERE p.timestamp > ?
        AND ({where_clause})
        LIMIT 1
    """
    
    # FIXED: Format with microseconds - SQLite stores timestamps with microsecond precision
    timestamp_str = since_dt.strftime('%Y-%m-%d %H:%M:%S.%f')
    all_params = [timestamp_str] + params
    
    cursor.execute(query, all_params)
    result = cursor.fetchone()
    
    return result is not None