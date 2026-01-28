# db_queries/events.py
import uuid
import sqlite3
import traceback # Added for error logging in new function
from datetime import datetime
from flask import g, current_app
from db import get_db
# Add imports for federation and user lookups
from .users import get_user_by_puid, get_user_by_id
from .friends import get_friends_list
from .groups import get_group_members, get_group_by_puid
from .followers import get_followers
# from .posts import add_post # This is the circular import
from .notifications import create_notification
# NEW: Import federation distribution functions
from utils.federation_utils import (distribute_event_update, distribute_event_cancel,
                                    distribute_event_response, distribute_event_invite,
                                    # NEW: Import function to send post to single node
                                    distribute_post_to_single_node)

# Helper for date formatting
def suffix(d):
    return 'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')

# Locale-independent day and month names
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def create_event(created_by_user, source_type, source_puid, title, event_datetime, location, details, is_public, event_end_datetime=None, is_remote=False, puid=None, hostname=None):
    """Creates a new event, determines invitees, and creates the initial post."""
    # Import locally to prevent circular dependency
    from .posts import add_post
    db = get_db()
    cursor = db.cursor()
    if puid is None:
        puid = str(uuid.uuid4())

    post_cuid = None

    try:
        cursor.execute("""
            INSERT INTO events (puid, created_by_user_puid, source_type, source_puid, title, event_datetime, event_end_datetime, location, details, is_public, hostname, is_remote)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (puid, created_by_user['puid'], source_type, source_puid, title, event_datetime, event_end_datetime, location, details, is_public, hostname, is_remote))
        event_id = cursor.lastrowid

        # Determine invitees based on source type
        invitee_puids = set()

        # Event posts are 'event' privacy, unless they are public page events set to 'public'
        privacy_setting = 'event'
        if source_type == 'public_page' and is_public:
            privacy_setting = 'public'


        group_puid_for_post = None
        if source_type == 'group':
            group_puid_for_post = source_puid
            # For remote events, we might need to create a stub for the group first.
            # For now, we assume the group exists locally as a stub or a real group.
            group = get_group_by_puid(source_puid)
            if group:
                members = get_group_members(group['id'])
                for member in members:
                    if member['puid'] != created_by_user['puid']: # Don't invite the creator
                        invitee_puids.add(member['puid'])

        elif source_type == 'public_page' and not is_public:
            # Only invite followers if the event is NOT public
            page = get_user_by_puid(source_puid)
            if page:
                followers = get_followers(page['id'])
                for follower in followers:
                    invitee_puids.add(follower['puid'])
        
        # If the event is public (from a page), no one is explicitly "invited" via this mechanism.
        # They discover it via the feed or discovery tab.

        # After creating the event, fetch the full event object to use for federation
        event = get_event_by_id(event_id)

        # Add invitees to the event_attendees table and create notifications/federate invites
        if event:
            for invitee_puid in invitee_puids:
                invitee = get_user_by_puid(invitee_puid)
                if invitee:
                    cursor.execute("INSERT OR IGNORE INTO event_attendees (event_id, user_puid) VALUES (?, ?)", (event_id, invitee_puid))

                    if invitee.get('hostname') and not is_remote:
                        # If the group member is remote, distribute the event invitation
                        distribute_event_invite(event, invitee_puid)
                    elif not is_remote:
                        # Only create notifications for local users
                        create_notification(invitee['id'], created_by_user['id'], 'event_invite', event_id=event_id)

        # Add the creator as 'attending'
        cursor.execute("INSERT OR IGNORE INTO event_attendees (event_id, user_puid, response) VALUES (?, ?, 'attending')", (event_id, created_by_user['puid']))

        # Create the initial post for the event only if it's a local event
        if not is_remote:
            post_cuid = add_post(
                user_id=created_by_user['id'],
                profile_user_id=None,
                content=None, # No content for event announcement posts
                privacy_setting=privacy_setting, # Use the determined privacy
                event_id=event_id,
                group_puid=group_puid_for_post
            )

        db.commit()
        return puid, post_cuid
    except sqlite3.Error as e:
        db.rollback()
        print(f"Error creating event: {e}")
        return None, None

def get_or_create_remote_event_stub(puid, created_by_user_puid, source_type, source_puid, title, event_datetime, location, details, is_public, event_end_datetime, hostname, profile_picture_path=None):
    """Finds a remote event by PUID or creates a stub for it."""
    db = get_db()
    cursor = db.cursor()

    event = get_event_by_puid(puid)
    if event:
        return event

    # If it doesn't exist, create it as a remote event stub
    from .federation import get_or_create_remote_user # Local import

    creator = get_user_by_puid(created_by_user_puid)
    if not creator:
        # We need at least a stub for the creator
        # Try to guess user_type based on source_type
        creator_user_type = 'public_page' if source_type == 'public_page' else 'remote'
        creator = get_or_create_remote_user(
            puid=created_by_user_puid, 
            username=f"user_{created_by_user_puid[:8]}", 
            display_name=f"User {created_by_user_puid[:8]}", 
            hostname=hostname,
            user_type=creator_user_type # Pass the guessed user_type
        )


    if not creator:
        print(f"CRITICAL: Could not create remote event stub because creator user {created_by_user_puid} could not be created.")
        return None

    try:
        new_puid, _ = create_event(
            created_by_user=creator,
            source_type=source_type,
            source_puid=source_puid,
            title=title,
            event_datetime=event_datetime,
            location=location,
            details=details,
            is_public=is_public,
            event_end_datetime=event_end_datetime,
            is_remote=True,
            puid=puid, # Use the original puid
            hostname=hostname
        )
        if new_puid:
            # Update profile picture path if provided
            if profile_picture_path:
                update_event_picture_path(new_puid, profile_picture_path)
            return get_event_by_puid(new_puid)
        return None
    except Exception as e:
        print(f"ERROR: Failed to create remote event stub: {e}")
        traceback.print_exc()
        return None

def get_event_by_id(event_id):
    """Retrieves an event by its internal ID."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    return dict(row) if row else None

def get_event_by_puid(puid, viewer_user_puid=None):
    """Retrieves a single event by its PUID, including creator and group details."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT e.*,
               u.display_name as creator_display_name,
               u.profile_picture_path as creator_profile_picture_path,
               u.hostname as creator_hostname,
               u.user_type as creator_user_type,
               g.name as group_name,
               g.puid as group_puid
        FROM events e
        JOIN users u ON e.created_by_user_puid = u.puid
        LEFT JOIN groups g ON e.source_type = 'group' AND e.source_puid = g.puid
        WHERE e.puid = ?
    """, (puid,))
    row = cursor.fetchone()
    if not row:
        return None

    event = dict(row)

    event['viewer_response'] = None # FIX: Initialize the key to None
    if viewer_user_puid:
        cursor.execute("SELECT response FROM event_attendees WHERE event_id = ? AND user_puid = ?", (event['id'], viewer_user_puid))
        response_row = cursor.fetchone()
        event['viewer_response'] = response_row['response'] if response_row else None

    # If the event is cancelled, override the viewer's response for UI purposes
    if event.get('is_cancelled'):
        event['viewer_response'] = 'cancelled'
    
    # If the event is public, and the user hasn't responded, they aren't 'invited'
    elif event.get('is_public') and event['viewer_response'] is None:
        event['viewer_response'] = None # Explicitly None, not 'invited'

    return event

