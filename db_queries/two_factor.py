# db_queries/two_factor.py
import json
import secrets
from db import get_db
from utils.auth import hash_password, check_password

def get_2fa_settings(user_id):
    """Get 2FA settings for a user."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, user_id, secret, backup_codes, enabled, created_at, last_used
        FROM user_2fa WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    return dict(row) if row else None

def create_2fa_secret(user_id, secret):
    """Create a new 2FA secret for a user (not enabled yet)."""
    db = get_db()
    cursor = db.cursor()
    
    # Generate 10 backup codes
    backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
    hashed_codes = json.dumps([hash_password(code) for code in backup_codes])
    
    cursor.execute("""
        INSERT OR REPLACE INTO user_2fa (user_id, secret, backup_codes, enabled)
        VALUES (?, ?, ?, FALSE)
    """, (user_id, secret, hashed_codes))
    db.commit()
    
    return backup_codes  # Return unhashed codes to show user once

def enable_2fa(user_id):
    """Enable 2FA after successful verification."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE user_2fa SET enabled = TRUE WHERE user_id = ?
    """, (user_id,))
    db.commit()
    return cursor.rowcount > 0

def disable_2fa(user_id):
    """Disable 2FA for a user."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM user_2fa WHERE user_id = ?", (user_id,))
    db.commit()
    return cursor.rowcount > 0

def update_2fa_last_used(user_id):
    """Update the last used timestamp for 2FA."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE user_2fa SET last_used = CURRENT_TIMESTAMP WHERE user_id = ?
    """, (user_id,))
    db.commit()

def verify_backup_code(user_id, code):
    """Verify and consume a backup code."""
    settings = get_2fa_settings(user_id)
    if not settings or not settings['backup_codes']:
        return False
    
    backup_codes = json.loads(settings['backup_codes'])
    
    # Check if code matches any backup code
    for i, hashed_code in enumerate(backup_codes):
        if check_password(hashed_code, code):
            # Remove used code
            backup_codes.pop(i)
            
            db = get_db()
            cursor = db.cursor()
            cursor.execute("""
                UPDATE user_2fa SET backup_codes = ? WHERE user_id = ?
            """, (json.dumps(backup_codes), user_id))
            db.commit()
            
            update_2fa_last_used(user_id)
            return True
    
    return False

def regenerate_backup_codes(user_id):
    """Generate new backup codes for a user."""
    settings = get_2fa_settings(user_id)
    if not settings:
        return None
    
    # Generate 10 new backup codes
    backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
    hashed_codes = json.dumps([hash_password(code) for code in backup_codes])
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE user_2fa SET backup_codes = ? WHERE user_id = ?
    """, (hashed_codes, user_id))
    db.commit()
    
    return backup_codes  # Return unhashed codes to show user once