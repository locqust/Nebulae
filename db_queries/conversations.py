# db_queries/conversations.py
# Contains functions for managing direct messaging conversations.

import uuid
import sqlite3
from datetime import datetime
from db import get_db

# =============================================================================
# CONVERSATION MANAGEMENT
# =============================================================================

def create_conversation(creator_user_id, participant_user_ids):
    """
    Creates a new conversation with the specified participants.
    
    Args:
        creator_user_id: ID of the user creating the conversation
        participant_user_ids: List of user IDs to add as participants (including creator)
    
    Returns:
        dict: Conversation data with conv_uid, or None on failure
    """
    db = get_db()
    cursor = db.cursor()
    conv_uid = str(uuid.uuid4())
    
    try:
        # Create the conversation
        cursor.execute("""
            INSERT INTO conversations (conv_uid, created_by_user_id)
            VALUES (?, ?)
        """, (conv_uid, creator_user_id))
        
        conversation_id = cursor.lastrowid
        
        # Add all participants
        for user_id in participant_user_ids:
            cursor.execute("""
                INSERT INTO conversation_participants (conversation_id, user_id)
                VALUES (?, ?)
            """, (conversation_id, user_id))
        
        db.commit()
        
        # Return the created conversation
        cursor.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
        
    except sqlite3.Error as e:
        print(f"Error creating conversation: {e}")
        db.rollback()
        return None


def get_conversation_by_conv_uid(conv_uid):
    """Retrieves a conversation by its unique conv_uid."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM conversations WHERE conv_uid = ?", (conv_uid,))
    row = cursor.fetchone()
    return dict(row) if row else None


def get_conversation_by_id(conversation_id):
    """Retrieves a conversation by its internal ID."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def get_or_create_conversation_between_users(user_ids):
    """
    Finds an existing conversation with exactly these users, or creates a new one.
    This prevents duplicate conversations between the same set of participants.
    
    Args:
        user_ids: List of user IDs (must include all participants)
    
    Returns:
        dict: Conversation data with conv_uid
    """
    db = get_db()
    cursor = db.cursor()
    
    # Sort user_ids for consistent comparison
    user_ids_sorted = sorted(user_ids)
    participant_count = len(user_ids_sorted)
    
    # Find conversations that have exactly this number of participants
    cursor.execute("""
        SELECT c.*, COUNT(cp.user_id) as participant_count
        FROM conversations c
        JOIN conversation_participants cp ON c.id = cp.conversation_id
        GROUP BY c.id
        HAVING participant_count = ?
    """, (participant_count,))
    
    potential_conversations = cursor.fetchall()
    
    # Check each conversation to see if it has exactly these users
    for conv_row in potential_conversations:
        conv_id = conv_row['id']
        
        # Get participants for this conversation
        cursor.execute("""
            SELECT user_id FROM conversation_participants 
            WHERE conversation_id = ?
            ORDER BY user_id
        """, (conv_id,))
        
        conv_user_ids = sorted([row['user_id'] for row in cursor.fetchall()])
        
        if conv_user_ids == user_ids_sorted:
            # Found exact match!
            return dict(conv_row)
    
    # No existing conversation found - create new one
    return create_conversation(user_ids[0], user_ids)


