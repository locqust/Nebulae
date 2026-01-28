# db_queries/polls.py
# Contains functions for managing polls

import json
from db import get_db
from db_queries.users import get_user_by_id, get_user_by_puid

def create_poll(post_id, options, allow_multiple_answers=False, allow_add_options=False):
    """
    Creates a poll attached to a post.
    
    Args:
        post_id: The ID of the post this poll belongs to
        options: List of option text strings
        allow_multiple_answers: Whether users can select multiple options
        allow_add_options: Whether users can add their own options
    
    Returns:
        int: The poll ID if successful, None otherwise
    """
    if not options or len(options) < 2:
        return None
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Create the poll
        cursor.execute("""
            INSERT INTO polls (post_id, allow_multiple_answers, allow_add_options)
            VALUES (?, ?, ?)
        """, (post_id, allow_multiple_answers, allow_add_options))
        
        poll_id = cursor.lastrowid
        
        # Add poll options
        for i, option_text in enumerate(options):
            cursor.execute("""
                INSERT INTO poll_options (poll_id, option_text, display_order)
                VALUES (?, ?, ?)
            """, (poll_id, option_text.strip(), i))
        
        db.commit()
        return poll_id
    except Exception as e:
        db.rollback()
        print(f"Error creating poll: {e}")
        return None


def get_poll_by_post_id(post_id, viewer_user_id=None):
    """
    Gets poll data for a specific post including vote counts and viewer's votes.
    
    Args:
        post_id: The ID of the post
        viewer_user_id: The ID of the viewing user (optional)
    
    Returns:
        dict: Poll data with options and votes, or None if no poll exists
    """
    db = get_db()
    cursor = db.cursor()
    
    # Get poll metadata
    cursor.execute("""
        SELECT id, allow_multiple_answers, allow_add_options
        FROM polls
        WHERE post_id = ?
    """, (post_id,))
    
    poll_row = cursor.fetchone()
    if not poll_row:
        return None
    
    poll = dict(poll_row)
    
    # Get poll options with vote counts
    cursor.execute("""
        SELECT 
            po.id,
            po.option_text,
            po.display_order,
            po.created_by_user_id,
            COUNT(pv.id) as vote_count,
            u.puid as creator_puid,
            u.display_name as creator_display_name
        FROM poll_options po
        LEFT JOIN poll_votes pv ON po.id = pv.poll_option_id
        LEFT JOIN users u ON po.created_by_user_id = u.id
        WHERE po.poll_id = ?
        GROUP BY po.id
        ORDER BY po.display_order ASC
    """, (poll['id'],))
    
    options = []
    for row in cursor.fetchall():
        option = dict(row)
        options.append(option)
    
    # Get total vote count
    total_votes = sum(opt['vote_count'] for opt in options)
    
    # Calculate percentages
    for option in options:
        if total_votes > 0:
            option['percentage'] = round((option['vote_count'] / total_votes) * 100)
        else:
            option['percentage'] = 0
    
    poll['options'] = options
    poll['total_votes'] = total_votes
    
    # Get viewer's votes if viewer_user_id is provided
    if viewer_user_id:
        cursor.execute("""
            SELECT poll_option_id
            FROM poll_votes
            WHERE poll_option_id IN (SELECT id FROM poll_options WHERE poll_id = ?)
            AND user_id = ?
        """, (poll['id'], viewer_user_id))
        
        poll['viewer_votes'] = [row['poll_option_id'] for row in cursor.fetchall()]
    else:
        poll['viewer_votes'] = []
    
    return poll


