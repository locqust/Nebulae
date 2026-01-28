# utils/thumbnails.py
import os
from PIL import Image
from flask import current_app
import hashlib

def get_thumbnail_path(media_file_path, source_type='media', user_path=''):
    """
    Generate the path where a thumbnail should be stored.
    Handles both full paths (e.g., '/app/user_media/andy_media') and folder names (e.g., 'andy_media').
    
    Args:
        media_file_path: Relative path to the original image (e.g., 'subfolder/image.jpg')
        source_type: 'media' or 'uploads'
        user_path: User's media_path or uploads_path - can be full path or just folder name
    
    Returns:
        Full path to where thumbnail should be stored
    """
    # Extract just the folder name from full path if needed
    if user_path.startswith('/app/user_media/'):
        user_folder = user_path.replace('/app/user_media/', '')
        source_type = 'media'
    elif user_path.startswith('/app/user_uploads/'):
        user_folder = user_path.replace('/app/user_uploads/', '')
        source_type = 'uploads'
    else:
        # Already just a folder name
        user_folder = user_path
    
    # Create a hash of the full source path to handle long filenames and duplicates
    full_source = f"{source_type}/{user_folder}/{media_file_path}"
    path_hash = hashlib.md5(full_source.encode()).hexdigest()[:8]
    
    # Get just the filename
    filename = os.path.basename(media_file_path)
    name, ext = os.path.splitext(filename)
    
    # Thumbnail filename: original_name_HASH.jpg
    thumb_filename = f"{name}_{path_hash}.jpg"
    
    # Store thumbnails in /app/thumbnails/{source_type}/{user_folder}/
    thumbnail_dir = os.path.join(
        current_app.config['THUMBNAIL_CACHE_DIR'],
        source_type,
        user_folder
    )
    
    # Create directory if it doesn't exist
    try:
        os.makedirs(thumbnail_dir, exist_ok=True)
    except Exception as e:
        print(f"✗ Failed to create thumbnail directory {thumbnail_dir}: {e}")
        return None
    
    full_thumb_path = os.path.join(thumbnail_dir, thumb_filename)
    return full_thumb_path


def create_thumbnail(source_full_path, thumbnail_path, size=(400, 400)):
    """
    Create a thumbnail from an image.
    
    Args:
        source_full_path: Full path to the original image
        thumbnail_path: Full path where thumbnail should be saved
        size: Tuple of (width, height) for thumbnail
    
    Returns:
        True if successful, False otherwise
    """
    try:
        with Image.open(source_full_path) as img:
            try:
                from PIL import ImageOps
                img = ImageOps.exif_transpose(img)
            except Exception as e:
                print(f"Note: Could not process EXIF for {source_full_path}: {e}")
                
            # Convert RGBA to RGB if necessary (for JPEG)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create a white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Create thumbnail maintaining aspect ratio
            img.thumbnail(size, Image.Resampling.LANCZOS)
            
            # Ensure thumbnail directory exists
            os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
            
            # Save as JPEG with optimization
            img.save(thumbnail_path, 'JPEG', quality=85, optimize=True)
            
            print(f"✓ Created thumbnail: {thumbnail_path}")
            return True
    except Exception as e:
        print(f"✗ Error creating thumbnail for {source_full_path}: {e}")
        return False


def get_or_create_thumbnail(media_file_path, user_media_path=None, user_uploads_path=None):
    """
    Get thumbnail path, creating it if it doesn't exist.
    
    Args:
        media_file_path: Relative path to media (e.g., 'subfolder/image.jpg')
        user_media_path: User's media path (can be full path like '/app/user_media/andy_media' or just 'andy_media')
        user_uploads_path: User's uploads path (can be full path like '/app/user_uploads/andy_uploads' or just 'andy_uploads')
    
    Returns:
        Path to thumbnail relative to THUMBNAIL_CACHE_DIR, or None if failed
    """
    source_type = None
    source_full_path = None
    user_path = None
    
    # Check if file is in uploads first (prioritize new uploads)
    if user_uploads_path:
        # Handle both full paths and folder names
        if user_uploads_path.startswith('/app/user_uploads/'):
            uploads_base = user_uploads_path
        else:
            uploads_base = os.path.join(current_app.config['USER_UPLOADS_BASE_DIR'], user_uploads_path)
        
        uploads_path = os.path.join(uploads_base, media_file_path)
        
        if os.path.exists(uploads_path):
            source_type = 'uploads'
            source_full_path = uploads_path
            user_path = user_uploads_path
    
    # Check if file is in media (read-only)
    if not source_full_path and user_media_path:
        # Handle both full paths and folder names
        if user_media_path.startswith('/app/user_media/'):
            media_base = user_media_path
        else:
            media_base = os.path.join(current_app.config['USER_MEDIA_BASE_DIR'], user_media_path)
        
        media_path = os.path.join(media_base, media_file_path)
        
        if os.path.exists(media_path):
            source_type = 'media'
            source_full_path = media_path
            user_path = user_media_path
    
    if not source_full_path:
        print(f"✗ Source file not found: {media_file_path}")
        return None
    
    # Get thumbnail path with proper organization
    thumbnail_path = get_thumbnail_path(media_file_path, source_type, user_path)
    
    if not thumbnail_path:
        return None
    
    # Create thumbnail if it doesn't exist
    if not os.path.exists(thumbnail_path):
        if not create_thumbnail(source_full_path, thumbnail_path):
            return None
    
    # Return relative path from thumbnail cache dir
    rel_path = os.path.relpath(thumbnail_path, current_app.config['THUMBNAIL_CACHE_DIR'])
    return rel_path