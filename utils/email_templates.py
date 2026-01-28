# utils/email_templates.py
from flask import current_app

def get_base_url():
    """Get the base URL for the node"""
    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'
    hostname = current_app.config.get('NODE_HOSTNAME')
    return f"{protocol}://{hostname}"

def get_email_template(username, subject, preview_text, main_content, action_button_text=None, action_button_url=None, preview_content=None):
    """
    Generate a beautiful HTML email template.
    
    Args:
        username: The recipient's display name
        subject: Email subject line
        preview_text: Preview text that appears in email clients
        main_content: Main HTML content of the email
        action_button_text: Optional button text (e.g., "View Post")
        action_button_url: Optional button URL
    """
    base_url = get_base_url()
    logo_url = f"{base_url}/static/images/branding/logo_900x900.png"
    
    button_html = ""
    if action_button_text and action_button_url:
        button_html = f'''
        <tr>
            <td style="padding: 20px 0;">
                <table border="0" cellpadding="0" cellspacing="0" style="margin: 0 auto;">
                    <tr>
                        <td style="background-color: #4f46e5; border-radius: 8px; text-align: center;">
                            <a href="{action_button_url}" 
                               style="display: inline-block; padding: 14px 28px; color: #ffffff; text-decoration: none; font-weight: 600; font-size: 16px;">
                                {action_button_text}
                            </a>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
        '''
    
    preview_html = ""
    if preview_content:
        preview_html = f'''
                                    <tr>
                                        <td style="padding: 20px 0;">
                                            {preview_content}
                                        </td>
                                    </tr>
        '''

    html = f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="color-scheme" content="light dark">
        <meta name="supported-color-schemes" content="light dark">
        <title>{subject}</title>
        <style>
            body {{
                margin: 0;
                padding: 0;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background-color: #f3f4f6;
                color: #1f2937;
            }}
            table {{
                border-collapse: collapse;
            }}
            @media (prefers-color-scheme: dark) {{
                body {{
                    background-color: #1f2937 !important;
                    color: #f3f4f6 !important;
                }}
                .content-container {{
                    background-color: #374151 !important;
                    color: #f3f4f6 !important;
                }}
                .footer {{
                    color: #9ca3af !important;
                }}
            }}
        </style>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f3f4f6;">
        <div style="display: none; max-height: 0; overflow: hidden;">
            {preview_text}
        </div>
        
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f3f4f6; padding: 20px 0;">
            <tr>
                <td align="center">
                    <table border="0" cellpadding="0" cellspacing="0" width="600" style="max-width: 600px; width: 100%;">
                        
                        <tr>
                            <td align="center" style="padding: 20px 0 30px 0;">
                                <a href="{base_url}" style="text-decoration: none;">
                                    <img src="{logo_url}" 
                                         alt="Nebulae" 
                                         width="120" 
                                         height="120" 
                                         style="display: block; border: 0; border-radius: 16px;">
                                </a>
                            </td>
                        </tr>
                        
                        <tr>
                            <td class="content-container" style="background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); padding: 40px 30px;">
                                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                    <tr>
                                        <td style="padding-bottom: 20px;">
                                            <h2 style="margin: 0; font-size: 18px; font-weight: 600; color: #1f2937;">
                                                Hey {username}!
                                            </h2>
                                        </td>
                                    </tr>
                                    
                                    <tr>
                                        <td style="padding-bottom: 10px; line-height: 1.6; color: #4b5563;">
                                            {main_content}
                                        </td>
                                    </tr>
                                    {preview_html}
                                    
                                    {button_html}
                                </table>
                            </td>
                        </tr>
                        
                        <tr>
                            <td class="footer" align="center" style="padding: 30px 20px; color: #6b7280; font-size: 12px; line-height: 1.5;">
                                <p style="margin: 0 0 10px 0;">
                                    This notification was sent from your Nebulae instance at<br>
                                    <a href="{base_url}" style="color: #4f46e5; text-decoration: none;">{base_url}</a>
                                </p>
                                <p style="margin: 0;">
                                    You can manage your notification preferences in your 
                                    <a href="{base_url}" style="color: #4f46e5; text-decoration: none;">account settings</a>.
                                </p>
                            </td>
                        </tr>
                        
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    '''
    
    return html


def get_notification_content(notification_type, actor_name, **kwargs):
    """
    Generate notification-specific content with proper links.
    
    Returns: (main_content_html, button_text, button_url, preview_content_html)
    """
    base_url = get_base_url()
    
    # Extract common parameters
    post_cuid = kwargs.get('post_cuid')
    group_puid = kwargs.get('group_puid')
    group_name = kwargs.get('group_name')
    event_puid = kwargs.get('event_puid')
    event_title = kwargs.get('event_title')
    muid = kwargs.get('muid')
    media_filename = kwargs.get('media_filename')
    
    # Notification type specific content
    if notification_type == 'friend_request':
        return (
            f"<p><strong>{actor_name}</strong> sent you a friend request.</p>",
            "View Request",
            f"{base_url}/",
            None
        )
    
    elif notification_type == 'friend_accept':
        return (
            f"<p><strong>{actor_name}</strong> accepted your friend request! You're now connected.</p>",
            f"View {actor_name}'s Profile",
            f"{base_url}/u/{kwargs.get('actor_puid')}" if kwargs.get('actor_puid') else base_url,
            None
        )
    
    elif notification_type == 'wall_post':
        return (
            f"<p><strong>{actor_name}</strong> posted on your wall.</p>",
            "View Post",
            f"{base_url}/post/{post_cuid}" if post_cuid else base_url,
            None
        )
    
    elif notification_type in ['mention', 'everyone_mention']:
        mention_type = "mentioned everyone" if notification_type == 'everyone_mention' else "mentioned you"
        context = ""
        button_url = base_url
        
        if group_puid and group_name:
            context = f" in <strong>{group_name}</strong>"
            button_url = f"{base_url}/group/{group_puid}"
        elif post_cuid:
            button_url = f"{base_url}/post/{post_cuid}"
        
        return (
            f"<p><strong>{actor_name}</strong> {mention_type}{context}.</p>",
            "View Post",
            button_url,
            None
        )
    
    elif notification_type == 'event_invite':
        preview_html = None
        
        # Generate event preview if we have the details
        if event_title and kwargs.get('event_datetime'):
            preview_html = get_event_preview_html(
                event_title=event_title,
                event_datetime=kwargs.get('event_datetime'),
                event_location=kwargs.get('event_location'),
                event_details=kwargs.get('event_details')
            )
        
        return (
            f"<p><strong>{actor_name}</strong> invited you to an event: <strong>{event_title}</strong></p>",
            "View Event",
            f"{base_url}/event/{event_puid}" if event_puid else base_url,
            preview_html
        )
    
    elif notification_type == 'event_update':
        preview_html = None
        
        if event_title and kwargs.get('event_datetime'):
            preview_html = get_event_preview_html(
                event_title=event_title,
                event_datetime=kwargs.get('event_datetime'),
                event_location=kwargs.get('event_location'),
                event_details=kwargs.get('event_details')
            )
        
        return (
            f"<p>An event you're attending (<strong>{event_title}</strong>) has been updated by <strong>{actor_name}</strong>.</p>",
            "View Event",
            f"{base_url}/event/{event_puid}" if event_puid else base_url,
            preview_html
        )
    
    elif notification_type == 'event_cancelled':
        return (
            f"<p>Unfortunately, the event <strong>{event_title}</strong> has been cancelled.</p>",
            None,
            None,
            None
        )
    
    elif notification_type == 'tagged_in_post':
        context = f" in <strong>{group_name}</strong>" if group_name else ""
        return (
            f"<p><strong>{actor_name}</strong> tagged you in a post{context}.</p>",
            "View Post",
            f"{base_url}/post/{post_cuid}" if post_cuid else base_url,
            None
        )
    
    elif notification_type == 'tagged_in_media':
        preview_html = None
        
        # Generate media preview if we have the URL
        if muid and media_filename:
            media_url = f"{base_url}/serve_media/{muid}"
            preview_html = get_media_preview_html(media_url, media_filename)
        
        return (
            f"<p><strong>{actor_name}</strong> tagged you in a photo or video.</p>",
            "View Media",
            f"{base_url}/media/{muid}" if muid else base_url,
            preview_html
        )
    
    elif notification_type == 'media_mention':
        return (
            f"<p><strong>{actor_name}</strong> mentioned you in a media post.</p>",
            "View Media",
            f"{base_url}/media/{muid}" if muid else base_url,
            None
        )
    
    elif notification_type == 'group_post':
        return (
            f"<p><strong>{actor_name}</strong> posted in <strong>{group_name}</strong>.</p>",
            "View Post",
            f"{base_url}/post/{post_cuid}" if post_cuid else f"{base_url}/group/{group_puid}",
            None
        )
    
    elif notification_type == 'group_request_accepted':
        return (
            f"<p>Your request to join <strong>{group_name}</strong> was accepted!</p>",
            "View Group",
            f"{base_url}/group/{group_puid}" if group_puid else base_url,
            None
        )
    
    elif notification_type == 'parental_approval_needed':
        return (
            f"<p><strong>{actor_name}</strong> needs your approval for a remote action.</p>",
            "Review Request",
            f"{base_url}/",
            None
        )
    
    elif notification_type == 'parental_approval_approved':
        return (
            f"<p>Your request was approved by <strong>{actor_name}</strong>.</p>",
            "View Notifications",
            base_url,
            None
        )
    
    elif notification_type == 'parental_approval_denied':
        return (
            f"<p>Your request was denied by <strong>{actor_name}</strong>.</p>",
            "View Notifications",
            base_url,
            None
        )
    
    # Default fallback
    return (
        f"<p>You have a new notification from <strong>{actor_name}</strong>.</p>",
        "View Notification",
        base_url,
        None
    )

def get_media_preview_html(media_url, media_filename):
    """
    Generate HTML for media thumbnail preview in emails.
    
    Args:
        media_url: Full URL to the media file
        media_filename: Name of the media file (used only for type detection)
    """
    # Determine if it's a video based on extension
    video_extensions = ('.mp4', '.mov', '.avi', '.webm', '.mkv')
    is_video = any(media_filename.lower().endswith(ext) for ext in video_extensions)
    
    if is_video:
        # For videos, show a placeholder with play icon
        return f'''
        <div style="background-color: #f3f4f6; border-radius: 8px; padding: 20px; text-align: center; border: 2px solid #e5e7eb;">
            <div style="background-color: #1f2937; border-radius: 8px; padding: 40px; display: inline-block;">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="12" cy="12" r="10" fill="#4f46e5"/>
                    <path d="M10 8l6 4-6 4V8z" fill="white"/>
                </svg>
            </div>
            <p style="margin: 10px 0 0 0; color: #6b7280; font-size: 14px;">
                Video
            </p>
        </div>
        '''
    else:
        # For images, show the actual thumbnail (no filename caption)
        return f'''
        <div style="text-align: center;">
            <img src="{media_url}" 
                 alt="Tagged media" 
                 style="max-width: 100%; height: auto; border-radius: 8px; border: 2px solid #e5e7eb; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
        </div>
        '''


def get_event_preview_html(event_title, event_datetime, event_location, event_details):
    """
    Generate HTML for event card preview in emails.
    
    Args:
        event_title: Title of the event
        event_datetime: Formatted datetime string
        event_location: Location of the event
        event_details: Event description/details
    """
    # Truncate details if too long
    max_detail_length = 200
    truncated_details = event_details[:max_detail_length] + '...' if event_details and len(event_details) > max_detail_length else event_details
    
    location_html = f'''
    <tr>
        <td style="padding: 8px 0; display: flex; align-items: start;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#4f46e5" stroke-width="2" style="margin-right: 8px; flex-shrink: 0;">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/>
                <circle cx="12" cy="10" r="3"/>
            </svg>
            <span style="color: #4b5563; font-size: 14px;">{event_location}</span>
        </td>
    </tr>
    ''' if event_location else ''
    
    details_html = f'''
    <tr>
        <td style="padding: 12px 0;">
            <p style="margin: 0; color: #6b7280; font-size: 14px; line-height: 1.5;">
                {truncated_details}
            </p>
        </td>
    </tr>
    ''' if truncated_details else ''
    
    return f'''
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 3px;">
        <div style="background-color: #ffffff; border-radius: 10px; padding: 20px;">
            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                    <td style="padding-bottom: 12px;">
                        <h3 style="margin: 0; font-size: 18px; font-weight: 700; color: #1f2937;">
                            {event_title}
                        </h3>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; display: flex; align-items: start;">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#4f46e5" stroke-width="2" style="margin-right: 8px; flex-shrink: 0;">
                            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                            <line x1="16" y1="2" x2="16" y2="6"/>
                            <line x1="8" y1="2" x2="8" y2="6"/>
                            <line x1="3" y1="10" x2="21" y2="10"/>
                        </svg>
                        <span style="color: #4b5563; font-size: 14px; font-weight: 600;">{event_datetime}</span>
                    </td>
                </tr>
                {location_html}
                {details_html}
            </table>
        </div>
    </div>
    '''