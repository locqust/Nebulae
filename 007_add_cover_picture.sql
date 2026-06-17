-- Migration: Add cover picture support for user profiles
-- Version: 006
-- Description: Adds cover_picture_path column to the users table to support
--              the profile banner/cover photo feature.
--
-- Safe to run multiple times — duplicate column errors are handled by
--  the _run_sql_migrations runner in db.py.

ALTER TABLE users ADD COLUMN cover_picture_path TEXT;
