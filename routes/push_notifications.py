# routes/push_notifications.py
"""
Routes for managing push notification subscriptions.
"""

from flask import Blueprint, request, jsonify, session
from db_queries.users import get_user_id_by_username
from db_queries.push_subscriptions import (
    save_push_subscription,
    get_push_subscriptions_for_user,
    delete_push_subscription
)
from utils.vapid_utils import get_vapid_keys_from_config

push_notifications_bp = Blueprint('push_notifications', __name__)

@push_notifications_bp.before_request
def login_required():
    """Ensures a user is logged in before accessing push notification routes."""
    if 'username' not in session:
        return jsonify({'error': 'Authentication required'}), 401

@push_notifications_bp.route('/push/vapid_public_key', methods=['GET'])
def get_vapid_public_key():
    """
    Returns the VAPID public key needed for push subscription.
    """
    vapid_keys = get_vapid_keys_from_config()
    
    if not vapid_keys:
        return jsonify({'error': 'Push notifications not configured'}), 503
    
    return jsonify({'public_key': vapid_keys['public_key']})

@push_notifications_bp.route('/push/subscribe', methods=['POST'])
def subscribe_to_push():
    """
    Save a push notification subscription for the current user.
    
    Expected JSON payload:
    {
        "endpoint": "https://...",
        "keys": {
            "p256dh": "...",
            "auth": "..."
        }
    }
    """
    user_id = get_user_id_by_username(session['username'])
    if not user_id:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request data'}), 400
    
    endpoint = data.get('endpoint')
    keys = data.get('keys', {})
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')
    
    if not endpoint or not p256dh or not auth:
        return jsonify({'error': 'Missing required subscription data'}), 400
    
    user_agent = request.headers.get('User-Agent')
    
    if save_push_subscription(user_id, endpoint, p256dh, auth, user_agent):
        return jsonify({'message': 'Push subscription saved successfully'}), 200
    else:
        return jsonify({'error': 'Failed to save push subscription'}), 500

@push_notifications_bp.route('/push/unsubscribe', methods=['POST'])
def unsubscribe_from_push():
    """
    Remove a push notification subscription for the current user.
    
    Expected JSON payload:
    {
        "endpoint": "https://..."
    }
    """
    user_id = get_user_id_by_username(session['username'])
    if not user_id:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request data'}), 400
    
    endpoint = data.get('endpoint')
    if not endpoint:
        return jsonify({'error': 'Missing endpoint'}), 400
    
    if delete_push_subscription(user_id, endpoint):
        return jsonify({'message': 'Push subscription removed successfully'}), 200
    else:
        return jsonify({'error': 'Failed to remove push subscription'}), 500

@push_notifications_bp.route('/push/subscriptions', methods=['GET'])
def get_subscriptions():
    """
    Get all push subscriptions for the current user.
    """
    user_id = get_user_id_by_username(session['username'])
    if not user_id:
        return jsonify({'error': 'User not found'}), 404
    
    subscriptions = get_push_subscriptions_for_user(user_id)
    
    # Remove sensitive keys from response
    safe_subscriptions = []
    for sub in subscriptions:
        safe_subscriptions.append({
            'id': sub['id'],
            'endpoint': sub['endpoint'],
            'user_agent': sub['user_agent'],
            'created_at': sub['created_at'],
            'last_used': sub['last_used']
        })
    
    return jsonify(safe_subscriptions), 200
