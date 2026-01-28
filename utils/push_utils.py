# utils/push_utils.py
"""
Utilities for sending Web Push notifications.
"""

import json
import traceback
import os
from datetime import datetime
from pywebpush import webpush, WebPushException
from db_queries.push_subscriptions import (
    get_push_subscriptions_for_user,
    delete_push_subscription
)
from utils.vapid_utils import get_vapid_keys_from_config

def send_push_notification(user_id, title, body, url, icon_url=None):
    """
    Send a push notification to all of a user's subscribed devices.
    
    Args:
        user_id: The ID of the user to notify
        title: The notification title
        body: The notification body text
        url: The URL to navigate to when clicked
        icon_url: Optional icon URL
    
    Returns:
        Dictionary with success count and failed endpoints
    """
    # Get VAPID keys
    vapid_keys = get_vapid_keys_from_config()
    if not vapid_keys:
        print("VAPID keys not configured. Push notifications disabled.")
        return {'success': 0, 'failed': []}
    
    # Get user's subscriptions
    subscriptions = get_push_subscriptions_for_user(user_id)
    if not subscriptions:
        return {'success': 0, 'failed': []}
    
    # Prepare the notification payload
    payload = json.dumps({
        'title': title,
        'body': body,
        'url': url,
        'icon': icon_url or '/static/icons/icon-192x192.png',
        'badge': '/static/icons/icon-192x192.png',
        'timestamp': int(datetime.now().timestamp() * 1000)
    })
    
    success_count = 0
    failed_endpoints = []
    
    # Send to each subscription
    for subscription in subscriptions:
        try:
            subscription_info = {
                'endpoint': subscription['endpoint'],
                'keys': {
                    'p256dh': subscription['p256dh_key'],
                    'auth': subscription['auth_key']
                }
            }
            
            # Save private key to a temporary file since pywebpush/py-vapid
            # doesn't reliably load from string
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
                f.write(vapid_keys['private_key'])
                temp_key_file = f.name
            
            try:
                webpush(
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=temp_key_file,  # Pass file path
                    vapid_claims={
                        "sub": f"mailto:admin@{os.environ.get('NODE_HOSTNAME', 'localhost')}"
                    }
                )
                
                success_count += 1
                print(f"Successfully sent push to endpoint: {subscription['endpoint'][:50]}...")
            finally:
                # Clean up temp file
                import os as os_module
                try:
                    os_module.unlink(temp_key_file)
                except:
                    pass
            
        except WebPushException as e:
            print(f"Push failed for endpoint {subscription['endpoint']}: {e}")
            
            # If the subscription is no longer valid, remove it
            if e.response and e.response.status_code in [404, 410]:
                print(f"Removing invalid subscription: {subscription['endpoint']}")
                delete_push_subscription(user_id, subscription['endpoint'])
            
            failed_endpoints.append(subscription['endpoint'])
            
        except Exception as e:
            print(f"Unexpected error sending push: {e}")
            traceback.print_exc()
            failed_endpoints.append(subscription['endpoint'])
    
    return {
        'success': success_count,
        'failed': failed_endpoints
    }