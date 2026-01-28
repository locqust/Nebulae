# utils/auth.py
import hashlib

def hash_password(password):
    """Hashes a password using SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(hashed_password, provided_password):
    """Checks if a provided password matches a hashed password."""
    return hashlib.sha256(provided_password.encode()).hexdigest() == hashed_password

