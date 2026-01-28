# utils/email_utils.py
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from db import get_db

def get_smtp_config():
    """Retrieves SMTP configuration from the node_config table."""
    db = get_db()
    cursor = db.cursor()
    keys = [
        'smtp_enabled', 'smtp_host', 'smtp_port', 'smtp_username',
        'smtp_password', 'smtp_ignore_cert_errors', 'smtp_from_address'
    ]
    config = {}
    for key in keys:
        cursor.execute("SELECT value FROM node_config WHERE key = ?", (key,))
        row = cursor.fetchone()
        config[key] = row['value'] if row else None
    
    # Type conversions
    config['smtp_enabled'] = config['smtp_enabled'] == 'True'
    config['smtp_ignore_cert_errors'] = config['smtp_ignore_cert_errors'] == 'True'
    if config['smtp_port']:
        try:
            config['smtp_port'] = int(config['smtp_port'])
        except (ValueError, TypeError):
            config['smtp_port'] = None # Or a default like 587
            
    return config

def send_email(recipient, subject, body_html):
    """
    Sends an email using the configured SMTP settings.
    
    :param recipient: The email address of the recipient.
    :param subject: The subject of the email.
    :param body_html: The HTML content of the email body.
    :return: A tuple (bool, str) indicating success and a message.
    """
    config = get_smtp_config()

    if not config.get('smtp_enabled'):
        return False, "Email notifications are disabled in the node configuration."

    required_settings = ['smtp_host', 'smtp_port', 'smtp_from_address']
    for setting in required_settings:
        if not config.get(setting):
            return False, f"Missing required SMTP setting: {setting}"

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = config['smtp_from_address']
    message["To"] = recipient

    # Attach the HTML part
    message.attach(MIMEText(body_html, "html"))

    try:
        # Create a secure SSL context
        context = ssl.create_default_context()
        if config.get('smtp_ignore_cert_errors'):
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        # Connect to the server
        with smtplib.SMTP(config['smtp_host'], config['smtp_port'], timeout=10) as server:
            server.starttls(context=context)
            # Login if credentials are provided
            if config.get('smtp_username') and config.get('smtp_password'):
                server.login(config['smtp_username'], config['smtp_password'])
            # Send the email
            server.sendmail(
                config['smtp_from_address'], recipient, message.as_string()
            )
        
        return True, "Email sent successfully."

    except smtplib.SMTPAuthenticationError:
        return False, "SMTP Authentication Error: The username or password was not accepted."
    except smtplib.SMTPServerDisconnected:
        return False, "SMTP Server Disconnected: The server unexpectedly disconnected."
    except smtplib.SMTPException as e:
        return False, f"An SMTP error occurred: {e}"
    except ConnectionRefusedError:
        return False, "Connection Refused: Check the SMTP host and port."
    except Exception as e:
        return False, f"An unexpected error occurred: {e}"
