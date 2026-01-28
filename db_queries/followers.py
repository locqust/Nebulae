# db_queries/followers.py
# Contains functions for managing follow relationships for public pages.

from db import get_db
import sqlite3
# NEW: Import get_user_by_id to fetch user objects
from .users import get_user_by_id

def follow_page(user_id, page_id):
    """
    Adds a follow relationship between a user and a public page.
    NEW: Also invites the user to future non-public events created by the page.
    """
    # NEW: Local import to avoid circular dependency
    from .events import invite_user_to_source_future_events

    db = get_db()
    cursor = db.cursor() # Use cursor for INSERT OR IGNORE check
    try:
        # Check if already following before attempting insert
        cursor.execute("SELECT 1 FROM followers WHERE user_id = ? AND page_id = ?", (user_id, page_id))
        already_following = cursor.fetchone()

        if already_following:
            return True # No need to do anything if already following

        # Proceed with inserting the follow relationship
        cursor.execute("INSERT INTO followers (user_id, page_id) VALUES (?, ?)",
                       (user_id, page_id))
        rows_affected = cursor.rowcount
        db.commit()

        # If the follow was successfully added (not ignored)...
        if rows_affected > 0:
            # Fetch the user and page objects to pass to the event invitation helper
            user = get_user_by_id(user_id)
            page = get_user_by_id(page_id)
            if user and page and page.get('puid'):
                # Invite the new follower to relevant future events
                invite_user_to_source_future_events(user, 'public_page', page['puid'])
            else:
                print(f"Warning: Could not fetch user ({user_id}) or page ({page_id}) after following, skipping event invites.")

        return True # Return True even if event invites failed, as the follow succeeded
    except sqlite3.Error as e:
        print(f"Database error in follow_page: {e}")
        db.rollback()
        return False

def unfollow_page(user_id, page_id):
    """Removes a follow relationship between a user and a public page."""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM followers WHERE user_id = ? AND page_id = ?",
                       (user_id, page_id))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Database error in unfollow_page: {e}")
        db.rollback()
        return False

def is_following(user_id, page_id):
    """Checks if a user is following a specific public page."""
    if not user_id or not page_id:
        return False
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT 1 FROM followers WHERE user_id = ? AND page_id = ?",
                   (user_id, page_id))
    return cursor.fetchone() is not None

def get_followers(page_id):
    """Gets a list of all users following a specific public page."""
    db = get_db()
    cursor = db.cursor()
    # Note: Joins with the users table to get follower details
    cursor.execute("""
        SELECT u.id, u.puid, u.username, u.display_name, u.profile_picture_path, u.hostname
        FROM users u
        JOIN followers f ON u.id = f.user_id
        WHERE f.page_id = ?
        ORDER BY u.display_name
    """, (page_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def get_following_pages(user_id):
    """Gets a list of all public pages a user is following."""
    db = get_db()
    cursor = db.cursor()
    # Note: Joins with the users table to get page details
    cursor.execute("""
        SELECT u.id, u.puid, u.username, u.display_name, u.profile_picture_path, u.hostname
        FROM users u
        JOIN followers f ON u.id = f.page_id
        WHERE f.user_id = ?
        ORDER BY u.display_name
    """, (user_id,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]
