-- schema.sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    puid TEXT UNIQUE NOT NULL, -- Public User ID (e.g., a UUID or random string)
    username TEXT NOT NULL, -- For local users, this is unique on this node. For remote, it's their username on their node.
    password TEXT, -- Can be NULL for remote users as they can't log in here.
    email TEXT, -- NEW: Optional email address, primarily for the admin user
    display_name TEXT,
    media_path TEXT,
    uploads_path TEXT,
    profile_picture_path TEXT,
    original_profile_picture_path TEXT,
    user_type TEXT NOT NULL DEFAULT 'user', -- 'user', 'admin', 'remote', 'public_page'
    password_must_change BOOLEAN DEFAULT FALSE, -- Force password change on next login
    requires_parental_approval BOOLEAN DEFAULT FALSE,
    hostname TEXT, -- NULL for local users, stores the origin hostname for remote users.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(username, hostname) -- A user from a specific node is unique.
);

-- NEW: Table for user sessions
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_id TEXT UNIQUE NOT NULL,
    user_agent TEXT,
    ip_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- NEW: Table for user sessions
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_id TEXT UNIQUE NOT NULL,
    user_agent TEXT,
    ip_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- NEW: Table for two-factor authentication
CREATE TABLE IF NOT EXISTS user_2fa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    secret TEXT NOT NULL,
    backup_codes TEXT, -- JSON array of hashed backup codes
    enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_2fa_user ON user_2fa(user_id);

-- EVENT TABLES START
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    puid TEXT UNIQUE NOT NULL,
    created_by_user_puid TEXT NOT NULL, -- PUID of the user/page who created the event
    source_puid TEXT, -- PUID of the group or page if it's a group/page event
    source_type TEXT NOT NULL, -- 'user', 'group', 'public_page'
    title TEXT NOT NULL,
    event_datetime DATETIME NOT NULL,
	event_end_datetime DATETIME, -- NEW: Add event end time
    location TEXT,
    details TEXT,
    is_public BOOLEAN DEFAULT FALSE, -- Only for 'public_page' source_type events
	is_cancelled BOOLEAN DEFAULT FALSE, -- NEW: Flag to indicate if the event is cancelled
	hostname TEXT, -- FEDERATION: The hostname where the event originated
    is_remote BOOLEAN DEFAULT FALSE, -- FEDERATION: Flag if this is a stub for a remote event
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS event_attendees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    user_puid TEXT NOT NULL,
    response TEXT NOT NULL DEFAULT 'invited', -- 'invited', 'attending', 'tentative', 'declined'
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, user_puid),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);
-- EVENT TABLES END

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cuid TEXT UNIQUE NOT NULL, -- Content Unique ID
    user_id INTEGER, -- The local user ID who created the post (can be NULL for remote posts)
    profile_user_id INTEGER, -- The local user ID of the profile timeline (can be NULL for group posts)
    group_id INTEGER, -- The ID of the group this post belongs to
	event_id INTEGER, -- The ID of the event this post belongs to
    author_puid TEXT NOT NULL, -- The PUID of the user who created the post (for federation)
    profile_puid TEXT, -- The PUID of the profile timeline the post appears on (can be NULL for group posts)
    content TEXT, -- Can be NULL for reposts
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    privacy_setting TEXT NOT NULL DEFAULT 'local', -- 'local', 'public', 'friends', 'group'
    nu_id TEXT, -- The NUID of the node where the post originated
    is_remote BOOLEAN DEFAULT FALSE, -- Flag to indicate if the post is from a remote node
    is_repost BOOLEAN DEFAULT FALSE, -- NEW: Flag to indicate if this is a repost
    original_post_cuid TEXT, -- NEW: The CUID of the post being reposted
    comments_disabled BOOLEAN DEFAULT FALSE NOT NULL, -- NEW: Ability to turn off comments
    tagged_user_puids TEXT, -- NEW: JSON array of PUIDs for users tagged in the post
    location TEXT, -- NEW: Location string for check-ins
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (profile_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
	FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE -- Link to events
);

CREATE TABLE IF NOT EXISTS post_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    muid TEXT UNIQUE NOT NULL, -- Media Unique ID
    post_id INTEGER NOT NULL,
    media_file_path TEXT NOT NULL, -- Path to the media file within the user's media_path
    alt_text TEXT, -- Alt text for the media file
    origin_hostname TEXT, -- The hostname where the media file is stored (for federation)
    tagged_user_puids TEXT, -- NEW: JSON array of PUIDs for users tagged in this media item
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
);