def update_conversation_last_message_time(conversation_id):
    """Updates the last_message_at timestamp for a conversation."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE conversations 
            SET last_message_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (conversation_id,))
        db.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error updating conversation last_message_at: {e}")
        db.rollback()
        return False

def rename_conversation(conv_uid, new_title, requesting_user_id):
    """
    Sets a custom title on a conversation. Only the creator can do this.
    Pass empty string or None to clear the title (revert to participant names).

    Returns:
        bool: True if updated, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE conversations
            SET title = ?
            WHERE conv_uid = ? AND created_by_user_id = ?
        """, (new_title.strip() if new_title else None, conv_uid, requesting_user_id))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error renaming conversation: {e}")
        db.rollback()
        return False

def update_conversation_picture(conv_uid, picture_path, origin_hostname=None):
    """Updates the group picture path for a conversation."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE conversations SET picture_path = ?, picture_origin_hostname = ? WHERE conv_uid = ?
        """, (picture_path, origin_hostname, conv_uid))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error updating conversation picture: {e}")
        db.rollback()
        return False

# =============================================================================
# PARTICIPANT MANAGEMENT
# =============================================================================

def get_conversation_participants(conversation_id):
    """
    Retrieves all participants in a conversation with their user data.
    
    Returns:
        list: List of participant dicts with user information
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT cp.*, u.puid, u.username, u.display_name, 
               u.profile_picture_path, u.hostname, u.user_type
        FROM conversation_participants cp
        JOIN users u ON cp.user_id = u.id
        WHERE cp.conversation_id = ?
        ORDER BY cp.left_at ASC, cp.joined_at ASC
    """, (conversation_id,))
    
    return [dict(row) for row in cursor.fetchall()]


def is_user_in_conversation(user_id, conversation_id):
    """Checks if a user is an active participant in a conversation (not left)."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT COUNT(*) as count 
        FROM conversation_participants 
        WHERE conversation_id = ? AND user_id = ? AND left_at IS NULL
    """, (conversation_id, user_id))
    
    result = cursor.fetchone()
    return result['count'] > 0


def invite_participant(conversation_id, user_id, invited_by_user_id):
    """
    Adds a user to a conversation, or re-activates them if they previously left.
    Emits a system message either way.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        # Get display names for system message
        cursor.execute("SELECT display_name FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        invited_name = row['display_name'] if row else 'Someone'

        cursor.execute("SELECT display_name FROM users WHERE id = ?", (invited_by_user_id,))
        row = cursor.fetchone()
        inviter_name = row['display_name'] if row else 'Someone'

        # Check if they were previously a participant (left)
        cursor.execute("""
            SELECT id, left_at FROM conversation_participants
            WHERE conversation_id = ? AND user_id = ?
        """, (conversation_id, user_id))
        existing = cursor.fetchone()

        if existing:
            if existing['left_at'] is None:
                return False  # Already active, don't double-add
            # Re-activate
            cursor.execute("""
                UPDATE conversation_participants
                SET left_at = NULL, is_archived = FALSE, last_read_at = CURRENT_TIMESTAMP
                WHERE conversation_id = ? AND user_id = ?
            """, (conversation_id, user_id))
        else:
            # Fresh addition
            cursor.execute("""
                INSERT INTO conversation_participants (conversation_id, user_id)
                VALUES (?, ?)
            """, (conversation_id, user_id))

        db.commit()
        send_system_message(
            conversation_id,
            f"{invited_name} was added by {inviter_name}."
        )
        return True
    except sqlite3.Error as e:
        print(f"Error inviting participant: {e}")
        db.rollback()
        return False


def remove_participant(conversation_id, user_id, removed_by_user_id):
    """
    Creator removes a participant from a conversation.
    Stamps left_at and emits a system message.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT display_name FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        removed_name = row['display_name'] if row else 'Someone'

        cursor.execute("SELECT display_name FROM users WHERE id = ?", (removed_by_user_id,))
        row = cursor.fetchone()
        remover_name = row['display_name'] if row else 'Someone'

        cursor.execute("""
            UPDATE conversation_participants
            SET left_at = CURRENT_TIMESTAMP, is_archived = TRUE
            WHERE conversation_id = ? AND user_id = ? AND left_at IS NULL
        """, (conversation_id, user_id))
        db.commit()
        if cursor.rowcount > 0:
            send_system_message(
                conversation_id,
                f"{removed_name} was removed by {remover_name}."
            )
            return True
        return False
    except sqlite3.Error as e:
        print(f"Error removing participant: {e}")
        db.rollback()
        return False

def leave_conversation(conversation_id, user_id):
    db = get_db()
    cursor = db.cursor()
    try:
        # Get user display name for system message
        cursor.execute("SELECT display_name FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        display_name = row['display_name'] if row else 'Someone'

        cursor.execute("""
            UPDATE conversation_participants
            SET left_at = CURRENT_TIMESTAMP, is_archived = TRUE
            WHERE conversation_id = ? AND user_id = ? AND left_at IS NULL
        """, (conversation_id, user_id))
        db.commit()
        if cursor.rowcount > 0:
            send_system_message(conversation_id, f"{display_name} left the conversation.")
            return True
        return False
    except sqlite3.Error as e:
        print(f"Error leaving conversation: {e}")
        db.rollback()
        return False
    
def hide_conversation_for_user(conversation_id, user_id):
    """
    Hides a conversation from the user's list without leaving it.
    Reappears automatically when a new message arrives (handled by unread logic).
    Reuses is_archived column — same behaviour, clearer intent.
    """
    return archive_conversation_for_user(conversation_id, user_id)

def archive_conversation_for_user(conversation_id, user_id):
    """Archives a conversation for a specific user (doesn't affect other participants)."""
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            UPDATE conversation_participants 
            SET is_archived = TRUE 
            WHERE conversation_id = ? AND user_id = ?
        """, (conversation_id, user_id))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error archiving conversation: {e}")
        db.rollback()
        return False


def unarchive_conversation_for_user(conversation_id, user_id):
    """Unarchives a conversation for a specific user."""
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            UPDATE conversation_participants 
            SET is_archived = FALSE 
            WHERE conversation_id = ? AND user_id = ?
        """, (conversation_id, user_id))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error unarchiving conversation: {e}")
        db.rollback()
        return False


def mark_conversation_as_read(conversation_id, user_id):
    """Updates the last_read_at timestamp for a user in a conversation."""
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            UPDATE conversation_participants 
            SET last_read_at = CURRENT_TIMESTAMP 
            WHERE conversation_id = ? AND user_id = ?
        """, (conversation_id, user_id))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error marking conversation as read: {e}")
        db.rollback()
        return False


def get_conversations_for_user(user_id, include_archived=False):
    """
    Retrieves all conversations for a user, ordered by last message time.
    Includes unread count and other participant information.
    
    Args:
        user_id: ID of the user
        include_archived: Whether to include archived conversations
    
    Returns:
        list: List of conversation dicts with metadata
    """
    db = get_db()
    cursor = db.cursor()
    
    archive_filter = "" if include_archived else """
        AND (cp.is_archived = FALSE 
             OR EXISTS (
                SELECT 1 FROM direct_messages dm
                WHERE dm.conversation_id = c.id
                AND dm.sender_id != cp.user_id
                AND dm.sent_at > COALESCE(cp.last_read_at, '1970-01-01')
                AND dm.is_deleted = FALSE
             ))"""
    
    cursor.execute(f"""
        SELECT c.*, cp.last_read_at, cp.is_archived,
            (SELECT COUNT(*) 
                FROM direct_messages dm 
                WHERE dm.conversation_id = c.id 
                AND dm.sent_at > COALESCE(cp.last_read_at, '1970-01-01')
                AND dm.sender_id != ?) as unread_count,
            (SELECT CASE WHEN is_deleted = 1 THEN 'This message was deleted.' ELSE content END
                FROM direct_messages 
                WHERE conversation_id = c.id 
                ORDER BY sent_at DESC LIMIT 1) as last_message_preview,
            (SELECT u.display_name 
                FROM direct_messages dm2
                JOIN users u ON u.id = dm2.sender_id
                WHERE dm2.conversation_id = c.id 
                ORDER BY dm2.sent_at DESC LIMIT 1) as last_message_sender_name,
            (SELECT dm3.sender_id 
                FROM direct_messages dm3
                WHERE dm3.conversation_id = c.id 
                ORDER BY dm3.sent_at DESC LIMIT 1) as last_message_sender_id
        FROM conversations c
        JOIN conversation_participants cp ON c.id = cp.conversation_id
        LEFT JOIN dm_requests dmr ON dmr.conversation_id = c.id
        WHERE cp.user_id = ? AND cp.left_at IS NULL
        AND (dmr.id IS NULL OR dmr.status = 'accepted') {archive_filter}
        ORDER BY c.last_message_at DESC
    """, (user_id, user_id))
    
    conversations = []
    for row in cursor.fetchall():
        conv_dict = dict(row)
        
        # Get other participants (not including the current user)
        conv_dict['participants'] = get_conversation_participants(conv_dict['id'])
        conv_dict['other_participants'] = [
            p for p in conv_dict['participants'] if p['user_id'] != user_id
        ]
        
        conversations.append(conv_dict)
    
    return conversations


def get_unread_message_count_for_user(user_id):
    """
    Gets the total number of unread messages across all conversations for a user.
    Used for notification badge counts.
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as unread_count
        FROM direct_messages dm
        JOIN conversation_participants cp ON dm.conversation_id = cp.conversation_id
        WHERE cp.user_id = ? 
        AND cp.left_at IS NULL
        AND dm.sender_id != ?
        AND dm.sent_at > COALESCE(cp.last_read_at, '1970-01-01')
        AND dm.is_deleted = FALSE
    """, (user_id, user_id))
    
    result = cursor.fetchone()
    return result['unread_count'] if result else 0

def get_unread_conversation_count_for_user(user_id):
    """
    Gets the number of conversations that have at least one unread message.
    Used for the header badge - shows "X convos need attention" not "X unread messages".
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT COUNT(DISTINCT dm.conversation_id) as unread_conv_count
        FROM direct_messages dm
        JOIN conversation_participants cp ON dm.conversation_id = cp.conversation_id
        WHERE cp.user_id = ? 
        AND cp.left_at IS NULL
        AND dm.sender_id != ?
        AND dm.sent_at > COALESCE(cp.last_read_at, '1970-01-01')
        AND dm.is_deleted = FALSE
    """, (user_id, user_id))
    
    result = cursor.fetchone()
    unread_conv_count = result['unread_conv_count'] if result else 0

    # Also count pending message requests so the badge reflects "attention needed"
    cursor.execute("""
        SELECT COUNT(*) as pending_count
        FROM dm_requests
        WHERE recipient_id = ? AND status = 'pending'
    """, (user_id,))
    
    pending_result = cursor.fetchone()
    pending_count = pending_result['pending_count'] if pending_result else 0

    return unread_conv_count + pending_count

# =============================================================================
# MESSAGE MANAGEMENT
# =============================================================================

def send_message(conversation_id, sender_id, content, nu_id=None, reply_to_msg_uid=None):
    """
    Sends a message in a conversation.
    
    Args:
        conversation_id: ID of the conversation
        sender_id: ID of the user sending the message
        content: Message text content
        nu_id: Optional node unique ID for federation tracking
    
    Returns:
        dict: Message data with msg_uid, or None on failure
    """
    db = get_db()
    cursor = db.cursor()
    msg_uid = str(uuid.uuid4())
    
    try:
        cursor.execute("""
            INSERT INTO direct_messages (msg_uid, conversation_id, sender_id, content, nu_id, reply_to_msg_uid)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (msg_uid, conversation_id, sender_id, content, nu_id, reply_to_msg_uid))
        
        message_id = cursor.lastrowid
        
        # Update the conversation's last message time
        update_conversation_last_message_time(conversation_id)
        
        db.commit()
        
        # Return the created message
        cursor.execute("SELECT * FROM direct_messages WHERE id = ?", (message_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
        
    except sqlite3.Error as e:
        print(f"Error sending message: {e}")
        db.rollback()
        return None

def send_system_message(conversation_id, content):
    """
    Inserts a system message (join/leave event) into a conversation.
    These have no sender — sender_id is NULL, message_type is 'system'.
    Cannot be edited, deleted, or replied to.
    """
    db = get_db()
    cursor = db.cursor()
    msg_uid = str(uuid.uuid4())
    try:
        cursor.execute("""
            INSERT INTO direct_messages (msg_uid, conversation_id, sender_id, content, message_type)
            VALUES (?, ?, NULL, ?, 'system')
        """, (msg_uid, conversation_id, content))
        update_conversation_last_message_time(conversation_id)
        db.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error sending system message: {e}")
        db.rollback()
        return False

def get_message_by_msg_uid(msg_uid):
    """Retrieves a message by its unique msg_uid."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM direct_messages WHERE msg_uid = ?", (msg_uid,))
    row = cursor.fetchone()
    return dict(row) if row else None

def create_federated_conversation(conv_uid, creator_user_id, participant_ids, title=None, picture_path=None, picture_origin_hostname=None):
    """
    Creates a conversation on this node using a conv_uid provided by the originating node.
    Used when receiving a federated conversation sync.
    
    Args:
        conv_uid: The canonical UUID from the originating node
        creator_user_id: Local user ID of the conversation creator
        participant_ids: List of local user IDs to add as participants
        title: Optional conversation title
        picture_path: Optional picture path
    
    Returns:
        bool: True on success, False on failure
    """
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO conversations (conv_uid, created_by_user_id, title, picture_path, picture_origin_hostname)
            VALUES (?, ?, ?, ?, ?)
        """, (conv_uid, creator_user_id, title, picture_path, picture_origin_hostname))
        conversation_id = cursor.lastrowid

        for user_id in participant_ids:
            cursor.execute("""
                INSERT OR IGNORE INTO conversation_participants (conversation_id, user_id)
                VALUES (?, ?)
            """, (conversation_id, user_id))

        db.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error creating federated conversation: {e}")
        db.rollback()
        return False


def receive_federated_message(conversation_id, sender_id, msg_uid, content, 
                               sent_at=None, reply_to_msg_uid=None, 
                               message_type='normal', nu_id=None):
    """
    Stores a message received via federation.
    Uses the msg_uid from the originating node to ensure idempotency.
    
    Returns:
        dict: Message data, or None on failure
    """
    db = get_db()
    cursor = db.cursor()
    try:
        # Check for duplicate (idempotent receive)
        cursor.execute("SELECT * FROM direct_messages WHERE msg_uid = ?", (msg_uid,))
        existing = cursor.fetchone()
        if existing:
            return dict(existing)  # Already have it, not an error

        cursor.execute("""
            INSERT INTO direct_messages 
                (msg_uid, conversation_id, sender_id, content, sent_at, 
                 reply_to_msg_uid, message_type, nu_id)
            VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?)
        """, (msg_uid, conversation_id, sender_id, content, sent_at,
              reply_to_msg_uid, message_type, nu_id))

        message_id = cursor.lastrowid
        update_conversation_last_message_time(conversation_id)
        db.commit()

        cursor.execute("SELECT * FROM direct_messages WHERE id = ?", (message_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    except sqlite3.Error as e:
        print(f"Error receiving federated message: {e}")
        db.rollback()
        return None

def get_messages_for_conversation(conversation_id, limit=50, before_timestamp=None):
    """
    Retrieves messages for a conversation with pagination support.
    
    Args:
        conversation_id: ID of the conversation
        limit: Maximum number of messages to return (default 50)
        before_timestamp: Get messages before this timestamp (for pagination)
    
    Returns:
        list: List of message dicts with sender information and media
    """
    db = get_db()
    cursor = db.cursor()
    
    time_filter = ""
    params = [conversation_id, limit]
    
    if before_timestamp:
        time_filter = "AND dm.sent_at < ?"
        params.insert(1, before_timestamp)
    
    cursor.execute(f"""
        SELECT dm.*, u.puid, u.display_name, u.profile_picture_path, u.hostname,
               (SELECT COUNT(*)
                FROM conversation_participants cp
                WHERE cp.conversation_id = dm.conversation_id
                AND cp.user_id != dm.sender_id
                AND (cp.last_read_at IS NULL OR cp.last_read_at < dm.sent_at)
               ) as unread_by_count,
               reply_dm.content as reply_to_content,
               reply_dm.is_deleted as reply_to_is_deleted,
               reply_u.display_name as reply_to_sender_name,
               reply_u.puid as reply_to_sender_puid,
               (SELECT dmm.media_file_path FROM direct_message_media dmm
                WHERE dmm.message_id = reply_dm.id
                ORDER BY dmm.id ASC LIMIT 1) as reply_to_media_path,
               (SELECT dmm.origin_hostname FROM direct_message_media dmm
                WHERE dmm.message_id = reply_dm.id
                ORDER BY dmm.id ASC LIMIT 1) as reply_to_media_origin_hostname
        FROM direct_messages dm
        LEFT JOIN users u ON dm.sender_id = u.id
        LEFT JOIN direct_messages reply_dm ON reply_dm.msg_uid = dm.reply_to_msg_uid
        LEFT JOIN users reply_u ON reply_u.id = reply_dm.sender_id
        WHERE dm.conversation_id = ? {time_filter}
        ORDER BY dm.sent_at DESC
        LIMIT ?
    """, params)
    
    messages = []
    for row in cursor.fetchall():
        msg_dict = dict(row)
        
        # Get media attachments for this message
        msg_dict['media_files'] = get_media_for_message(msg_dict['id'])
        
        messages.append(msg_dict)
    
    # Reverse to show oldest first (chronological order)
    return list(reversed(messages))


def edit_message(msg_uid, new_content, sender_id):
    """
    Edits an existing message's content.
    
    Args:
        msg_uid: Unique ID of the message to edit
        new_content: New message text
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            UPDATE direct_messages 
            SET content = ?, edited_at = CURRENT_TIMESTAMP 
            WHERE msg_uid = ? AND sender_id = ? AND is_deleted = FALSE
        """, (new_content, msg_uid, sender_id))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error editing message: {e}")
        db.rollback()
        return False


def delete_message(msg_uid, sender_id):
    """
    Soft deletes a message (marks as deleted, doesn't actually remove).
    
    Args:
        msg_uid: Unique ID of the message to delete
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        # AFTER:
        cursor.execute("""
            UPDATE direct_messages 
            SET is_deleted = TRUE, content = '', edited_at = CURRENT_TIMESTAMP
            WHERE msg_uid = ? AND sender_id = ?
        """, (msg_uid, sender_id))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error deleting message: {e}")
        db.rollback()
        return False


# =============================================================================
# MESSAGE MEDIA MANAGEMENT
# =============================================================================

def add_media_to_message(message_id, media_file_path, alt_text=None, origin_hostname=None):
    """
    Adds a media attachment to a message.
    
    Args:
        message_id: Internal ID of the message
        media_file_path: Path to the media file
        alt_text: Optional alt text for accessibility
        origin_hostname: For federation - hostname where media is stored
    
    Returns:
        str: The muid of the created media, or None on failure
    """
    db = get_db()
    cursor = db.cursor()
    muid = str(uuid.uuid4())
    
    try:
        cursor.execute("""
            INSERT INTO direct_message_media (muid, message_id, media_file_path, alt_text, origin_hostname)
            VALUES (?, ?, ?, ?, ?)
        """, (muid, message_id, media_file_path, alt_text, origin_hostname))
        
        db.commit()
        return muid
        
    except sqlite3.Error as e:
        print(f"Error adding media to message: {e}")
        db.rollback()
        return None


def get_media_for_message(message_id):
    """Retrieves all media attachments for a message."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT * FROM direct_message_media 
        WHERE message_id = ?
        ORDER BY id ASC
    """, (message_id,))
    
    return [dict(row) for row in cursor.fetchall()]


def get_media_by_muid(muid):
    """Retrieves a specific media attachment by its muid."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM direct_message_media WHERE muid = ?", (muid,))
    row = cursor.fetchone()
    return dict(row) if row else None


# =============================================================================
# MESSAGE REQUESTS MANAGEMENT
# =============================================================================

def create_message_request(conversation_id, requester_id, recipient_id):
    """
    Creates a message request when a non-friend tries to message someone.
    
    Args:
        conversation_id: ID of the conversation
        requester_id: User requesting to message
        recipient_id: User who needs to accept the request
    
    Returns:
        bool: True if created, False if already exists or error
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        # If a declined request already exists, reset it to pending so the
        # recipient gets a fresh chance to accept or decline again
        cursor.execute("""
            INSERT INTO dm_requests (conversation_id, requester_id, recipient_id, status)
            VALUES (?, ?, ?, 'pending')
            ON CONFLICT(conversation_id, recipient_id) DO UPDATE SET
                status = CASE WHEN excluded.status = 'pending' THEN 'pending'
                              ELSE 'pending' END,
                requester_id = excluded.requester_id,
                requested_at = CURRENT_TIMESTAMP,
                responded_at = NULL
            WHERE dm_requests.status = 'declined'
        """, (conversation_id, requester_id, recipient_id))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error creating message request: {e}")
        db.rollback()
        return False


def get_pending_message_requests_for_user(user_id):
    """
    Gets all pending message requests for a user.
    Includes conversation and requester information.
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT dmr.*, c.conv_uid, c.created_at as conversation_created_at,
               u.puid, u.display_name, u.profile_picture_path, u.hostname
        FROM dm_requests dmr
        JOIN conversations c ON dmr.conversation_id = c.id
        JOIN users u ON dmr.requester_id = u.id
        WHERE dmr.recipient_id = ? AND dmr.status = 'pending'
        ORDER BY dmr.requested_at DESC
    """, (user_id,))
    
    return [dict(row) for row in cursor.fetchall()]


def accept_message_request(conversation_id, recipient_id):
    """
    Accepts a message request, allowing the conversation to proceed.
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            UPDATE dm_requests 
            SET status = 'accepted', responded_at = CURRENT_TIMESTAMP 
            WHERE conversation_id = ? AND recipient_id = ? AND status = 'pending'
        """, (conversation_id, recipient_id))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error accepting message request: {e}")
        db.rollback()
        return False


def decline_message_request(conversation_id, recipient_id):
    """
    Declines a message request.
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            UPDATE dm_requests 
            SET status = 'declined', responded_at = CURRENT_TIMESTAMP 
            WHERE conversation_id = ? AND recipient_id = ? AND status = 'pending'
        """, (conversation_id, recipient_id))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error declining message request: {e}")
        db.rollback()
        return False


def has_pending_request_for_conversation(conversation_id, recipient_id):
    """Checks if there's a pending message request for a conversation."""
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as count 
        FROM dm_requests 
        WHERE conversation_id = ? AND recipient_id = ? AND status = 'pending'
    """, (conversation_id, recipient_id))
    
    result = cursor.fetchone()
    return result['count'] > 0


def get_request_status_for_conversation(conversation_id, recipient_id):
    """
    Gets the status of a message request for a conversation.
    Returns 'pending', 'accepted', 'declined', or None if no request exists.
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT status FROM dm_requests 
        WHERE conversation_id = ? AND recipient_id = ?
        ORDER BY requested_at DESC
        LIMIT 1
    """, (conversation_id, recipient_id))
    
    result = cursor.fetchone()
    return result['status'] if result else None


# =============================================================================
# BLOCKING MANAGEMENT
# =============================================================================

def block_user_from_dms(blocker_id, blocked_id):
    """
    Blocks a user from sending direct messages.
    
    Args:
        blocker_id: User doing the blocking
        blocked_id: User being blocked
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO dm_blocks (blocker_id, blocked_id)
            VALUES (?, ?)
        """, (blocker_id, blocked_id))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        # Already blocked
        return False
    except sqlite3.Error as e:
        print(f"Error blocking user from DMs: {e}")
        db.rollback()
        return False


def unblock_user_from_dms(blocker_id, blocked_id):
    """
    Unblocks a user from sending direct messages.
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM dm_blocks 
            WHERE blocker_id = ? AND blocked_id = ?
        """, (blocker_id, blocked_id))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error unblocking user from DMs: {e}")
        db.rollback()
        return False


def is_user_blocked_from_dms(blocker_id, blocked_id):
    """Checks if a user is blocked from sending DMs."""
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as count 
        FROM dm_blocks 
        WHERE blocker_id = ? AND blocked_id = ?
    """, (blocker_id, blocked_id))
    
    result = cursor.fetchone()
    return result['count'] > 0


