# utils/backup_utils.py
"""
Database backup and restore utilities for NODE.
Handles both scheduled and ad-hoc SQLite database backups.
"""

import os
import shutil
import sqlite3
from datetime import datetime
from flask import current_app


def get_backup_directory():
    """Get the backup directory path, creating it if it doesn't exist."""
    backup_dir = os.path.join(current_app.instance_path, 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def create_backup(backup_name=None, is_scheduled=False):
    """
    Create a backup of the database.
    
    Args:
        backup_name: Optional custom name for the backup. If None, generates timestamp-based name.
        is_scheduled: Boolean indicating if this is a scheduled backup (for naming convention).
    
    Returns:
        tuple: (success: bool, message: str, backup_path: str or None)
    """
    try:
        # Get database path
        db_path = current_app.config['DATABASE']
        if not os.path.exists(db_path):
            return False, "Database file not found.", None
        
        # Generate backup filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if backup_name:
            # Sanitize backup name
            backup_name = "".join(c for c in backup_name if c.isalnum() or c in (' ', '-', '_')).strip()
            filename = f"{backup_name}_{timestamp}.db"
        elif is_scheduled:
            filename = f"scheduled_{timestamp}.db"
        else:
            filename = f"backup_{timestamp}.db"
        
        # Create backup directory if it doesn't exist
        backup_dir = get_backup_directory()
        backup_path = os.path.join(backup_dir, filename)
        
        # Perform the backup using SQLite's backup API (handles locks properly)
        source_conn = sqlite3.connect(db_path)
        backup_conn = sqlite3.connect(backup_path)
        
        with backup_conn:
            source_conn.backup(backup_conn)
        
        source_conn.close()
        backup_conn.close()
        
        # Verify backup was created and has content
        if os.path.exists(backup_path) and os.path.getsize(backup_path) > 0:
            backup_size = os.path.getsize(backup_path)
            return True, f"Backup created successfully ({format_size(backup_size)}).", backup_path
        else:
            return False, "Backup file was not created properly.", None
            
    except sqlite3.Error as e:
        return False, f"Database error during backup: {str(e)}", None
    except Exception as e:
        return False, f"Unexpected error during backup: {str(e)}", None


def list_backups():
    """
    List all available database backups.
    
    Returns:
        list: List of dicts with backup information (filename, path, size, date)
    """
    backup_dir = get_backup_directory()
    backups = []
    
    try:
        for filename in os.listdir(backup_dir):
            if filename.endswith('.db'):
                filepath = os.path.join(backup_dir, filename)
                stat_info = os.stat(filepath)
                
                backups.append({
                    'filename': filename,
                    'path': filepath,
                    'size': stat_info.st_size,
                    'size_formatted': format_size(stat_info.st_size),
                    'created': datetime.fromtimestamp(stat_info.st_ctime),
                    'modified': datetime.fromtimestamp(stat_info.st_mtime),
                    'is_scheduled': filename.startswith('scheduled_')
                })
        
        # Sort by creation date, newest first
        backups.sort(key=lambda x: x['created'], reverse=True)
        return backups
        
    except Exception as e:
        print(f"Error listing backups: {e}")
        return []


def restore_backup(backup_filename):
    """
    Restore the database from a backup file.
    
    Args:
        backup_filename: Name of the backup file to restore from
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        backup_dir = get_backup_directory()
        backup_path = os.path.join(backup_dir, backup_filename)
        
        # Verify backup file exists
        if not os.path.exists(backup_path):
            return False, "Backup file not found."
        
        # Verify backup file is valid SQLite database
        try:
            test_conn = sqlite3.connect(backup_path)
            test_conn.execute("SELECT 1")
            test_conn.close()
        except sqlite3.Error:
            return False, "Backup file is not a valid SQLite database."
        
        # Get current database path
        db_path = current_app.config['DATABASE']
        
        # Create a pre-restore backup of current database
        pre_restore_success, pre_restore_msg, _ = create_backup(
            backup_name="pre_restore_backup",
            is_scheduled=False
        )
        
        if not pre_restore_success:
            return False, f"Failed to create pre-restore backup: {pre_restore_msg}"
        
        # Close any existing connections (this is tricky in Flask - we'll need to handle it carefully)
        # The actual database connection will be closed by Flask's teardown
        
        # Replace the current database with the backup
        shutil.copy2(backup_path, db_path)
        
        return True, f"Database restored successfully from {backup_filename}. A pre-restore backup was created."
        
    except Exception as e:
        return False, f"Error during restore: {str(e)}"


def delete_backup(backup_filename):
    """
    Delete a backup file.
    
    Args:
        backup_filename: Name of the backup file to delete
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        backup_dir = get_backup_directory()
        backup_path = os.path.join(backup_dir, backup_filename)
        
        if not os.path.exists(backup_path):
            return False, "Backup file not found."
        
        os.remove(backup_path)
        return True, f"Backup {backup_filename} deleted successfully."
        
    except Exception as e:
        return False, f"Error deleting backup: {str(e)}"


def get_backup_settings():
    """
    Get backup schedule settings from database.
    
    Returns:
        dict: Backup settings including schedule info
    """
    from db import get_db
    
    db = get_db()
    cursor = db.cursor()
    
    # Get settings
    settings = {}
    cursor.execute("SELECT key, value FROM node_config WHERE key LIKE 'backup_%'")
    for row in cursor.fetchall():
        settings[row['key']] = row['value']
    
    # Set defaults if not present
    settings.setdefault('backup_enabled', 'False')
    settings.setdefault('backup_frequency', 'daily')
    settings.setdefault('backup_time', '02:00')  # Default 2 AM
    settings.setdefault('backup_retention_days', '30')
    settings.setdefault('backup_last_run', None)
    
    return settings


def save_backup_settings(enabled, frequency, retention_days, backup_time='02:00'):
    """
    Save backup schedule settings to database.
    
    Args:
        enabled: Boolean or string 'True'/'False'
        frequency: String - 'daily', 'weekly', or 'monthly'
        retention_days: Integer or string - number of days to keep backups
        backup_time: String - time in HH:MM format (24-hour)
    
    Returns:
        tuple: (success: bool, message: str)
    """
    from db import get_db
    
    try:
        db = get_db()
        
        # Validate inputs
        if frequency not in ['daily', 'weekly', 'monthly']:
            return False, "Invalid frequency. Must be 'daily', 'weekly', or 'monthly'."
        
        try:
            retention_days = int(retention_days)
            if retention_days < 1:
                return False, "Retention days must be at least 1."
        except ValueError:
            return False, "Retention days must be a valid number."
        
        # Validate time format
        try:
            from datetime import datetime
            datetime.strptime(backup_time, '%H:%M')
        except ValueError:
            return False, "Invalid time format. Use HH:MM (24-hour format)."
        
        # Save settings
        enabled_str = str(enabled).lower() == 'true' or enabled == True
        
        db.execute("INSERT OR REPLACE INTO node_config (key, value) VALUES (?, ?)",
                   ('backup_enabled', str(enabled_str)))
        db.execute("INSERT OR REPLACE INTO node_config (key, value) VALUES (?, ?)",
                   ('backup_frequency', frequency))
        db.execute("INSERT OR REPLACE INTO node_config (key, value) VALUES (?, ?)",
                   ('backup_time', backup_time))
        db.execute("INSERT OR REPLACE INTO node_config (key, value) VALUES (?, ?)",
                   ('backup_retention_days', str(retention_days)))
        
        db.commit()
        return True, "Backup settings saved successfully."
        
    except Exception as e:
        return False, f"Error saving backup settings: {str(e)}"


def cleanup_old_backups():
    """
    Delete backups older than the retention period.
    Only affects scheduled backups, not manual ones.
    
    Returns:
        tuple: (deleted_count: int, message: str)
    """
    try:
        settings = get_backup_settings()
        retention_days = int(settings.get('backup_retention_days', 30))
        
        backup_dir = get_backup_directory()
        deleted_count = 0
        current_time = datetime.now()
        
        for filename in os.listdir(backup_dir):
            # Only clean up scheduled backups
            if filename.startswith('scheduled_') and filename.endswith('.db'):
                filepath = os.path.join(backup_dir, filename)
                file_time = datetime.fromtimestamp(os.path.getctime(filepath))
                age_days = (current_time - file_time).days
                
                if age_days > retention_days:
                    os.remove(filepath)
                    deleted_count += 1
        
        return deleted_count, f"Deleted {deleted_count} old backup(s)."
        
    except Exception as e:
        return 0, f"Error during cleanup: {str(e)}"


def should_run_scheduled_backup():
    """
    Check if a scheduled backup should run based on settings.
    Checks both the frequency AND the scheduled time.
    
    Returns:
        bool: True if backup should run
    """
    settings = get_backup_settings()
    
    # Check if backups are enabled
    if settings.get('backup_enabled', 'False').lower() != 'true':
        return False
    
    # Get last run time
    last_run = settings.get('backup_last_run')
    current_time = datetime.now()
    
    # Get scheduled time (default to 02:00 if not set)
    scheduled_time_str = settings.get('backup_time', '02:00')
    try:
        scheduled_hour, scheduled_minute = map(int, scheduled_time_str.split(':'))
    except (ValueError, AttributeError):
        scheduled_hour, scheduled_minute = 2, 0  # Default to 2 AM
    
    # Check if we're within the scheduled time window (within 15 minutes of scheduled time)
    current_hour = current_time.hour
    current_minute = current_time.minute
    
    # Calculate if we're within 15 minutes of the scheduled time
    scheduled_minutes_total = scheduled_hour * 60 + scheduled_minute
    current_minutes_total = current_hour * 60 + current_minute
    minutes_diff = abs(current_minutes_total - scheduled_minutes_total)
    
    # Not within the time window
    if minutes_diff > 15:
        return False
    
    # If never run before, run now (if we're in the time window)
    if not last_run:
        return True
    
    try:
        last_run_time = datetime.fromisoformat(last_run)
        time_since_last = current_time - last_run_time
        
        frequency = settings.get('backup_frequency', 'daily')
        
        # Check if enough time has passed AND we're in the time window
        if frequency == 'daily' and time_since_last.days >= 1:
            return True
        elif frequency == 'weekly' and time_since_last.days >= 7:
            return True
        elif frequency == 'monthly' and time_since_last.days >= 30:
            return True
        
        return False
        
    except Exception:
        return True  # If there's an error parsing the date, run the backup


def update_last_backup_time():
    """Update the last backup run timestamp in the database."""
    from db import get_db
    
    try:
        db = get_db()
        current_time = datetime.now().isoformat()
        db.execute("INSERT OR REPLACE INTO node_config (key, value) VALUES (?, ?)",
                   ('backup_last_run', current_time))
        db.commit()
    except Exception as e:
        print(f"Error updating last backup time: {e}")


def format_size(bytes_size):
    """Format bytes into human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"