-- Table for media albums
CREATE TABLE IF NOT EXISTS media_albums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    album_uid TEXT UNIQUE NOT NULL, -- Album Unique ID
    owner_puid TEXT NOT NULL, -- PUID of the user who created the album
    group_puid TEXT, -- PUID of the group if this is a group album (NULL for user albums)
    title TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_puid) REFERENCES users(puid) ON DELETE CASCADE
);

-- Junction table for album media
CREATE TABLE IF NOT EXISTS album_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id INTEGER NOT NULL,
    media_id INTEGER NOT NULL, -- References post_media.id
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    display_order INTEGER DEFAULT 0, -- For custom ordering within album
    UNIQUE(album_id, media_id),
    FOREIGN KEY (album_id) REFERENCES media_albums(id) ON DELETE CASCADE,
    FOREIGN KEY (media_id) REFERENCES post_media(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_album_media_album ON album_media(album_id);
CREATE INDEX IF NOT EXISTS idx_album_media_media ON album_media(media_id);
CREATE INDEX IF NOT EXISTS idx_media_albums_owner ON media_albums(owner_puid);
CREATE INDEX IF NOT EXISTS idx_media_albums_group ON media_albums(group_puid);

-- NEW: Table for URL link previews
CREATE TABLE IF NOT EXISTS link_previews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL, -- The normalized URL
    title TEXT,
    description TEXT,
    image_url TEXT,
    site_name TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_valid BOOLEAN DEFAULT TRUE -- FALSE if preview fetch failed
);

-- Junction table for posts and their link previews
CREATE TABLE IF NOT EXISTS post_link_previews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    link_preview_id INTEGER NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0, -- For multiple links in one post
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (link_preview_id) REFERENCES link_previews(id) ON DELETE CASCADE,
    UNIQUE(post_id, link_preview_id)
);

-- Junction table for comments and their link previews
CREATE TABLE IF NOT EXISTS comment_link_previews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comment_id INTEGER NOT NULL,
    link_preview_id INTEGER NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (comment_id) REFERENCES comments(id) ON DELETE CASCADE,
    FOREIGN KEY (link_preview_id) REFERENCES link_previews(id) ON DELETE CASCADE,
    UNIQUE(comment_id, link_preview_id)
);

-- NEW: Table for polls
CREATE TABLE IF NOT EXISTS polls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL UNIQUE,
    allow_multiple_answers BOOLEAN DEFAULT FALSE,
    allow_add_options BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
);

