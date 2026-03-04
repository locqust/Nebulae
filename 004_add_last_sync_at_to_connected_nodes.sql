-- Migration: Add last_sync_at to connected_nodes for federation recovery tracking
-- Version: 004

ALTER TABLE connected_nodes ADD COLUMN last_sync_at TIMESTAMP;