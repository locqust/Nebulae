-- Migration: Add Federation Outbox for catch-up/recovery after node downtime
-- Version: 003

CREATE TABLE IF NOT EXISTS federation_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_hostname TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT 'POST',
    payload TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_federation_outbox_hostname_time 
    ON federation_outbox(target_hostname, created_at);