-- NEW: Table for poll options
CREATE TABLE IF NOT EXISTS poll_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id INTEGER NOT NULL,
    option_text TEXT NOT NULL,
    display_order INTEGER NOT NULL,
    created_by_user_id INTEGER, -- NULL if created by poll creator, otherwise the user who added it
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- NEW: Table for poll votes
CREATE TABLE IF NOT EXISTS poll_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_option_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(poll_option_id, user_id), -- User can only vote once per option
    FOREIGN KEY (poll_option_id) REFERENCES poll_options(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_poll_votes_user ON poll_votes(user_id);
CREATE INDEX IF NOT EXISTS idx_poll_votes_option ON poll_votes(poll_option_id);

CREATE TABLE IF NOT EXISTS user_profile_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    field_value TEXT,
    privacy_public INTEGER DEFAULT 0,
    privacy_local INTEGER DEFAULT 0,
    privacy_friends INTEGER DEFAULT 0,
    UNIQUE(user_id, field_name),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- NEW: Table for family relationships
CREATE TABLE IF NOT EXISTS family_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    relative_user_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,
    anniversary_date DATE,
    privacy_public INTEGER DEFAULT 0,
    privacy_local INTEGER DEFAULT 0,
    privacy_friends INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, relative_user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (relative_user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- NEW: Table for parental controls (separate from general family relationships)
CREATE TABLE IF NOT EXISTS parental_controls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_user_id INTEGER NOT NULL,
    parent_user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(child_user_id, parent_user_id), -- Each parent-child pair is unique, but child can have multiple parents
    FOREIGN KEY (child_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_parental_controls_child ON parental_controls(child_user_id);
CREATE INDEX IF NOT EXISTS idx_parental_controls_parent ON parental_controls(parent_user_id);

-- NEW: Table for pending parental approvals
CREATE TABLE IF NOT EXISTS parental_approval_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_user_id INTEGER NOT NULL,
    approval_type TEXT NOT NULL, -- 'friend_request_out', 'group_join', event_invite', 'media_tag'
    target_puid TEXT NOT NULL, -- PUID of the friend/group/event/media being requested
    target_hostname TEXT, -- Hostname if remote, NULL if local
    request_data TEXT, -- JSON data about the request
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'approved', 'denied'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by_user_id INTEGER,
    FOREIGN KEY (child_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (resolved_by_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_parental_queue_child ON parental_approval_queue(child_user_id);
CREATE INDEX IF NOT EXISTS idx_parental_queue_status ON parental_approval_queue(status);

CREATE TABLE IF NOT EXISTS friend_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    status TEXT DEFAULT 'pending' NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sender_id, receiver_id),
    FOREIGN KEY (sender_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (receiver_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS friends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id_1 INTEGER NOT NULL,
    user_id_2 INTEGER NOT NULL,
    established_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id_1, user_id_2),
    CHECK (user_id_1 < user_id_2),
    FOREIGN KEY (user_id_1) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id_2) REFERENCES users (id) ON DELETE CASCADE
);

-- Table for managing friend states like snooze and block
CREATE TABLE IF NOT EXISTS friend_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, -- The user performing the action
    friend_id INTEGER NOT NULL, -- The user being actioned upon
    is_blocked BOOLEAN DEFAULT FALSE,
    snooze_until DATETIME,
    blocked_at DATETIME, -- NEW: To store the timestamp of when the block was initiated
    UNIQUE(user_id, friend_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (friend_id) REFERENCES users(id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cuid TEXT UNIQUE NOT NULL, -- Content Unique ID
    post_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    parent_comment_id INTEGER,
    nu_id TEXT, -- The NUID of the node where the comment originated
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_comment_id) REFERENCES comments(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS comment_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    muid TEXT UNIQUE NOT NULL, -- Media Unique ID
    comment_id INTEGER NOT NULL,
    media_file_path TEXT NOT NULL,
    alt_text TEXT,
    FOREIGN KEY (comment_id) REFERENCES comments (id) ON DELETE CASCADE
);

-- NEW: Table for page followers
CREATE TABLE IF NOT EXISTS followers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL, -- The user doing the following
    page_id INTEGER NOT NULL, -- The public page being followed
    followed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, page_id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (page_id) REFERENCES users (id) ON DELETE CASCADE
);

-- NEW: Table for hiding items from discovery lists
CREATE TABLE IF NOT EXISTS hidden_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    item_type TEXT NOT NULL CHECK(item_type IN ('user', 'group', 'page')),
    item_id INTEGER NOT NULL,
    hidden_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, item_type, item_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_hidden_items_user_type ON hidden_items(user_id, item_type);

-- NEW: Table for hidden posts and comments
CREATE TABLE IF NOT EXISTS hidden_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    content_type TEXT NOT NULL CHECK(content_type IN ('post', 'comment', 'media_comment')),
    content_id INTEGER NOT NULL, -- post.id, comment.id, or media_comments.id
    hidden_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, content_type, content_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_hidden_content_user_type ON hidden_content(user_id, content_type);

-- NEW: Table for notifications
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,          -- The user receiving the notification
    actor_id INTEGER NOT NULL,         -- The user who performed the action
    type TEXT NOT NULL,                -- 'mention', 'comment', 'reply', 'wall_post', 'friend_request', 'friend_accept', 'birthday', 'group_request_accepted', 'group_request_rejected', 'group_post', 'group_invite', 'repost', 'page_post', 'tagged_in_post', 'parental_approval_needed', 'parental_approval_approved', 'parental_approval_denied'
    post_id INTEGER,                   -- The post the notification relates to (can be NULL)
    comment_id INTEGER,                -- The specific comment/reply if applicable
    group_id INTEGER,                  -- The group the notification relates to (can be NULL)
	event_id INTEGER,                  -- The event the notification relates to (for invites)
    media_id INTEGER,                  -- NEW: The media item (post_media.id) the notification relates to
    media_comment_id INTEGER,          -- NEW: The specific media comment if applicable
    is_read BOOLEAN DEFAULT FALSE,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (comment_id) REFERENCES comments(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
	FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    FOREIGN KEY (media_id) REFERENCES post_media(id) ON DELETE CASCADE,
    FOREIGN KEY (media_comment_id) REFERENCES media_comments(id) ON DELETE CASCADE
);

-- NEW: Table for push notification subscriptions
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    endpoint TEXT NOT NULL,
    p256dh_key TEXT NOT NULL,
    auth_key TEXT NOT NULL,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, endpoint),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user ON push_subscriptions(user_id);

-- NEW: Table for application state
CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- FEDERATION: Table for managing connections to other nodes
CREATE TABLE IF NOT EXISTS connected_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hostname TEXT NOT NULL, -- e.g., friends-node.example.com
    nickname TEXT, -- A user-friendly name for the node
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'connected', 'blocked'
    shared_secret TEXT, -- A long, secure key for signing API requests
    origin_nu_id TEXT, -- The NUID of the remote node
    connection_type TEXT NOT NULL DEFAULT 'full', -- 'full' (admin-created), 'targeted' (auto-created for specific resources)
    resource_type TEXT, -- 'group', 'public_page' (only for targeted connections)
    resource_puid TEXT, -- PUID of the specific group or page (only for targeted connections)
    resource_name TEXT, -- Display name of the resource for admin UI
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(hostname, connection_type, resource_puid) -- Allow one full connection and multiple targeted ones per hostname
);

-- FEDERATION: Table for one-time pairing tokens
CREATE TABLE IF NOT EXISTS pairing_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT UNIQUE NOT NULL,
    created_by_user_id INTEGER NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Node Configuration Table
CREATE TABLE IF NOT EXISTS node_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- NEW: Tables for Groups feature
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    puid TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    profile_picture_path TEXT,
    original_profile_picture_path TEXT,
    picture_admin_puid TEXT, -- PUID of the admin who uploaded the picture
    created_by_user_id INTEGER NOT NULL,
    initial_admin_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    hostname TEXT, -- FEDERATION FIX: Stores the origin hostname for remote groups
    is_remote BOOLEAN DEFAULT FALSE, -- FEDERATION FIX: Flag to indicate if the group is from a remote node
    join_rules TEXT, -- NEW: Rules text that users must agree to
    join_questions TEXT, -- NEW: JSON array of questions
    FOREIGN KEY (created_by_user_id) REFERENCES users(id),
    FOREIGN KEY (initial_admin_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'member', -- 'member', 'moderator', 'admin'
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_banned BOOLEAN DEFAULT FALSE,
    snooze_until DATETIME,
    UNIQUE(group_id, user_id),
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS group_join_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'accepted', 'rejected'
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_id, user_id),
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- NEW: Table for storing additional, privacy-controlled group info
CREATE TABLE IF NOT EXISTS group_profile_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    field_name TEXT NOT NULL, -- e.g., 'website', 'email', 'about', 'show_admins'
    field_value TEXT,
    privacy_public INTEGER DEFAULT 0, -- 1 for true, 0 for false
    privacy_members_only INTEGER DEFAULT 1, -- 1 for true, 0 for false
    UNIQUE(group_id, field_name),
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
);

