# db_queries/push_subscriptions.py
"""
Database queries for managing push notification subscriptions.
"""

from db import get_db
from datetime import datetime

def save_push_subscription(user_id, endpoint, p256dh_key, auth_key, user_agent=None):
    """
    Save or update a push notification subscription for a user.
    
    Args:
        user_id: The ID of the user
        endpoint: The push service endpoint URL
        p256dh_key: The p256dh encryption key
        auth_key: The auth secret
        user_agent: Optional user agent string
    
    Returns:
        True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO push_subscriptions 
            (user_id, endpoint, p256dh_key, auth_key, user_agent, created_at, last_used)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, endpoint) 
            DO UPDATE SET 
                p256dh_key = excluded.p256dh_key,
                auth_key = excluded.auth_key,
                user_agent = excluded.user_agent,
                last_used = excluded.last_used
        """, (user_id, endpoint, p256dh_key, auth_key, user_agent, 
              datetime.utcnow(), datetime.utcnow()))
        
        db.commit()
        return True
    except Exception as e:
        print(f"Error saving push subscription: {e}")
        db.rollback()
        return False

def get_push_subscriptions_for_user(user_id):
    """
    Get all push subscriptions for a specific user.
    
    Args:
        user_id: The ID of the user
    
    Returns:
        List of subscription dictionaries
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT id, endpoint, p256dh_key, auth_key, user_agent, created_at, last_used
        FROM push_subscriptions
        WHERE user_id = ?
        ORDER BY last_used DESC
    """, (user_id,))
    
    return [dict(row) for row in cursor.fetchall()]

def delete_push_subscription(user_id, endpoint):
    """
    Delete a specific push subscription.
    
    Args:
        user_id: The ID of the user
        endpoint: The endpoint to delete
    
    Returns:
        True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM push_subscriptions
            WHERE user_id = ? AND endpoint = ?
        """, (user_id, endpoint))
        
        db.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Error deleting push subscription: {e}")
        db.rollback()
        return False

def update_subscription_last_used(user_id, endpoint):
    """
    Update the last_used timestamp for a subscription.
    
    Args:
        user_id: The ID of the user
        endpoint: The endpoint to update
    
    Returns:
        True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            UPDATE push_subscriptions
            SET last_used = ?
            WHERE user_id = ? AND endpoint = ?
        """, (datetime.utcnow(), user_id, endpoint))
        
        db.commit()
        return True
    except Exception as e:
        print(f"Error updating subscription last_used: {e}")
        db.rollback()
        return False

def cleanup_old_subscriptions(days=90):
    """
    Remove subscriptions that haven't been used in a specified number of days.
    
    Args:
        days: Number of days of inactivity before removal (default: 90)
    
    Returns:
        Number of subscriptions removed
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM push_subscriptions
            WHERE last_used < datetime('now', '-' || ? || ' days')
        """, (days,))
        
        db.commit()
        return cursor.rowcount
    except Exception as e:
        print(f"Error cleaning up old subscriptions: {e}")
        db.rollback()
        return 0