# utils/media.py
import os
from flask import current_app
from werkzeug.utils import secure_filename
from db import get_db
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
                for entry in os.scandir(current_dir):
                    item = entry.name
                    if entry.is_dir():
                        directories.append(item)
                    elif '.' in item and item.rsplit('.', 1)[1].lower() in allowed_extensions:
                        relative_path = os.path.join(subfolder, item)
                        try:
                            item_mtime = entry.stat().st_mtime
                        except OSError:
                            item_mtime = 0
                        media_files.append({
                            'path': relative_path,
                            'source': 'media',  # Tag as from media library
                            'writable': False,
                            'mtime': item_mtime
                        })
            except OSError as e:
                print(f"Error reading media directory {current_dir}: {e}")
    
    # NEW: List from writable uploads path
    if user_uploads_path:
        uploads_dir = os.path.join(current_app.config['USER_UPLOADS_BASE_DIR'], user_uploads_path)
        uploads_current_dir = os.path.join(uploads_dir, subfolder)
        
        if os.path.exists(uploads_current_dir) and os.path.isdir(uploads_current_dir):
            try:
                for entry in os.scandir(uploads_current_dir):
                    item = entry.name
                    if entry.is_dir():
                        if item not in directories:  # Avoid duplicates
                            directories.append(item)
                    elif '.' in item and item.rsplit('.', 1)[1].lower() in allowed_extensions:
                        relative_path = os.path.join(subfolder, item)
                        try:
                            item_mtime = entry.stat().st_mtime
                        except OSError:
                            item_mtime = 0
                        media_files.append({
                            'path': relative_path,
                            'source': 'uploads',  # Tag as from uploads
                            'writable': True,
                            'mtime': item_mtime
                        })
            except OSError as e:
                print(f"Error reading uploads directory {uploads_current_dir}: {e}")

    # Sort newest first, across both media and uploads sources combined,
    # so photos/videos interleave by actual capture/add time instead of
    # being grouped by extension or filesystem listing order.
    media_files.sort(key=lambda f: f['mtime'], reverse=True)

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
