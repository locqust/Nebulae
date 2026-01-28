# routes/comments.py
import json
import traceback

from flask import (Blueprint, render_template, request, redirect, url_for, session, flash, jsonify)

# Import database functions from the new query modules
from db_queries.users import get_user_id_by_username, get_user_by_username, get_user_by_puid
from db_queries.posts import get_post_by_cuid
from db_queries.comments import (add_comment, get_comment_by_cuid, get_comment_by_internal_id, update_comment,
                                 delete_comment, remove_mention_from_comment, 
                                 hide_comment_for_user)
# MODIFICATION: Import is_user_group_moderator_or_admin
from db_queries.groups import is_user_group_member, is_user_group_admin, is_user_group_moderator_or_admin
# Import the distribution functions
from utils.federation_utils import distribute_comment, distribute_comment_update, distribute_comment_delete
from urllib.parse import urlparse, urlunparse

comments_bp = Blueprint('comments', __name__)


@comments_bp.route('/add_comment/<string:post_cuid>', methods=['POST'])
def add_comment_route(post_cuid):
    """Allows a logged-in user to add a comment to a post or reply to an existing comment, optionally with media."""
    current_user = None
    # FEDERATION FIX: Check for both local and federated viewer sessions.
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])

    if not current_user:
        flash('Please log in to add comments.', 'danger')
        return redirect(url_for('auth.login'))

    current_user_id = current_user['id']

    # Fetch the post first to perform permission checks
    post = get_post_by_cuid(post_cuid, viewer_user_puid=current_user['puid'])
    if not post:
        flash('Post not found.', 'danger')
        return redirect(url_for('main.index'))

    # NEW: Check if comments are disabled for this post
    if post.get('comments_disabled'):
        flash('Comments have been disabled for this post.', 'info')
        return redirect(request.referrer or url_for('main.view_post', cuid=post_cuid))

    # PERMISSIONS FIX: Check for group membership or event attendance
    if post.get('group') and not is_user_group_member(current_user_id, post['group']['id']):
        flash('You must be a member of this group to comment.', 'danger')
        return redirect(request.referrer or url_for('main.index'))
    elif post.get('event'):
        # BUG FIX: Add a safe check for the event object itself before accessing its properties
        event_data = post.get('event')
        if event_data:
            viewer_response = event_data.get('viewer_response')
            is_creator = current_user['puid'] == event_data.get('created_by_user_puid')
            if not is_creator and viewer_response not in ['attending', 'tentative']:
                flash('You must be attending or interested in the event to comment.', 'danger')
                return redirect(request.referrer or url_for('main.index'))
        else:
            # This handles the edge case where the post is an event post, but the event was deleted.
            flash('Cannot comment as the associated event is no longer available.', 'warning')
            return redirect(request.referrer or url_for('main.index'))

    comment_content = request.form.get('comment_content')
    parent_comment_id = request.form.get('parent_comment_id')
    selected_comment_media_files_json = request.form.get('selected_comment_media_files', '[]')
    media_files_for_db = json.loads(selected_comment_media_files_json)

    if not comment_content and not media_files_for_db:
        flash('Comment content or media cannot be empty.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    try:
        parent_id = int(parent_comment_id) if parent_comment_id else None
        # For group/event posts, post['profile_user_id'] will be None, which is handled correctly by add_comment
        new_comment_cuid = add_comment(post_cuid, current_user_id, comment_content, post.get('profile_user_id'),
                                     parent_id, media_files_for_db)

        if new_comment_cuid:
            distribute_comment(new_comment_cuid)
            flash('Comment added successfully!', 'success')
        else:
            flash('Failed to create comment.', 'danger')

    except Exception as e:
        error_message = str(e)
        flash(f'Failed to add comment: {error_message}', 'danger')
        print(f"ERROR: Failed to add comment: {error_message}")
        traceback.print_exc()

    # BUG FIX & REFACTOR: Safely check for the event and its puid before redirecting.
        # Add anchor to scroll back to the post
    event_data = post.get('event')
    if event_data and event_data.get('puid'):
        return redirect(url_for('events.event_profile', puid=event_data['puid'], _anchor=f'post-{post_cuid}'))
    elif request.referrer:
        # Parse referrer to properly add hash fragment
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(request.referrer)
        # Replace any existing fragment with our anchor
        redirect_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, f'post-{post_cuid}'))
        return redirect(redirect_url)
    else:
        return redirect(url_for('main.view_post', cuid=post_cuid, _anchor=f'post-{post_cuid}'))


@comments_bp.route('/edit_comment/<string:cuid>', methods=['POST'])
def edit_comment_route(cuid):
    """Allows a logged-in user to edit their own comment, optionally with media."""
    current_user = None
    # FEDERATION FIX: Check for both local and federated viewer sessions.
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])

    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 403

    is_node_admin = session.get('is_admin', False)

    comment_info = get_comment_by_cuid(cuid)
    if not comment_info:
        return jsonify({'error': 'Comment not found'}), 404

    comment = get_comment_by_internal_id(comment_info['comment_id'])
    if not comment:
        return jsonify({'error': 'Comment details not found'}), 404

    # PERMISSIONS FIX: Check authorization based on the current user's ID, not their username.
    # This now works for both local and remote users.
    if not (comment['user_id'] == current_user['id'] or is_node_admin):
        return jsonify({'error': 'Not authorized to edit this comment'}), 403

    data = request.get_json()
    new_content = data.get('content')
    selected_comment_media_files_json = data.get('selected_comment_media_files', '[]')
    media_files_for_db = json.loads(selected_comment_media_files_json)

    if not new_content and not media_files_for_db:
        return jsonify({'error': 'Comment content or media cannot be empty'}), 400

    try:
        if update_comment(cuid, new_content, media_files_for_db):
            distribute_comment_update(cuid)
            return jsonify({'message': 'Comment updated successfully!'}), 200
        else:
            return jsonify({'error': 'Failed to update comment.'}), 500
    except Exception as e:
        print(f"ERROR: Failed to edit comment {cuid}: {e}")
        traceback.print_exc()
        return jsonify({'error': 'An unexpected error occurred while updating the comment.'}), 500


