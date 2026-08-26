-- Migration 011: Add indexes to the core content tables
--
-- The newer features (DMs, polls, parental controls, albums, shortcuts) were
-- all built with indexes. The original tables - posts, comments, users,
-- friends, media - never got any, so every feed load does full table scans.
--
-- The feed query is:
--     SELECT p.cuid FROM posts p
--     WHERE (privacy_setting = 'public')
--        OR (privacy_setting = 'friends'   AND profile_puid IN (...))
--        OR (privacy_setting = 'group'     AND group_id     IN (...))
--        OR (privacy_setting = 'event'     AND event_id     IN (...))
--        OR (privacy_setting = 'followers' AND author_puid  IN (...))
--     ORDER BY p.timestamp DESC LIMIT ? OFFSET ?
--
-- so it wants an index on timestamp for the sort, and one on each column used
-- to scope a privacy tier. The rest cover the per-post lookups that follow.
--
-- NOTE ON WHAT IS *NOT* HERE: SQLite creates an implicit index for every
-- UNIQUE constraint, and a composite index can serve lookups on its leftmost
-- column. So posts(cuid), comments(cuid), users(puid), post_media(muid),
-- friends(user_id_1), group_members(group_id), followers(user_id) and
-- event_attendees(event_id) are ALREADY covered and are deliberately omitted.
-- Duplicating them would slow every write for no read benefit.
--
-- Safe to run repeatedly, and safe on a live database - each CREATE INDEX
-- holds a write lock only while it builds, which at household scale is
-- milliseconds.

-- ---------------------------------------------------------------------------
-- posts: the feed
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_posts_timestamp          ON posts(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_posts_privacy_timestamp  ON posts(privacy_setting, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_posts_profile_puid       ON posts(profile_puid);
CREATE INDEX IF NOT EXISTS idx_posts_author_puid        ON posts(author_puid);
CREATE INDEX IF NOT EXISTS idx_posts_group_id           ON posts(group_id);
CREATE INDEX IF NOT EXISTS idx_posts_event_id           ON posts(event_id);
CREATE INDEX IF NOT EXISTS idx_posts_user_id            ON posts(user_id);
CREATE INDEX IF NOT EXISTS idx_posts_profile_user_id    ON posts(profile_user_id);
CREATE INDEX IF NOT EXISTS idx_posts_original_cuid      ON posts(original_post_cuid);

-- ---------------------------------------------------------------------------
-- comments: fetched per post, so the cost multiplies by page size
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_comments_post_id         ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_comments_parent          ON comments(parent_comment_id);
CREATE INDEX IF NOT EXISTS idx_comments_user_id         ON comments(user_id);

-- ---------------------------------------------------------------------------
-- media attached to posts and comments
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_post_media_post_id       ON post_media(post_id);
CREATE INDEX IF NOT EXISTS idx_comment_media_comment_id ON comment_media(comment_id);

-- ---------------------------------------------------------------------------
-- users
-- puid and username are already covered by UNIQUE constraints. hostname is the
-- SECOND column of UNIQUE(username, hostname), so it needs its own index - it
-- is used to separate local from remote users throughout the codebase.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_users_hostname           ON users(hostname);
CREATE INDEX IF NOT EXISTS idx_users_user_type          ON users(user_type);

-- ---------------------------------------------------------------------------
-- relationships consulted on every feed build.
-- In each case the FIRST column of the UNIQUE constraint is already indexed;
-- these cover lookups by the SECOND column, which is the direction the
-- friendship / membership queries actually go in.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_friends_user_2           ON friends(user_id_2);
CREATE INDEX IF NOT EXISTS idx_group_members_user       ON group_members(user_id);
CREATE INDEX IF NOT EXISTS idx_event_attendees_puid     ON event_attendees(user_puid);
CREATE INDEX IF NOT EXISTS idx_followers_page           ON followers(page_id);

-- ---------------------------------------------------------------------------
-- notifications: polled every few seconds by every open browser tab
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_notifications_user_read  ON notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_timestamp  ON notifications(timestamp DESC);