-- Create table for storing join request responses
CREATE TABLE IF NOT EXISTS group_join_request_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    rules_agreed BOOLEAN DEFAULT FALSE,
    question_responses TEXT, -- JSON object with question:answer pairs
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (request_id) REFERENCES group_join_requests(id) ON DELETE CASCADE,
    UNIQUE(request_id)
);

-- NEW: Table for user-specific settings
CREATE TABLE IF NOT EXISTS user_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    setting_key TEXT NOT NULL,
    setting_value TEXT NOT NULL,
    UNIQUE(user_id, setting_key),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- NEW: Table for comments on individual media items
CREATE TABLE IF NOT EXISTS media_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cuid TEXT UNIQUE NOT NULL, -- Content Unique ID
    media_id INTEGER NOT NULL, -- References post_media.id
    user_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    parent_comment_id INTEGER, -- For nested replies
    nu_id TEXT, -- The NUID of the node where the comment originated
    FOREIGN KEY (media_id) REFERENCES post_media(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_comment_id) REFERENCES media_comments(id) ON DELETE CASCADE
);

-- NEW: Table for media attachments on media comments
CREATE TABLE IF NOT EXISTS media_comment_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    muid TEXT UNIQUE NOT NULL, -- Media Unique ID
    media_comment_id INTEGER NOT NULL,
    media_file_path TEXT NOT NULL,
    alt_text TEXT,
    origin_hostname TEXT, -- The hostname where the media file is stored (for federation)
    FOREIGN KEY (media_comment_id) REFERENCES media_comments(id) ON DELETE CASCADE
);