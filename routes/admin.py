# routes/admin.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app, g
import os
import sys
import secrets
from datetime import datetime, timedelta
import requests
import sqlite3
from utils.password_validation import validate_password

# CIRCULAR IMPORT FIX: Database and federation imports are moved inside the functions that use them.

# Import federation utilities from the renamed file
from utils.federation_utils import get_remote_node_api_url
# NEW: Import email utilities
from utils.email_utils import get_smtp_config, send_email
from utils.email_templates import get_email_template, get_base_url


admin_bp = Blueprint('admin', __name__)

@admin_bp.before_request
def admin_required():
    """Ensures only admin users can access admin routes."""
    if 'username' not in session or not session.get('is_admin'):
        flash('Unauthorized access. Please log in as an admin.', 'danger')
        return redirect(url_for('auth.login'))

@admin_bp.route('/admin')
def admin_dashboard():
    """Admin dashboard page. Accessible only by admin users."""
    from db_queries.federation import get_node_nu_id
    from db_queries.users import get_admin_user
    nu_id = get_node_nu_id()
    admin_user = get_admin_user()
    return render_template('admin_dashboard.html', username=session['username'], nu_id=nu_id, admin_user=admin_user)

@admin_bp.route('/admin/update_email', methods=['POST'])
def update_admin_email_route():
    """Updates the admin user's email address."""
    from db_queries.users import get_admin_user, update_admin_email
    email = request.form.get('email')
    admin_user = get_admin_user()
    if admin_user:
        if update_admin_email(admin_user['id'], email):
            flash('Admin email updated successfully!', 'success')
        else:
            flash('Failed to update admin email.', 'danger')
    else:
        flash('Admin user not found.', 'danger')
    return redirect(url_for('admin.admin_dashboard'))

# --- NEW: Email Settings Routes ---

@admin_bp.route('/admin/email_settings', methods=['GET', 'POST'])
def admin_email_settings():
    """Admin page to configure SMTP email settings."""
    from db import get_db

    if request.method == 'POST':
        db = get_db()
        try:
            settings_to_save = [
                ('smtp_enabled', str(request.form.get('smtp_enabled') == 'on')),
                ('smtp_host', request.form.get('smtp_host')),
                ('smtp_port', request.form.get('smtp_port')),
                ('smtp_username', request.form.get('smtp_username')),
                ('smtp_ignore_cert_errors', str(request.form.get('smtp_ignore_cert_errors') == 'on')),
                ('smtp_from_address', request.form.get('smtp_from_address')),
            ]
            
            # Only update the password if a new value is provided
            smtp_password = request.form.get('smtp_password')
            if smtp_password:
                settings_to_save.append(('smtp_password', smtp_password))

            for key, value in settings_to_save:
                db.execute(
                    "INSERT OR REPLACE INTO node_config (key, value) VALUES (?, ?)",
                    (key, value)
                )
            db.commit()
            flash('SMTP settings saved successfully!', 'success')

            # If the test button was clicked, send a test email
            if 'test_email' in request.form:
                from db_queries.users import get_admin_user
                from utils.email_templates import get_email_template
                admin_user = get_admin_user()
                if not admin_user or not admin_user.get('email'):
                    flash('Cannot send test email: Admin email address is not set.', 'warning')
                else:
                    # Generate a beautiful test email using the template
                    test_content = '''
                        <p>This is a test email from your Nebulae instance.</p>
                        <p>If you're reading this, your SMTP settings are configured correctly! 🎉</p>
                        <p style="margin-top: 20px; padding: 15px; background-color: #f3f4f6; border-left: 4px solid #4f46e5; border-radius: 4px;">
                            <strong>What's Next?</strong><br>
                            Your email notifications are now ready to keep you connected with your Nebulae community.
                        </p>
                    '''
                    
                    html_body = get_email_template(
                        username=admin_user.get('display_name') or admin_user.get('username') or 'Admin',
                        subject="Test Email",
                        preview_text="Testing your Nebulae email configuration",
                        main_content=test_content,
                        action_button_text="Visit Your Nebulae",
                        action_button_url=get_base_url(),
                        preview_content=None
                    )
                    
                    success, message = send_email(
                        recipient=admin_user['email'],
                        subject="Nebulae - Test Email",
                        body_html=html_body
                    )
                    flash(message, 'success' if success else 'danger')

        except sqlite3.Error as e:
            db.rollback()
            flash(f"Database error saving settings: {e}", 'danger')
        
        return redirect(url_for('admin.admin_email_settings'))

    # For GET request
    smtp_config = get_smtp_config()
    return render_template('admin_email_settings.html', config=smtp_config)