def get_blocked_users_for_dms(user_id):
    """
    Gets all users blocked by a specific user from sending DMs.
    Includes user information for display.
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT dmb.*, u.puid, u.display_name, u.profile_picture_path, u.hostname
        FROM dm_blocks dmb
        JOIN users u ON dmb.blocked_id = u.id
        WHERE dmb.blocker_id = ?
        ORDER BY dmb.blocked_at DESC
    """, (user_id,))
    
    return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def can_user_message(sender_id, recipient_id):
    """
    Checks if a user can send messages to another user.
    Considers blocking status.
    
    Args:
        sender_id: User wanting to send a message
        recipient_id: User who would receive the message
    
    Returns:
        tuple: (bool: can_message, str: reason if blocked)
    """
    # Check if sender is blocked by recipient
    if is_user_blocked_from_dms(recipient_id, sender_id):
        return False, "You are blocked from messaging this user"
    
    # Check if recipient is blocked by sender (sender can't message someone they blocked)
    if is_user_blocked_from_dms(sender_id, recipient_id):
        return False, "You have blocked this user"
    
    return True, None


def conversation_requires_request(sender_id, recipient_id):
    """
    Determines if a message request is needed between two users.
    Message requests are required if users are not friends.
    
    Args:
        sender_id: User wanting to send a message
        recipient_id: User who would receive the message
    
    Returns:
        bool: True if a message request is needed, False if they can message directly
    """
    from db_queries.friends import is_friends_with
    
    # Friends can always message each other directly
    if is_friends_with(sender_id, recipient_id):
        return False
    
    # Non-friends require a message request
    return True

