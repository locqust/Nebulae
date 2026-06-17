-- Migration 008: Add cover picture support for events and groups
-- Safe to run multiple times — duplicate column errors are handled by
-- the _run_sql_migrations runner in db.py.

ALTER TABLE events ADD COLUMN cover_picture_path TEXT;
ALTER TABLE groups ADD COLUMN cover_picture_path TEXT;