# --- End Email Settings Routes ---

# --- NEW: Push Notification Settings Routes ---

@admin_bp.route('/admin/push_settings', methods=['GET', 'POST'])
def admin_push_settings():
    """Admin page to configure push notification settings."""
    from utils.vapid_utils import (
        get_vapid_keys_from_config,
        generate_vapid_keys,
        store_vapid_keys_in_config
    )
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'generate':
            try:
                # Generate new VAPID keys
                keys = generate_vapid_keys()
                
                # Store in database
                store_vapid_keys_in_config(keys['private_key'], keys['public_key'])
                
                flash('VAPID keys generated successfully! Push notifications are now enabled.', 'success')
            except ImportError as e:
                flash(f'Error: {str(e)}', 'danger')
            except Exception as e:
                flash(f'Failed to generate VAPID keys: {str(e)}', 'danger')
                import traceback
                traceback.print_exc()
        
        return redirect(url_for('admin.admin_push_settings'))
    
    # GET request - show current status
    vapid_keys = get_vapid_keys_from_config()
    
    return render_template('admin_push_settings.html',
                          username=session['username'],
                          vapid_configured=vapid_keys is not None,
                          public_key=vapid_keys['public_key'] if vapid_keys else None)


@admin_bp.route('/admin/post_local', methods=['GET', 'POST'])
def admin_post_local():
    """Allows admin to post messages to local users' timelines."""
    from db_queries.users import get_user_by_username
    from db_queries.posts import add_post

    if request.method == 'POST':
        post_content = request.form['content']
        admin_username = session['username']
        
        admin_user = get_user_by_username(admin_username)
        if admin_user:
            add_post(admin_user['id'], admin_user['id'], post_content, privacy_setting='local', media_files=[])
            flash('Message posted to local timelines!', 'success')
        else:
            flash('Admin user not found, could not post message.', 'danger')
            
        return redirect(url_for('admin.admin_dashboard'))
    return render_template('admin_post_local.html')

@admin_bp.route('/admin/manage_users', methods=['GET'])
def admin_manage_users():
    """Admin page to view and manage users."""
    from db_queries.users import get_all_local_users
    users = get_all_local_users()
    return render_template('admin_manage_users.html', users=users)