def get_new_messages_since(user_id, since_timestamp):
    """
    Returns messages in conversations the user is part of,
    sent after since_timestamp, with sender and conversation info.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT
                dm.id, dm.content, dm.sender_id, dm.sent_at,
                dm.message_type,
                c.conv_uid, c.title as conv_title,
                u.display_name, u.puid,
                (SELECT GROUP_CONCAT(u2.display_name, ', ')
                 FROM conversation_participants cp2
                 JOIN users u2 ON u2.id = cp2.user_id
                 WHERE cp2.conversation_id = c.id
                 AND cp2.user_id != ?
                 AND cp2.left_at IS NULL
                 LIMIT 3) as participant_names
            FROM direct_messages dm
            JOIN conversations c ON c.id = dm.conversation_id
            JOIN conversation_participants cp ON cp.conversation_id = c.id AND cp.user_id = ? AND cp.left_at IS NULL
            LEFT JOIN users u ON u.id = dm.sender_id
            WHERE dm.sent_at > ?
            AND dm.is_deleted = 0
            ORDER BY dm.sent_at ASC
        """, (user_id, user_id, since_timestamp))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error in get_new_messages_since: {e}")
        return []
    
def get_updated_messages_since(conversation_id, since_timestamp):
    """
    Returns messages in a specific conversation that have been edited or deleted
    since since_timestamp. Used to push edit/delete changes to other participants.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            SELECT msg_uid, content, is_deleted, edited_at
            FROM direct_messages
            WHERE conversation_id = ?
            AND edited_at IS NOT NULL
            AND edited_at > ?
        """, (conversation_id, since_timestamp))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error in get_updated_messages_since: {e}")
        return []