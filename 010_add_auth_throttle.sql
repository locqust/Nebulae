-- Migration: Add auth throttling to slow down online password / 2FA guessing
-- Version: 010
--
-- Deliberately NOT an account lockout. Each row is a single failed attempt;
-- utils/throttle.py counts recent rows and imposes an escalating cooldown that
-- always expires on its own. A lockout would hand anyone who knows a user's
-- email a denial-of-service button, which on a household node means the admin
-- gets woken up rather than an attacker getting stopped.
--
-- Safe to run multiple times.

CREATE TABLE IF NOT EXISTS auth_throttle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,          -- 'login' | 'twofa' | 'reset'
    identifier TEXT NOT NULL,     -- lowercased username / email, or 'ip:x.x.x.x'
    failed_at INTEGER NOT NULL    -- unix timestamp
);

CREATE INDEX IF NOT EXISTS idx_auth_throttle_lookup
    ON auth_throttle(scope, identifier, failed_at);

CREATE INDEX IF NOT EXISTS idx_auth_throttle_cleanup
    ON auth_throttle(failed_at);