def get_event_attendees(event_id):
    """Retrieves all attendees for an event with their details."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT a.response, u.puid, u.display_name, u.profile_picture_path, u.hostname
        FROM event_attendees a
        JOIN users u ON a.user_puid = u.puid
        WHERE a.event_id = ?
        ORDER BY a.response, u.display_name
    """, (event_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def respond_to_event(event_puid, user_puid, response, distribute=True):
    """Updates a user's response to an event invitation."""
    db = get_db()
    cursor = db.cursor()
    try:
        event = get_event_by_puid(event_puid)
        if not event:
            return False, "Event not found."
        event_id = event['id']

        cursor.execute("SELECT response FROM event_attendees WHERE event_id = ? AND user_puid = ?", (event_id, user_puid))
        existing_response_row = cursor.fetchone()
        
        if not existing_response_row:
            cursor.execute("""
                INSERT INTO event_attendees (event_id, user_puid, response, updated_at)
                VALUES (?, ?, ?, ?)
            """, (event_id, user_puid, response, datetime.utcnow()))
            print(f"🔵 DEBUG: NEW attendee inserted - event_id:{event_id}, user_puid:{user_puid}, response:{response}")
        else:
            cursor.execute("""
                UPDATE event_attendees
                SET response = ?, updated_at = ?
                WHERE event_id = ? AND user_puid = ?
            """, (response, datetime.utcnow(), event_id, user_puid))
            print(f"🟢 DEBUG: Existing attendee updated - event_id:{event_id}, user_puid:{user_puid}, old:{existing_response_row['response']}, new:{response}")

        db.commit()
        
        # Verify the record exists after commit
        cursor.execute("SELECT response FROM event_attendees WHERE event_id = ? AND user_puid = ?", (event_id, user_puid))
        verify_row = cursor.fetchone()
        if verify_row:
            print(f"✅ DEBUG: Verified attendee record - event_id:{event_id}, user_puid:{user_puid}, response:{verify_row['response']}")
        else:
            print(f"❌ DEBUG: FAILED to find attendee record after commit!")

        if distribute and event.get('hostname'):
            distribute_event_response(event_puid, user_puid, response)

        return True, "Response updated."
    except sqlite3.Error as e:
        db.rollback()
        print(f"ERROR in respond_to_event: {e}")
        return False, f"Database error: {e}"

def get_events_for_user(user_puid):
    """
    Retrieves events for the 'My Events' page, categorized for the tabs.
    Now includes the is_cancelled flag and group info.
    """
    db = get_db()
    cursor = db.cursor()
    now = datetime.utcnow()

    # Get all events the user has responded to (attending, tentative, declined)
    cursor.execute("""
        SELECT e.*, ea.response, u.puid as created_by_user_puid, u.display_name as creator_display_name, u.hostname as creator_hostname, g.name as group_name, g.puid as group_puid
        FROM events e
        JOIN event_attendees ea ON e.id = ea.event_id
        JOIN users u ON e.created_by_user_puid = u.puid
        LEFT JOIN groups g ON e.source_type = 'group' AND e.source_puid = g.puid
        WHERE ea.user_puid = ? AND ea.response != 'invited'
    """, (user_puid,))
    responded_events = [dict(row) for row in cursor.fetchall()]

    # Get all pending invitations for the user (for non-cancelled events)
    cursor.execute("""
        SELECT e.*, ea.response, u.puid as created_by_user_puid, u.display_name as creator_display_name, u.hostname as creator_hostname, g.name as group_name, g.puid as group_puid
        FROM events e
        JOIN event_attendees ea ON e.id = ea.event_id
        JOIN users u ON e.created_by_user_puid = u.puid
        LEFT JOIN groups g ON e.source_type = 'group' AND e.source_puid = g.puid
        WHERE ea.user_puid = ? AND ea.response = 'invited' AND e.event_datetime > ? AND e.is_cancelled = FALSE
    """, (user_puid, now))
    invited_events = [dict(row) for row in cursor.fetchall()]

    # Get all upcoming public, non-cancelled events
    cursor.execute("""
        SELECT e.*, u.puid as created_by_user_puid, u.display_name as creator_display_name, u.hostname as creator_hostname, g.name as group_name, g.puid as group_puid
        FROM events e
        JOIN users u ON e.created_by_user_puid = u.puid
        LEFT JOIN groups g ON e.source_type = 'group' AND e.source_puid = g.puid
        WHERE e.is_public = 1 AND e.event_datetime > ? AND e.is_cancelled = FALSE
    """, (now,))
    public_events_raw = cursor.fetchall()

    # Filter out public events the user is already involved with
    user_event_ids = {e['id'] for e in responded_events} | {e['id'] for e in invited_events}
    public_events = [dict(row) for row in public_events_raw if row['id'] not in user_event_ids]


    def process_event_list(events):
        processed = []
        for event_dict in events:
            try:
                # Make a copy to avoid modifying the original dict during iteration if needed later
                event = event_dict.copy()
                if event.get('event_datetime') and isinstance(event.get('event_datetime'), str):
                    event['event_datetime'] = datetime.strptime(event['event_datetime'], '%Y-%m-%d %H:%M:%S')
                if event.get('event_end_datetime') and isinstance(event.get('event_end_datetime'), str):
                    event['event_end_datetime'] = datetime.strptime(event['event_end_datetime'], '%Y-%m-%d %H:%M:%S')
                processed.append(event)
            except (ValueError, TypeError) as e:
                print(f"Warning: Could not parse datetime for event {event_dict.get('puid')}: {e}")
                processed.append(event_dict) # Keep original if parsing fails
        return processed

    responded_events = process_event_list(responded_events)
    invited_events = process_event_list(invited_events)
    public_events = process_event_list(public_events)


    # Categorize responded events into past and upcoming
    past_events = sorted(
        [e for e in responded_events if (isinstance(e.get('event_datetime'), datetime) and e.get('event_datetime') < now) or e.get('is_cancelled')],
        key=lambda x: x.get('event_datetime') or datetime.min, reverse=True # Sort past newest first
    )
    my_upcoming_events = sorted(
        [e for e in responded_events if isinstance(e.get('event_datetime'), datetime) and e.get('event_datetime') >= now and not e.get('is_cancelled')],
        key=lambda x: x.get('event_datetime') or datetime.max # Sort upcoming soonest first
    )

    # Sort invitations and discoverable events
    invitations = sorted(invited_events, key=lambda x: x.get('event_datetime') or datetime.max)
    discover_public = sorted(public_events, key=lambda x: x.get('event_datetime') or datetime.max)

    return {
        'my_upcoming': my_upcoming_events,
        'invitations': invitations,
        'discover_public': discover_public,
        'past': past_events,
    }


def update_event_picture_path(event_puid, profile_picture_path, original_profile_picture_path=None):
    """Updates an event's picture path."""
    db = get_db()
    cursor = db.cursor()
    try:
        if original_profile_picture_path:
            cursor.execute("UPDATE events SET profile_picture_path = ?, original_profile_picture_path = ? WHERE puid = ?",
                           (profile_picture_path, original_profile_picture_path, event_puid))
        else:
            cursor.execute("UPDATE events SET profile_picture_path = ?, original_profile_picture_path = NULL WHERE puid = ?",
                           (profile_picture_path, event_puid))
        db.commit()
        return True
    except sqlite3.Error as e:
        db.rollback()
        print(f"Error updating event picture path: {e}")
        return False

def update_event_details(puid, title, event_datetime, location, details, updated_by_user, event_end_datetime=None, distribute=True):
    """Updates the details of an event, creates a post about the update, and notifies attendees."""
    from .posts import add_post, get_post_by_cuid
    db = get_db()
    cursor = db.cursor()
    try:
        original_event = get_event_by_puid(puid)
        if not original_event:
            return False, "Event not found."

        # Convert original datetime string to object for comparison
        original_dt_obj = datetime.strptime(original_event['event_datetime'], '%Y-%m-%d %H:%M:%S') if isinstance(original_event.get('event_datetime'), str) else original_event.get('event_datetime')
        original_end_dt_obj = None
        if original_event.get('event_end_datetime'):
            original_end_dt_obj = datetime.strptime(original_event['event_end_datetime'], '%Y-%m-%d %H:%M:%S') if isinstance(original_event.get('event_end_datetime'), str) else original_event.get('event_end_datetime')


        # Check if anything actually changed
        if original_event['title'] == title and \
           original_dt_obj == event_datetime and \
           original_event['location'] == location and \
           original_event['details'] == details and \
           original_end_dt_obj == event_end_datetime:
                if distribute: # Only return "No changes" if distribution was intended
                    return True, "No changes were made to the event."
                # If no distribute, just confirm success without message
                return True, ""


        cursor.execute("""
            UPDATE events SET title = ?, event_datetime = ?, location = ?, details = ?, event_end_datetime = ?
            WHERE puid = ?
        """, (title, event_datetime, location, details, event_end_datetime, puid))


        changes = []
        if original_event['title'] != title:
            changes.append(f"The title of this event has been changed to '{title}'")

        if original_dt_obj != event_datetime:
            day_with_suffix = str(event_datetime.day) + suffix(event_datetime.day)
            day_name = DAY_NAMES[event_datetime.weekday()].capitalize()
            month_name = MONTH_NAMES[event_datetime.month - 1].capitalize()
            start_str = f"{day_name}, {day_with_suffix} {month_name} {event_datetime.year} at {event_datetime.strftime('%H:%M')}"
            changes.append(f"The start time has been updated to {start_str}")

        if original_end_dt_obj != event_end_datetime:
            if event_end_datetime:
                day_with_suffix = str(event_end_datetime.day) + suffix(event_end_datetime.day)
                day_name = DAY_NAMES[event_end_datetime.weekday()].capitalize()
                month_name = MONTH_NAMES[event_end_datetime.month - 1].capitalize()
                end_str = f"{day_name}, {day_with_suffix} {month_name} {event_end_datetime.year} at {event_end_datetime.strftime('%H:%M')}"
                changes.append(f"The end time has been updated to {end_str}")
            else:
                changes.append("The end time has been removed")

        if original_event['location'] != location:
            changes.append(f"The location of this event has been updated to '{location}'")

        if original_event['details'] != details:
             changes.append("The details have been updated.") # Keep it simple for details change

        if changes:
            update_message = "; ".join(changes) + "."

            group_puid_for_post = None
            if original_event.get('source_type') == 'group':
                group_puid_for_post = original_event.get('source_puid')

            post_cuid = add_post(
                user_id=updated_by_user['id'],
                profile_user_id=None,
                content=update_message,
                privacy_setting='event',
                event_id=original_event['id'],
                group_puid=group_puid_for_post,
                author_hostname=updated_by_user.get('hostname') # Include hostname if remote actor
            )

            if post_cuid:
                new_post = get_post_by_cuid(post_cuid)
                new_post_id = new_post['id'] if new_post else None

                attendees = get_event_attendees(original_event['id'])
                for attendee in attendees:
                    attendee_user = get_user_by_puid(attendee['puid'])
                    if attendee_user and attendee_user['puid'] != updated_by_user['puid']:
                        if attendee_user.get('hostname') is None: # Only notify local users directly
                            create_notification(
                                user_id=attendee_user['id'],
                                actor_id=updated_by_user['id'],
                                type='event_update',
                                event_id=original_event['id'],
                                post_id=new_post_id # Link to the update post
                            )

        db.commit()

        if distribute:
            distribute_event_update(puid, updated_by_user)

        return True, "Event updated successfully."

    except (sqlite3.Error, ValueError) as e:
        db.rollback()
        print(f"Error updating event details: {e}")
        traceback.print_exc()
        return False, f"A database error occurred: {e}"

def cancel_event(event_puid, cancelled_by_user_id, distribute=True):
    """Marks an event as cancelled, posts an announcement, and notifies attendees."""
    from .posts import add_post
    db = get_db()
    cursor = db.cursor()
    try:
        event = get_event_by_puid(event_puid)
        if not event:
            return False, "Event not found."

        cancelling_user = get_user_by_id(cancelled_by_user_id)
        if not cancelling_user:
             return False, "Cancelling user not found."
             
        # Authorization check: only creator can cancel
        if event['created_by_user_puid'] != cancelling_user['puid']:
            return False, "You do not have permission to cancel this event."

        # Check if already cancelled
        if event.get('is_cancelled'):
            return True, "Event is already cancelled." # Not an error, just return success

        cursor.execute("UPDATE events SET is_cancelled = 1 WHERE id = ?", (event['id'],))

        # Delete any pending parental approval requests for this event
        from db_queries.parental_controls import delete_approval_requests_for_event
        delete_approval_requests_for_event(event['puid'])
        
        # Create cancellation post
        cancellation_content = f"This event, {event['title']}, has been cancelled."
        group_puid_for_post = event.get('source_puid') if event.get('source_type') == 'group' else None
        
        post_cuid = add_post(
            user_id=cancelled_by_user_id,
            content=cancellation_content,
            privacy_setting='event', # Cancellation is relevant to attendees
            event_id=event['id'],
            profile_user_id=None,
            group_puid=group_puid_for_post,
            author_hostname=cancelling_user.get('hostname')
        )

        # Notify attendees
        notified_puids = set()
        attendees = get_event_attendees(event['id'])
        for attendee in attendees:
            if attendee['puid'] != cancelling_user['puid']:
                notified_puids.add(attendee['puid'])

        # If it was a public event from a public page, also notify followers?
        # Maybe too noisy - let's stick to attendees for now.
        # if event['source_type'] == 'public_page' and event['is_public']:
        #     page_creator = get_user_by_puid(event['created_by_user_puid'])
        #     if page_creator:
        #         followers = get_followers(page_creator['id'])
        #         for follower in followers:
        #             notified_puids.add(follower['puid'])

        for puid_to_notify in notified_puids:
            user_to_notify = get_user_by_puid(puid_to_notify)
            if user_to_notify and user_to_notify.get('hostname') is None: # Only local notifications
                create_notification(
                    user_id=user_to_notify['id'],
                    actor_id=cancelled_by_user_id,
                    type='event_cancelled',
                    event_id=event['id']
                )

        db.commit()

        if distribute:
            distribute_event_cancel(event_puid, cancelling_user)

        return True, "Event cancelled successfully."
    except sqlite3.Error as e:
        db.rollback()
        print(f"Error cancelling event: {e}")
        traceback.print_exc()
        return False, f"A database error occurred: {e}"

def get_friends_to_invite_to_event(user_id, event_id):
    """Gets a list of friends who have not yet been invited or responded."""
    db = get_db()
    cursor = db.cursor()

    all_friends = get_friends_list(user_id)
    friend_puids = {friend['puid'] for friend in all_friends}

    cursor.execute("SELECT user_puid FROM event_attendees WHERE event_id = ?", (event_id,))
    already_involved_puids = {row['user_puid'] for row in cursor.fetchall()}

    invitable_puids = friend_puids - already_involved_puids

    invitable_friends = [friend for friend in all_friends if friend['puid'] in invitable_puids]

    return invitable_friends

def invite_friend_to_event(event_id, inviter_id, invitee_puid):
    """Adds a user to an event as 'invited' and sends a notification."""
    db = get_db()
    cursor = db.cursor()
    try:
        # Ensure the user isn't already involved before inserting 'invited'
        cursor.execute("SELECT 1 FROM event_attendees WHERE event_id = ? AND user_puid = ?", (event_id, invitee_puid))
        if cursor.fetchone():
            return True # Already involved, treat as success

        cursor.execute("INSERT INTO event_attendees (event_id, user_puid, response) VALUES (?, ?, 'invited')", (event_id, invitee_puid))

        invitee = get_user_by_puid(invitee_puid)
        if invitee and invitee.get('hostname') is None: # Only create notification for local invitee
            create_notification(
                user_id=invitee['id'],
                actor_id=inviter_id,
                type='event_invite',
                event_id=event_id
            )
        db.commit()
        return True
    except sqlite3.Error as e:
        db.rollback()
        print(f"Error inviting friend to event: {e}")
        return False

def get_posts_for_event(event_id, viewer_user_puid=None, page=1, limit=20):
    """Retrieves all posts for a given event's timeline."""
    db = get_db()
    cursor = db.cursor()
    from .posts import get_post_by_cuid
    
    offset = (page - 1) * limit
    
    # Query with LIMIT and OFFSET
    cursor.execute(
        "SELECT cuid FROM posts WHERE event_id = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        (event_id, limit, offset)  # Pass all three params
    )
    post_cuids = [row['cuid'] for row in cursor.fetchall()]
    
    final_posts = []

    # NEW: Get viewer_user_id for filtering
    viewer_user_id = None
    if viewer_user_puid:
        from .users import get_user_by_puid
        viewer_user = get_user_by_puid(viewer_user_puid)
        if viewer_user:
            viewer_user_id = viewer_user['id']
            
    for cuid in post_cuids:
        post = get_post_by_cuid(cuid, viewer_user_puid=viewer_user_puid)
        if post:
            # NEW: Skip hidden posts
            if viewer_user_id:
                from .posts import is_post_hidden_for_user
                if is_post_hidden_for_user(viewer_user_id, post['id']):
                    continue
            final_posts.append(post)
    return final_posts

# --- NEW FUNCTIONS ---

def get_future_events_for_source(source_type, source_puid):
    """Retrieves future, non-public, non-cancelled events created by a specific source."""
    db = get_db()
    cursor = db.cursor()
    now = datetime.utcnow()
    try:
        cursor.execute("""
            SELECT * FROM events
            WHERE source_type = ?
              AND source_puid = ?
              AND event_datetime > ?
              AND is_cancelled = FALSE
              AND is_public = FALSE
            ORDER BY event_datetime ASC
        """, (source_type, source_puid, now))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"Error fetching future events for {source_type} {source_puid}: {e}")
        return []