def vote_on_poll(poll_option_id, user_id):
    """
    Casts a vote on a poll option. Handles both single and multiple choice.
    
    Args:
        poll_option_id: The ID of the option being voted on
        user_id: The ID of the user voting
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Get the poll to check if multiple answers are allowed
        cursor.execute("""
            SELECT p.id, p.allow_multiple_answers
            FROM polls p
            JOIN poll_options po ON p.id = po.poll_id
            WHERE po.id = ?
        """, (poll_option_id,))
        
        poll_row = cursor.fetchone()
        if not poll_row:
            return False
        
        poll = dict(poll_row)
        
        # If single choice, remove any existing votes for this poll
        if not poll['allow_multiple_answers']:
            cursor.execute("""
                DELETE FROM poll_votes
                WHERE user_id = ?
                AND poll_option_id IN (
                    SELECT id FROM poll_options WHERE poll_id = ?
                )
            """, (user_id, poll['id']))
        
        # Add the new vote
        cursor.execute("""
            INSERT OR IGNORE INTO poll_votes (poll_option_id, user_id)
            VALUES (?, ?)
        """, (poll_option_id, user_id))
        
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Error voting on poll: {e}")
        return False


def remove_vote_from_poll(poll_option_id, user_id):
    """
    Removes a vote from a poll option (for multi-choice polls when deselecting).
    
    Args:
        poll_option_id: The ID of the option
        user_id: The ID of the user
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM poll_votes
            WHERE poll_option_id = ? AND user_id = ?
        """, (poll_option_id, user_id))
        
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Error removing vote: {e}")
        return False


def add_poll_option(poll_id, option_text, user_id):
    """
    Adds a new option to a poll (if allowed).
    
    Args:
        poll_id: The ID of the poll
        option_text: The text for the new option
        user_id: The ID of the user adding the option
    
    Returns:
        int: The new option ID if successful, None otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Check if adding options is allowed
        cursor.execute("""
            SELECT allow_add_options FROM polls WHERE id = ?
        """, (poll_id,))
        
        poll_row = cursor.fetchone()
        if not poll_row or not poll_row['allow_add_options']:
            return None
        
        # Get the next display order
        cursor.execute("""
            SELECT MAX(display_order) as max_order
            FROM poll_options
            WHERE poll_id = ?
        """, (poll_id,))
        
        max_order = cursor.fetchone()['max_order'] or 0
        
        # Add the new option
        cursor.execute("""
            INSERT INTO poll_options (poll_id, option_text, display_order, created_by_user_id)
            VALUES (?, ?, ?, ?)
        """, (poll_id, option_text.strip(), max_order + 1, user_id))
        
        option_id = cursor.lastrowid
        db.commit()
        return option_id
    except Exception as e:
        db.rollback()
        print(f"Error adding poll option: {e}")
        return None


def delete_poll_option(option_id, poll_creator_user_id):
    """
    Deletes a poll option if the requestor is the poll creator.
    
    Args:
        option_id: The ID of the option to delete
        poll_creator_user_id: The ID of the poll creator
    
    Returns:
        bool: True if successful, False otherwise
    """
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Verify user is the poll creator (allow deleting any option)
        cursor.execute("""
            SELECT po.id, p.post_id
            FROM poll_options po
            JOIN polls p ON po.poll_id = p.id
            JOIN posts ON p.post_id = posts.id
            WHERE po.id = ?
            AND posts.user_id = ?
        """, (option_id, poll_creator_user_id))
        
        if not cursor.fetchone():
            return False
        
        # Check if this is the last option - don't allow deleting it
        cursor.execute("""
            SELECT COUNT(*) as option_count
            FROM poll_options po
            JOIN polls p ON po.poll_id = p.id
            WHERE po.poll_id = (SELECT poll_id FROM poll_options WHERE id = ?)
        """, (option_id,))
        
        option_count = cursor.fetchone()['option_count']
        if option_count <= 2:
            # Don't allow deleting if it would leave less than 2 options
            return False
        
        # Delete the option (votes will cascade)
        cursor.execute("DELETE FROM poll_options WHERE id = ?", (option_id,))
        
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Error deleting poll option: {e}")
        return False


def get_voters_for_option(option_id):
    """
    Gets the list of users who voted for a specific option.
    
    Args:
        option_id: The ID of the poll option
    
    Returns:
        list: List of user dictionaries
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT 
            u.id, u.puid, u.username, u.display_name, 
            u.profile_picture_path, u.hostname
        FROM poll_votes pv
        JOIN users u ON pv.user_id = u.id
        WHERE pv.poll_option_id = ?
        ORDER BY pv.voted_at DESC
    """, (option_id,))
    
    voters = []
    for row in cursor.fetchall():
        voters.append(dict(row))
    
    return voters


def get_poll_option_by_text(poll_id, option_text):
    """
    Gets a poll option by its text (used for federation matching).
    
    Args:
        poll_id: The ID of the poll
        option_text: The text of the option
    
    Returns:
        dict: Option data or None if not found
    """
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT id, option_text, display_order, created_by_user_id
        FROM poll_options
        WHERE poll_id = ? AND option_text = ?
    """, (poll_id, option_text))
    
    row = cursor.fetchone()
    return dict(row) if row else None