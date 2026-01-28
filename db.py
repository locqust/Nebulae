# db.py
# Contains the core database connection, initialization, and closing logic.

import sqlite3
import hashlib
import uuid
import os
import time
from flask import g, current_app

# Define the path for the SQLite database file (will be set from app.config)
DATABASE = None

def get_db():
    """
    Establishes a database connection or returns the existing one.
    Uses Flask's 'g' object to store the connection for the current request.
    Configures SQLite for optimal concurrent performance with WAL mode.
    """
    global DATABASE # Declare global to use the DATABASE variable set by init_db
    if DATABASE is None: # Ensure DATABASE is set if get_db is called before init_db
        DATABASE = current_app.config['DATABASE']

    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, timeout=30.0, check_same_thread=False)
        g.db.row_factory = sqlite3.Row # Return rows as dictionary-like objects
        
        # Configure SQLite pragmas for production multi-worker environment
        # These are applied per-connection and are safe to run on every connection
        cursor = g.db.cursor()
        
        # Set busy timeout to 30 seconds (handles write lock contention)
        cursor.execute("PRAGMA busy_timeout=30000")
        
        # Optimize for performance
        cursor.execute("PRAGMA synchronous=NORMAL")  # Safe with WAL mode
        cursor.execute("PRAGMA cache_size=-64000")   # 64MB cache per connection
        cursor.execute("PRAGMA temp_store=MEMORY")   # Use RAM for temp tables
        cursor.execute("PRAGMA mmap_size=268435456") # 256MB memory-mapped I/O
        
        cursor.close()
        
    return g.db

def close_db(e=None):
    """
    Closes the database connection at the end of the request.
    """
    db = g.pop('db', None)
    if db is not None:
        db.close()

def ensure_profile_info_fields_exist(db):
    """
    Ensures that all expected profile info fields exist for all users and groups.
    This is called during database initialization.
    
    Args:
        db: SQLite database connection
    """
    cursor = db.cursor()

    # Define default user profile fields
    default_user_profile_fields = [
        'dob', 'hometown', 'occupation', 'bio', 'show_username', 
        'show_friends', 'website', 'email', 'phone', 'address'
    ]

    # Define default group profile fields
    default_group_profile_fields = ['website', 'email', 'about', 'show_admins', 'show_members']

    # Fetch all users
    cursor.execute("SELECT id FROM users")
    user_ids = [row['id'] for row in cursor.fetchall()]

    for user_id in user_ids:
        for field_name in default_user_profile_fields:
            cursor.execute("SELECT COUNT(*) FROM user_profile_info WHERE user_id = ? AND field_name = ?", (user_id, field_name))
            if cursor.fetchone()[0] == 0:
                # Default privacy: private (0,0,0), except show_friends defaults to friends-only (0,0,1)
                if field_name == 'show_friends':
                    db.execute("INSERT INTO user_profile_info (user_id, field_name, field_value, privacy_public, privacy_local, privacy_friends) VALUES (?, ?, 'visible', 0, 0, 1)", (user_id, field_name))
                else:
                    db.execute("INSERT INTO user_profile_info (user_id, field_name, field_value, privacy_public, privacy_local, privacy_friends) VALUES (?, ?, NULL, 0, 0, 0)", (user_id, field_name))

    # Fetch all groups
    cursor.execute("SELECT id FROM groups")
    group_ids = [row['id'] for row in cursor.fetchall()]

    for group_id in group_ids:
        for field_name in default_group_profile_fields:
            cursor.execute("SELECT COUNT(*) FROM group_profile_info WHERE group_id = ? AND field_name = ?", (group_id, field_name))
            if cursor.fetchone()[0] == 0:
                # Default for 'show_admins' and 'show_members' to be members only, others private
                if field_name in ['show_admins', 'show_members']:
                    # Set value to 'visible' and privacy to members only
                    db.execute("INSERT INTO group_profile_info (group_id, field_name, field_value, privacy_public, privacy_members_only) VALUES (?, ?, 'visible', 0, 1)", (group_id, field_name))
                else:
                    db.execute("INSERT INTO group_profile_info (group_id, field_name, field_value, privacy_public, privacy_members_only) VALUES (?, ?, NULL, 0, 0)", (group_id, field_name))

    db.commit()
    print("Ensured default profile info fields exist for all users and groups.")

