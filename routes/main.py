# routes/main.py
import os
import json
import base64
import shutil
import traceback
from urllib.parse import quote, unquote
import requests
import hmac
import hashlib
from werkzeug.utils import secure_filename
import time

from flask import (Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app,
                   send_from_directory, abort)

# Import database functions from the new query modules
from db import get_db
from db_queries.users import (get_user_by_username, get_user_id_by_username, update_user_profile_picture_path,
                              update_user_display_name, get_user_by_puid, get_user_by_id)
from db_queries.posts import (get_posts_for_feed, add_post, update_post,
                              delete_post, get_posts_for_profile_timeline, get_media_for_user_gallery,
                              get_post_by_cuid, get_media_by_muid, get_muid_by_media_path,
                              disable_comments_for_post, remove_user_tag_from_post, 
                              remove_mention_from_post, hide_post_for_user) # NEW: Import disable_comments_for_post
from db_queries.profiles import (get_profile_info_for_user, update_profile_info_field, add_family_relationship,
                                 remove_family_relationship, get_family_relationships_for_user,
                                 get_relationship_by_id, update_family_relationship)
from db_queries.friends import (get_friends_list, get_friendship_details, get_friendship_status,
                                is_friends_with, get_friend_relationship, get_pending_friend_requests,
                                get_outgoing_friend_requests, get_blocked_friends_list)
from db_queries.federation import get_node_by_hostname, get_or_create_remote_user
# MODIFICATION: Import group moderator check
from db_queries.groups import is_user_group_admin, is_user_group_moderator_or_admin
from db_queries.settings import get_user_settings
from db_queries.followers import follow_page, unfollow_page, is_following, get_followers


# Import media and federation utilities
from utils.media import list_media_content, allowed_file, get_media_by_id, update_media_alt_text
from utils.federation_utils import (get_remote_node_api_url, distribute_post, distribute_post_update,
                                    distribute_post_delete,
                                    distribute_post_comment_status_update) # NEW: Import
from db_queries.comments import get_comment_by_internal_id, get_comment_by_cuid, get_media_by_muid_from_comment
from db_queries.media import (add_media_tags, remove_media_tag, get_media_tags, 
                              add_media_comment, get_media_comments, get_media_comment_by_cuid,
                              update_media_comment, delete_media_comment, 
                              hide_media_comment_for_user, get_comment_media_details_by_muid)
from db_queries.notifications import get_unread_notification_count

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """
    Renders the main index page.
    """
    viewer_token = request.args.get('viewer_token')
    if viewer_token:
        session['viewer_token'] = viewer_token
        return redirect(url_for('main.index'))

    posts = []
    current_username = session.get('username')
    is_admin_session = session.get('is_admin', False)
    current_user_id = None
    user_media_path = None
    current_user_puid = None
    current_user_profile = None

    if current_username:
        user_data = get_user_by_username(current_username)
        if user_data:
            current_user_id = user_data['id']
            user_media_path = user_data['media_path']
            current_user_puid = user_data['puid']
            is_admin_session = (user_data['user_type'] == 'admin')
            session['is_admin'] = is_admin_session
            current_user_profile = user_data
        else:
            flash('Your user account could not be found. Please log in again.', 'danger')
            session.clear()
            return redirect(url_for('auth.login'))

    # MODIFICATION: Post fetching is moved to its own API endpoint.
    # This route now just serves the main shell.
    # posts = get_posts_for_feed(current_user_id=current_user_id, current_user_is_admin=is_admin_session)

    viewer_home_url = None
    viewer_puid_for_js = None
    if current_user_id:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"
        viewer_puid_for_js = current_user_puid
        
    # NEW: Pass the URL for the initial content to load
    initial_content_url = url_for('main.get_feed_content')

    from db_queries.parental_controls import requires_parental_approval
    
    # Add to context
    current_user_requires_parental_approval = requires_parental_approval(current_user_id) if current_user_id else False

    return render_template('index.html',
                           username=current_username,
                           # posts=posts, # Posts are no longer passed here
                           user_media_path=user_media_path,
                           current_user_puid=current_user_puid,
                           current_user_id=current_user_id,
                           current_user_profile=current_user_profile,
                           viewer_home_url=viewer_home_url,
                           viewer_puid_for_js=viewer_puid_for_js,
                           initial_content_url=initial_content_url,
                           current_user_requires_parental_approval=current_user_requires_parental_approval)


@main_bp.route('/api/page/feed')
def get_feed_content():
    """
    API endpoint to fetch the HTML for the main feed content.
    """
    posts = []
    current_username = session.get('username')
    is_admin_session = session.get('is_admin', False)
    current_user_id = None
    user_media_path = None
    current_user_puid = None
    current_user_profile = None

    if current_username:
        user_data = get_user_by_username(current_username)
        if user_data:
            current_user_id = user_data['id']
            user_media_path = user_data['media_path']
            current_user_puid = user_data['puid']
            is_admin_session = (user_data['user_type'] == 'admin')
            session['is_admin'] = is_admin_session
            current_user_profile = user_data
        else:
            # This should ideally not be reachable if index() already checked
            flash('Your user account could not be found. Please log in again.', 'danger')
            session.clear()
            return redirect(url_for('auth.login'))

    posts = get_posts_for_feed(current_user_id=current_user_id, current_user_is_admin=is_admin_session, page=1, limit=20)

    # NEW: Get friend PUIDs for snooze/block actions in post menus
    friend_puids = set()
    if current_user_id:
        from db_queries.friends import get_all_friends_puid
        friend_puids = get_all_friends_puid(current_user_id)

    viewer_home_url = None
    viewer_puid_for_js = None
    if current_user_id:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"
        viewer_puid_for_js = current_user_puid
    
    from db_queries.parental_controls import requires_parental_approval
    
    # Add to context
    current_user_requires_parental_approval = requires_parental_approval(current_user_id) if current_user_id else False

    # Render the *partial* template
    return render_template('_feed_content.html',
                           username=current_username,
                           posts=posts,
                           user_media_path=user_media_path,
                           current_user_puid=current_user_puid,
                           current_user_id=current_user_id,
                           current_user_profile=current_user_profile,
                           viewer_home_url=viewer_home_url,
                           viewer_puid_for_js=viewer_puid_for_js,
                           friend_puids=friend_puids,
                           current_user_requires_parental_approval=current_user_requires_parental_approval)

@main_bp.route('/api/feed/posts')
def get_feed_posts_api():
    """
    API endpoint to fetch paginated posts for the main feed.
    Returns JSON with rendered HTML for each post.
    """
    if 'username' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    
    current_user_id = current_user['id']
    is_admin = (current_user['user_type'] == 'admin')
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    # Validate parameters
    if page < 1:
        page = 1
    if limit < 1 or limit > 50:  # Max 50 posts per page
        limit = 20
    
    # Get paginated posts
    posts = get_posts_for_feed(
        current_user_id=current_user_id,
        current_user_is_admin=is_admin,
        page=page,
        limit=limit
    )
    
    # NEW: Get friend PUIDs for snooze/block actions in post menus
    friend_puids = set()
    if current_user_id:
        from db_queries.friends import get_all_friends_puid
        friend_puids = get_all_friends_puid(current_user_id)
    
    from db_queries.parental_controls import requires_parental_approval
    
    # Add to context
    current_user_requires_parental_approval = requires_parental_approval(current_user_id) if current_user_id else False

    # Render each post to HTML
    rendered_posts = []
    for post in posts:
        html = render_template('_post_template.html',
                             post=post,
                             current_user_id=current_user_id,
                             current_user_puid=current_user['puid'],
                             current_user=current_user,
                             is_admin=is_admin,
                             is_federated_viewer=False,
                             viewer_home_url=f"http://{current_app.config.get('NODE_HOSTNAME')}",
                             friend_puids=friend_puids,
                             current_user_requires_parental_approval=current_user_requires_parental_approval)
        rendered_posts.append(html)
    
    return jsonify({'posts': rendered_posts})

@main_bp.route('/api/feed/check_new')
def check_new_feed_posts():
    """
    Check if there are new posts in the feed since a given timestamp.
    Returns JSON with has_new_posts boolean.
    """
    since_timestamp = request.args.get('since')
    
    if not since_timestamp:
        return jsonify({'has_new_posts': False}), 400
    
    current_username = session.get('username')
    
    if not current_username:
        return jsonify({'has_new_posts': False}), 401
    
    user_data = get_user_by_username(current_username)
    if not user_data:
        return jsonify({'has_new_posts': False}), 401
    
    current_user_id = user_data['id']
    is_admin_session = user_data['user_type'] == 'admin'
    
    
    # Check if there are posts newer than the timestamp
    from db_queries.posts import check_new_posts_in_feed
    has_new = check_new_posts_in_feed(
        current_user_id=current_user_id,
        current_user_is_admin=is_admin_session,
        since_timestamp=since_timestamp
    )
    
    return jsonify({'has_new_posts': has_new})

@main_bp.route('/api/profile/<puid>/posts')
def get_profile_posts_api(puid):
    """
    API endpoint to fetch paginated posts for a user's profile timeline.
    Returns JSON with rendered HTML for each post.
    """
    # Determine viewer
    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if not viewer_puid:
            return jsonify({'error': 'Unauthorized'}), 401
        current_viewer = get_user_by_puid(viewer_puid)
    elif 'username' in session:
        current_viewer = get_user_by_username(session['username'])
    else:
        return jsonify({'error': 'Authentication required'}), 401
    
    if not current_viewer:
        return jsonify({'error': 'Viewer not found'}), 404
    
    # Get the profile user
    profile_user = get_user_by_puid(puid)
    if not profile_user:
        return jsonify({'error': 'Profile not found'}), 404
    
    current_viewer_id = current_viewer['id']
    is_admin = (current_viewer.get('user_type') == 'admin')
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    # Validate parameters
    if page < 1:
        page = 1
    if limit < 1 or limit > 50:
        limit = 20
    
    # Get paginated posts
    posts = get_posts_for_profile_timeline(
        profile_user_puid=puid,
        viewer_user_id=current_viewer_id,
        viewer_is_admin=is_admin,
        page=page,
        limit=limit
    )
    
    # Determine viewer info for templates
    is_federated_viewer = session.get('is_federated_viewer', False)
    if is_federated_viewer:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        viewer_home_url = f"{protocol}://{current_viewer.get('hostname')}"
    else:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"
    
    from db_queries.parental_controls import requires_parental_approval
    
    # Add to context
    current_user_requires_parental_approval = requires_parental_approval(current_viewer_id) if current_viewer_id else False
    
    # Render each post to HTML
    rendered_posts = []
    for post in posts:
        html = render_template('_post_template.html',
                             post=post,
                             current_user_id=current_viewer_id,
                             current_user_puid=current_viewer['puid'],
                             current_user=current_viewer,
                             is_admin=is_admin,
                             is_federated_viewer=is_federated_viewer,
                             viewer_home_url=viewer_home_url,
                             current_user_requires_parental_approval=current_user_requires_parental_approval)
        rendered_posts.append(html)
    
    return jsonify({'posts': rendered_posts})

@main_bp.route('/api/page/<puid>/posts')
def get_page_posts_api(puid):
    """
    API endpoint to fetch paginated posts for a public page's timeline.
    Returns JSON with rendered HTML for each post.
    """
    # Determine viewer
    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if not viewer_puid:
            return jsonify({'error': 'Unauthorized'}), 401
        current_viewer = get_user_by_puid(viewer_puid)
    elif 'username' in session:
        current_viewer = get_user_by_username(session['username'])
    else:
        return jsonify({'error': 'Authentication required'}), 401
    
    if not current_viewer:
        return jsonify({'error': 'Viewer not found'}), 404
    
    # Get the public page
    page_user = get_user_by_puid(puid)
    if not page_user or page_user.get('user_type') != 'public_page':
        return jsonify({'error': 'Public page not found'}), 404
    
    current_viewer_id = current_viewer['id']
    is_admin = (current_viewer.get('user_type') == 'admin')
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    
    # Validate parameters
    if page < 1:
        page = 1
    if limit < 1 or limit > 50:
        limit = 20
    
    # Get paginated posts
    posts = get_posts_for_profile_timeline(
        profile_user_puid=puid,
        viewer_user_id=current_viewer_id,
        viewer_is_admin=is_admin,
        page=page,
        limit=limit
    )
    
    # Determine viewer info for templates
    is_federated_viewer = session.get('is_federated_viewer', False)
    if is_federated_viewer:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        viewer_home_url = f"{protocol}://{current_viewer.get('hostname')}"
    else:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"

    from db_queries.parental_controls import requires_parental_approval
    
    # Add to context
    current_user_requires_parental_approval = requires_parental_approval(current_viewer_id) if current_viewer_id else False
    
    # Render each post to HTML
    rendered_posts = []
    for post in posts:
        html = render_template('_post_template.html',
                             post=post,
                             current_user_id=current_viewer_id,
                             current_user_puid=current_viewer['puid'],
                             current_user=current_viewer,
                             is_admin=is_admin,
                             is_federated_viewer=is_federated_viewer,
                             viewer_home_url=viewer_home_url,
                             current_user_requires_parental_approval=current_user_requires_parental_approval)
        rendered_posts.append(html)
    
    return jsonify({'posts': rendered_posts})

