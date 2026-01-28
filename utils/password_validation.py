# utils/password_validation.py
# Centralized password validation for consistent enforcement across the application

import re

# Password requirements configuration
PASSWORD_MIN_LENGTH = 12
PASSWORD_REQUIREMENTS = {
    'min_length': PASSWORD_MIN_LENGTH,
    'uppercase': True,
    'lowercase': True,
    'number': True,
    'special': True
}

# Special characters allowed
SPECIAL_CHARACTERS = "!@#$%^&*()_+-=[]{}|;:,.<>?"

def validate_password(password):
    """
    Validates a password against security requirements.
    
    Args:
        password (str): The password to validate
        
    Returns:
        tuple: (is_valid, error_message)
               is_valid (bool): True if password meets all requirements
               error_message (str): Description of why password is invalid, or None if valid
    """
    if not password:
        return False, "Password is required."
    
    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."
    
    if PASSWORD_REQUIREMENTS['uppercase'] and not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter."
    
    if PASSWORD_REQUIREMENTS['lowercase'] and not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter."
    
    if PASSWORD_REQUIREMENTS['number'] and not re.search(r'\d', password):
        return False, "Password must contain at least one number."
    
    if PASSWORD_REQUIREMENTS['special'] and not re.search(f'[{re.escape(SPECIAL_CHARACTERS)}]', password):
        return False, f"Password must contain at least one special character ({SPECIAL_CHARACTERS})."
    
    return True, None

def get_password_requirements_text():
    """
    Returns a human-readable string describing password requirements.
    
    Returns:
        str: Password requirements description
    """
    requirements = [
        f"At least {PASSWORD_MIN_LENGTH} characters long"
    ]
    
    if PASSWORD_REQUIREMENTS['uppercase']:
        requirements.append("At least one uppercase letter (A-Z)")
    
    if PASSWORD_REQUIREMENTS['lowercase']:
        requirements.append("At least one lowercase letter (a-z)")
    
    if PASSWORD_REQUIREMENTS['number']:
        requirements.append("At least one number (0-9)")
    
    if PASSWORD_REQUIREMENTS['special']:
        requirements.append(f"At least one special character ({SPECIAL_CHARACTERS})")
    
    return "Password must contain: " + "; ".join(requirements) + "."

def get_password_requirements_html():
    """
    Returns an HTML formatted string describing password requirements.
    Useful for displaying in forms.
    
    Returns:
        str: HTML formatted password requirements
    """
    requirements = []
    
    requirements.append(f"• At least {PASSWORD_MIN_LENGTH} characters long")
    
    if PASSWORD_REQUIREMENTS['uppercase']:
        requirements.append("• At least one uppercase letter (A-Z)")
    
    if PASSWORD_REQUIREMENTS['lowercase']:
        requirements.append("• At least one lowercase letter (a-z)")
    
    if PASSWORD_REQUIREMENTS['number']:
        requirements.append("• At least one number (0-9)")
    
    if PASSWORD_REQUIREMENTS['special']:
        requirements.append(f"• At least one special character ({SPECIAL_CHARACTERS})")
    
    return "<br>".join(requirements)