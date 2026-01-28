# db_queries/settings.py
# Contains functions for managing user-specific settings.

import sqlite3
from db import get_db

def get_user_settings(user_id):
    """
    Retrieves all settings for a given user.
    Returns a dictionary of setting_key: setting_value pairs.
    Provides default values for any settings not found in the database.
    """
    db = get_db()
    cursor = db.cursor()
    
    # Define default settings
    settings = {
        'text_size': '100', # Default text size is 100%
        'timezone': 'auto',
        'theme': 'light',
        # NEW: Email notification settings with defaults
        'user_email_address': '',
        'email_notifications_enabled': 'False',
        'email_on_friend_request': 'False',
        'email_on_friend_accept': 'False',
        'email_on_wall_post': 'False',
        'email_on_mention': 'False',
        'email_on_event_invite': 'False',
        'email_on_event_update': 'False',
        'email_on_post_tag': 'False',
        'email_on_media_tag': 'False',
        'email_on_media_mention': 'False',
        'email_on_parental_approval': 'True'
    }
    
    if not user_id:
        return settings

    cursor.execute("SELECT setting_key, setting_value FROM user_settings WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    
    # Override defaults with any settings found in the database
    for row in rows:
        if row['setting_key'] in settings:
            settings[row['setting_key']] = row['setting_value']
        
    return settings

def update_user_setting(user_id, setting_key, setting_value):
    """
    Updates or inserts a specific setting for a user.
    """
    if not user_id or not setting_key:
        return False
        
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO user_settings (user_id, setting_key, setting_value)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, setting_key) DO UPDATE SET
            setting_value=excluded.setting_value
        """, (user_id, setting_key, setting_value))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Database error in update_user_setting: {e}")
        db.rollback()
        return False