@main_bp.route('/my_media/')
def my_media_gallery_page():
    """
    Renders the main index.html "shell" and tells the client-side
    router to load the "My Media" content.
    """
    if 'username' not in session or session.get('is_admin'):
        flash('Please log in to view your media gallery.', 'danger')
        return redirect(url_for('auth.login'))

    current_user_id = get_user_id_by_username(session['username'])
    if not current_user_id:
        flash('User not found.', 'danger')
        return redirect(url_for('main.index'))

    # Fetch all the data needed for the header/sidebar, just like index()
    current_username = session.get('username')
    user_data = get_user_by_username(current_username)
    user_media_path = None
    current_user_puid = None
    current_user_profile = None
    viewer_home_url = None
    
    if user_data:
        user_media_path = user_data['media_path']
        current_user_puid = user_data['puid']
        current_user_profile = user_data
        
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"

    # Pass the URL for the "My Media" content to load
    initial_content_url = url_for('main.get_my_media_content')

    return render_template('index.html',
                           username=current_username,
                           user_media_path=user_media_path,
                           current_user_puid=current_user_puid,
                           current_user_id=current_user_id,
                           current_user_profile=current_user_profile,
                           viewer_home_url=viewer_home_url,
                           viewer_puid_for_js=current_user_puid,
                           initial_content_url=initial_content_url,
                           is_my_media_page=True)


@main_bp.route('/api/page/my_media')
def get_my_media_content():
    """
    API endpoint to fetch the HTML for the "My Media Gallery" content.
    """
    if 'username' not in session:
        return jsonify({'error': 'Authentication required.'}), 401

    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found.'}), 404
    
    is_admin_session = session.get('is_admin', False)
    
    # Get all media for the gallery
    from db_queries.media import get_tagged_media_for_user
    
    # Get media user posted
    own_media = get_media_for_user_gallery(
        current_user['puid'],  # <-- Changed from profile_user to current_user
        current_user['id'], 
        is_admin_session
    )
    
    # Get media user is tagged in
    tagged_media = get_tagged_media_for_user(
        current_user['puid'],  # <-- Changed from profile_user to current_user
        current_user['id'],
        is_admin_session
    )
    
    # Mark tagged media with a flag
    for media in tagged_media:
        media['is_tagged_photo'] = 1
    
    # Merge the two lists and remove duplicates (in case user tagged themselves in their own photo)
    media_dict = {m['muid']: m for m in own_media}
    for media in tagged_media:
        if media['muid'] not in media_dict:
            media_dict[media['muid']] = media
        else:
            # If it's in both lists, mark it as tagged
            media_dict[media['muid']]['is_tagged_photo'] = 1
    
    all_media = list(media_dict.values())
    # Sort by timestamp descending
    all_media.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    # Render the *partial* template
    return render_template('_media_gallery_content.html',
                           profile_user=current_user,
                           all_media=all_media)

@main_bp.route('/post/<string:cuid>')
def view_post(cuid):
    """Renders a single post page, identified by its CUID."""
    post = get_post_by_cuid(cuid)
    if not post:
        flash('Post not found.', 'danger')
        return redirect(url_for('main.index'))

    current_username = session.get('username')
    current_user_id = None
    user_media_path = None
    current_user_puid = None
    current_user_profile = None

    if current_username:
        user_data = get_user_by_username(current_username)
        if user_data:
            current_user_id = user_data['id']
            user_media_path = user_data['media_path']
            current_user_puid = user_data['puid']
            current_user_profile = user_data

    viewer_home_url = None
    viewer_puid_for_js = None
    if current_user_id:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"
        viewer_puid_for_js = current_user_puid

    return render_template('index.html',
                           username=current_username,
                           posts=[post],
                           user_media_path=user_media_path,
                           current_user_puid=current_user_puid,
                           current_user_id=current_user_id,
                           current_user_profile=current_user_profile,
                           is_single_post_view=True,
                           viewer_home_url=viewer_home_url,
                           viewer_puid_for_js=viewer_puid_for_js)


@main_bp.route('/comment/<string:cuid>')
def view_comment(cuid):
    """Finds a comment by its CUID and redirects to the parent post with an anchor."""
    comment_info = get_comment_by_cuid(cuid)
    if not comment_info:
        flash('Comment not found.', 'danger')
        return redirect(url_for('main.index'))

    post_cuid = comment_info['post_cuid']
    comment_cuid = comment_info['comment_cuid']

    return redirect(url_for('main.view_post', cuid=post_cuid) + f'#comment-{comment_cuid}')


@main_bp.route('/media/<string:muid>')
def view_media(muid):
    """
    Direct link to media - redirects to parent post with auto-open parameter.
    The modal will auto-open via JavaScript when the post page loads.
    """
    # Get media item (try post media first, then comment media)
    media_info = get_media_details_by_muid(muid)
    if not media_info:
        media_info = get_comment_media_details_by_muid(muid)
    
    if not media_info:
        flash('Media not found.', 'danger')
        return redirect(url_for('main.index'))
    
    # Get parent post
    parent_post = get_post_by_cuid(media_info['post_cuid'])
    if not parent_post:
        flash('Parent post not found.', 'danger')
        return redirect(url_for('main.index'))
    
    # Redirect to post with auto-open parameter
    return redirect(url_for('main.view_post', cuid=parent_post['cuid'], open_media=muid))


@main_bp.route('/api/media/<muid>/modal')
def view_media_modal(muid):
    """
    API endpoint that returns just the media view content for display in a modal.
    This reuses all the same logic as view_media but renders only the content partial.
    """
    # Handle both regular users and federated viewers
    current_user = None
    current_user_puid = None
    current_user_id = None
    is_federated_viewer = session.get('is_federated_viewer', False)
    
    if is_federated_viewer:
        # Federated viewer
        current_user_puid = session.get('federated_viewer_puid')
        if current_user_puid:
            current_user = get_user_by_puid(current_user_puid)
            if current_user:
                current_user_id = current_user['id']
    elif 'username' in session:
        # Regular local user
        current_user = get_user_by_username(session['username'])
        if current_user:
            current_user_puid = current_user['puid']
            current_user_id = current_user['id']
    
    # SECURITY FIX: Require authentication to view media
    if not current_user or not current_user_puid:
        return jsonify({'error': 'Authentication required', 'redirect': url_for('auth.login')}), 401
    
    # Get media item (try post media first, then comment media)
    media_info = get_media_details_by_muid(muid)
    is_comment_media = False
    
    if not media_info:
        # Try comment media
        media_info = get_comment_media_details_by_muid(muid)
        if media_info:
            is_comment_media = True
        else:
            return jsonify({'error': 'Media not found'}), 404
    
    # Get parent post
    parent_post = get_post_by_cuid(media_info['post_cuid'])
    if not parent_post:
        return jsonify({'error': 'Parent post not found'}), 404
    
    # SECURITY FIX: Check if viewer has permission to view this post/media
    # Check privacy settings
    privacy_setting = parent_post.get('privacy_setting', 'local')
    
    # Public posts - anyone can view
    if privacy_setting == 'public':
        pass  # Allow access
    
    # Group posts - must be a group member
    elif privacy_setting == 'group':
        if parent_post.get('group_id'):
            from db_queries.groups import is_user_group_member
            if not is_user_group_member(current_user_id, parent_post['group_id']):
                return jsonify({'error': 'You must be a group member to view this media'}), 403
    
    # Friends posts - must be friends with author
    elif privacy_setting == 'friends':
        post_author_id = parent_post.get('user_id')
        if post_author_id and post_author_id != current_user_id:
            from db_queries.friends import is_friends_with
            if not is_friends_with(current_user_id, post_author_id):
                return jsonify({'error': 'You must be friends with the author to view this media'}), 403
    
    # Local posts - must be logged in (already checked above)
    # Wall posts - check if it's a friends-only wall
    if parent_post.get('profile_user_id') and parent_post['profile_user_id'] != current_user_id:
        profile_owner_id = parent_post['profile_user_id']
        # Check if the profile owner has restricted wall visibility
        # For now, allow if authenticated (can be enhanced later)
        pass
    # Get media author (different for comment media vs post media)
    if is_comment_media:
        # For comment media, get the comment author
        comment = get_comment_by_internal_id(media_info['comment_id'])
        media_author = get_user_by_id(comment['user_id'])
    else:
        # For post media, get the post author
        if parent_post.get('user_id'):
            media_author = get_user_by_id(parent_post['user_id'])
        else:
            # Remote post - get by PUID
            media_author = get_user_by_puid(parent_post['author_puid'])
    
    # Check if current user is the owner
    is_owner = current_user_puid and current_user_puid == media_author['puid']
    
    # Carousel navigation (only for post media)
    prev_muid = None
    next_muid = None
    all_post_media = []
    current_media_index = 0
    
    if not is_comment_media:
        # Get all media in this post for carousel navigation
        all_post_media = get_media_for_post(parent_post['id'])
        
        # Find current media index and get prev/next
        current_media_index = next((i for i, m in enumerate(all_post_media) if m['muid'] == muid), 0)
        prev_muid = all_post_media[current_media_index - 1]['muid'] if current_media_index > 0 else None
        next_muid = all_post_media[current_media_index + 1]['muid'] if current_media_index < len(all_post_media) - 1 else None
    
    # Get tagged users (only for post media - comments can't be tagged)
    tagged_users = []
    tagged_user_puids = []
    
    if not is_comment_media:
        tagged_users = get_media_tags(muid)
        tagged_user_puids = [user['puid'] for user in tagged_users]
        
        # Build profile URLs for tagged users
        for user in tagged_users:
            if user['hostname']:
                insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
                protocol = 'http' if insecure_mode else 'https'
                user['profile_url'] = f"{protocol}://{user['hostname']}/u/{user['puid']}"
            else:
                user['profile_url'] = url_for('main.user_profile', puid=user['puid'])
    
    # Get media comments - IMPORTANT: Pass current_user_id (works for both local and federated)
    media_comments = get_media_comments(muid, current_user_id)
    
    # Build media URL - use the same logic as federated_media_url
    # The media_info dict has: media_file_path, origin_hostname
    # We need the author's PUID to construct the URL
    if media_info.get('origin_hostname') and media_info['origin_hostname'] != current_app.config.get('NODE_HOSTNAME'):
        # Remote media
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        from urllib.parse import quote
        # Get the author PUID for the URL
        author_puid = media_author['puid']
        media_url = f"{protocol}://{media_info['origin_hostname']}/media/{author_puid}/{quote(media_info['media_file_path'])}"
    else:
        # Local media
        author_puid = media_author['puid']
        media_url = url_for('main.serve_user_media', puid=author_puid, filename=media_info['media_file_path'])
    
    # Build author profile URL
    if media_author.get('hostname'):
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        protocol = 'http' if insecure_mode else 'https'
        author_profile_url = f"{protocol}://{media_author['hostname']}/u/{media_author['puid']}"
    else:
        author_profile_url = url_for('main.user_profile', puid=media_author['puid'])
    
    # Get current user profile picture for comment input
    current_user_profile_picture = url_for('static', filename='images/default_avatar.png')
    if current_user and current_user.get('profile_picture_path'):
        if current_user.get('hostname'):
            # Federated user - get from their node
            insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
            protocol = 'http' if insecure_mode else 'https'
            current_user_profile_picture = f"{protocol}://{current_user['hostname']}/profile_pictures/{current_user['profile_picture_path']}"
        else:
            # Local user
            current_user_profile_picture = url_for('main.serve_profile_picture', filename=current_user['profile_picture_path'])
    
    # Get user settings
    user_settings = get_user_settings(current_user_id) if current_user_id else get_user_settings(None)
    
    # Render ONLY the content partial for modal
    return render_template('_view_media_content.html',
                            media_item=media_info,
                            parent_post=parent_post,
                            media_author=media_author,
                            is_owner=is_owner,
                            is_comment_media=is_comment_media,
                            all_post_media=all_post_media,
                            current_media_index=current_media_index,
                            prev_muid=prev_muid,
                            next_muid=next_muid,
                            tagged_users=tagged_users,
                            tagged_user_puids=tagged_user_puids,
                            media_comments=media_comments,
                            media_url=media_url,
                            author_profile_url=author_profile_url,
                            current_user=current_user,
                            current_user_puid=current_user_puid,
                            current_user_profile_picture=current_user_profile_picture,
                            user_settings=user_settings)

@main_bp.route('/media/<muid>/tag', methods=['POST'])
def tag_media(muid):
    """Add or update tags on a media item. Only the post author can tag."""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get media item
    media_info = get_media_by_muid(muid)
    if not media_info:
        return jsonify({'error': 'Media not found'}), 404
    
    # Get parent post to check ownership
    parent_post = get_post_by_cuid(media_info['post_cuid'])
    if not parent_post:
        return jsonify({'error': 'Parent post not found'}), 404
    
    # Check if current user is the post author
    if parent_post['user_id'] != current_user['id']:
        return jsonify({'error': 'Only the post author can tag people'}), 403
    
    # Get tagged user PUIDs from request
    data = request.get_json()
    tagged_user_puids = data.get('tagged_user_puids', [])
    
    # Add tags
    success = add_media_tags(muid, tagged_user_puids, current_user['puid'])
    
    if success:
        return jsonify({'success': True}), 200
    else:
        return jsonify({'error': 'Failed to update tags'}), 500


@main_bp.route('/media/<muid>/untag', methods=['POST'])
def untag_media(muid):
    """Allow a tagged user to remove their own tag."""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    
    # Remove the tag
    success = remove_media_tag(muid, current_user['puid'])
    
    if success:
        return jsonify({'success': True}), 200
    else:
        return jsonify({'error': 'Failed to remove tag'}), 500


