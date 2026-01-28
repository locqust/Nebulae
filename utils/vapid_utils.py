# utils/vapid_utils.py
"""
Utilities for generating and managing VAPID keys for Web Push notifications.
VAPID (Voluntary Application Server Identification) keys are required for sending push notifications.
"""

from cryptography.hazmat.primitives import serialization

def generate_vapid_keys():
    """
    Generate a new pair of VAPID keys for push notifications.
    Returns a dictionary with 'private_key' and 'public_key' in base64 format.
    
    This function requires the 'py-vapid' package to be installed.
    Install it with: pip install py-vapid
    """
    try:
        from py_vapid import Vapid
        
        vapid = Vapid()
        vapid.generate_keys()
        
        # Get the public key in the correct format for the browser
        # The browser expects uncompressed point format, base64url encoded
        public_key_bytes = vapid.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        
        # Convert to base64url (URL-safe base64 without padding)
        import base64
        public_key_base64 = base64.urlsafe_b64encode(public_key_bytes).decode('utf-8').rstrip('=')
        
        return {
            'private_key': vapid.private_pem().decode('utf-8'),
            'public_key': public_key_base64
        }
    except ImportError:
        raise ImportError(
            "The 'py-vapid' package is required for push notifications. "
            "Install it with: pip install py-vapid"
        )

def get_vapid_keys_from_config():
    """
    Retrieve VAPID keys from the node_config table.
    Returns a dictionary with 'private_key' and 'public_key', or None if not configured.
    """
    from db import get_db
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT value FROM node_config WHERE key = ?", ('vapid_private_key',))
    private_row = cursor.fetchone()
    
    cursor.execute("SELECT value FROM node_config WHERE key = ?", ('vapid_public_key',))
    public_row = cursor.fetchone()
    
    if private_row and public_row:
        return {
            'private_key': private_row['value'],
            'public_key': public_row['value']
        }
    
    return None

def store_vapid_keys_in_config(private_key, public_key):
    """
    Store VAPID keys in the node_config table.
    """
    from db import get_db
    
    db = get_db()
    cursor = db.cursor()
    
    # Store or update private key
    cursor.execute("""
        INSERT INTO node_config (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, ('vapid_private_key', private_key))
    
    # Store or update public key
    cursor.execute("""
        INSERT INTO node_config (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, ('vapid_public_key', public_key))
    
    db.commit()
    
    return True