@admin_bp.route('/admin/add_user', methods=['GET', 'POST'])
def admin_add_user():
    """Admin page to add a new user."""
    from db_queries.users import add_user, get_all_local_users, get_user_by_username
    from db_queries.profiles import update_profile_info_field
    from db_queries.parental_controls import set_parental_control
    from db_queries.friends import send_friend_request_db, accept_friend_request_db, get_pending_friend_requests
    from datetime import datetime, date
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        display_name = request.form.get('display_name') or username
        date_of_birth = request.form.get('date_of_birth')
        parent_user_id = request.form.get('parent_user_id')
        
        # Validate password against security requirements
        is_valid, error_message = validate_password(password)
        if not is_valid:
            flash(error_message, 'danger')
            potential_parents = [user for user in get_all_local_users() 
                               if user['user_type'] in ['user', 'admin'] and user['username'] != 'admin']
            return render_template('admin_add_user.html', 
                                 today=date.today().isoformat(),
                                 potential_parents=potential_parents)
        
        # Validate date of birth
        if not date_of_birth:
            flash('Date of birth is required.', 'danger')
            potential_parents = [user for user in get_all_local_users() 
                               if user['user_type'] in ['user', 'admin'] and user['username'] != 'admin']
            return render_template('admin_add_user.html', 
                                 today=date.today().isoformat(),
                                 potential_parents=potential_parents)
        
        try:
            dob = datetime.strptime(date_of_birth, '%Y-%m-%d').date()
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            
            # Check if parent is required
            if age < 16 and not parent_user_id:
                flash('A parent/guardian must be assigned for users under 16.', 'danger')
                potential_parents = [user for user in get_all_local_users() 
                                   if user['user_type'] in ['user', 'admin'] and user['username'] != 'admin']
                return render_template('admin_add_user.html', 
                                     today=date.today().isoformat(),
                                     potential_parents=potential_parents)
            
        except ValueError:
            flash('Invalid date of birth format.', 'danger')
            potential_parents = [user for user in get_all_local_users() 
                               if user['user_type'] in ['user', 'admin'] and user['username'] != 'admin']
            return render_template('admin_add_user.html', 
                                 today=date.today().isoformat(),
                                 potential_parents=potential_parents)
        
        # Create the user
        if add_user(username, password, display_name, user_type='user'):
            # Get the newly created user's ID
            new_user = get_user_by_username(username)
            
            # Store DOB in profile_info with default privacy (not visible)
            update_profile_info_field(new_user['id'], 'dob', date_of_birth, 
                                     privacy_public=0, privacy_local=0, privacy_friends=0)
            
            # If under 16, set up parental controls
            if age < 16 and parent_user_id:
                # Set parental control relationship
                if set_parental_control(new_user['id'], int(parent_user_id)):
                    # Force friendship between parent and child
                    # Send friend request from child to parent
                    send_friend_request_db(new_user['id'], int(parent_user_id))
                    # Auto-accept it
                    pending = get_pending_friend_requests(int(parent_user_id))
                    for req in pending:
                        if req['sender_id'] == new_user['id']:
                            accept_friend_request_db(req['id'], int(parent_user_id))
                            break
                    
                    flash(f'User "{username}" added successfully with parental controls.', 'success')
                else:
                    flash(f'User "{username}" added but parental control setup failed.', 'warning')
            else:
                flash(f'User "{username}" added successfully!', 'success')
            
            return redirect(url_for('admin.admin_manage_users'))
        else:
            flash(f'User "{username}" already exists.', 'danger')
    
    # GET request - show form with potential parents
    from db_queries.users import get_all_local_users
    from datetime import date
    potential_parents = [user for user in get_all_local_users() 
                        if user['user_type'] in ['user', 'admin'] and user['username'] != 'admin']
    return render_template('admin_add_user.html', 
                         today=date.today().isoformat(),
                         potential_parents=potential_parents)

# --- Public Page Management ---

@admin_bp.route('/admin/manage_public_pages', methods=['GET'])
def admin_manage_public_pages():
    """Admin page to view and manage public pages."""
    from db_queries.users import get_all_public_pages
    pages = get_all_public_pages()
    return render_template('admin_manage_public_pages.html', public_pages=pages)

@admin_bp.route('/admin/add_public_page', methods=['GET', 'POST'])
def admin_add_public_page():
    """Admin page to add a new public page."""
    from db_queries.users import add_user
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        display_name = request.form.get('display_name') or username
        
        # Validate password against security requirements
        is_valid, error_message = validate_password(password)
        if not is_valid:
            flash(error_message, 'danger')
            return render_template('admin_add_public_page.html')
        
        # Create a user with the 'public_page' type
        if add_user(username, password, display_name, user_type='public_page'):
            flash(f'Public page "{username}" added successfully!', 'success')
            return redirect(url_for('admin.admin_manage_public_pages'))
        else:
            flash(f'A user or page with the username "{username}" already exists.', 'danger')
    return render_template('admin_add_public_page.html')


@admin_bp.route('/admin/reset_password/<username>', methods=['POST'])
def admin_reset_password(username):
    """Admin endpoint to reset a user's password. Returns JSON response."""
    from db_queries.users import get_user_by_username, update_user_password, clear_password_must_change
    user = get_user_by_username(username)
    if not user:
        return jsonify({'error': f'User "{username}" not found.'}), 404

    new_password = request.form.get('new_password')
    if not new_password:
        return jsonify({'error': 'New password is required.'}), 400

    # Validate password against security requirements
    is_valid, error_message = validate_password(new_password)
    if not is_valid:
        return jsonify({'error': error_message}), 400

    if update_user_password(username, new_password):
        # Clear the password_must_change flag if it was set
        if user.get('password_must_change'):
            clear_password_must_change(user['id'])
        return jsonify({'message': f'Password for "{username}" reset successfully!'}), 200
    else:
        return jsonify({'error': f'Failed to update password for "{username}".'}), 500

