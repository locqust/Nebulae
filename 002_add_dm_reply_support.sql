-- Migration: Add Reply Support for Direct Messages
-- Version: 002
-- Description: Adds reply_to_msg_uid column to direct_messages table,
--              enabling users to reply to specific messages in a conversation.
--
-- IMPORTANT: SQLite does not support adding foreign key constraints via
--            ALTER TABLE. The FK relationship is defined in schema.sql for
--            fresh installs only. The column is added here without the FK
--            constraint, which is fine as the relationship is enforced in
--            application logic (Python/Flask).
--
-- Run this migration once against your existing database:
--   sqlite3 your_database.db < 002_add_dm_reply_support.sql

ALTER TABLE direct_messages ADD COLUMN reply_to_msg_uid TEXT;

CREATE INDEX IF NOT EXISTS idx_dm_reply_to ON direct_messages(reply_to_msg_uid);