@comments_bp.route('/delete_comment/<string:cuid>', methods=['POST'])
def delete_comment_route(cuid):
    """Allows a logged-in user to delete their own comment, or a post owner/admin/moderator to delete any comment on their post."""
    current_user = None
    # FEDERATION FIX: Check for both local and federated viewer sessions.
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])

    if not current_user:
        flash('Please log in to delete comments.', 'danger')
        return redirect(url_for('auth.login'))

    is_node_admin = session.get('is_admin', False)

    comment_info = get_comment_by_cuid(cuid)
    if not comment_info:
        flash('Comment not found.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    comment = get_comment_by_internal_id(comment_info['comment_id'])
    if not comment:
        flash('Comment details could not be retrieved.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    post = get_post_by_cuid(comment_info['post_cuid'])
    if not post:
        flash('Associated post not found.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    # --- PERMISSIONS CHECK ---
    # MODIFICATION: Use PUID for comment author check for consistency with posts
    is_comment_author = (comment.get('puid') == current_user.get('puid')) if comment and current_user else False

    is_post_profile_owner = False
    if post.get('profile_owner'):
        is_post_profile_owner = (post['profile_owner']['puid'] == current_user['puid'])

    # NEW CHECK: Is the current user the owner of the public page this post is on?
    is_public_page_owner = False
    if post['author'].get('user_type') == 'public_page' and post['author']['puid'] == current_user['puid']:
        is_public_page_owner = True

    is_group_moderator = False
    if post.get('group'):
        # Ensure group ID exists before checking moderator status
        group_id = post['group'].get('id')
        if group_id:
            is_group_moderator = is_user_group_moderator_or_admin(current_user['id'], group_id)

    # NEW: Check if it's an event post and if the current user created the event
    is_event_creator = False
    if post.get('event') and post['event'].get('created_by_user_puid'):
        if post['event']['created_by_user_puid'] == current_user['puid']:
            is_event_creator = True

    # Final authorization check - including group moderator status
    if not (is_comment_author or is_post_profile_owner or is_node_admin or is_group_moderator or is_public_page_owner or is_event_creator):
        flash('You are not authorized to delete this comment.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    try:
        # Pass the full comment and post objects *before* deletion for federation
        if delete_comment(cuid):
            distribute_comment_delete(comment, post)
            flash('Comment deleted successfully!', 'success')
        else:
            flash('Failed to delete comment.', 'danger')
    except Exception as e:
        flash(f'Failed to delete comment: {e}', 'danger')
        print(f"ERROR: Failed to delete comment {cuid}: {e}")
        traceback.print_exc()

    # UNINDENT THESE - same level as 'try'
    # Add anchor to scroll back to the post after deleting comment
    if request.referrer:
        return redirect(request.referrer + f'#post-{post["cuid"]}')
    else:
        return redirect(url_for('main.view_post', cuid=post['cuid'], _anchor=f'post-{post["cuid"]}'))

@comments_bp.route('/remove_mention_from_comment/<string:comment_cuid>', methods=['POST'])
def remove_mention_from_comment_route(comment_cuid):
    """
    Allows a mentioned user to remove their @mention from a comment.
    """
    current_user = None
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])

    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        display_name = current_user.get('display_name') or current_user.get('username')
        if remove_mention_from_comment(comment_cuid, display_name):
            # NEW: Distribute the mention removal to remote nodes
            from utils.federation_utils import distribute_mention_removal_comment
            distribute_mention_removal_comment(comment_cuid, display_name, current_user['puid'])
            # TODO: Optionally distribute this change to federated nodes if needed
            return jsonify({'message': 'Mention removed successfully'}), 200
        else:
            return jsonify({'error': 'Failed to remove mention'}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'An error occurred: {e}'}), 500


@comments_bp.route('/hide_comment/<string:comment_cuid>', methods=['POST'])
def hide_comment_route(comment_cuid):
    """
    Allows a user to hide a comment from their view.
    """
    current_user = None
    if session.get('is_federated_viewer'):
        current_user = get_user_by_puid(session.get('federated_viewer_puid'))
    elif 'username' in session:
        current_user = get_user_by_username(session['username'])

    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    comment_info = get_comment_by_cuid(comment_cuid)
    if not comment_info:
        return jsonify({'error': 'Comment not found'}), 404

    try:
        if hide_comment_for_user(current_user['id'], comment_info['comment_id']):
            # Delete any notifications related to this comment for this user
            from db import get_db
            db = get_db()
            cursor = db.cursor()
            cursor.execute("""
                DELETE FROM notifications
                WHERE user_id = ? AND comment_id = ?
            """, (current_user['id'], comment_info['comment_id']))
            db.commit()
            
            return jsonify({'message': 'Comment hidden successfully'}), 200
        else:
            return jsonify({'error': 'Failed to hide comment'}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'An error occurred: {e}'}), 500