@admin_bp.route('/admin/change_username/<username>', methods=['POST'])
def admin_change_username(username):
    """Admin endpoint to change a user's username. Returns JSON response."""
    from db_queries.users import get_user_by_username, update_username
    user = get_user_by_username(username)
    if not user:
        return jsonify({'error': f'User "{username}" not found.'}), 404

    new_username = request.form.get('new_username')
    if not new_username:
        return jsonify({'error': 'New username is required.'}), 400

    success, message = update_username(user['id'], new_username)
    if success:
        return jsonify({'message': f'Username for "{username}" changed to "{new_username}" successfully!'}), 200
    else:
        return jsonify({'error': message}), 400

@admin_bp.route('/admin/delete_user/<username>', methods=['POST'])
def admin_delete_user(username):
    """Admin action to delete a user or public page."""
    from db_queries.users import delete_user, get_user_by_username
    
    # Check the user type before deleting to know where to redirect
    user_to_delete = get_user_by_username(username)
    if not user_to_delete:
        flash(f'User or page "{username}" not found.', 'danger')
        return redirect(request.referrer or url_for('admin.admin_dashboard'))

    user_type = user_to_delete.get('user_type')

    if delete_user(username):
        flash(f'Successfully deleted "{username}"!', 'success')
    else:
        flash(f'Failed to delete "{username}".', 'danger')
    
    if user_type == 'public_page':
        return redirect(url_for('admin.admin_manage_public_pages'))
    else:
        return redirect(url_for('admin.admin_manage_users'))


@admin_bp.route('/admin/set_user_media_path/<username>', methods=['POST'])
def admin_set_user_media_path(username):
    """Admin endpoint to set/update a user's media volume path and uploads path. Returns JSON response."""
    from db_queries.users import get_user_by_username, update_user_media_paths
    
    user = get_user_by_username(username)
    if not user:
        return jsonify({'error': f'User "{username}" not found.'}), 404

    media_path = request.form.get('media_path', '').strip()
    uploads_path = request.form.get('uploads_path', '').strip()

    # Validate media_path if provided
    if media_path and not os.path.isdir(os.path.join(current_app.config['USER_MEDIA_BASE_DIR'], media_path)):
        return jsonify({'error': f'Error: The media path "{media_path}" does not exist or is not a directory inside the container. Please ensure it is correctly mounted in docker-compose.yml.'}), 400

    # Validate uploads_path if provided
    if uploads_path:
        full_uploads_path = os.path.join(current_app.config['USER_UPLOADS_BASE_DIR'], uploads_path)
        if not os.path.isdir(full_uploads_path):
            return jsonify({'error': f'Error: The uploads path "{uploads_path}" does not exist or is not a directory inside the container. Please ensure it is correctly mounted in docker-compose.yml.'}), 400
        
        # Test if writable
        test_file = os.path.join(full_uploads_path, '.write_test')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except Exception as e:
            return jsonify({'error': f'Error: The uploads path "{uploads_path}" is not writable: {str(e)}'}), 400

    if update_user_media_paths(username, media_path if media_path else None, uploads_path if uploads_path else None):
        return jsonify({'message': f'Media paths for "{username}" updated successfully!'}), 200
    else:
        return jsonify({'error': f'Failed to update media paths for "{username}".'}), 500

# --- Group Management Routes ---
@admin_bp.route('/admin/manage_groups')
def manage_groups():
    """Admin page to view and manage groups."""
    from db_queries.groups import get_all_groups, get_group_admins
    from db_queries.users import get_all_local_users
    groups = get_all_groups()
    # BUG FIX: Allow both 'user' and 'admin' types to be group admins, but exclude the main 'admin' account.
    users = [user for user in get_all_local_users() if user['user_type'] in ['user', 'admin'] and user['username'] != 'admin']
    
    # For each group, fetch its admins
    for group in groups:
        group['admins'] = get_group_admins(group['id'])

    return render_template('admin_manage_groups.html', groups=groups, all_users=users)