def invite_user_to_source_future_events(user, source_type, source_puid):
    """Invites a user to all relevant future events from a source they just joined/followed."""
    # Local import to avoid circular dependency
    from .posts import get_event_announcement_post

    if not user:
        print("invite_user_to_source_future_events: No user provided.")
        return

    future_events = get_future_events_for_source(source_type, source_puid)
    if not future_events:
        # print(f"No future non-public events found for {source_type} {source_puid} to invite {user.get('puid', 'Unknown User')}.")
        return

    print(f"Found {len(future_events)} future non-public events for {source_type} {source_puid}. Inviting {user.get('puid', 'Unknown User')}.")

    # Assuming all events from the same source have the same creator
    inviter = get_user_by_puid(future_events[0]['created_by_user_puid'])
    if not inviter:
        print(f"Could not find inviter ({future_events[0]['created_by_user_puid']}) for events.")
        print("Skipping event invitations as inviter could not be found.")
        return

    for event in future_events:
        print(f"Inviting user {user.get('puid', 'Unknown User')} to event {event['puid']} ({event['id']})...")
        # Add user to local attendee list (creates local notification if user is local)
        success = invite_friend_to_event(event['id'], inviter['id'], user['puid'])

        # If user is remote and invite was successful (or user was already involved)
        if success and user.get('hostname'):
            print(f"User {user.get('puid')} is remote. Finding announcement post for event {event['id']}...")
            post_cuid = get_event_announcement_post(event['id'])
            if post_cuid:
                print(f"Distributing announcement post {post_cuid} to node {user.get('hostname')}...")
                try:
                    # Pass the cuid and hostname to the distribution function
                    distribute_post_to_single_node(post_cuid, user.get('hostname'))
                    print(f"Successfully initiated distribution of post {post_cuid} to {user.get('hostname')}.")
                except Exception as e:
                    print(f"Error distributing post {post_cuid} to {user.get('hostname')}: {e}")
                    traceback.print_exc()
            else:
                print(f"Warning: Could not find announcement post for event {event['id']}.")
        elif success:
            print(f"Successfully invited local user {user.get('puid')} to event {event['puid']}.")
        else:
             print(f"Failed to invite user {user.get('puid')} to event {event['puid']}.")

