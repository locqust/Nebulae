# routes/auth.py
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from db_queries.users import get_user_by_username, create_user_session, delete_session_by_id, get_user_by_email, update_user_password_by_id
from utils.auth import check_password, hash_password
from utils.email_utils import send_email
from utils.password_validation import validate_password, get_password_requirements_text

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handles user and admin login with optional 2FA.
    """
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        otp_code = request.form.get('otp_code', '').strip()

        user = get_user_by_username(username)
        
        # Check if this is a 2FA verification attempt (from login_2fa.html)
        if otp_code and 'pending_2fa_user_id' in session:
            # User is attempting 2FA verification - skip password check
            from db_queries.two_factor import get_2fa_settings, update_2fa_last_used, verify_backup_code
            import pyotp
            
            # Verify this is the same user
            if session['pending_2fa_user_id'] != user['id']:
                flash('Invalid authentication attempt', 'danger')
                session.pop('pending_2fa_user_id', None)
                session.pop('pending_2fa_username', None)
                return redirect(url_for('auth.login'))
            
            twofa_settings = get_2fa_settings(user['id'])
            
            if twofa_settings and twofa_settings['enabled']:
                # Verify OTP code
                totp = pyotp.TOTP(twofa_settings['secret'])
                
                # Try OTP first, then backup codes
                if totp.verify(otp_code, valid_window=1):
                    update_2fa_last_used(user['id'])
                    # OTP verified - continue to login completion
                elif verify_backup_code(user['id'], otp_code):
                    flash('Backup code used successfully. Consider regenerating backup codes in settings.', 'warning')
                    # Backup code verified - continue to login completion
                else:
                    flash('Invalid authentication code', 'danger')
                    return render_template('login_2fa.html', username=username)
            
            # Clear pending 2FA session data
            session.pop('pending_2fa_user_id', None)
            session.pop('pending_2fa_username', None)
            
            # Fall through to login completion below
            
        elif user and check_password(user['password'], password):
            # Initial login with valid password
            from db_queries.two_factor import get_2fa_settings
            
            # Check if 2FA is enabled for this user
            twofa_settings = get_2fa_settings(user['id'])
            
            if twofa_settings and twofa_settings['enabled']:
                # 2FA is enabled - require OTP
                session['pending_2fa_user_id'] = user['id']
                session['pending_2fa_username'] = username
                return render_template('login_2fa.html', username=username)
            
            # No 2FA - fall through to login completion below
            
        else:
            # Invalid username or password
            flash('Invalid username or password', 'danger')
            return render_template('login.html')
        
        # Login completion (reached after password check OR successful 2FA)
        session.clear()
        session['username'] = username
        session['is_admin'] = (user['user_type'] == 'admin')
        
        # Create a new session ID
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
        
        # Store session in the database
        create_user_session(user['id'], session_id, request.user_agent.string, request.remote_addr)
        
        # Check if user must change password
        if user.get('password_must_change'):
            flash('You must change your password from the default before continuing.', 'warning')
            return redirect(url_for('admin.admin_manage_users', force_password_reset='admin'))
        
        flash('Login successful!', 'success')
        if session['is_admin']:
            return redirect(url_for('admin.admin_dashboard'))
        else:
            return redirect(url_for('main.index'))
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    """
    Logs out the current user or admin.
    """
    session_id = session.get('session_id')
    if session_id:
        user = get_user_by_username(session.get('username'))
        if user:
            delete_session_by_id(session_id, user['id'])
            
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))

@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    """
    Handles the request to reset a password.
    Sends an email with a time-sensitive token.
    """
    if request.method == 'POST':
        email = request.form.get('email')
        user = get_user_by_email(email)

        if user:
            # Generate a password reset token
            s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
            token = s.dumps(user['email'], salt='password-reset-salt')

            # Create the reset link
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            # Send the email
            subject = "Password Reset Request"
            body_html = f"<p>You are receiving this email because a password reset was requested for your account.</p><p>Click the link below to reset your password:</p><p><a href='{reset_url}'>{reset_url}</a></p><p>If you did not request a password reset, please ignore this email.</p>"
            
            send_email(user['email'], subject, body_html)

        # Flash a generic message to prevent user enumeration
        flash('If an account with that email exists, a password reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('forgot_password.html')

@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """
    Handles the actual password reset using the token.
    """
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        # The token is valid for 1800 seconds (30 minutes)
        email = s.loads(token, salt='password-reset-salt', max_age=1800)
    except (SignatureExpired, BadTimeSignature):
        flash('The password reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)

        # Validate password against security requirements
        is_valid, error_message = validate_password(password)
        if not is_valid:
            flash(error_message, 'danger')
            return render_template('reset_password.html', token=token)

        user = get_user_by_email(email)
        if user:
            update_user_password_by_id(user['id'], password)
            flash('Your password has been reset successfully. You can now log in.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('User not found.', 'danger')
            return redirect(url_for('auth.login'))

    return render_template('reset_password.html', token=token)
