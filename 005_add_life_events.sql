-- Migration: Add Life Events support to posts table
-- Version: 005

ALTER TABLE posts ADD COLUMN post_type TEXT NOT NULL DEFAULT 'normal';
ALTER TABLE posts ADD COLUMN life_event_type TEXT;
ALTER TABLE posts ADD COLUMN life_event_date DATE;

CREATE INDEX IF NOT EXISTS idx_posts_post_type ON posts(post_type);
CREATE INDEX IF NOT EXISTS idx_posts_life_event_type ON posts(life_event_type);
CREATE INDEX IF NOT EXISTS idx_posts_life_event_date ON posts(life_event_date);