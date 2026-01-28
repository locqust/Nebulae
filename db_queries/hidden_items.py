# db_queries/hidden_items.py
"""
Database queries for managing hidden items in discovery lists.
"""
from db import get_db

def hide_item(user_id, item_type, item_id):
    """
    Hide an item (user, group, or page) for a specific user.
    
    Args:
        user_id: The ID of the user hiding the item
        item_type: Type of item ('user', 'group', or 'page')
        item_id: The ID of the item to hide
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO hidden_items (user_id, item_type, item_id)
            VALUES (?, ?, ?)
        """, (user_id, item_type, item_id))
        db.commit()
        return True
    except Exception as e:
        print(f"Error hiding item: {e}")
        return False

def unhide_item(user_id, item_type, item_id):
    """
    Unhide a previously hidden item for a specific user.
    
    Args:
        user_id: The ID of the user unhiding the item
        item_type: Type of item ('user', 'group', or 'page')
        item_id: The ID of the item to unhide
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            DELETE FROM hidden_items
            WHERE user_id = ? AND item_type = ? AND item_id = ?
        """, (user_id, item_type, item_id))
        db.commit()
        return True
    except Exception as e:
        print(f"Error unhiding item: {e}")
        return False

def get_hidden_items(user_id, item_type=None):
    """
    Get all hidden items for a user, optionally filtered by type.
    
    Args:
        user_id: The ID of the user
        item_type: Optional type filter ('user', 'group', or 'page')
    
    Returns:
        set: Set of item IDs that are hidden
    """
    db = get_db()
    cursor = db.cursor()
    
    if item_type:
        cursor.execute("""
            SELECT item_id FROM hidden_items
            WHERE user_id = ? AND item_type = ?
        """, (user_id, item_type))
    else:
        cursor.execute("""
            SELECT item_id FROM hidden_items
            WHERE user_id = ?
        """, (user_id,))
    
    return {row['item_id'] for row in cursor.fetchall()}

def get_hidden_users_with_details(user_id):
    """
    Get detailed information about hidden users and pages for a user.
    
    Args:
        user_id: The ID of the user
    
    Returns:
        list: List of dictionaries containing user/page information
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT u.*, hi.hidden_at
        FROM hidden_items hi
        JOIN users u ON u.id = hi.item_id
        WHERE hi.user_id = ? AND hi.item_type IN ('user', 'page')
        ORDER BY hi.hidden_at DESC
    """, (user_id,))
    
    return [dict(row) for row in cursor.fetchall()]

def get_hidden_groups_with_details(user_id):
    """
    Get detailed information about hidden groups for a user.
    
    Args:
        user_id: The ID of the user
    
    Returns:
        list: List of dictionaries containing group information
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT g.*, hi.hidden_at
        FROM hidden_items hi
        JOIN groups g ON g.id = hi.item_id
        WHERE hi.user_id = ? AND hi.item_type = 'group'
        ORDER BY hi.hidden_at DESC
    """, (user_id,))
    
    return [dict(row) for row in cursor.fetchall()]

def is_item_hidden(user_id, item_type, item_id):
    """
    Check if a specific item is hidden for a user.
    
    Args:
        user_id: The ID of the user
        item_type: Type of item ('user', 'group', or 'page')
        item_id: The ID of the item
    
    Returns:
        bool: True if hidden, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT 1 FROM hidden_items
        WHERE user_id = ? AND item_type = ? AND item_id = ?
    """, (user_id, item_type, item_id))
    
    return cursor.fetchone() is not None