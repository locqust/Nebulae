# utils/media.py
import os
from flask import current_app, send_from_directory, abort
from werkzeug.utils import secure_filename
from db import get_db
from db_queries.users import get_user_by_puid
# Unused imports removed to help break circular dependency
# from db_queries.comments import get_comment_by_id
# from db_queries.posts import get_post_by_id

def list_media_content(user_media_path, user_uploads_path, subfolder=''):
    """
    Lists directories and media files from both read-only media and writable uploads.
    Combines results from both locations.
    """
    directories = []
    media_files = []
    allowed_extensions = current_app.config['ALLOWED_MEDIA_EXTENSIONS']
    
    # List from read-only media path
    if user_media_path:
        base_dir = os.path.join(current_app.config['USER_MEDIA_BASE_DIR'], user_media_path)
        current_dir = os.path.join(base_dir, subfolder)
        
        if os.path.exists(current_dir) and os.path.isdir(current_dir):
            try:
                for item in os.listdir(current_dir):
                    item_path = os.path.join(current_dir, item)
                    if os.path.isdir(item_path):
                        directories.append(item)
                    elif '.' in item and item.rsplit('.', 1)[1].lower() in allowed_extensions:
                        relative_path = os.path.join(subfolder, item)
                        media_files.append({
                            'path': relative_path,
                            'source': 'media',  # Tag as from media library
                            'writable': False
                        })
            except OSError as e:
                print(f"Error reading media directory {current_dir}: {e}")
    
    # NEW: List from writable uploads path
    if user_uploads_path:
        uploads_dir = os.path.join(current_app.config['USER_UPLOADS_BASE_DIR'], user_uploads_path)
        uploads_current_dir = os.path.join(uploads_dir, subfolder)
        
        if os.path.exists(uploads_current_dir) and os.path.isdir(uploads_current_dir):
            try:
                for item in os.listdir(uploads_current_dir):
                    item_path = os.path.join(uploads_current_dir, item)
                    if os.path.isdir(item_path):
                        if item not in directories:  # Avoid duplicates
                            directories.append(item)
                    elif '.' in item and item.rsplit('.', 1)[1].lower() in allowed_extensions:
                        relative_path = os.path.join(subfolder, item)
                        media_files.append({
                            'path': relative_path,
                            'source': 'uploads',  # Tag as from uploads
                            'writable': True
                        })
            except OSError as e:
                print(f"Error reading uploads directory {uploads_current_dir}: {e}")
    
    return directories, media_files

def allowed_file(filename):
    """Checks if a filename has an allowed extension for profile pictures."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_PROFILE_PICTURE_EXTENSIONS']

def get_media_by_id(media_id):
    """
    Retrieves a media item by its ID from either post_media or comment_media tables.
    """
    db = get_db()
    
    # Check post_media first
    post_media_cursor = db.cursor()
    post_media_cursor.execute("SELECT *, 'post' as type FROM post_media WHERE id = ?", (media_id,))
    media = post_media_cursor.fetchone()
    if media:
        return dict(media)
        
    # If not found, check comment_media
    comment_media_cursor = db.cursor()
    comment_media_cursor.execute("SELECT *, 'comment' as type FROM comment_media WHERE id = ?", (media_id,))
    media = comment_media_cursor.fetchone()
    if media:
        return dict(media)

    return None

def update_media_alt_text(media_id, alt_text):
    """Updates the alt text for a media item in either post_media or comment_media."""
    db = get_db()
    cursor = db.cursor()
    
    # First, try to update in post_media
    cursor.execute("UPDATE post_media SET alt_text = ? WHERE id = ?", (alt_text, media_id))
    if cursor.rowcount > 0:
        db.commit()
        return True
        
    # If not found or not updated, try comment_media
    cursor.execute("UPDATE comment_media SET alt_text = ? WHERE id = ?", (alt_text, media_id))
    if cursor.rowcount > 0:
        db.commit()
        return True
        
    return False

def serve_user_media_route(puid, filename):
    """
    Serves a media file for a given user PUID.
    Checks uploads path first, then media path.
    """
    user = get_user_by_puid(puid)
    if not user:
        abort(404, "User not found.")

    decoded_filename = os.path.normpath(filename)
    
    # Check if it's a profile picture
    if decoded_filename.startswith('profile.'):
        directory = os.path.join(current_app.config['PROFILE_PICTURE_STORAGE_DIR'], user['puid'])
        base_filename = decoded_filename
    else:
        # NEW: Check uploads path first (writable location)
        if user.get('uploads_path'):
            uploads_dir = os.path.join(current_app.config['USER_UPLOADS_BASE_DIR'], user['uploads_path'])
            subfolder_path = os.path.dirname(decoded_filename)
            if subfolder_path:
                uploads_dir = os.path.join(uploads_dir, subfolder_path)
            
            base_filename = os.path.basename(decoded_filename)
            uploads_file_path = os.path.join(uploads_dir, base_filename)
            
            if os.path.exists(uploads_file_path):
                return send_from_directory(uploads_dir, base_filename, as_attachment=False)
        
        # Fall back to read-only media path
        if not user.get('media_path'):
            abort(404, "User does not have a configured media path.")
        
        directory = os.path.join(current_app.config['USER_MEDIA_BASE_DIR'], user['media_path'])
        subfolder_path = os.path.dirname(decoded_filename)
        if subfolder_path:
            directory = os.path.join(directory, subfolder_path)
        base_filename = os.path.basename(decoded_filename)

    # Security check
    valid_bases = [
        current_app.config['USER_MEDIA_BASE_DIR'],
        current_app.config['USER_UPLOADS_BASE_DIR'],
        current_app.config['PROFILE_PICTURE_STORAGE_DIR']
    ]
    
    if not any(os.path.abspath(directory).startswith(os.path.abspath(base)) for base in valid_bases):
        abort(400, "Invalid media path.")

    if not os.path.exists(os.path.join(directory, base_filename)):
        abort(404, "File not found.")

    return send_from_directory(directory, base_filename, as_attachment=False)
