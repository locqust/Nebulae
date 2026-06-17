-- Migration 009: Add user shortcuts (favourites) feature
-- Creates the user_shortcuts table for storing sidebar shortcut items.
-- Supports users and groups (events excluded by design).

CREATE TABLE IF NOT EXISTS user_shortcuts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL CHECK(entity_type IN ('user', 'group')),
    entity_puid TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, entity_type, entity_puid),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_shortcuts_user ON user_shortcuts(user_id);
