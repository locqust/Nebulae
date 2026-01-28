# routes/polls.py
# Handles poll-related routes

import json
from flask import Blueprint, request, jsonify, session, flash, redirect, url_for
from db_queries.users import get_user_by_username, get_user_by_puid
from db_queries.posts import get_post_by_cuid
from db_queries.polls import (
    vote_on_poll, remove_vote_from_poll, add_poll_option,
    delete_poll_option, get_voters_for_option, get_poll_by_post_id
)

polls_bp = Blueprint('polls', __name__)


@polls_bp.route('/polls/vote/<string:post_cuid>/<int:option_id>', methods=['POST'])
def vote_on_poll_route(post_cuid, option_id):
    """Allows a logged-in user to vote on a poll option."""
    current_user = None
    
    # Check for both local and federated viewers
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
    
    if not current_user:
        return jsonify({'error': 'Please log in to vote'}), 401
    
    # Verify post exists
    post = get_post_by_cuid(post_cuid)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    
    # Cast vote
    success = vote_on_poll(option_id, current_user['id'])
    
    if success:
        # NEW: Distribute vote to federation
        from utils.federation_utils import distribute_poll_vote
        distribute_poll_vote(post_cuid, option_id, current_user['puid'], True)
        
        return jsonify({'success': True, 'message': 'Vote recorded'}), 200
    else:
        return jsonify({'error': 'Failed to vote'}), 500


@polls_bp.route('/polls/unvote/<string:post_cuid>/<int:option_id>', methods=['POST'])
def unvote_on_poll_route(post_cuid, option_id):
    """Removes a vote from a poll option (for multi-choice polls)."""
    current_user = None
    
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
    
    if not current_user:
        return jsonify({'error': 'Please log in'}), 401
    
    success = remove_vote_from_poll(option_id, current_user['id'])
    
    if success:
        # NEW: Distribute unvote to federation
        from utils.federation_utils import distribute_poll_vote
        distribute_poll_vote(post_cuid, option_id, current_user['puid'], False)
        
        return jsonify({'success': True, 'message': 'Vote removed'}), 200
    else:
        return jsonify({'error': 'Failed to remove vote'}), 500


@polls_bp.route('/polls/data/<string:post_cuid>', methods=['GET'])
def get_poll_data_route(post_cuid):
    """Gets poll data for a post."""
    current_user = None
    viewer_user_id = None
    
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
        if current_user:
            viewer_user_id = current_user['id']
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
        if current_user:
            viewer_user_id = current_user['id']
    
    post = get_post_by_cuid(post_cuid)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    
    poll = get_poll_by_post_id(post['id'], viewer_user_id)
    
    if not poll:
        return jsonify({'error': 'No poll found'}), 404
    
    # Add is_creator flag
    if current_user:
        poll['is_creator'] = (post['user_id'] == current_user['id'])
    else:
        poll['is_creator'] = False
    
    return jsonify({'success': True, 'poll': poll}), 200


@polls_bp.route('/polls/voters/<int:option_id>', methods=['GET'])
def get_poll_voters_route(option_id):
    """Gets the list of voters for a specific poll option."""
    voters = get_voters_for_option(option_id)
    
    return jsonify({'success': True, 'voters': voters}), 200


@polls_bp.route('/polls/add_option/<string:post_cuid>', methods=['POST'])
def add_poll_option_route(post_cuid):
    """Adds a user-created option to a poll."""
    current_user = None
    
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
    
    if not current_user:
        return jsonify({'error': 'Please log in'}), 401
    
    data = request.get_json()
    option_text = data.get('option_text', '').strip()
    
    if not option_text:
        return jsonify({'error': 'Option text is required'}), 400
    
    if len(option_text) > 200:
        return jsonify({'error': 'Option text too long'}), 400
    
    # Get post and poll
    post = get_post_by_cuid(post_cuid)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    
    poll = get_poll_by_post_id(post['id'])
    if not poll:
        return jsonify({'error': 'Poll not found'}), 404
    
    if not poll['allow_add_options']:
        return jsonify({'error': 'Adding options is not allowed'}), 403
    
    # Check for duplicate option text
    from db_queries.polls import get_poll_option_by_text
    existing_option = get_poll_option_by_text(poll['id'], option_text)
    if existing_option:
        return jsonify({'error': 'This option already exists'}), 400
    
    # Add option
    option_id = add_poll_option(poll['id'], option_text, current_user['id'])
    
    if option_id:
        # NEW: Distribute the new option to federation
        from utils.federation_utils import distribute_poll_option_add
        distribute_poll_option_add(post_cuid, option_text, current_user['puid'])
        
        return jsonify({'success': True, 'option_id': option_id}), 200
    else:
        return jsonify({'error': 'Failed to add option'}), 500


@polls_bp.route('/polls/delete_option/<int:option_id>', methods=['DELETE'])
def delete_poll_option_route(option_id):
    """Deletes a user-added poll option."""
    current_user = None
    
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
    
    if not current_user:
        return jsonify({'error': 'Please log in'}), 401
    
    # Get option details before deletion for federation
    from db import get_db
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT po.option_text, p.post_id, posts.cuid
        FROM poll_options po
        JOIN polls p ON po.poll_id = p.id
        JOIN posts ON p.post_id = posts.id
        WHERE po.id = ?
    """, (option_id,))
    
    option_row = cursor.fetchone()
    if option_row:
        option_text = option_row['option_text']
        post_cuid = option_row['cuid']
    else:
        option_text = None
        post_cuid = None
    
    success = delete_poll_option(option_id, current_user['id'])
    
    if success:
        # NEW: Distribute the deletion to federation
        if option_text and post_cuid:
            from utils.federation_utils import distribute_poll_option_delete
            distribute_poll_option_delete(post_cuid, option_text)
        
        return jsonify({'success': True, 'message': 'Option deleted'}), 200
    else:
        return jsonify({'error': 'Failed to delete option'}), 403