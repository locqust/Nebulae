-- Migration: Add feeling/emotion support to posts table
-- Version: 006

ALTER TABLE posts ADD COLUMN feeling TEXT;

CREATE INDEX IF NOT EXISTS idx_posts_feeling ON posts(feeling);