# db_queries/shortcuts.py
# Database query functions for the user shortcuts (favourites) feature.

from flask import g
from db import get_db

MAX_SHORTCUTS = 15


def get_user_shortcuts(user_id):
    """
    Returns all shortcuts for a user, with resolved display names,
    profile picture paths, and entity type.

    Returns a dict with two lists:
        {
            'users':  [{'puid', 'display_name', 'profile_picture_path', 'hostname'}, ...],
            'groups': [{'puid', 'display_name', 'profile_picture_path', 'hostname'}, ...],
        }
    Ordered by created_at ASC (oldest shortcut first — stable order).
    """
    db = get_db()
    cursor = db.cursor()

    result = {'users': [], 'groups': []}

    # ── User shortcuts (includes public_pages — both are in the users table) ──
    cursor.execute("""
        SELECT
            u.puid,
            u.display_name,
            u.profile_picture_path,
            u.hostname,
            u.user_type
        FROM user_shortcuts s
        JOIN users u ON u.puid = s.entity_puid
        WHERE s.user_id = ? AND s.entity_type = 'user'
        ORDER BY s.created_at ASC
    """, (user_id,))
    result['users'] = [dict(row) for row in cursor.fetchall()]

    # ── Group shortcuts ──
    cursor.execute("""
        SELECT
            g.puid,
            g.name AS display_name,
            g.profile_picture_path,
            g.hostname
        FROM user_shortcuts s
        JOIN groups g ON g.puid = s.entity_puid
        WHERE s.user_id = ? AND s.entity_type = 'group'
        ORDER BY s.created_at ASC
    """, (user_id,))
    result['groups'] = [dict(row) for row in cursor.fetchall()]

    return result


def get_shortcut_count(user_id):
    """Returns the total number of shortcuts for a user."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM user_shortcuts WHERE user_id = ?", (user_id,)
    )
    return cursor.fetchone()[0]


def is_shortcutted(user_id, entity_type, entity_puid):
    """Returns True if the given entity is already in the user's shortcuts."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """SELECT 1 FROM user_shortcuts
           WHERE user_id = ? AND entity_type = ? AND entity_puid = ?""",
        (user_id, entity_type, entity_puid)
    )
    return cursor.fetchone() is not None


def add_shortcut(user_id, entity_type, entity_puid):
    """
    Adds a shortcut. Returns (True, None) on success,
    (False, reason_string) on failure.
    """
    if entity_type not in ('user', 'group'):
        return False, 'Invalid entity type.'

    count = get_shortcut_count(user_id)
    if count >= MAX_SHORTCUTS:
        return False, f'You can have a maximum of {MAX_SHORTCUTS} shortcuts. Remove one first.'

    db = get_db()
    try:
        db.execute(
            """INSERT OR IGNORE INTO user_shortcuts (user_id, entity_type, entity_puid)
               VALUES (?, ?, ?)""",
            (user_id, entity_type, entity_puid)
        )
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        print(f"Error in add_shortcut: {e}")
        return False, 'Database error.'


def remove_shortcut(user_id, entity_type, entity_puid):
    """
    Removes a shortcut. Returns True on success, False on failure.
    """
    db = get_db()
    try:
        db.execute(
            """DELETE FROM user_shortcuts
               WHERE user_id = ? AND entity_type = ? AND entity_puid = ?""",
            (user_id, entity_type, entity_puid)
        )
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Error in remove_shortcut: {e}")
        return False