@admin_bp.route('/admin/add_group', methods=['GET', 'POST'])
def admin_add_group():
    """Admin page to add a new group."""
    from db_queries.groups import add_group
    from db_queries.users import get_user_id_by_username, get_all_local_users

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        admin_user_id = request.form.get('admin_user_id')
        
        if not name or not admin_user_id:
            flash('Group name and an initial admin are required.', 'danger')
            return redirect(url_for('admin.admin_add_group'))

        created_by_user_id = get_user_id_by_username(session['username'])
        
        if add_group(name, description, created_by_user_id, admin_user_id):
            flash(f'Group "{name}" created successfully!', 'success')
            return redirect(url_for('admin.manage_groups'))
        else:
            flash('Failed to create group.', 'danger')

    # For the GET request, fetch local users to populate the admin selection dropdown
    # BUG FIX: Allow both 'user' and 'admin' types to be group admins, but exclude the main 'admin' account.
    users = [user for user in get_all_local_users() if user['user_type'] in ['user', 'admin'] and user['username'] != 'admin']
    return render_template('admin_add_group.html', users=users)

@admin_bp.route('/admin/delete_group/<int:group_id>', methods=['POST'])
def admin_delete_group(group_id):
    """Admin action to delete a group."""
    from db_queries.groups import delete_group
    if delete_group(group_id):
        flash('Group deleted successfully.', 'success')
    else:
        flash('Failed to delete group.', 'danger')
    return redirect(url_for('admin.manage_groups'))

@admin_bp.route('/admin/group/<int:group_id>/add_admin', methods=['POST'])
def admin_add_group_admin(group_id):
    """Admin action to add a new admin to a group."""
    from db_queries.groups import add_group_admin
    user_id = request.form.get('user_id')
    if not user_id:
        flash('No user selected.', 'danger')
        return redirect(url_for('admin.manage_groups'))

    if add_group_admin(group_id, user_id):
        flash('New group admin added successfully.', 'success')
    else:
        flash('Failed to add new group admin. They might already be an admin.', 'danger')
    return redirect(url_for('admin.manage_groups'))

@admin_bp.route('/admin/remove_group_admin/<int:group_id>/<int:user_id>', methods=['POST'])
def admin_remove_group_admin(group_id, user_id):
    """Admin action to remove an admin from a group."""
    from db_queries.groups import remove_group_admin
    success, message = remove_group_admin(group_id, user_id)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    return redirect(url_for('admin.manage_groups'))

# --- FEDERATION ROUTES ---

@admin_bp.route('/admin/manage_nodes', methods=['GET'])
def manage_nodes():
    """Displays the node management page."""
    from db_queries.federation import get_all_connected_nodes_grouped
    grouped_nodes = get_all_connected_nodes_grouped()
    return render_template('admin_manage_nodes.html', 
                       full_connections=grouped_nodes['full'],
                       targeted_subscriptions=grouped_nodes['targeted'],
                       pairing_token=None,  # No token until user generates one
                       token_expires_at=None)

@admin_bp.route('/admin/generate_pairing_token', methods=['POST'])
def generate_pairing_token():
    """Generates a new single-use pairing token and displays it."""
    from db_queries.federation import create_pairing_token, get_all_connected_nodes_grouped
    from db_queries.users import get_user_id_by_username

    admin_user_id = get_user_id_by_username(session['username'])
    token = secrets.token_hex(16)
    expires_at = datetime.utcnow() + timedelta(minutes=15)
    
    if create_pairing_token(token, admin_user_id, expires_at):
        flash('New pairing token generated successfully!', 'success')
    else:
        flash('Failed to generate pairing token.', 'danger')

    # Use grouped nodes instead of get_all_connected_nodes
    grouped_nodes = get_all_connected_nodes_grouped()
    return render_template('admin_manage_nodes.html', 
                           full_connections=grouped_nodes['full'],
                           targeted_subscriptions=grouped_nodes['targeted'],
                           pairing_token=token, 
                           token_expires_at=expires_at.strftime('%Y-%m-%d %H:%M:%S UTC'))

