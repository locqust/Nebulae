# routes/shortcuts.py
# Routes for the user shortcuts (favourites/star) feature.

from flask import Blueprint, request, jsonify, session
from db_queries.users import get_user_by_username, get_user_by_puid
from db_queries.shortcuts import (
    add_shortcut, remove_shortcut, is_shortcutted, get_shortcut_count, MAX_SHORTCUTS
)

shortcuts_bp = Blueprint('shortcuts', __name__, url_prefix='/shortcuts')


def _get_current_user():
    """Helper — returns the current user row, whether local or federated viewer."""
    if session.get('is_admin'):
        return None
    if session.get('username'):
        return get_user_by_username(session['username'])
    if session.get('is_federated_viewer') and session.get('federated_viewer_puid'):
        return get_user_by_puid(session['federated_viewer_puid'])
    return None


@shortcuts_bp.route('/add', methods=['POST'])
def add():
    """
    POST /shortcuts/add
    Body: { entity_type: 'user'|'group', entity_puid: '<puid>' }
    Returns: { success: bool, error?: str, count: int }
    """
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'error': 'Authentication required.'}), 401

    data = request.get_json(silent=True) or {}
    entity_type = data.get('entity_type', '').strip()
    entity_puid = data.get('entity_puid', '').strip()

    if not entity_type or not entity_puid:
        return jsonify({'success': False, 'error': 'Missing entity_type or entity_puid.'}), 400

    # Prevent self-shortcutting
    if entity_type == 'user' and entity_puid == user['puid']:
        return jsonify({'success': False, 'error': 'You cannot shortcut yourself.'}), 400

    ok, error = add_shortcut(user['id'], entity_type, entity_puid)
    if not ok:
        return jsonify({'success': False, 'error': error}), 400

    count = get_shortcut_count(user['id'])
    return jsonify({'success': True, 'count': count}), 200


@shortcuts_bp.route('/remove', methods=['POST'])
def remove():
    """
    POST /shortcuts/remove
    Body: { entity_type: 'user'|'group', entity_puid: '<puid>' }
    Returns: { success: bool, error?: str, count: int }
    """
    user = _get_current_user()
    if not user:
        return jsonify({'success': False, 'error': 'Authentication required.'}), 401

    data = request.get_json(silent=True) or {}
    entity_type = data.get('entity_type', '').strip()
    entity_puid = data.get('entity_puid', '').strip()

    if not entity_type or not entity_puid:
        return jsonify({'success': False, 'error': 'Missing entity_type or entity_puid.'}), 400

    ok = remove_shortcut(user['id'], entity_type, entity_puid)
    if not ok:
        return jsonify({'success': False, 'error': 'Could not remove shortcut.'}), 500

    count = get_shortcut_count(user['id'])
    return jsonify({'success': True, 'count': count}), 200


@shortcuts_bp.route('/status/<entity_type>/<entity_puid>', methods=['GET'])
def status(entity_type, entity_puid):
    """
    GET /shortcuts/status/<entity_type>/<entity_puid>
    Returns: { shortcutted: bool }
    Used by templates that need to check state after page load.
    """
    user = _get_current_user()
    if not user:
        return jsonify({'shortcutted': False}), 200

    shortcutted = is_shortcutted(user['id'], entity_type, entity_puid)
    return jsonify({'shortcutted': shortcutted}), 200