@main_bp.route('/media/<muid>/comment', methods=['POST'])
def add_media_comment_route(muid):
    """Add a comment or reply to a media item."""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get media item
    media_info = get_media_by_muid(muid)
    if not media_info:
        return jsonify({'error': 'Media not found'}), 404
    
    # Get comment data
    data = request.get_json()
    content = data.get('content', '').strip()
    parent_comment_cuid = data.get('parent_comment_cuid')
    media_files = data.get('media_files', [])
    
    if not content and not media_files:
        return jsonify({'error': 'Comment cannot be empty'}), 400
    
    # Convert parent_comment_cuid to parent_comment_id if provided
    parent_comment_id = None
    if parent_comment_cuid:
        parent_comment_info = get_media_comment_by_cuid(parent_comment_cuid)
        if parent_comment_info:
            parent_comment_id = parent_comment_info['comment_id']
    
    # Add the comment
    comment_cuid = add_media_comment(
        muid=muid,
        user_id=current_user['id'],
        content=content,
        parent_comment_id=parent_comment_id,  # Use the internal ID, not CUID
        media_files=media_files
    )
    
    if comment_cuid:
        return jsonify({'success': True, 'cuid': comment_cuid}), 200
    else:
        return jsonify({'error': 'Failed to add comment'}), 500


@main_bp.route('/media/comment/<cuid>/edit', methods=['POST'])
def edit_media_comment_route(cuid):
    """Edit a media comment."""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get comment
    comment = get_media_comment_by_cuid(cuid)
    if not comment:
        return jsonify({'error': 'Comment not found'}), 404
    
    # Check ownership
    if comment['user_id'] != current_user['id']:
        return jsonify({'error': 'You can only edit your own comments'}), 403
    
    # Get new content
    data = request.get_json()
    new_content = data.get('content', '').strip()
    media_files = data.get('media_files', [])
    
    if not new_content and not media_files:
        return jsonify({'error': 'Comment cannot be empty'}), 400
    
    # Update comment
    success = update_media_comment(cuid, new_content, media_files)
    
    if success:
        return jsonify({'success': True}), 200
    else:
        return jsonify({'error': 'Failed to update comment'}), 500


@main_bp.route('/media/comment/<cuid>/delete', methods=['POST'])
def delete_media_comment_route(cuid):
    """Delete a media comment."""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get comment
    comment_info = get_media_comment_by_cuid(cuid)
    if not comment_info:
        return jsonify({'error': 'Comment not found'}), 404
    
    # Get media item to check if user is media owner
    media_info = get_media_by_muid(comment_info['muid'])
    if not media_info:
        return jsonify({'error': 'Media not found'}), 404
    
    # Get parent post
    parent_post = get_post_by_cuid(media_info['post_cuid'])
    
    # Check if user can delete (comment author or media owner)
    can_delete = (comment_info['user_id'] == current_user['id'] or 
                 (parent_post and parent_post['user_id'] == current_user['id']))
    
    if not can_delete:
        return jsonify({'error': 'You can only delete your own comments or comments on your media'}), 403
    
    # Delete comment
    success = delete_media_comment(cuid)
    
    if success:
        return jsonify({'success': True}), 200
    else:
        return jsonify({'error': 'Failed to delete comment'}), 500


@main_bp.route('/media/comment/<int:comment_id>/hide', methods=['POST'])
def hide_media_comment_route(comment_id):
    """Hide a media comment from the current user's view."""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    
    # Hide the comment (this also hides all replies recursively)
    success = hide_media_comment_for_user(current_user['id'], comment_id)
    
    if success:
        # Delete any notifications related to this comment for this user
        from db import get_db
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            DELETE FROM notifications
            WHERE user_id = ? AND media_comment_id = ?
        """, (current_user['id'], comment_id))
        db.commit()
        
        return jsonify({'success': True}), 200
    else:
        return jsonify({'error': 'Failed to hide comment'}), 500


@main_bp.route('/media/comment/<cuid>/remove_mention', methods=['POST'])
def remove_media_comment_mention_route(cuid):
    """Remove the current user's mention from a media comment."""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get the user's display name
    user_display_name = current_user['display_name'] or current_user['username']
    
    # Remove the mention
    from db_queries.media import remove_mention_from_media_comment
    success = remove_mention_from_media_comment(cuid, user_display_name)
    
    if success:
        return jsonify({'success': True}), 200
    else:
        return jsonify({'error': 'Failed to remove mention'}), 500

@main_bp.route('/create_post', methods=['POST'])
def create_post():
    """
    Allows a logged-in user to create a new post and distributes it.
    """
    if 'username' not in session or session.get('is_admin'):
        flash('Please log in as a regular user to create posts.', 'danger')
        return redirect(url_for('auth.login'))

    current_user = get_user_by_username(session['username'])
    if not current_user:
        flash('Your user account could not be found.', 'danger')
        return redirect(url_for('auth.login'))

    profile_puid = request.form.get('profile_puid')
    event_puid = request.form.get('event_puid')
    profile_user_id = None
    event_id = None

    if event_puid:
        from db_queries.events import get_event_by_puid
        event = get_event_by_puid(event_puid, current_user['puid'])
        if not event:
            flash("The event you're trying to post in doesn't exist.", "danger")
            return redirect(url_for('main.index'))
        event_id = event['id']
    elif profile_puid:
        profile_user = get_user_by_puid(profile_puid)
        if not profile_user:
            flash("The profile you're trying to post on doesn't exist.", 'danger')
            return redirect(url_for('main.index'))
        profile_user_id = profile_user['id']
        if profile_user_id != current_user['id']:
            if not is_friends_with(current_user['id'], profile_user_id):
                flash("You can only post on the timeline of your friends.", 'danger')
                return redirect(url_for('main.user_profile', puid=profile_puid))

    content = request.form['content']
    selected_media_files_json = request.form.get('selected_media_files', '[]')
    media_files_for_db = json.loads(selected_media_files_json)
    privacy_setting = request.form.get('privacy_setting', 'local')
    
    # PARENTAL CONTROL CHECK: Prevent children from making public posts
    from db_queries.parental_controls import requires_parental_approval
    
    if requires_parental_approval(current_user['id']) and privacy_setting == 'public':
        flash('You cannot create public posts while parental controls are active.', 'warning')
        return redirect(request.referrer or url_for('main.index'))

    # PARENTAL CONTROL CHECK: Prevent friends from making public posts on parental-controlled profiles
    if profile_user_id and profile_user_id != current_user['id']:
        if requires_parental_approval(profile_user_id) and privacy_setting == 'public':
            flash('You cannot create public posts on this profile while parental controls are active.', 'warning')
            return redirect(request.referrer or url_for('main.user_profile', puid=profile_puid))
        
    # NEW: Get tagged users and location
    tagged_user_puids_json = request.form.get('tagged_users', '[]')
    tagged_user_puids = json.loads(tagged_user_puids_json) if tagged_user_puids_json else []
    location = request.form.get('location', '').strip() or None
    
    # NEW: Get poll data if provided
    poll_data_json = request.form.get('poll_data', '')
    poll_data = None
    if poll_data_json:
        try:
            poll_data = json.loads(poll_data_json)
            # Validate that there's content if there's a poll
            if poll_data and not content.strip():
                flash("You can't create a poll without text in your post.", 'danger')
                return redirect(request.referrer or url_for('main.index'))
        except json.JSONDecodeError:
            poll_data = None

    try:
        post_cuid = add_post(
            user_id=current_user['id'],
            profile_user_id=profile_user_id,
            content=content,
            privacy_setting=privacy_setting,
            media_files=media_files_for_db,
            event_id=event_id,
            tagged_user_puids=tagged_user_puids,  # NEW
            location=location,
            poll_data=poll_data
        )
        if post_cuid:
            distribute_post(post_cuid)
            if poll_data:
                from utils.federation_utils import distribute_poll_data
                time.sleep(0.5)
                distribute_poll_data(post_cuid)
            flash('Post created successfully!', 'success')
        else:
            flash('Failed to create post.', 'danger')
    except Exception as e:
        flash(f'An error occurred: {e}', 'danger')
        traceback.print_exc()

    return redirect(request.referrer or url_for('main.index'))

@main_bp.route('/repost/<string:cuid>', methods=['POST'])
def repost_route(cuid):
    """Allows a logged-in user to repost a public post to their own timeline."""
    if 'username' not in session or session.get('is_admin'):
        flash('Please log in as a regular user to share posts.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    reposter_user = get_user_by_username(session['username'])
    if not reposter_user:
        flash('Your user account could not be found.', 'danger')
        return redirect(url_for('auth.login'))

    original_post = get_post_by_cuid(cuid)
    if not original_post:
        flash('The post you are trying to share does not exist.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    # You can't repost a repost. Find the ultimate original post.
    ultimate_original_post = original_post.get('original_post', original_post)

    # Only public posts can be reposted.
    if ultimate_original_post.get('privacy_setting') != 'public':
        flash('Only public posts can be shared.', 'warning')
        return redirect(request.referrer or url_for('main.index'))

    try:
        # Create the new post entry, marking it as a repost
        new_post_cuid = add_post(
            user_id=reposter_user['id'],
            profile_user_id=reposter_user['id'], # Reposts always go on the reposter's timeline
            content=None,
            privacy_setting='public', # Reposts are always public
            media_files=None,
            is_repost=True,
            original_post_cuid=ultimate_original_post['cuid']
        )
        if new_post_cuid:
            # Distribute the new repost to federated nodes
            distribute_post(new_post_cuid)
            flash('Post shared successfully!', 'success')
        else:
            flash('Failed to share post.', 'danger')
    except Exception as e:
        flash(f'An error occurred while sharing the post: {e}', 'danger')
        traceback.print_exc()

    return redirect(request.referrer or url_for('main.index'))


@main_bp.route('/edit_post/<string:post_cuid>', methods=['POST'])
def edit_post(post_cuid):
    """
    Allows the author of a post to edit it. Handles federated posts via CUID.
    """
    current_user = None
    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if not viewer_puid:
            return jsonify({'error': 'Unauthorized. Federated session is invalid.'}), 401
        current_user = get_user_by_puid(viewer_puid)
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
    else:
        return jsonify({'error': 'Unauthorized. Please log in.'}), 401

    if not current_user:
        return jsonify({'error': 'Current user not found.'}), 403

    post = get_post_by_cuid(post_cuid)
    if not post:
        return jsonify({'error': 'Post not found'}), 404

    if post['author']['puid'] != current_user['puid']:
        return jsonify({'error': 'Not authorized to edit this post'}), 403

    data = request.get_json()
    content = data.get('content')
    privacy_setting = data.get('privacy_setting', 'local')

    # PARENTAL CONTROL CHECK: Prevent children from editing posts to public
    from db_queries.parental_controls import requires_parental_approval
    
    if requires_parental_approval(current_user['id']) and privacy_setting == 'public':
        return jsonify({'error': 'You cannot create public posts while parental controls are active.'}), 403
    
    # PARENTAL CONTROL CHECK: Prevent editing wall posts to public on parental-controlled profiles
    if post.get('profile_user') and post['profile_user']['id'] != current_user['id']:
        if requires_parental_approval(post['profile_user']['id']) and privacy_setting == 'public':
            return jsonify({'error': 'You cannot edit posts to public on this profile while parental controls are active.'}), 403
    
    selected_media_files_json = data.get('selected_media_files', '[]')
    media_files = json.loads(selected_media_files_json)

    # NEW: Get tagged users and location
    tagged_users_json = data.get('tagged_users', '[]')
    location = data.get('location', '')
    
    # NEW: Parse tagged users
    try:
        tagged_user_puids = json.loads(tagged_users_json) if tagged_users_json else []
    except json.JSONDecodeError:
        tagged_user_puids = []

    if not content and not media_files:
        return jsonify({'error': 'Post content or media cannot be empty'}), 400

    try:
        # Store old privacy before update
        old_privacy = post['privacy_setting']
        
        if update_post(post_cuid, content, privacy_setting, media_files, tagged_user_puids, location):
            # Pass old privacy to distribution function
            distribute_post_update(post_cuid, old_privacy_setting=old_privacy)
            return jsonify({'message': 'Post updated successfully!'}), 200
        else:
            return jsonify({'error': 'Failed to update post in the database.'}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'An unexpected error occurred: {e}'}), 500


@main_bp.route('/delete_post/<string:post_cuid>', methods=['POST'])
def delete_post_route(post_cuid):
    """
    Allows the author, profile owner, or group admin/moderator to delete a post.
    """
    current_user = None
    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if not viewer_puid:
            flash('Unauthorized. Federated session is invalid.', 'danger')
            return redirect(request.referrer or url_for('main.index'))
        current_user = get_user_by_puid(viewer_puid)
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
    else:
        flash('Please log in to delete posts.', 'danger')
        return redirect(url_for('auth.login'))

    if not current_user:
        flash('Current user not found.', 'danger')
        return redirect(url_for('auth.login'))

    post = get_post_by_cuid(post_cuid)
    if not post:
        flash('Post not found.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    # --- PERMISSION CHECK ---
    is_author = post['author']['puid'] == current_user['puid']
    is_profile_owner = False
    is_group_moderator = False # Initialize to False
    is_event_creator = False # NEW: Initialize to False

    # Check for profile owner only if it's a profile post
    if post.get('profile_owner') and post['profile_owner'].get('puid'):
        is_profile_owner = post['profile_owner']['puid'] == current_user['puid']

    # MODIFICATION: Check for group moderator/admin only if it's a group post
    if post.get('group') and post['group'].get('id'):
        # Pass the current user's *internal* ID and the group's *internal* ID
        is_group_moderator = is_user_group_moderator_or_admin(current_user['id'], post['group']['id'])

    # NEW: Check if it's an event post and if the current user created the event
    if post.get('event') and post['event'].get('created_by_user_puid'):
        if post['event']['created_by_user_puid'] == current_user['puid']:
            is_event_creator = True

    # MODIFICATION: Add is_group_moderator AND is_event_creator to the authorization check
    if not (is_author or is_profile_owner or is_group_moderator or session.get('is_admin') or is_event_creator):
        flash('You are not authorized to delete this post.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    # Distribute the delete action *before* deleting locally.
    distribute_post_delete(post)

    if delete_post(post_cuid):
        flash('Post deleted successfully!', 'success')
    else:
        flash('Failed to delete post.', 'danger')

    # Add anchor to scroll to previous position
    if request.referrer:
        return redirect(request.referrer + '#')  # Just go back, no specific post to anchor to
    else:
        return redirect(url_for('main.index'))

@main_bp.route('/remove_tag_from_post/<string:post_cuid>', methods=['POST'])
def remove_tag_from_post_route(post_cuid):
    """
    Allows a tagged user to remove their tag from a post.
    """
    current_user = None
    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if not viewer_puid:
            return jsonify({'error': 'Unauthorized'}), 401
        current_user = get_user_by_puid(viewer_puid)
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
    else:
        return jsonify({'error': 'Unauthorized'}), 401

    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    try:
        if remove_user_tag_from_post(post_cuid, current_user['puid']):
            # NEW: Distribute the tag removal to remote nodes
            from utils.federation_utils import distribute_tag_removal
            distribute_tag_removal(post_cuid, current_user['puid'], current_user['puid'])
            # TODO: Optionally distribute this change to federated nodes if needed
            return jsonify({'message': 'Tag removed successfully'}), 200
        else:
            return jsonify({'error': 'Failed to remove tag'}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'An error occurred: {e}'}), 500


@main_bp.route('/remove_mention_from_post/<string:post_cuid>', methods=['POST'])
def remove_mention_from_post_route(post_cuid):
    """
    Allows a mentioned user to remove their @mention from a post.
    """
    current_user = None
    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if not viewer_puid:
            return jsonify({'error': 'Unauthorized'}), 401
        current_user = get_user_by_puid(viewer_puid)
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
    else:
        return jsonify({'error': 'Unauthorized'}), 401

    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    try:
        display_name = current_user.get('display_name') or current_user.get('username')
        if remove_mention_from_post(post_cuid, display_name):
            # NEW: Distribute the mention removal to remote nodes
            from utils.federation_utils import distribute_mention_removal_post
            distribute_mention_removal_post(post_cuid, display_name, current_user['puid'])
            # TODO: Optionally distribute this change to federated nodes if needed
            return jsonify({'message': 'Mention removed successfully'}), 200
        else:
            return jsonify({'error': 'Failed to remove mention'}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'An error occurred: {e}'}), 500


@main_bp.route('/hide_post/<string:post_cuid>', methods=['POST'])
def hide_post_route(post_cuid):
    """
    Allows a user to hide a post from their timeline.
    """
    current_user = None
    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if not viewer_puid:
            return jsonify({'error': 'Unauthorized'}), 401
        current_user = get_user_by_puid(viewer_puid)
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
    else:
        return jsonify({'error': 'Unauthorized'}), 401

    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    post = get_post_by_cuid(post_cuid)
    if not post:
        return jsonify({'error': 'Post not found'}), 404

    try:
        if hide_post_for_user(current_user['id'], post['id']):
            # Delete any notifications related to this post for this user
            db = get_db()
            cursor = db.cursor()
            cursor.execute("""
                DELETE FROM notifications
                WHERE user_id = ? AND post_id = ?
            """, (current_user['id'], post['id']))
            db.commit()
            
            return jsonify({'message': 'Post hidden successfully'}), 200
        else:
            return jsonify({'error': 'Failed to hide post'}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'An error occurred: {e}'}), 500