@admin_bp.route('/admin/initiate_pairing', methods=['POST'])
def initiate_pairing():
    """Initiates the handshake by sending a pairing request to a remote node."""
    from db_queries.federation import add_pending_node, update_node_connection_status
    
    remote_hostname = request.form.get('hostname')
    token = request.form.get('token')

    if not remote_hostname or not token:
        flash('Hostname and token are required.', 'danger')
        return redirect(url_for('admin.manage_nodes'))

    if not add_pending_node(remote_hostname):
        flash(f'A connection with {remote_hostname} already exists or is pending.', 'danger')
        return redirect(url_for('admin.manage_nodes'))

    try:
        insecure_mode = current_app.config.get('FEDERATION_INSECURE_MODE', False)
        verify_ssl = not insecure_mode

        remote_url = get_remote_node_api_url(
            remote_hostname,
            '/federation/initiate_pairing',
            insecure_mode
        )
        
        local_hostname = current_app.config.get('NODE_HOSTNAME')
        if not local_hostname:
            flash('CRITICAL ERROR: NODE_HOSTNAME is not configured on this server. Cannot initiate pairing.', 'danger')
            return redirect(url_for('admin.manage_nodes'))

        payload = {
            'hostname': local_hostname,
            'token': token,
            'nu_id': g.nu_id  # Send our NUID
        }
        
        response = requests.post(remote_url, json=payload, timeout=10, verify=verify_ssl)
        response.raise_for_status()

        response_data = response.json()
        shared_secret = response_data.get('shared_secret')
        remote_nu_id = response_data.get('nu_id') # Receive their NUID

        if not shared_secret or not remote_nu_id:
            raise ValueError("Shared secret or NUID not found in response from remote node.")

        if update_node_connection_status(remote_hostname, 'connected', shared_secret, remote_nu_id):
            flash(f'Successfully connected to {remote_hostname}!', 'success')
        else:
            flash('Received success from remote node, but failed to update local database.', 'danger')

    except requests.exceptions.Timeout:
        flash(f'Error: The connection to {remote_hostname} timed out. Please check the hostname and that the other node is running.', 'danger')
    except requests.exceptions.RequestException as e:
        flash(f'Error connecting to remote node: {e}', 'danger')
    except (ValueError, KeyError) as e:
        flash(f'Error processing response from remote node: {e}', 'danger')
    
    return redirect(url_for('admin.manage_nodes'))


@admin_bp.route('/admin/remove_node_connection/<int:node_id>', methods=['POST'])
def remove_node_connection_route(node_id):
    """Removes a connection to another node."""
    from db_queries.federation import remove_node_connection
    if remove_node_connection(node_id):
        flash('Node connection removed successfully.', 'success')
    else:
        flash('Failed to remove node connection.', 'danger')
    return redirect(url_for('admin.manage_nodes'))

@admin_bp.route('/admin/edit_node/<int:node_id>', methods=['POST'])
def edit_node(node_id):
    """Updates the nickname for a connected node."""
    from db_queries.federation import update_node_nickname
    nickname = request.form.get('nickname')
    if update_node_nickname(node_id, nickname):
        flash('Node nickname updated successfully!', 'success')
    else:
        flash('Failed to update node nickname.', 'danger')
    return redirect(url_for('admin.manage_nodes'))

# --- DATABASE BACKUP & RESTORE ROUTES ---

@admin_bp.route('/admin/database_backups')
def database_backups():
    """Admin page for database backup management."""
    from utils.backup_utils import list_backups, get_backup_settings
    
    backups = list_backups()
    settings = get_backup_settings()
    
    return render_template('admin_database_backups.html', 
                         backups=backups,
                         settings=settings)


@admin_bp.route('/admin/backup/create', methods=['POST'])
def create_database_backup():
    """Create an ad-hoc database backup."""
    from utils.backup_utils import create_backup
    
    backup_name = request.form.get('backup_name', '').strip()
    
    success, message, backup_path = create_backup(backup_name=backup_name, is_scheduled=False)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('admin.database_backups'))


@admin_bp.route('/admin/backup/restore/<backup_filename>', methods=['POST'])
def restore_database_backup(backup_filename):
    """Restore database from a backup file."""
    from utils.backup_utils import restore_backup
    
    # Get confirmation from form
    confirmed = request.form.get('confirmed') == 'true'
    
    if not confirmed:
        flash('Restore operation not confirmed.', 'warning')
        return redirect(url_for('admin.database_backups'))
    
    success, message = restore_backup(backup_filename)
    
    if success:
        flash(message, 'success')
        # After restore, redirect to login since sessions may be invalidated
        return redirect(url_for('auth.logout'))
    else:
        flash(message, 'danger')
        return redirect(url_for('admin.database_backups'))


