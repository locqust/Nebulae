# routes/discovery_filters.py
"""
Routes for managing discovery list filters (hiding/unhiding items).
"""
from flask import Blueprint, request, jsonify, session
from db_queries.users import get_user_id_by_username
from db_queries.hidden_items import hide_item, unhide_item, get_hidden_users_with_details, get_hidden_groups_with_details

discovery_filters_bp = Blueprint('discovery_filters', __name__)

@discovery_filters_bp.route('/api/hide_item', methods=['POST'])
def api_hide_item():
    """Hide an item from discovery lists."""
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    current_user_id = get_user_id_by_username(session['username'])
    if not current_user_id:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    item_type = data.get('item_type')  # 'user', 'group', or 'page'
    item_id = data.get('item_id')
    
    if not item_type or not item_id:
        return jsonify({'error': 'Missing item_type or item_id'}), 400
    
    if item_type not in ['user', 'group', 'page']:
        return jsonify({'error': 'Invalid item_type'}), 400
    
    if hide_item(current_user_id, item_type, item_id):
        return jsonify({'status': 'success', 'message': 'Item hidden successfully'})
    else:
        return jsonify({'error': 'Failed to hide item'}), 500

@discovery_filters_bp.route('/api/unhide_item', methods=['POST'])
def api_unhide_item():
    """Unhide a previously hidden item."""
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    current_user_id = get_user_id_by_username(session['username'])
    if not current_user_id:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    item_type = data.get('item_type')  # 'user', 'group', or 'page'
    item_id = data.get('item_id')
    
    if not item_type or not item_id:
        return jsonify({'error': 'Missing item_type or item_id'}), 400
    
    if item_type not in ['user', 'group', 'page']:
        return jsonify({'error': 'Invalid item_type'}), 400
    
    if unhide_item(current_user_id, item_type, item_id):
        return jsonify({'status': 'success', 'message': 'Item unhidden successfully'})
    else:
        return jsonify({'error': 'Failed to unhide item'}), 500

@discovery_filters_bp.route('/api/get_hidden_users')
def api_get_hidden_users():
    """Get all hidden users and pages for the current user."""
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    current_user_id = get_user_id_by_username(session['username'])
    if not current_user_id:
        return jsonify({'error': 'User not found'}), 404
    
    hidden_items = get_hidden_users_with_details(current_user_id)
    return jsonify(hidden_items)

@discovery_filters_bp.route('/api/get_hidden_groups')
def api_get_hidden_groups():
    """Get all hidden groups for the current user."""
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    current_user_id = get_user_id_by_username(session['username'])
    if not current_user_id:
        return jsonify({'error': 'User not found'}), 404
    
    hidden_groups = get_hidden_groups_with_details(current_user_id)
    return jsonify(hidden_groups)