@main_bp.route('/update_media_alt_text/<int:media_id>', methods=['POST'])
def update_media_alt_text_route(media_id):
    """
    API endpoint to update the alt text for a specific media item.
    """
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 403

    current_user_id = get_user_id_by_username(session['username'])
    is_admin = session.get('is_admin', False)

    media_item = get_media_by_id(media_id)
    if not media_item:
        return jsonify({'error': 'Media not found'}), 404

    if media_item.get('post_id'):
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT p.cuid, u.puid as author_puid FROM posts p JOIN users u ON p.author_puid = u.puid WHERE p.id = ?",
                       (media_item['post_id'],))
        post_info_row = cursor.fetchone()
        post_info = dict(post_info_row) if post_info_row else None


        current_user = get_user_by_id(current_user_id)

        if not post_info or (post_info['author_puid'] != current_user['puid'] and not is_admin):
            return jsonify({'error': 'Not authorized to edit this post media item'}), 403
    elif media_item.get('comment_id'):
        comment = get_comment_by_internal_id(media_item['comment_id'])
        if not comment or (comment.get('user_id') != current_user_id and not is_admin):
            return jsonify({'error': 'Not authorized to edit this comment media item'}), 403
    else:
        media_owner_id = media_item.get('user_id')
        if not media_owner_id or (media_owner_id != current_user_id and not is_admin):
            return jsonify({'error': 'Not authorized to edit this media item'}), 403

    data = request.get_json()
    alt_text = data.get('alt_text')

    if update_media_alt_text(media_id, alt_text):
        return jsonify({'message': 'Alt text updated successfully'}), 200
    else:
        return jsonify({'error': 'Failed to update alt text'}), 500


@main_bp.route('/browse_media/<path:subfolder>')
@main_bp.route('/browse_media')
def browse_media(subfolder=''):
    """Browse media files for the logged-in user from both media and uploads."""
    if 'username' not in session or session.get('is_admin'):
        flash('Please log in as a regular user to browse media.', 'danger')
        return redirect(url_for('auth.login'))
    
    user_data = get_user_by_username(session['username'])
    if not user_data:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.login'))
    
    user_media_path = user_data.get('media_path')
    user_uploads_path = user_data.get('uploads_path')
    
    if not user_media_path and not user_uploads_path:
        return render_template('browse_media.html',
                               error_message='No media volumes configured for your account. Please contact an admin.',
                               is_single_select=request.args.get('mode') == 'single_select',
                               current_user_puid=user_data['puid'])
    
    # Use the subfolder from the path parameter, not query parameter
    decoded_subfolder = unquote(subfolder) if subfolder else ''
    
    # Get combined media from both sources
    directories, media_files = list_media_content(user_media_path, user_uploads_path, decoded_subfolder)
    
    # Convert media_files from dict format to string paths for template compatibility
    # The template expects just paths, not the metadata
    media_file_paths = []
    for item in media_files:
        if isinstance(item, dict):
            media_file_paths.append(item['path'])
        else:
            media_file_paths.append(item)
    
    parent_folder_url = None
    if decoded_subfolder:
        parent_path = os.path.dirname(decoded_subfolder)
        parent_folder_url = None
        if decoded_subfolder:
            parent_path = os.path.dirname(decoded_subfolder)
            if parent_path and parent_path != '.':
                # Going to a parent subfolder
                parent_folder_url = url_for('main.browse_media',
                                            subfolder=parent_path,
                                            mode=request.args.get('mode'))
            else:
                # Going back to root - don't pass subfolder parameter
                parent_folder_url = url_for('main.browse_media',
                                            mode=request.args.get('mode'))
    
    is_single_select = request.args.get('mode') == 'single_select'
    selected_media_paths = []
    selected_param = request.args.get('selected')
    if selected_param:
        try:
            parsed_selected = json.loads(unquote(selected_param))
            selected_media_paths = [item['media_file_path'] if isinstance(item, dict) else item for item in
                                    parsed_selected]
        except json.JSONDecodeError:
            selected_media_paths = []
    
    return render_template('browse_media.html',
                           directories=directories, 
                           media_files=media_file_paths,
                           current_subfolder=decoded_subfolder, 
                           parent_folder_url=parent_folder_url,
                           user_media_path=user_media_path,
                           user_uploads_path=user_uploads_path,
                           is_single_select=is_single_select,
                           selected_media_paths=selected_media_paths,
                           current_user_puid=user_data['puid'])

@main_bp.route('/upload_media', methods=['POST'])
def upload_media():
    """
    Handles uploading media files to the user's WRITABLE uploads directory.
    Returns JSON with uploaded file paths.
    """
    if 'username' not in session or session.get('is_admin'):
        return jsonify({'error': 'Authentication required'}), 401

    user_data = get_user_by_username(session['username'])
    if not user_data:
        return jsonify({'error': 'User not found'}), 404

    # IMPORTANT: Use uploads_path (writable) not media_path (read-only)
    user_uploads_path = user_data.get('uploads_path')
    if not user_uploads_path:
        return jsonify({'error': 'No uploads directory configured for your account. Please contact an admin.'}), 400

    uploaded_files = request.files.getlist('files')
    if not uploaded_files:
        return jsonify({'error': 'No files provided'}), 400

    # Get the full path to the user's uploads directory
    uploads_base_dir = os.path.join(current_app.config['USER_UPLOADS_BASE_DIR'], user_uploads_path)
    
    # Verify the uploads directory exists and is writable
    if not os.path.exists(uploads_base_dir):
        try:
            os.makedirs(uploads_base_dir, exist_ok=True)
        except Exception as e:
            return jsonify({'error': f'Failed to create uploads directory: {e}'}), 500
    
    # Test if writable
    test_file = os.path.join(uploads_base_dir, '.write_test')
    try:
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
    except Exception as e:
        return jsonify({'error': f'Uploads directory is not writable: {e}'}), 500

    uploaded_media = []
    allowed_extensions = current_app.config['ALLOWED_MEDIA_EXTENSIONS']

    for file in uploaded_files:
        if file and file.filename:
            try:
                # Validate file extension
                file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                if file_extension not in allowed_extensions:
                    continue

                # Generate unique filename with timestamp
                from datetime import datetime
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                safe_filename = secure_filename(file.filename)
                # Remove any path components that might have slipped through
                safe_filename = os.path.basename(safe_filename)
                unique_filename = f"{timestamp}_{safe_filename}"
                
                file_path = os.path.join(uploads_base_dir, unique_filename)
                file.save(file_path)

                # Return just the filename (no directory path)
                # The frontend will handle combining with user PUID for serving
                uploaded_media.append({
                    'media_file_path': unique_filename,
                    'alt_text': '',
                    'is_uploaded': True
                })

            except Exception as e:
                print(f"Error uploading file {file.filename}: {e}")
                traceback.print_exc()
                continue

    if not uploaded_media:
        return jsonify({'error': 'No valid files were uploaded'}), 400

    return jsonify({'uploaded_media': uploaded_media}), 200

@main_bp.route('/upload_profile_picture', methods=['POST'])
def upload_profile_picture():
    """
    Handles uploading a profile picture for the logged-in user.
    """
    if 'username' not in session or session.get('is_admin'):
        flash('Please log in as a regular user to upload a profile picture.', 'danger')
        return redirect(url_for('auth.login'))

    user_data = get_user_by_username(session['username'])
    if not user_data:
        flash('User data not found. Cannot upload profile picture.', 'danger')
        return redirect(url_for('main.index'))

    profile_picture_path = None
    original_profile_picture_path = None

    user_profile_pic_dir = os.path.join(current_app.config['PROFILE_PICTURE_STORAGE_DIR'], user_data['puid'])
    os.makedirs(user_profile_pic_dir, exist_ok=True)

    cropped_image_data = request.form.get('cropped_image_data')
    original_image_path_from_browser = request.form.get('original_image_path_from_browser')

    if cropped_image_data:
        try:
            header, encoded_data = cropped_image_data.split(',', 1)
            decoded_image = base64.b64decode(encoded_data)
            mime_type = header.split(';')[0].split(':')[1]
            file_extension = mime_type.split('/')[-1]
            standardized_filename = f"profile.{file_extension}"
            file_path = os.path.join(user_profile_pic_dir, standardized_filename)

            with open(file_path, 'wb') as f:
                f.write(decoded_image)

            profile_picture_path = os.path.join(user_data['puid'], standardized_filename)
            flash('Profile picture adjusted and uploaded successfully!', 'success')

            if original_image_path_from_browser:
                original_profile_picture_path = original_image_path_from_browser

        except Exception as e:
            flash(f'Error processing adjusted image: {e}', 'danger')
            traceback.print_exc()
            return redirect(url_for('main.user_profile', puid=user_data['puid']))

    if profile_picture_path:
        update_user_profile_picture_path(user_data['puid'], profile_picture_path, original_profile_picture_path)

    return redirect(url_for('main.user_profile', puid=user_data['puid']))