@admin_bp.route('/admin/backup/delete/<backup_filename>', methods=['POST'])
def delete_database_backup(backup_filename):
    """Delete a backup file."""
    from utils.backup_utils import delete_backup
    
    success, message = delete_backup(backup_filename)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('admin.database_backups'))


@admin_bp.route('/admin/backup/settings', methods=['POST'])
def save_backup_settings():
    """Save backup schedule settings."""
    from utils.backup_utils import save_backup_settings
    
    enabled = request.form.get('backup_enabled') == 'on'
    frequency = request.form.get('backup_frequency', 'daily')
    retention_days = request.form.get('backup_retention_days', '30')
    backup_time = request.form.get('backup_time', '02:00')
    
    success, message = save_backup_settings(enabled, frequency, retention_days, backup_time)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('admin.database_backups'))


@admin_bp.route('/admin/backup/cleanup', methods=['POST'])
def cleanup_old_backups():
    """Manually trigger cleanup of old backups."""
    from utils.backup_utils import cleanup_old_backups
    
    deleted_count, message = cleanup_old_backups()
    flash(message, 'success')
    
    return redirect(url_for('admin.database_backups'))

@admin_bp.route('/admin/get_parental_controls/<int:user_id>', methods=['GET'])
def get_parental_controls(user_id):
    """Get parental control settings for a user."""
    from db_queries.parental_controls import get_child_parents, requires_parental_approval
    from db_queries.users import get_user_by_id, get_all_local_users
    from db_queries.profiles import get_profile_info_for_user
    from datetime import datetime, date
    
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get current parents
    parents = get_child_parents(user_id)
    
    # Get all potential parents (exclude the child user and existing parents)
    all_users = get_all_local_users()
    existing_parent_ids = [p['parent_user_id'] for p in parents]
    available_parents = [
        u for u in all_users 
        if u['id'] != user_id and u['id'] not in existing_parent_ids and u['user_type'] in ['user', 'admin']
    ]
    
    # Check if parental controls are actually active by checking if there are parent-child relationships
    has_parental_controls = requires_parental_approval(user_id)
    
    # Calculate user's age from DOB
    age = None
    profile_info = get_profile_info_for_user(user_id, user_id, False)  # Admin viewing, so get full access
    dob_field = profile_info.get('dob')
    if dob_field and dob_field.get('value'):
        try:
            dob = datetime.strptime(dob_field['value'], '%Y-%m-%d').date()
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        except:
            age = None
    
    return jsonify({
        'requires_parental_approval': has_parental_controls,
        'parents': parents,
        'available_parents': available_parents,
        'age': age
    })

@admin_bp.route('/admin/update_parental_controls/<int:user_id>', methods=['POST'])
def update_parental_controls(user_id):
    """Update parental control settings for a user."""
    from db_queries.parental_controls import update_parental_requirement
    
    data = request.json
    requires_approval = data.get('requires_parental_approval', False)
    
    if update_parental_requirement(user_id, requires_approval):
        return jsonify({'message': 'Parental controls updated successfully'}), 200
    else:
        return jsonify({'error': 'Failed to update parental controls'}), 500

@admin_bp.route('/admin/add_parent_to_child', methods=['POST'])
def add_parent_to_child():
    """Assign a parent to monitor a child account."""
    from db_queries.parental_controls import add_parent_child_relationship
    
    data = request.json
    child_user_id = data.get('child_user_id')
    parent_user_id = data.get('parent_user_id')
    
    if not child_user_id or not parent_user_id:
        return jsonify({'error': 'Missing required fields'}), 400
    
    success, message = add_parent_child_relationship(parent_user_id, child_user_id)
    
    if success:
        return jsonify({'message': message}), 200
    else:
        return jsonify({'error': message}), 400

@admin_bp.route('/admin/remove_parent_from_child', methods=['POST'])
def remove_parent_from_child():
    """Remove a parent assignment from a child account."""
    from db_queries.parental_controls import remove_parent_child_relationship
    
    data = request.json
    child_user_id = data.get('child_user_id')
    parent_user_id = data.get('parent_user_id')
    
    if not child_user_id or not parent_user_id:
        return jsonify({'error': 'Missing required fields'}), 400
    
    success, message = remove_parent_child_relationship(parent_user_id, child_user_id)
    
    if success:
        return jsonify({'message': message}), 200
    else:
        return jsonify({'error': message}), 400