def init_db(app):
    """
    Initializes the database schema.
    Creates tables, a default admin user, a Node Unique ID (NUID),
    and default profile fields.
    
    This function uses file-based locking to ensure only ONE worker
    performs initialization when multiple gunicorn workers start simultaneously.
    """
    # FIX: Move imports inside the function to prevent circular dependencies.
    from db_queries.users import get_user_by_username
    from db_queries.profiles import update_profile_info_field

    global DATABASE
    DATABASE = app.config['DATABASE'] # Set the global DATABASE variable from app config
    
    # Use a lock file to ensure only one worker performs initialization
    lock_file = DATABASE + '.init.lock'
    lock_acquired = False
    
    try:
        # Try to acquire the lock (non-blocking)
        if not os.path.exists(lock_file):
            # Create lock file atomically
            try:
                fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                lock_acquired = True
            except FileExistsError:
                # Another worker got the lock first
                lock_acquired = False
        
        if lock_acquired:
            # This worker won the race - perform initialization
            print(f"Worker {os.getpid()} performing database initialization...")
            
            # Direct connection for initialization (bypasses get_db() to avoid recursion)
            init_conn = sqlite3.connect(DATABASE, timeout=30.0)
            init_conn.row_factory = sqlite3.Row
            
            # Enable WAL mode first (this is a one-time database-level change)
            cursor = init_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            result = cursor.fetchone()[0]
            if result == 'wal':
                print("WAL mode enabled successfully")
            cursor.close()
            init_conn.commit()
            
            # Run schema initialization
            with app.open_resource('schema.sql', mode='r') as f:
                init_conn.cursor().executescript(f.read())
            init_conn.commit()

            cursor = init_conn.cursor()

            # Generate and store the Node Unique ID (NUID) if it doesn't exist
            cursor.execute("SELECT COUNT(*) FROM node_config WHERE key = ?", ('nu_id',))
            if cursor.fetchone()[0] == 0:
                nu_id = str(uuid.uuid4())
                cursor.execute("INSERT INTO node_config (key, value) VALUES (?, ?)", ('nu_id', nu_id))
                init_conn.commit()
                print("Node Unique ID (NUID) created.")
            else:
                print("NUID already exists.")

            # Add default admin user if not exists in the 'users' table with user_type 'admin'
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = ? AND user_type = ?", ('admin', 'admin'))
            if cursor.fetchone()[0] == 0:
                # Hash the default admin password
                hashed_password = hashlib.sha256("adminpassword".encode()).hexdigest()
                admin_puid = str(uuid.uuid4())
                # Explicitly set hostname to NULL for local admin and add PUID
                # Set password_must_change=TRUE to force password change on first login
                cursor.execute("INSERT INTO users (puid, username, password, user_type, display_name, hostname, password_must_change) VALUES (?, ?, ?, ?, ?, NULL, TRUE)", 
                               (admin_puid, 'admin', hashed_password, 'admin', 'Administrator'))
                init_conn.commit()
                print("Default admin user 'admin' created with password 'adminpassword'")
            else:
                print("Admin user already exists.")
                
            # --- ONE-TIME DATA CORRECTION SCRIPT ---
            # This script will find any user accounts that look like local accounts (hostname is NULL)
            # but have an incorrect user_type of 'remote', and it will correct them to 'user'.
            # This specifically excludes the main 'admin' account from being changed.
            try:
                updated_rows = init_conn.execute("""
                    UPDATE users 
                    SET user_type = 'user' 
                    WHERE hostname IS NULL AND user_type = 'remote' AND username != 'admin'
                """).rowcount
                init_conn.commit()
                if updated_rows > 0:
                    print(f"Corrected {updated_rows} user account(s) with incorrect 'remote' user_type.")
            except sqlite3.Error as e:
                print(f"Error during data correction: {e}")
                init_conn.rollback()

            # Ensure profile info fields exist for all users and groups
            ensure_profile_info_fields_exist(init_conn)
            
            # Close the initialization connection
            init_conn.close()
            
            print(f"Worker {os.getpid()} completed database initialization")
            
        else:
            # Another worker is handling initialization - wait for it to complete
            print(f"Worker {os.getpid()} waiting for database initialization...")
            max_wait = 30  # Wait up to 30 seconds
            waited = 0
            while os.path.exists(lock_file) and waited < max_wait:
                time.sleep(0.5)
                waited += 0.5
            
            if waited >= max_wait:
                print(f"Worker {os.getpid()} timed out waiting for initialization")
            else:
                print(f"Worker {os.getpid()} resuming after initialization completed")
    
    finally:
        # Remove lock file if this worker created it
        if lock_acquired and os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except:
                pass  # Ignore errors during cleanup

def init_app(app):
    """
    Register database functions with the Flask app. This is called by
    the application factory.
    """
    app.teardown_appcontext(close_db)
    # The init_db function is now called from the app factory in app.py
    # No need for a command line interface here as per the original structure