@main_bp.route('/thumbnails/<puid>/<path:filename>')
def serve_thumbnail(puid, filename):
    """
    Serve a thumbnail image, generating it on-demand if it doesn't exist.
    """
    from utils.thumbnails import get_or_create_thumbnail
    from db_queries.users import get_user_by_puid
    
    # Security: Prevent directory traversal
    safe_path = os.path.normpath(filename)
    if safe_path.startswith('..') or safe_path.startswith('/'):
        abort(403)
    
    # Get user info to find their media paths
    user = get_user_by_puid(puid)
    if not user:
        abort(404)
    
    # Try to get or create the thumbnail
    thumbnail_rel_path = get_or_create_thumbnail(
        filename,
        user.get('media_path'),
        user.get('uploads_path')
    )
    
    if not thumbnail_rel_path:
        # Thumbnail generation failed, return 404
        abort(404)
    
    # Serve the thumbnail
    thumbnail_dir = current_app.config['THUMBNAIL_CACHE_DIR']
    full_path = os.path.join(thumbnail_dir, thumbnail_rel_path)
    
    if not os.path.exists(full_path):
        abort(404)
    
    return send_from_directory(
        os.path.dirname(full_path),
        os.path.basename(full_path),
        mimetype='image/jpeg'
    )

@main_bp.route('/u/<puid>')
def user_profile(puid):
    """
    Displays a user's profile page. Handles both local and remote users.
    """
    viewer_token = request.args.get('viewer_token')
    if viewer_token:
        session['viewer_token'] = viewer_token
        return redirect(url_for('main.user_profile', puid=puid))

    profile_user = get_user_by_puid(puid)
    if not profile_user:
        flash('User not found.', 'danger')
        return redirect(url_for('main.index'))

    # NEW: Redirect to public page if user_type is 'public_page'
    if profile_user['user_type'] == 'public_page':
        return redirect(url_for('main.public_page_profile', puid=puid))

    current_viewer_is_local = 'username' in session and not session.get('is_federated_viewer')

    if profile_user.get('hostname') and current_viewer_is_local:
        local_viewer = get_user_by_username(session['username'])
        remote_hostname = profile_user['hostname']
        node = get_node_by_hostname(remote_hostname)

        if not node or not node['shared_secret']:
            flash(f'Cannot view remote profile: Your node is not securely connected to {remote_hostname}.', 'danger')
            return redirect(request.referrer or url_for('main.index'))

        try:
            insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
            verify_ssl = not insecure_mode

            token_request_url = get_remote_node_api_url(
                remote_hostname,
                '/federation/api/v1/request_viewer_token',
                insecure_mode
            )

            local_viewer_settings = get_user_settings(local_viewer['id'])

            payload = {
                'viewer_puid': local_viewer['puid'],
                'target_puid': puid,
                'viewer_settings': local_viewer_settings
            }
            request_body = json.dumps(payload, sort_keys=True).encode('utf-8')

            signature = hmac.new(
                node['shared_secret'].encode('utf-8'),
                msg=request_body,
                digestmod=hashlib.sha256
            ).hexdigest()

            headers = {
                'X-Node-Hostname': current_app.config.get('NODE_HOSTNAME'),
                'X-Node-Signature': signature,
                'Content-Type': 'application/json'
            }

            response = requests.post(token_request_url, data=request_body, headers=headers, timeout=10,
                                     verify=verify_ssl)
            response.raise_for_status()

            token_data = response.json()
            new_viewer_token = token_data.get('viewer_token')

            if not new_viewer_token:
                raise Exception("Failed to retrieve a viewer token from the remote node.")

            remote_profile_url = get_remote_node_api_url(
                remote_hostname,
                f"/u/{puid}",
                insecure_mode
            )
            return redirect(f"{remote_profile_url}?viewer_token={new_viewer_token}")

        except requests.exceptions.RequestException as e:
            flash(f"Error connecting to remote node: {e}", "danger")
            return redirect(request.referrer or url_for('main.index'))
        except Exception as e:
            flash(f"An error occurred while trying to view the remote profile: {e}", "danger")
            traceback.print_exc()
            return redirect(request.referrer or url_for('main.index'))

    current_viewer_id = None
    viewer_is_admin = False
    is_federated_viewer = False
    viewer_home_url = None
    viewer_puid = None
    # --- FIX: START ---
    # Initialize current_viewer_data to None
    current_viewer_data = None
    # --- FIX: END ---

    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'

    if session.get('is_federated_viewer'):
        is_federated_viewer = True
        viewer_puid = session.get('federated_viewer_puid')
        federated_viewer = get_user_by_puid(viewer_puid)
        if federated_viewer:
            current_viewer_id = federated_viewer['id']
            viewer_home_url = f"{protocol}://{federated_viewer['hostname']}"
            # --- FIX: START ---
            # Assign the fetched federated_viewer object
            current_viewer_data = federated_viewer
            # --- FIX: END ---
    elif 'username' in session:
        current_viewer = get_user_by_username(session['username'])
        if current_viewer:
            current_viewer_id = current_viewer['id']
            viewer_is_admin = (current_viewer['user_type'] == 'admin')
            viewer_puid = current_viewer['puid']
            viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"
            # --- FIX: START ---
            # Assign the fetched current_viewer object
            current_viewer_data = current_viewer
            # --- FIX: END ---

    friendship_status_result = get_friendship_status(current_viewer_id, profile_user['id'])
    friendship_status = friendship_status_result[0] if isinstance(friendship_status_result,
                                                                    tuple) else friendship_status_result
    incoming_request_id = friendship_status_result[1] if isinstance(friendship_status_result, tuple) else None

    friendship_date = None
    relationship_info = None
    if friendship_status == 'friends':
        friendship_date = get_friendship_details(current_viewer_id, profile_user['id'])
        relationship_info = get_friend_relationship(current_viewer_id, profile_user['id'])

    is_owner = (current_viewer_id == profile_user['id']) if current_viewer_id else False
    profile_info = get_profile_info_for_user(profile_user['id'], current_viewer_id, viewer_is_admin)
    family_relationships = get_family_relationships_for_user(profile_user['id'], current_viewer_id, viewer_is_admin)

    user_posts = get_posts_for_profile_timeline(
    profile_user_puid=profile_user['puid'],
    viewer_user_id=current_viewer_id,
    viewer_is_admin=viewer_is_admin,
    page=1,
    limit=20
    )
    all_gallery_media = get_media_for_user_gallery(profile_user['puid'], current_viewer_id, viewer_is_admin)

    profile_picture_muid = get_muid_by_media_path(
        profile_user.get('original_profile_picture_path')
    )
    profile_user['profile_picture_muid'] = profile_picture_muid

    latest_gallery_media = all_gallery_media[:9]

    # --- FIX: START ---
    # This line is now redundant because current_viewer_data is set inside the session checks
    # current_viewer_data = get_user_by_id(current_viewer_id) if current_viewer_id else None
    # --- FIX: END ---
    user_media_path = current_viewer_data['media_path'] if current_viewer_data else None

    # Always fetch friends list to get the count
    friends_full_list = get_friends_list(profile_user['id'])
    friends_count = len(friends_full_list)

    # Check if viewer can see friends list based on privacy settings
    show_friends_info = profile_info.get('show_friends', {})
    can_view_friends = is_owner or viewer_is_admin

    if not can_view_friends:
        # Check if viewer meets any of the privacy criteria
        if show_friends_info.get('privacy_public'):
            can_view_friends = True
        elif show_friends_info.get('privacy_local') and not is_federated_viewer:
            can_view_friends = True
        elif show_friends_info.get('privacy_friends') and friendship_status == 'friends':
            can_view_friends = True

    # Only show friends list if viewer has permission
    if can_view_friends:
        friends = friends_full_list
    else:
        friends = []

    from db_queries.parental_controls import requires_parental_approval

    # Add to context
    current_user_requires_parental_approval = requires_parental_approval(current_viewer_data['id']) if current_viewer_data else False

    profile_user_requires_parental_approval = requires_parental_approval(profile_user['id'])

    return render_template('user_profile.html',
                           profile_user=profile_user, user_posts=user_posts,
                           latest_gallery_media=latest_gallery_media, total_media_count=len(all_gallery_media),
                           user_media_path=user_media_path, profile_info=profile_info,
                           family_relationships=family_relationships, friends=friends,
                           is_owner=is_owner, friendship_status=friendship_status,
                           incoming_request_id=incoming_request_id, friendship_date=friendship_date,
                           relationship_info=relationship_info,
                           current_user_id=current_viewer_id,
                           viewer_token=session.pop('viewer_token', None),
                           is_federated_viewer=is_federated_viewer,
                           viewer_home_url=viewer_home_url,
                           viewer_puid=viewer_puid,
                           viewer_puid_for_js=viewer_puid,
                           friends_count=friends_count,
                           current_user_requires_parental_approval=current_user_requires_parental_approval,
                           profile_user_requires_parental_approval=profile_user_requires_parental_approval,
                           # --- FIX: START ---
                           # Pass the new variable to the template
                           current_viewer_data=current_viewer_data
                           # --- FIX: END ---
                           )

# NEW: Route for public pages
@main_bp.route('/page/<puid>')
def public_page_profile(puid):
    """Displays a public page's profile."""
    viewer_token = request.args.get('viewer_token')
    if viewer_token:
        session['viewer_token'] = viewer_token
        return redirect(url_for('main.public_page_profile', puid=puid))

    profile_user = get_user_by_puid(puid)
    if not profile_user or profile_user['user_type'] != 'public_page':
        flash('Public page not found.', 'danger')
        return redirect(url_for('main.index'))

    current_viewer_id = None
    viewer_is_admin = False
    is_federated_viewer = False
    viewer_home_url = None
    viewer_puid = None
    # --- FIX: START ---
    # Initialize current_viewer_data to None
    current_viewer_data = None
    # --- FIX: END ---

    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'

    if session.get('is_federated_viewer'):
        is_federated_viewer = True
        viewer_puid = session.get('federated_viewer_puid')
        federated_viewer = get_user_by_puid(viewer_puid)
        if federated_viewer:
            current_viewer_id = federated_viewer['id']
            viewer_home_url = f"{protocol}://{federated_viewer['hostname']}"
            # --- FIX: START ---
            # Assign the fetched federated_viewer object
            current_viewer_data = federated_viewer
            # --- FIX: END ---
    elif 'username' in session:
        current_viewer = get_user_by_username(session['username'])
        if current_viewer:
            current_viewer_id = current_viewer['id']
            viewer_is_admin = (current_viewer['user_type'] == 'admin')
            viewer_puid = current_viewer['puid']
            viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"
            # --- FIX: START ---
            # Assign the fetched current_viewer object
            current_viewer_data = current_viewer
            # --- FIX: END ---

    is_owner = (current_viewer_id == profile_user['id']) if current_viewer_id else False
    following = is_following(current_viewer_id, profile_user['id'])

    profile_info = get_profile_info_for_user(profile_user['id'], current_viewer_id, viewer_is_admin)

    # Always fetch followers list to get the count
    followers_full_list = get_followers(profile_user['id'])
    followers_count = len(followers_full_list)

    # Check if viewer can see followers list based on privacy settings
    show_friends_info = profile_info.get('show_friends', {})
    can_view_followers = is_owner or viewer_is_admin

    if not can_view_followers:
        # Check if viewer meets any of the privacy criteria
        if show_friends_info.get('privacy_public'):
            can_view_followers = True
        elif show_friends_info.get('privacy_friends'):
            # For public pages, privacy_friends means "followers only"
            if current_viewer_id and following:
                can_view_followers = True

    # Only show followers list if viewer has permission
    if can_view_followers:
        followers = followers_full_list
    else:
        followers = []

    profile_info = get_profile_info_for_user(profile_user['id'], current_viewer_id, viewer_is_admin)
    user_posts = get_posts_for_profile_timeline(
        profile_user_puid=profile_user['puid'],
        viewer_user_id=current_viewer_id,
        viewer_is_admin=viewer_is_admin,
        page=1,
        limit=20
    )

    all_gallery_media = get_media_for_user_gallery(profile_user['puid'], current_viewer_id, viewer_is_admin)
    latest_gallery_media = all_gallery_media[:9]

    profile_picture_muid = get_muid_by_media_path(profile_user.get('original_profile_picture_path'))
    profile_user['profile_picture_muid'] = profile_picture_muid

    # --- FIX: START ---
    # This line is now redundant
    # current_viewer_data = get_user_by_id(current_viewer_id) if current_viewer_id else None
    # --- FIX: END ---
    user_media_path = current_viewer_data['media_path'] if current_viewer_data else None

    from db_queries.parental_controls import requires_parental_approval

    # Add to context
    current_user_requires_parental_approval = requires_parental_approval(current_viewer_data['id']) if current_viewer_data else False

    return render_template('public_page_profile.html',
                           profile_user=profile_user,
                           user_posts=user_posts,
                           latest_gallery_media=latest_gallery_media,
                           total_media_count=len(all_gallery_media),
                           user_media_path=user_media_path,
                           profile_info=profile_info,
                           is_owner=is_owner,
                           following=following,
                           followers=followers,
                           current_user_id=current_viewer_id,
                           viewer_home_url=viewer_home_url,
                           viewer_puid=viewer_puid,
                           current_user_puid=viewer_puid,
                           viewer_puid_for_js=viewer_puid,
                           is_federated_viewer=is_federated_viewer,
                           viewer_token=session.pop('viewer_token', None),
                           followers_count=followers_count,
                           current_user_requires_parental_approval=current_user_requires_parental_approval,
                           # --- FIX: START ---
                           # Pass the new variable to the template
                           current_viewer_data=current_viewer_data
                           # --- FIX: END ---
                           )