# --- NEW FUNCTION for event discovery ---
def get_discoverable_public_events():
    """Retrieves all future, public, non-cancelled events created by public pages."""
    db = get_db()
    cursor = db.cursor()
    now = datetime.utcnow()
    try:
        # This query fetches both local public events and remote public event stubs
        cursor.execute("""
            SELECT e.*,
                   u.puid as created_by_user_puid,
                   u.display_name as creator_display_name,
                   u.hostname as creator_hostname
            FROM events e
            JOIN users u ON e.created_by_user_puid = u.puid
            WHERE e.source_type = 'public_page'
              AND e.is_public = 1
              AND e.event_datetime > ?
              AND e.is_cancelled = FALSE
            ORDER BY e.event_datetime ASC
        """, (now,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"Error fetching discoverable public events: {e}")
        return []

def check_new_posts_in_event(event_puid, viewer_user_id, since_timestamp):
    """
    Check if there are new posts in an event since a given timestamp.
    """
    from datetime import datetime
    
    try:
        since_dt = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return False
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get the event
    event = get_event_by_puid(event_puid)
    if not event:
        return False
    
    # Check posts table (not event_posts) with microsecond precision
    query = """
        SELECT 1
        FROM posts p
        WHERE p.event_id = ?
        AND p.timestamp > ?
        LIMIT 1
    """
    
    cursor.execute(query, (event['id'], since_dt.strftime('%Y-%m-%d %H:%M:%S.%f')))
    result = cursor.fetchone()
    return result is not None