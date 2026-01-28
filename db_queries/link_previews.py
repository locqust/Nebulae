# db_queries/link_previews.py
from db import get_db
from utils.url_preview import fetch_url_preview, extract_urls_from_text
from datetime import datetime, timedelta

def get_or_create_link_preview(url):
    """
    Gets an existing link preview from the database or creates a new one by fetching metadata.
    Returns the link_preview dict or None if fetch fails.
    """
    db = get_db()
    cursor = db.cursor()
    
    # Check if we already have this URL (fetched within last 7 days to allow refresh)
    cursor.execute("""
        SELECT id, url, title, description, image_url, site_name, is_valid, fetched_at
        FROM link_previews
        WHERE url = ?
        AND fetched_at > datetime('now', '-7 days')
    """, (url,))
    
    existing = cursor.fetchone()
    if existing:
        return dict(existing)
    
    # Fetch new preview
    preview_data = fetch_url_preview(url)
    
    if preview_data:
        # Store in database
        cursor.execute("""
            INSERT OR REPLACE INTO link_previews (url, title, description, image_url, site_name, is_valid, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            preview_data['url'],
            preview_data['title'],
            preview_data['description'],
            preview_data['image_url'],
            preview_data['site_name'],
            True,
            datetime.now()
        ))
        db.commit()
        
        link_preview_id = cursor.lastrowid
        return {
            'id': link_preview_id,
            **preview_data,
            'is_valid': True,
            'fetched_at': datetime.now()
        }
    else:
        # Store failed fetch to avoid retrying immediately
        cursor.execute("""
            INSERT OR REPLACE INTO link_previews (url, is_valid, fetched_at)
            VALUES (?, ?, ?)
        """, (url, False, datetime.now()))
        db.commit()
        return None


def associate_link_previews_with_post(post_id, content):
    """
    Extracts URLs from post content and associates link previews with the post.
    """
    if not content:
        return
    
    urls = extract_urls_from_text(content)
    if not urls:
        return
    
    db = get_db()
    cursor = db.cursor()
    
    for idx, url in enumerate(urls[:3]):  # Limit to 3 previews per post
        preview = get_or_create_link_preview(url)
        if preview and preview.get('is_valid'):
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO post_link_previews (post_id, link_preview_id, display_order)
                    VALUES (?, ?, ?)
                """, (post_id, preview['id'], idx))
                db.commit()
            except Exception as e:
                print(f"Error associating link preview with post: {e}")


def associate_link_previews_with_comment(comment_id, content):
    """
    Extracts URLs from comment content and associates link previews with the comment.
    """
    if not content:
        return
    
    urls = extract_urls_from_text(content)
    if not urls:
        return
    
    db = get_db()
    cursor = db.cursor()
    
    for idx, url in enumerate(urls[:2]):  # Limit to 2 previews per comment
        preview = get_or_create_link_preview(url)
        if preview and preview.get('is_valid'):
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO comment_link_previews (comment_id, link_preview_id, display_order)
                    VALUES (?, ?, ?)
                """, (comment_id, preview['id'], idx))
                db.commit()
            except Exception as e:
                print(f"Error associating link preview with comment: {e}")


def get_link_previews_for_post(post_id):
    """
    Retrieves all link previews associated with a post, ordered by display_order.
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT lp.id, lp.url, lp.title, lp.description, lp.image_url, lp.site_name
        FROM link_previews lp
        JOIN post_link_previews plp ON lp.id = plp.link_preview_id
        WHERE plp.post_id = ? AND lp.is_valid = 1
        ORDER BY plp.display_order
    """, (post_id,))
    
    return [dict(row) for row in cursor.fetchall()]


def get_link_previews_for_comment(comment_id):
    """
    Retrieves all link previews associated with a comment, ordered by display_order.
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT lp.id, lp.url, lp.title, lp.description, lp.image_url, lp.site_name
        FROM link_previews lp
        JOIN comment_link_previews clp ON lp.id = clp.link_preview_id
        WHERE clp.comment_id = ? AND lp.is_valid = 1
        ORDER BY clp.display_order
    """, (comment_id,))
    
    return [dict(row) for row in cursor.fetchall()]


def remove_link_previews_for_post(post_id):
    """
    Removes all link preview associations for a post (used when editing posts).
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM post_link_previews WHERE post_id = ?", (post_id,))
    db.commit()


def remove_link_previews_for_comment(comment_id):
    """
    Removes all link preview associations for a comment (used when editing comments).
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM comment_link_previews WHERE comment_id = ?", (comment_id,))
    db.commit()