# NEW: API routes for follow/unfollow actions
@main_bp.route('/follow/<puid>', methods=['POST'])
def follow_route(puid):
    """Handles a user following a public page."""
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': 'Authentication required.'}), 401

    current_user = get_user_by_username(session['username'])
    page_to_follow = get_user_by_puid(puid)

    if not current_user or not page_to_follow:
        return jsonify({'status': 'error', 'message': 'User or page not found.'}), 404

    if page_to_follow['user_type'] != 'public_page':
        return jsonify({'status': 'error', 'message': 'You can only follow public pages.'}), 400

    if follow_page(current_user['id'], page_to_follow['id']):
        return jsonify({'status': 'success', 'message': f'You are now following {page_to_follow["display_name"]}.'})
    else:
        return jsonify({'status': 'error', 'message': 'Failed to follow page.'}), 500

@main_bp.route('/follow_remote', methods=['POST'])
def follow_remote_proxy():
    """
    Acts as a proxy to send a follow request from a local user to a remote public page.
    """
    if 'username' not in session:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json()
    target_puid = data.get('target_puid')
    target_hostname = data.get('target_hostname')
    target_display_name = data.get('target_display_name')
    target_user_type = data.get('target_user_type')

    if not all([target_puid, target_hostname, target_display_name, target_user_type]):
        return jsonify({'error': 'Missing target user data'}), 400

    follower = get_user_by_username(session['username'])
    if not follower:
        return jsonify({'error': 'Could not identify sender.'}), 401

    # TARGETED SUBSCRIPTION: Check for connection and create targeted subscription if needed
    from db_queries.federation import get_or_create_targeted_subscription
    
    node = get_node_by_hostname(target_hostname)
    if not node or node['status'] != 'connected' or not node['shared_secret']:
        # No connection exists, create a targeted subscription
        print(f"No connection to {target_hostname}, creating targeted subscription for page {target_display_name}")
        node = get_or_create_targeted_subscription(
            target_hostname,
            'public_page',
            target_puid,
            target_display_name
        )
        
        if not node:
            return jsonify({'error': 'Unable to establish connection to the remote node. Please try again later.'}), 500

    try:
        # Create a local stub for the remote page if it doesn't exist
        remote_page_stub = get_or_create_remote_user(
            puid=target_puid,
            display_name=target_display_name,
            hostname=target_hostname,
            profile_picture_path=None,
            user_type=target_user_type
        )
        if not remote_page_stub:
            return jsonify({'error': 'Failed to create a local record for the remote page.'}), 500

        # Immediately follow the local stub
        follow_page(follower['id'], remote_page_stub['id'])

        # Now, notify the remote node
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        verify_ssl = not insecure_mode
        local_hostname = current_app.config.get('NODE_HOSTNAME')

        remote_url = get_remote_node_api_url(
            target_hostname,
            '/federation/api/v1/receive_follow',
            insecure_mode
        )

        payload = {
            "page_to_follow_puid": target_puid,
            "follower_puid": follower['puid'],
            "follower_display_name": follower['display_name'],
            "follower_hostname": local_hostname
        }

        request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            node['shared_secret'].encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        headers = {
            'X-Node-Hostname': local_hostname,
            'X-Node-Signature': signature,
            'Content-Type': 'application/json'
        }

        response = requests.post(remote_url, data=request_body, headers=headers, timeout=10, verify=verify_ssl)
        response.raise_for_status()

        return jsonify(response.json()), response.status_code

    except requests.exceptions.RequestException as e:
        print(f"ERROR proxying follow request to {target_hostname}: {e}")
        # We already followed locally, so this is not a critical failure for the user
        return jsonify({'status': 'success', 'message': 'Followed successfully (pending remote confirmation).'}), 200
    except Exception as e:
        print(f"ERROR in follow_remote_proxy: {e}")
        traceback.print_exc()
        return jsonify({'error': 'An unexpected error occurred.'}), 500


@main_bp.route('/unfollow/<puid>', methods=['POST'])
def unfollow_route(puid):
    """Handles a user unfollowing a public page."""
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': 'Authentication required.'}), 401

    current_user = get_user_by_username(session['username'])
    page_to_unfollow = get_user_by_puid(puid)

    if not current_user or not page_to_unfollow:
        return jsonify({'status': 'error', 'message': 'User or page not found.'}), 404

    if unfollow_page(current_user['id'], page_to_unfollow['id']):
        return jsonify({'status': 'success', 'message': f'You have unfollowed {page_to_unfollow["display_name"]}.'})
    else:
        return jsonify({'status': 'error', 'message': 'Failed to unfollow page.'}), 500

@main_bp.route('/update_profile_info', methods=['POST'])
def update_profile_info():
    """
    Handles updating user profile information.
    """
    if 'username' not in session or session.get('is_admin'):
        return jsonify({'error': 'Unauthorized to update profile information.'}), 403

    current_user_id = get_user_id_by_username(session['username'])
    if not current_user_id:
        return jsonify({'error': 'User not found.'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request data'}), 400

    display_name = data.get('display_name')
    if display_name:
        update_user_display_name(current_user_id, display_name)

    profile_fields = data.get('profile_fields', {})
    for field_name, field_data in profile_fields.items():
        # Prevent updating DOB value (but allow privacy settings to be updated)
        if field_name == 'dob':
            # Only update privacy settings for DOB, not the value itself
            from db_queries.profiles import update_profile_info_privacy_only
            update_profile_info_privacy_only(current_user_id, field_name,
                                           1 if field_data.get('privacy_public') else 0,
                                           1 if field_data.get('privacy_local') else 0,
                                           1 if field_data.get('privacy_friends') else 0)
        else:
            update_profile_info_field(current_user_id, field_name, field_data.get('value'),
                                      1 if field_data.get('privacy_public') else 0,
                                      1 if field_data.get('privacy_local') else 0,
                                      1 if field_data.get('privacy_friends') else 0)

    new_family_members = data.get('new_family_members', [])
    for member in new_family_members:
        if member.get('relative_user_id') and member.get('relationship_type'):
            add_family_relationship(current_user_id, member.get('relative_user_id'),
                                    member.get('relationship_type'), member.get('anniversary_date') or None,
                                    1 if member.get('privacy_public') else 0,
                                    1 if member.get('privacy_local') else 0,
                                    1 if member.get('privacy_friends') else 0)

    flash('Profile information updated successfully!', 'success')
    return jsonify({'message': 'Profile information updated successfully'}), 200


@main_bp.route('/remove_family_member/<int:relationship_id>', methods=['POST'])
def remove_family_member_route(relationship_id):
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 403

    current_user_id = get_user_id_by_username(session['username'])
    if not current_user_id:
        return jsonify({'error': 'User not found.'}), 404

    if remove_family_relationship(relationship_id, current_user_id):
        return jsonify({'message': 'Family member removed successfully.'}), 200
    else:
        return jsonify({'error': 'Failed to remove family member or unauthorized.'}), 400


@main_bp.route('/get_relationship_details/<int:relationship_id>')
def get_relationship_details(relationship_id):
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 403

    current_user_id = get_user_id_by_username(session['username'])
    relationship = get_relationship_by_id(relationship_id, current_user_id)

    if relationship:
        return jsonify(relationship)
    else:
        return jsonify({'error': 'Relationship not found or unauthorized'}), 404


@main_bp.route('/update_family_member/<int:relationship_id>', methods=['POST'])
def update_family_member_route(relationship_id):
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 403

    current_user_id = get_user_id_by_username(session['username'])
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Invalid data'}), 400

    if update_family_relationship(
            relationship_id, current_user_id,
            data.get('relative_user_id'), data.get('relationship_type'),
            data.get('anniversary_date') or None,
            1 if data.get('privacy_public') else 0,
            1 if data.get('privacy_local') else 0,
            1 if data.get('privacy_friends') else 0
    ):
        return jsonify({'message': 'Family member updated successfully.'}), 200
    else:
        return jsonify({'error': 'Failed to update family member or unauthorized.'}), 400


@main_bp.route('/u/<puid>/gallery')
def media_gallery(puid):
    """Displays a user's full media gallery with full profile context."""
    if 'username' not in session and not session.get('is_federated_viewer'):
        flash('Please log in to view galleries.', 'danger')
        return redirect(url_for('auth.login'))

    profile_user = get_user_by_puid(puid)
    if not profile_user:
        flash('User not found.', 'danger')
        return redirect(url_for('main.index'))

    current_viewer_id = None
    viewer_is_admin = False
    is_federated_viewer = False
    viewer_home_url = None
    viewer_puid = None
    current_viewer_data = None

    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = 'http' if insecure_mode else 'https'
    
    user_settings = get_user_settings(None) # Default settings

    if session.get('is_federated_viewer'):
        is_federated_viewer = True
        viewer_puid = session.get('federated_viewer_puid')
        federated_viewer = get_user_by_puid(viewer_puid)
        if federated_viewer:
            current_viewer_id = federated_viewer['id']
            viewer_home_url = f"{protocol}://{federated_viewer['hostname']}"
            current_viewer_data = federated_viewer
            if session.get('federated_viewer_settings'):
                user_settings.update(session.get('federated_viewer_settings'))
    elif 'username' in session:
        current_viewer = get_user_by_username(session['username'])
        if current_viewer:
            current_viewer_id = current_viewer['id']
            viewer_is_admin = (current_viewer['user_type'] == 'admin')
            viewer_puid = current_viewer['puid']
            viewer_home_url = f"{protocol}://{current_app.config.get('NODE_HOSTNAME')}"
            current_viewer_data = current_viewer
            user_settings = get_user_settings(current_viewer_id)

    is_owner = (current_viewer_id == profile_user['id']) if current_viewer_id else False

    friendship_status_result = get_friendship_status(current_viewer_id, profile_user['id'])
    friendship_status = friendship_status_result[0] if isinstance(friendship_status_result, tuple) else friendship_status_result
    incoming_request_id = friendship_status_result[1] if isinstance(friendship_status_result, tuple) else None

    friendship_date = None
    relationship_info = None
    if friendship_status == 'friends':
        friendship_date = get_friendship_details(current_viewer_id, profile_user['id'])
        relationship_info = get_friend_relationship(current_viewer_id, profile_user['id'])

    # Permission check - public pages are viewable by anyone
    if profile_user['user_type'] == 'public_page':
        can_view = True  # Anyone can view public page media
    else:
        # For regular users, existing friend-based permission logic
        can_view = is_owner
        if not is_owner:
            can_view = (friendship_status == 'friends')

    if not can_view and not viewer_is_admin:
        flash('You do not have permission to view this user\'s media gallery.', 'danger')
        return redirect(url_for('main.user_profile', puid=puid))

    # Get all media for the gallery
    from db_queries.media import get_tagged_media_for_user
    
    # Get media user posted
    own_media = get_media_for_user_gallery(profile_user['puid'], current_viewer_id, viewer_is_admin)
    
    # Get media user is tagged in
    tagged_media = get_tagged_media_for_user(
        profile_user['puid'],
        current_viewer_id,
        viewer_is_admin
    )
    
    # Mark tagged media with a flag
    for media in tagged_media:
        media['is_tagged_photo'] = 1
    
    # Merge the two lists and remove duplicates (in case user tagged themselves in their own photo)
    media_dict = {m['muid']: m for m in own_media}
    for media in tagged_media:
        if media['muid'] not in media_dict:
            media_dict[media['muid']] = media
        else:
            # If it's in both lists, mark it as tagged
            media_dict[media['muid']]['is_tagged_photo'] = 1
    
    all_media = list(media_dict.values())
    # Sort by timestamp descending
    all_media.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    # Get data for the sidebar
    profile_info = get_profile_info_for_user(profile_user['id'], current_viewer_id, viewer_is_admin)
    family_relationships = get_family_relationships_for_user(profile_user['id'], current_viewer_id, viewer_is_admin)
    
    profile_picture_muid = get_muid_by_media_path(profile_user.get('original_profile_picture_path'))
    profile_user['profile_picture_muid'] = profile_picture_muid
    
    latest_gallery_media = all_media[:9]
    total_media_count = len(all_media)

    # Get friends OR followers depending on user type
    if profile_user['user_type'] == 'public_page':
        from db_queries.followers import get_followers, is_following
        # Always fetch to get count
        followers_full_list = get_followers(profile_user['id'])
        followers_count = len(followers_full_list)
        following = is_following(current_viewer_id, profile_user['id']) if current_viewer_id else False
        
        # Check privacy for followers list (reuse profile_info logic)
        show_friends_info = profile_info.get('show_friends', {})
        can_view_followers = is_owner or viewer_is_admin
        
        if not can_view_followers:
            if show_friends_info.get('privacy_public'):
                can_view_followers = True
            elif show_friends_info.get('privacy_friends') and following:
                can_view_followers = True
        
        friends = followers_full_list if can_view_followers else []
        friends_count = followers_count  # For consistency in template
    else:
        # Always fetch to get count
        friends_full_list = get_friends_list(profile_user['id'])
        friends_count = len(friends_full_list)
        following = False  # Not applicable for regular users
        
        # Check privacy for friends list
        show_friends_info = profile_info.get('show_friends', {})
        can_view_friends = is_owner or viewer_is_admin
        
        if not can_view_friends:
            if show_friends_info.get('privacy_public'):
                can_view_friends = True
            elif show_friends_info.get('privacy_local') and not is_federated_viewer:
                can_view_friends = True
            elif show_friends_info.get('privacy_friends') and friendship_status == 'friends':
                can_view_friends = True
        
        friends = friends_full_list if can_view_friends else []
        following = False  # Not applicable for regular users

    # Get unread notification count for the VIEWER
    unread_count = 0
    if current_viewer_id and not is_federated_viewer:
        unread_count = get_unread_notification_count(current_viewer_id)

    return render_template('media_gallery.html',
                           profile_user=profile_user,
                           all_media=all_media,
                           is_owner=is_owner,
                           profile_info=profile_info,
                           family_relationships=family_relationships,
                           latest_gallery_media=latest_gallery_media,
                           total_media_count=total_media_count,
                           friends=friends,
                           following=following,
                           current_viewer_data=current_viewer_data,
                           current_user_id=current_viewer_id,
                           viewer_puid=viewer_puid,
                           viewer_home_url=viewer_home_url,
                           is_federated_viewer=is_federated_viewer,
                           user_settings=user_settings,
                           viewer_token=session.pop('viewer_token', None),
                           friendship_status=friendship_status,
                           incoming_request_id=incoming_request_id,
                           friendship_date=friendship_date,
                           relationship_info=relationship_info,
                           user_media_path=current_viewer_data.get('media_path') if current_viewer_data else None,
                           viewer_puid_for_js=viewer_puid,
                           friends_count=friends_count,
                           unread_notification_count=unread_count)

@main_bp.route('/api/albums/user/<puid>')
def get_user_albums_api(puid):
    """API endpoint to get all albums for a user with cover images"""
    from db_queries.albums import get_albums_for_user, get_album_media
    from db_queries.users import get_user_by_puid, get_user_by_username
    
    user = get_user_by_puid(puid)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get current viewer info for privacy filtering
    # Get current viewer info for privacy filtering
    current_user_id = None
    is_admin = False

    # Check for federated viewer first
    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if viewer_puid:
            from db_queries.users import get_user_by_puid
            viewer_user = get_user_by_puid(viewer_puid)
            if viewer_user:
                current_user_id = viewer_user['id']
                # Federated viewers are never admins
                is_admin = False
    elif 'username' in session:
        from db_queries.users import get_user_by_username
        current_user = get_user_by_username(session['username'])
        if current_user:
            current_user_id = current_user['id']
            is_admin = session.get('is_admin', False)
    
        albums = get_albums_for_user(puid)
        
        # Add cover image and filter out empty albums (except for owner)
        filtered_albums = []
        
        # Check if viewer is the album owner
        viewer_puid = None
        if current_user_id:
            viewer_user = get_user_by_id(current_user_id)
            if viewer_user:
                viewer_puid = viewer_user['puid']
        
        for album in albums:
            media_items = get_album_media(album['id'], current_user_id, is_admin, album['owner_puid'])
            
            is_owner = (viewer_puid == album['owner_puid'])
            
            # Include album if: has media OR viewer is owner
            if media_items or is_owner:
                album['cover_image'] = dict(media_items[0]) if media_items else None
                album['media_count'] = len(media_items)  # Update count to reflect visible items
                filtered_albums.append(album)
        
        return jsonify(filtered_albums), 200


@main_bp.route('/api/albums/group/<group_puid>')
def get_group_albums_api(group_puid):
    """API endpoint to get all albums for a group with cover images"""
    from db_queries.albums import get_albums_for_group, get_album_media
    from db_queries.groups import get_group_by_puid
    from db_queries.users import get_user_by_username
    
    group = get_group_by_puid(group_puid)
    if not group:
        return jsonify({'error': 'Group not found'}), 404
    
    # Get current viewer info for privacy filtering
    # Get current viewer info for privacy filtering
    current_user_id = None
    is_admin = False

    # Check for federated viewer first
    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if viewer_puid:
            from db_queries.users import get_user_by_puid
            viewer_user = get_user_by_puid(viewer_puid)
            if viewer_user:
                current_user_id = viewer_user['id']
                # Federated viewers are never admins
                is_admin = False
    elif 'username' in session:
        from db_queries.users import get_user_by_username
        current_user = get_user_by_username(session['username'])
        if current_user:
            current_user_id = current_user['id']
            is_admin = session.get('is_admin', False)
    
    albums = get_albums_for_group(group_puid)
        
    # Add cover image and filter out empty albums (except for owner)
    filtered_albums = []
    
    # Check if viewer is the album owner
    viewer_puid = None
    if current_user_id:
        from db_queries.users import get_user_by_id
        viewer_user = get_user_by_id(current_user_id)
        if viewer_user:
            viewer_puid = viewer_user['puid']
    
    for album in albums:
        media_items = get_album_media(album['id'], current_user_id, is_admin, album['owner_puid'], group_puid)
        
        is_owner = (viewer_puid == album['owner_puid'])
        
        # Include album if: has media OR viewer is owner
        if media_items or is_owner:
            album['cover_image'] = dict(media_items[0]) if media_items else None
            album['media_count'] = len(media_items)  # Update count to reflect visible items
            
            # Add owner display name for group albums
            from db_queries.users import get_user_by_puid
            owner = get_user_by_puid(album['owner_puid'])
            if owner:
                album['owner_display_name'] = owner['display_name']
                album['owner_username'] = owner['username']
            
            filtered_albums.append(album)
    
    return jsonify(filtered_albums), 200


@main_bp.route('/api/albums/<album_uid>')
def get_album_api(album_uid):
    """API endpoint to get a specific album with all its media"""
    from db_queries.albums import get_album_by_uid, get_album_media
    from db_queries.users import get_user_by_username
    
    album = get_album_by_uid(album_uid)
    if not album:
        return jsonify({'error': 'Album not found'}), 404
    
    # Get current viewer info for privacy filtering
    # Get current viewer info for privacy filtering
    current_user_id = None
    is_admin = False

    # Check for federated viewer first
    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if viewer_puid:
            from db_queries.users import get_user_by_puid
            viewer_user = get_user_by_puid(viewer_puid)
            if viewer_user:
                current_user_id = viewer_user['id']
                # Federated viewers are never admins
                is_admin = False
    elif 'username' in session:
        from db_queries.users import get_user_by_username
        current_user = get_user_by_username(session['username'])
        if current_user:
            current_user_id = current_user['id']
            is_admin = session.get('is_admin', False)
    
    # Get media items with privacy filtering
    media_items = get_album_media(album['id'], current_user_id, is_admin, album['owner_puid'], album.get('group_puid'))
    album['media'] = media_items
    
    # Add owner display name (especially useful for group albums)
    from db_queries.users import get_user_by_puid
    owner = get_user_by_puid(album['owner_puid'])
    if owner:
        album['owner_display_name'] = owner['display_name']
        album['owner_username'] = owner['username']
    
    return jsonify(album), 200


@main_bp.route('/api/albums/create', methods=['POST'])
def create_album():
    """API endpoint to create a new album"""
    from db_queries.albums import create_album as db_create_album
    from db_queries.users import get_user_by_username
    from db_queries.groups import get_group_by_puid, is_user_group_member
    
    # Check authentication for both local and federated users
    current_user = None

    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if viewer_puid:
            from db_queries.users import get_user_by_puid
            current_user = get_user_by_puid(viewer_puid)
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])

    if not current_user:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.get_json()
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    group_puid = data.get('group_puid')
    
    if not title:
        return jsonify({'error': 'Title is required'}), 400
    
    # If creating a group album, verify membership
    if group_puid:
        group = get_group_by_puid(group_puid)
        if not group:
            return jsonify({'error': 'Group not found'}), 404
        
        if not is_user_group_member(current_user['id'], group['id']):
            return jsonify({'error': 'Must be a group member to create group albums'}), 403
    
    owner_puid = current_user['puid']
    album_uid = db_create_album(owner_puid, title, description, group_puid)
    
    if album_uid:
        return jsonify({'success': True, 'album_uid': album_uid}), 200
    else:
        return jsonify({'error': 'Failed to create album'}), 500


