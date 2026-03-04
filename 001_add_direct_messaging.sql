-- Migration: Add Direct Messaging Tables
-- Version: 001
-- Date: 2025-02-16
-- Description: Adds support for direct messaging with multi-participant conversations,
--              message requests, blocking, and federation support.
-- 
-- IMPORTANT: This migration is idempotent and safe to run multiple times.
--            All tables use "CREATE TABLE IF NOT EXISTS" to prevent errors if already applied.

-- =============================================================================
-- CONVERSATIONS TABLE
-- =============================================================================
-- Stores conversation metadata (not individual messages)
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conv_uid TEXT UNIQUE NOT NULL,  -- Conversation Unique ID (like PUID for users)
    created_by_user_id INTEGER NOT NULL,  -- User who initiated the conversation
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- For sorting conversations
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_conversations_conv_uid ON conversations(conv_uid);
CREATE INDEX IF NOT EXISTS idx_conversations_last_message ON conversations(last_message_at DESC);

-- =============================================================================
-- CONVERSATION PARTICIPANTS TABLE
-- =============================================================================
-- Junction table linking users to conversations (supports multi-participant)
CREATE TABLE IF NOT EXISTS conversation_participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_read_at TIMESTAMP,  -- Track read status per participant
    is_archived BOOLEAN DEFAULT FALSE,  -- User can archive conversations
    UNIQUE(conversation_id, user_id),  -- User can only be in a conversation once
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_conv_participants_user ON conversation_participants(user_id);
CREATE INDEX IF NOT EXISTS idx_conv_participants_conversation ON conversation_participants(conversation_id);

-- =============================================================================
-- DIRECT MESSAGES TABLE
-- =============================================================================
-- Individual messages within conversations
CREATE TABLE IF NOT EXISTS direct_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_uid TEXT UNIQUE NOT NULL,  -- Message Unique ID
    conversation_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    edited_at TIMESTAMP,  -- Track if message was edited
    is_deleted BOOLEAN DEFAULT FALSE,  -- Soft delete for message history
    nu_id TEXT,  -- Node Unique ID - for federation tracking
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_dm_msg_uid ON direct_messages(msg_uid);
CREATE INDEX IF NOT EXISTS idx_dm_conversation ON direct_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_dm_sender ON direct_messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_dm_sent_at ON direct_messages(sent_at DESC);

-- =============================================================================
-- DIRECT MESSAGE MEDIA TABLE
-- =============================================================================
-- Media attachments for direct messages
CREATE TABLE IF NOT EXISTS direct_message_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    muid TEXT UNIQUE NOT NULL,  -- Media Unique ID
    message_id INTEGER NOT NULL,
    media_file_path TEXT NOT NULL,
    alt_text TEXT,
    origin_hostname TEXT,  -- For federation - where the media is stored
    FOREIGN KEY (message_id) REFERENCES direct_messages(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_dm_media_message ON direct_message_media(message_id);
CREATE INDEX IF NOT EXISTS idx_dm_media_muid ON direct_message_media(muid);

-- =============================================================================
-- MESSAGE REQUESTS TABLE
-- =============================================================================
-- Handles message requests from non-friends to prevent spam
CREATE TABLE IF NOT EXISTS dm_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    requester_id INTEGER NOT NULL,  -- User who wants to message
    recipient_id INTEGER NOT NULL,  -- User who needs to accept
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'accepted', 'declined'
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP,
    UNIQUE(conversation_id, recipient_id),  -- One request per recipient per conversation
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (requester_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (recipient_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_dm_requests_recipient ON dm_requests(recipient_id);
CREATE INDEX IF NOT EXISTS idx_dm_requests_status ON dm_requests(status);
CREATE INDEX IF NOT EXISTS idx_dm_requests_conversation ON dm_requests(conversation_id);

-- =============================================================================
-- DM BLOCKS TABLE
-- =============================================================================
-- User-level blocking for direct messages (separate from friend blocking)
CREATE TABLE IF NOT EXISTS dm_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    blocker_id INTEGER NOT NULL,  -- User doing the blocking
    blocked_id INTEGER NOT NULL,  -- User being blocked
    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(blocker_id, blocked_id),  -- Can only block a user once
    FOREIGN KEY (blocker_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (blocked_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_dm_blocks_blocker ON dm_blocks(blocker_id);
CREATE INDEX IF NOT EXISTS idx_dm_blocks_blocked ON dm_blocks(blocked_id);

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================
-- All direct messaging tables have been created successfully.
-- The system will now support:
-- - Multi-participant conversations
-- - Message requests for non-friends
-- - Blocking users from sending messages
-- - Media attachments in messages
-- - Federation support via nu_id tracking