@main_bp.route('/api/albums/<album_uid>', methods=['PUT', 'DELETE'])
def manage_album(album_uid):
    """API endpoint to update or delete an album"""
    from db_queries.albums import check_album_management_permission, update_album, delete_album
    from db_queries.users import get_user_by_username, get_user_by_puid
    
    # Check authentication for both local and federated users
    current_user = None

    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if viewer_puid:
            current_user = get_user_by_puid(viewer_puid)
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])

    if not current_user:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_puid = current_user['puid']
    user_id = current_user['id']
    
    # Check management permissions (considering group roles)
    permissions = check_album_management_permission(album_uid, user_puid, user_id)
    
    if request.method == 'DELETE':
        if not permissions['can_delete']:
            return jsonify({'error': 'Unauthorized'}), 403
            
        if delete_album(album_uid):
            return jsonify({'success': True}), 200
        else:
            return jsonify({'error': 'Failed to delete album'}), 500
    
    elif request.method == 'PUT':
        if not permissions['can_edit']:
            return jsonify({'error': 'Unauthorized - only album owner can edit'}), 403
            
        data = request.get_json()
        title = data.get('title')
        description = data.get('description')
        
        if update_album(album_uid, title, description):
            return jsonify({'success': True}), 200
        else:
            return jsonify({'error': 'Failed to update album'}), 500


@main_bp.route('/api/albums/<album_uid>/media', methods=['POST', 'DELETE'])
def manage_album_media(album_uid):
    """API endpoint to add/remove media from an album"""
    from db_queries.albums import (check_album_ownership, get_album_by_uid, 
                                   add_media_to_album, remove_media_from_album)
    from db_queries.users import get_user_by_username, get_user_by_puid
    
    # Check authentication for both local and federated users
    current_user = None

    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if viewer_puid:
            current_user = get_user_by_puid(viewer_puid)
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])

    if not current_user:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_puid = current_user['puid']
    
    # For adding/removing media, only the owner can do this (not admins/mods)
    if not check_album_ownership(album_uid, user_puid):
        return jsonify({'error': 'Unauthorized - only album owner can add/remove media'}), 403
    
    album = get_album_by_uid(album_uid)
    if not album:
        return jsonify({'error': 'Album not found'}), 404
    
    data = request.get_json()
    media_id = data.get('media_id')
    
    if not media_id:
        return jsonify({'error': 'media_id is required'}), 400
    
    if request.method == 'POST':
        if add_media_to_album(album['id'], media_id):
            return jsonify({'success': True}), 200
        else:
            return jsonify({'error': 'Failed to add media'}), 500
    
    elif request.method == 'DELETE':
        if remove_media_from_album(album['id'], media_id):
            return jsonify({'success': True}), 200
        else:
            return jsonify({'error': 'Failed to remove media'}), 500
        
@main_bp.route('/api/albums/my')
def get_my_albums_api():
    """API endpoint to get albums for the current logged-in user"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    from db_queries.albums import get_albums_for_user, get_album_media
    from db_queries.users import get_user_by_username
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    
    albums = get_albums_for_user(current_user['puid'])
    
    # Get viewer info (user viewing their own albums)
    current_user_id = current_user['id']
    is_admin = session.get('is_admin', False)
    
    # Add cover image for each album
    for album in albums:
        media_items = get_album_media(album['id'], current_user_id, is_admin, album['owner_puid'])
        album['cover_image'] = dict(media_items[0]) if media_items else None
    
    return jsonify(albums), 200

@main_bp.route('/api/my-media-for-album')
def get_my_media_for_album():
    """Get all media for the current user for album selection"""
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    from db_queries.users import get_user_by_username
    from db_queries.posts import get_media_for_user_gallery
    
    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get all user's media
    media = get_media_for_user_gallery(current_user['puid'], current_user['id'], False)
    
    return jsonify(media), 200


@main_bp.route('/api/user-media-for-album/<puid>')
def get_user_media_for_album(puid):
    """Get all media for a specific user for album selection"""
    from db_queries.users import get_user_by_puid
    from db_queries.posts import get_media_for_user_gallery
    
    user = get_user_by_puid(puid)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Check if viewer has permission (for now, allow owner only)
    current_user_id = None
    if 'username' in session:
        from db_queries.users import get_user_by_username
        current_user = get_user_by_username(session['username'])
        if current_user:
            current_user_id = current_user['id']
    
    is_owner = current_user_id == user['id']
    if not is_owner:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get all user's media
    media = get_media_for_user_gallery(puid, current_user_id, False)
    
    return jsonify(media), 200

@main_bp.route('/api/albums/group-media/<group_puid>')
def get_group_media_for_selection(group_puid):
    """API endpoint to get media for bulk add selection in group albums"""
    from db_queries.albums import get_group_media_for_user
    from db_queries.users import get_user_by_username
    from db_queries.groups import get_group_by_puid, is_user_group_member
    
    # Check authentication for both local and federated users
    current_user = None

    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if viewer_puid:
            from db_queries.users import get_user_by_puid
            current_user = get_user_by_puid(viewer_puid)
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])

    if not current_user:
        return jsonify({'error': 'Not authenticated'}), 401
    
    # Check group membership
    group = get_group_by_puid(group_puid)
    if not group:
        return jsonify({'error': 'Group not found'}), 404
    
    if not is_user_group_member(current_user['id'], group['id']):
        return jsonify({'error': 'Not a group member'}), 403
    
    # Get only this user's media in the group
    media_items = get_group_media_for_user(group_puid, current_user['puid'])
    
    return jsonify(media_items), 200

@main_bp.route('/profile_pictures/<path:filename>')
def serve_profile_picture(filename):
    """Serves profile pictures from their dedicated storage directory."""
    return send_from_directory(current_app.config['PROFILE_PICTURE_STORAGE_DIR'], filename)

# NEW ROUTE for serving event pictures
@main_bp.route('/event_pictures/<path:filename>')
def serve_event_picture(filename):
    """Serves event pictures from their dedicated storage directory."""
    # The filename will contain the 'event_pics/<puid>/event_pic.ext' structure
    event_pics_dir = os.path.join(current_app.config['PROFILE_PICTURE_STORAGE_DIR'])
    return send_from_directory(event_pics_dir, filename)


@main_bp.route('/media/<puid>/<path:filename>')
def serve_user_media(puid, filename):
    """
    Serves a media file for a given user PUID.
    Checks uploads path first (writable), then media path (read-only).
    """
    user = get_user_by_puid(puid)
    if not user:
        abort(404, "User not found.")

    decoded_filename = os.path.normpath(filename)
    
    # Check if it's a profile picture
    if decoded_filename.startswith('profile.'):
        directory = os.path.join(current_app.config['PROFILE_PICTURE_STORAGE_DIR'], user['puid'])
        base_filename = decoded_filename
    else:
        # NEW: Check uploads_path first (writable location)
        if user.get('uploads_path'):
            uploads_dir = os.path.join(current_app.config['USER_UPLOADS_BASE_DIR'], user['uploads_path'])
            subfolder_path = os.path.dirname(decoded_filename)
            if subfolder_path:
                uploads_dir = os.path.join(uploads_dir, subfolder_path)
            
            base_filename = os.path.basename(decoded_filename)
            uploads_file_path = os.path.join(uploads_dir, base_filename)
            
            if os.path.exists(uploads_file_path):
                # File found in uploads, serve it
                return send_from_directory(uploads_dir, base_filename, as_attachment=False)
        
        # Fall back to read-only media path
        if not user.get('media_path'):
            abort(404, "User does not have a configured media path.")
        
        directory = os.path.join(current_app.config['USER_MEDIA_BASE_DIR'], user['media_path'])
        subfolder_path = os.path.dirname(decoded_filename)
        if subfolder_path:
            directory = os.path.join(directory, subfolder_path)
        base_filename = os.path.basename(decoded_filename)

    # Security check
    valid_bases = [
        current_app.config['USER_MEDIA_BASE_DIR'],
        current_app.config['USER_UPLOADS_BASE_DIR'],
        current_app.config['PROFILE_PICTURE_STORAGE_DIR']
    ]
    
    if not any(os.path.abspath(directory).startswith(os.path.abspath(base)) for base in valid_bases):
        abort(400, "Invalid media path.")

    if not os.path.exists(os.path.join(directory, base_filename)):
        abort(404, "File not found.")

    return send_from_directory(directory, base_filename, as_attachment=False)

@main_bp.route('/post/<string:cuid>/disable_comments', methods=['POST'])
def disable_comments_route(cuid):
    """
    Disables comments on a post.
    Authorized for post author, profile owner, group admin/mod, or node admin.
    """
    current_user = None
    if session.get('is_federated_viewer'):
        viewer_puid = session.get('federated_viewer_puid')
        if not viewer_puid:
            flash('Unauthorized. Federated session is invalid.', 'danger')
            return redirect(request.referrer or url_for('main.index'))
        current_user = get_user_by_puid(viewer_puid)
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])
    else:
        flash('Please log in to perform this action.', 'danger')
        return redirect(url_for('auth.login'))

    if not current_user:
        flash('Current user not found.', 'danger')
        return redirect(url_for('auth.login'))

    post = get_post_by_cuid(cuid)
    if not post:
        flash('Post not found.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    # --- PERMISSION CHECK ---
    is_author = post['author']['puid'] == current_user['puid']
    is_profile_owner = False
    is_group_moderator = False
    is_node_admin = session.get('is_admin', False)
    is_event_creator = False # NEW: Initialize to False

    if post.get('profile_owner') and post['profile_owner'].get('puid'):
        is_profile_owner = post['profile_owner']['puid'] == current_user['puid']

    if post.get('group') and post['group'].get('id'):
        is_group_moderator = is_user_group_moderator_or_admin(current_user['id'], post['group']['id'])

    # NEW: Check if it's an event post and if the current user created the event
    if post.get('event') and post['event'].get('created_by_user_puid'):
        if post['event']['created_by_user_puid'] == current_user['puid']:
            is_event_creator = True

    if not (is_author or is_profile_owner or is_group_moderator or is_node_admin or is_event_creator):
        flash('You are not authorized to disable comments on this post.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    # --- ACTION ---
    if disable_comments_for_post(cuid):
        # Federate the change
        distribute_post_comment_status_update(cuid, current_user)
        flash('Comments have been permanently disabled for this post.', 'success')
    else:
        flash('Failed to disable comments.', 'danger')

    # Add anchor to scroll back to the post
    if request.referrer:
        return redirect(request.referrer + f'#post-{cuid}')
    else:
        return redirect(url_for('main.view_post', cuid=cuid, _anchor=f'post-{cuid}'))
    
@main_bp.route('/api/page/friends')
def get_my_friends_content():
    """
    API endpoint to fetch the HTML for the "My Friends/Followers" content.
    """
    if 'username' not in session:
        return jsonify({'error': 'Authentication required.'}), 401

    current_user = get_user_by_username(session['username'])
    if not current_user:
        return jsonify({'error': 'User not found.'}), 404
    
    is_admin_session = session.get('is_admin', False)
    
    # Get friends OR followers depending on user type
    if current_user['user_type'] == 'public_page':
        from db_queries.followers import get_followers
        friends = get_followers(current_user['id'])
        # Public pages don't have friend requests or blocking
        followed_pages = []
        pending_incoming_requests = []
        pending_outgoing_requests = []
        blocked_friends = []
    else:
        friends = get_friends_list(current_user['id'])
        # Get pages this user follows
        from db_queries.followers import get_following_pages
        followed_pages = get_following_pages(current_user['id'])
        # Get pending friend requests
        from db_queries.friends import get_pending_friend_requests, get_outgoing_friend_requests, get_blocked_friends_list
        pending_incoming_requests = get_pending_friend_requests(current_user['id'])
        pending_outgoing_requests = get_outgoing_friend_requests(current_user['id'])
        # Get blocked friends
        blocked_friends = get_blocked_friends_list(current_user['id'])

    # Render the *partial* template
    return render_template('_friends_content.html',
                           profile_user=current_user,
                           friends=friends,
                           followed_pages=followed_pages,
                           pending_incoming_requests=pending_incoming_requests,
                           pending_outgoing_requests=pending_outgoing_requests,
                           blocked_friends=blocked_friends,
                           is_owner=True)

@main_bp.route('/api/post/<string:cuid>/tagged_users')
def get_post_tagged_users(cuid):
    """
    API endpoint to fetch tagged users for a specific post.
    Returns user details including profile picture URLs and profile URLs.
    """
    from db_queries.posts import get_post_by_cuid
    from db_queries.friends import get_friends_list
    import json
    
    post = get_post_by_cuid(cuid)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    
    # Get tagged user PUIDs
    tagged_puids = []
    if post.get('tagged_user_puids'):
        if isinstance(post['tagged_user_puids'], str):
            try:
                tagged_puids = json.loads(post['tagged_user_puids'])
            except json.JSONDecodeError:
                tagged_puids = []
        else:
            tagged_puids = post['tagged_user_puids']
    
    if not tagged_puids:
        return jsonify({'tagged_users': []})
    
    # Get current user's friends for mutual friends count (if logged in)
    current_user_friends = []
    if 'username' in session and not session.get('is_admin'):
        current_user = get_user_by_username(session['username'])
        if current_user:
            current_user_friends = [f['puid'] for f in get_friends_list(current_user['id'])]
    
    # Get insecure mode setting
    insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
    protocol = "http" if insecure_mode else "https"
    
    # Build user details
    tagged_users = []
    for puid in tagged_puids:
        user = get_user_by_puid(puid)
        if user:
            # Build profile picture URL
            if user.get('profile_picture_path'):
                if user.get('hostname'):
                    profile_picture_url = f"{protocol}://{user['hostname']}/profile_pictures/{user['profile_picture_path']}"
                else:
                    profile_picture_url = url_for('main.serve_profile_picture', filename=user['profile_picture_path'])
            else:
                profile_picture_url = None
            
            # Build profile URL (use existing context processor function pattern)
            if user.get('hostname'):
                profile_url = f"{protocol}://{user['hostname']}/u/{puid}"
            else:
                profile_url = url_for('main.user_profile', puid=puid)
            
            # Calculate mutual friends (if applicable)
            mutual_friends = 0
            if current_user_friends and user.get('puid') in current_user_friends:
                # This user is already a friend, so don't count
                pass
            
            # Check if can add friend
            can_add_friend = False
            if 'username' in session and not session.get('is_admin'):
                current_user = get_user_by_username(session['username'])
                if current_user and current_user['puid'] != puid:
                    # Check if not already friends
                    can_add_friend = puid not in current_user_friends
            
            tagged_users.append({
                'puid': puid,
                'display_name': user['display_name'],
                'profile_picture_url': profile_picture_url,
                'profile_url': profile_url,
                'mutual_friends': mutual_friends,
                'can_add_friend': can_add_friend
            })
    
    return jsonify({'tagged_users': tagged_users})

def get_media_for_post(post_id):
    """Get all media items for a post."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, muid, media_file_path, alt_text, origin_hostname
        FROM post_media
        WHERE post_id = ?
        ORDER BY id
    """, (post_id,))
    
    media_items = cursor.fetchall()
    
    # Add media_type based on file extension
    result = []
    for item in media_items:
        media_dict = dict(item)
        file_path = media_dict['media_file_path'].lower()
        if file_path.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')):
            media_dict['media_type'] = 'image'
        elif file_path.endswith(('.mp4', '.mov', '.webm', '.avi', '.mkv')):
            media_dict['media_type'] = 'video'
        else:
            media_dict['media_type'] = 'other'
        result.append(media_dict)
    
    return result

def get_media_details_by_muid(muid):
    """Get complete media details by MUID including all necessary fields for media view page."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT 
            pm.id,
            pm.muid, 
            pm.post_id,
            pm.media_file_path,
            pm.alt_text,
            pm.origin_hostname,
            pm.tagged_user_puids,
            p.cuid as post_cuid
        FROM post_media pm
        JOIN posts p ON pm.post_id = p.id
        WHERE pm.muid = ?
    """, (muid,))
    result = cursor.fetchone()
    
    if result:
        media_dict = dict(result)
        # Add media_type based on file extension
        file_path = media_dict['media_file_path'].lower()
        if file_path.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')):
            media_dict['media_type'] = 'image'
        elif file_path.endswith(('.mp4', '.mov', '.webm', '.avi', '.mkv')):
            media_dict['media_type'] = 'video'
        else:
            media_dict['media_type'] = 'other'
        return media_dict
    return None

@main_bp.route('/api/media/<muid>/tagged_users')
def get_media_tagged_users(muid):
    """
    API endpoint to get all tagged users for a media item.
    Similar to /api/post/<cuid>/tagged_users but for media.
    Returns user info with profile URLs, pictures, and mutual friends.
    """
    # Get current user for mutual friends calculation
    current_user_friends = set()
    current_user_puid = None
    
    if 'username' in session and not session.get('is_admin'):
        current_user = get_user_by_username(session['username'])
        if current_user:
            current_user_puid = current_user['puid']
            # CORRECTED: Use get_friends_list instead of get_friends
            friends_list = get_friends_list(current_user['id'])
            current_user_friends = {friend['puid'] for friend in friends_list}
    elif session.get('is_federated_viewer'):
        current_user_puid = session.get('federated_viewer_puid')
        # Federated viewers don't have mutual friends
    
    # Get media tags
    from db_queries.media import get_media_tags
    tagged_users_data = get_media_tags(muid)
    
    # Build response with additional info
    tagged_users = []
    for user in tagged_users_data:
        puid = user['puid']
        
        # Build profile URL
        if user['hostname']:
            insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
            protocol = 'http' if insecure_mode else 'https'
            profile_url = f"{protocol}://{user['hostname']}/u/{puid}"
        else:
            profile_url = url_for('main.user_profile', puid=puid)
        
        # Build profile picture URL
        if user['profile_picture_path']:
            if user['hostname']:
                insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
                protocol = 'http' if insecure_mode else 'https'
                profile_picture_url = f"{protocol}://{user['hostname']}/profile_pictures/{user['profile_picture_path']}"
            else:
                profile_picture_url = url_for('main.serve_profile_picture', filename=user['profile_picture_path'])
        else:
            profile_picture_url = None
        
        # Calculate mutual friends (simplified for now)
        mutual_friends = 0
        
        # Check if can add friend
        can_add_friend = False
        if 'username' in session and not session.get('is_admin'):
            current_user = get_user_by_username(session['username'])
            if current_user and current_user['puid'] != puid:
                # Check if not already friends
                can_add_friend = puid not in current_user_friends
        
        tagged_users.append({
            'puid': puid,
            'display_name': user['display_name'],
            'profile_picture_url': profile_picture_url,
            'profile_url': profile_url,
            'mutual_friends': mutual_friends,
            'can_add_friend': can_add_friend
        })
    
    return jsonify({'tagged_users': tagged_users})