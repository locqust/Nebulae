# db_queries/profiles.py
# Contains functions for managing user profiles and family relationships.

from datetime import datetime
from db import get_db
from .friends import is_friends_with
from .notifications import trigger_birthday_notifications_for_user
from .users import get_user_by_id # Import get_user_by_id to check viewer's hostname

def get_profile_info_for_user(profile_user_id, viewer_user_id, viewer_is_admin):
    """
    Retrieves profile information for a user, respecting privacy settings.
    This function is now defensive and will return a default structure if no info is found.
    """
    db = get_db()
    cursor = db.cursor()

    default_profile_fields = ['dob', 'hometown', 'occupation', 'bio', 'show_username', 'show_friends', 'website', 'email', 'phone', 'address']
    profile_info = {}
    for field in default_profile_fields:
        profile_info[field] = {
            'value': None,
            'privacy_public': 0,
            'privacy_local': 0,
            'privacy_friends': 0
        }

    cursor.execute("SELECT user_type FROM users WHERE id = ?", (profile_user_id,))
    profile_owner_data_row = cursor.fetchone()
    if not profile_owner_data_row:
        return profile_info
    
    profile_owner_data = dict(profile_owner_data_row)
    profile_owner_user_type = profile_owner_data['user_type']
    
    # MODIFICATION: Determine if the viewer is from a remote node.
    is_federated_viewer = False
    if viewer_user_id:
        viewer_user = get_user_by_id(viewer_user_id)
        if viewer_user and viewer_user['hostname'] is not None:
            is_federated_viewer = True

    cursor.execute("SELECT field_name, field_value, privacy_public, privacy_local, privacy_friends FROM user_profile_info WHERE user_id = ?", (profile_user_id,))
    raw_info = cursor.fetchall()

    for item_row in raw_info:
        item = dict(item_row)
        field_name = item['field_name']
        if field_name not in default_profile_fields:
            continue

        field_value = item['field_value']
        is_visible = False

        if viewer_user_id == profile_user_id or viewer_is_admin:
            is_visible = True
        elif item['privacy_public'] == 1:
            is_visible = True
        # MODIFICATION: A federated viewer should NOT see local-only info.
        elif viewer_user_id is not None and item['privacy_local'] == 1 and not is_federated_viewer:
            is_visible = True
        elif viewer_user_id is not None and item['privacy_friends'] == 1 and is_friends_with(viewer_user_id, profile_user_id):
            is_visible = True
        elif profile_owner_user_type == 'admin' and item['privacy_friends'] == 1 and viewer_user_id is not None:
            is_visible = True

        if is_visible:
            final_value = 'visible' if field_name == 'show_username' else field_value
            profile_info[field_name] = {
                'value': final_value,
                'privacy_public': item['privacy_public'],
                'privacy_local': item['privacy_local'],
                'privacy_friends': item['privacy_friends']
            }
        else:
            profile_info[field_name] = {
                'value': '' if viewer_user_id != profile_user_id and not viewer_is_admin else None,
                'privacy_public': item['privacy_public'],
                'privacy_local': item['privacy_local'],
                'privacy_friends': item['privacy_friends']
            }
            
    return profile_info

def update_profile_info_field(user_id, field_name, field_value, privacy_public, privacy_local, privacy_friends):
    """
    Updates a single profile information field for a user and triggers
    birthday notifications if the DOB is updated to today.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_profile_info
        (user_id, field_name, field_value, privacy_public, privacy_local, privacy_friends)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, field_name, field_value, privacy_public, privacy_local, privacy_friends))
    
    if field_name == 'dob' and field_value:
        try:
            dob_date = datetime.strptime(field_value, '%Y-%m-%d').date()
            today = datetime.utcnow().date()
            if dob_date.month == today.month and dob_date.day == today.day and privacy_friends == 1:
                trigger_birthday_notifications_for_user(user_id)
        except ValueError:
            print(f"WARN: Could not parse date '{field_value}' for birthday check.")

    db.commit()
    return cursor.rowcount > 0

def add_family_relationship(user_id, relative_user_id, relationship_type, anniversary_date, privacy_public, privacy_local, privacy_friends):
    """Adds or updates a family relationship."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO family_relationships (user_id, relative_user_id, relationship_type, anniversary_date, privacy_public, privacy_local, privacy_friends)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, relative_user_id) DO UPDATE SET
        relationship_type=excluded.relationship_type,
        anniversary_date=excluded.anniversary_date,
        privacy_public=excluded.privacy_public,
        privacy_local=excluded.privacy_local,
        privacy_friends=excluded.privacy_friends
    """, (user_id, relative_user_id, relationship_type, anniversary_date, privacy_public, privacy_local, privacy_friends))
    db.commit()
    return cursor.lastrowid

def get_relationship_by_id(relationship_id, user_id):
    """Retrieves a single family relationship by its ID, ensuring user has permission."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM family_relationships WHERE id = ? AND user_id = ?", (relationship_id, user_id))
    row = cursor.fetchone()
    return dict(row) if row else None

def update_family_relationship(relationship_id, user_id, relative_user_id, relationship_type, anniversary_date, privacy_public, privacy_local, privacy_friends):
    """Updates an existing family relationship, ensuring user has permission."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE family_relationships SET
        relative_user_id = ?,
        relationship_type = ?,
        anniversary_date = ?,
        privacy_public = ?,
        privacy_local = ?,
        privacy_friends = ?
        WHERE id = ? AND user_id = ?
    """, (relative_user_id, relationship_type, anniversary_date, privacy_public, privacy_local, privacy_friends, relationship_id, user_id))
    db.commit()
    return cursor.rowcount > 0

def remove_family_relationship(relationship_id, user_id):
    """Removes a family relationship, ensuring the user has permission."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM family_relationships WHERE id = ? AND user_id = ?", (relationship_id, user_id))
    db.commit()
    return cursor.rowcount > 0

def get_family_relationships_for_user(profile_user_id, viewer_user_id, viewer_is_admin):
    """Retrieves family relationships for a user, respecting privacy settings."""
    db = get_db()
    cursor = db.cursor()
    
    # BUG FIX: Added u.profile_picture_path to the SELECT statement
    query = """
        SELECT fr.id, fr.relative_user_id, fr.relationship_type, fr.anniversary_date,
               u.username as relative_username, u.display_name as relative_display_name, 
               u.puid as relative_puid, u.hostname as relative_hostname, u.profile_picture_path,
               fr.privacy_public, fr.privacy_local, fr.privacy_friends
        FROM family_relationships fr
        JOIN users u ON fr.relative_user_id = u.id
        WHERE fr.user_id = ?
    """
    cursor.execute(query, (profile_user_id,))
    all_relations = cursor.fetchall()
    
    visible_relations = []
    is_profile_owner = (profile_user_id == viewer_user_id)
    # BUG FIX: Correctly check friendship status. It requires viewer_user_id to be not None.
    are_friends = False
    if viewer_user_id:
        are_friends = is_friends_with(profile_user_id, viewer_user_id)
    
    # MODIFICATION: Determine if the viewer is from a remote node.
    is_federated_viewer = False
    if viewer_user_id:
        viewer_user = get_user_by_id(viewer_user_id)
        if viewer_user and viewer_user['hostname'] is not None:
            is_federated_viewer = True

    for rel_row in all_relations:
        rel = dict(rel_row)
        is_visible = False
        if is_profile_owner or viewer_is_admin:
            is_visible = True
        elif rel['privacy_public'] == 1:
            is_visible = True
        # MODIFICATION: A federated viewer should NOT see local-only info.
        elif viewer_user_id is not None and rel['privacy_local'] == 1 and not is_federated_viewer:
            is_visible = True
        elif are_friends and rel['privacy_friends'] == 1:
            is_visible = True
        
        if is_visible:
            visible_relations.append(rel)
            
    return visible_relations

def update_profile_info_privacy_only(user_id, field_name, privacy_public, privacy_local, privacy_friends):
    """
    Updates only the privacy settings for a profile field without changing its value.
    Used specifically for DOB which should not be editable after account creation.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE user_profile_info
        SET privacy_public = ?,
            privacy_local = ?,
            privacy_friends = ?
        WHERE user_id = ? AND field_name = ?
    """, (privacy_public, privacy_local, privacy_friends, user_id, field_name))
    db.commit()
    return cursor.rowcount > 0

def get_friend_birthdays_next_12_months(viewer_user_id, current_app_config):
    """
    Retrieves upcoming birthdays (next 12 months from today) for all friends,
    both local and federated.

    Local friends:
      - privacy_public = 1  → visible
      - privacy_friends = 1 → visible (we ARE friends)
      - privacy_local = 1   → visible (they're on the same node as the viewer)

    Federated friends:
      - Fetched via the /federation/api/v1/friend_birthdays endpoint on each
        connected node. The remote node applies its own privacy rules and will
        never return privacy_local DOBs across the node boundary.

    Returns a list of dicts sorted by next_birthday (ascending).
    """
    from datetime import date
    import hmac as hmac_lib
    import hashlib
    import requests
    import json
    from db_queries.federation import get_all_connected_nodes, get_node_by_hostname
    from utils.federation_utils import get_remote_node_api_url

    db = get_db()
    cursor = db.cursor()
    today = date.today()

    # ------------------------------------------------------------------ #
    # Step 1: Fetch ALL friends (local + federated stubs)
    # ------------------------------------------------------------------ #
    cursor.execute("""
        SELECT u.id, u.display_name, u.username, u.puid,
               u.profile_picture_path, u.hostname
        FROM friends f
        JOIN users u ON (u.id = f.user_id_1 OR u.id = f.user_id_2)
        WHERE (f.user_id_1 = ? OR f.user_id_2 = ?) AND u.id != ?
    """, (viewer_user_id, viewer_user_id, viewer_user_id))
    all_friends = [dict(row) for row in cursor.fetchall()]

    if not all_friends:
        return []

    # Split into local vs federated, grouped by hostname for efficiency
    local_friends = [f for f in all_friends if f['hostname'] is None]
    remote_friends_by_node = {}
    for f in all_friends:
        if f['hostname'] is not None:
            remote_friends_by_node.setdefault(f['hostname'], []).append(f)

    raw_birthday_data = []  # Will collect dicts with dob string + friend info

    # ------------------------------------------------------------------ #
    # Step 2: Local friends — query directly with full privacy logic
    # ------------------------------------------------------------------ #
    if local_friends:
        local_ids = [f['id'] for f in local_friends]
        local_map = {f['id']: f for f in local_friends}
        placeholders = ','.join('?' * len(local_ids))
        cursor.execute(f"""
            SELECT user_id, field_value, privacy_public, privacy_local, privacy_friends
            FROM user_profile_info
            WHERE field_name = 'dob'
              AND field_value IS NOT NULL
              AND field_value != ''
              AND user_id IN ({placeholders})
        """, local_ids)

        for row in cursor.fetchall():
            row = dict(row)
            friend = local_map.get(row['user_id'])
            if not friend:
                continue
            # Viewer is local, friend is local → all three privacy levels apply
            if row['privacy_public'] == 1 or row['privacy_friends'] == 1 or row['privacy_local'] == 1:
                raw_birthday_data.append({
                    'dob': row['field_value'],
                    **friend
                })

    # ------------------------------------------------------------------ #
    # Step 3: Federated friends — call each remote node
    # ------------------------------------------------------------------ #
    local_hostname = current_app_config.get('NODE_HOSTNAME')
    insecure_mode = current_app_config.get('FEDERATION_INSECURE_MODE', False)
    verify_ssl = not insecure_mode

    for hostname, friends_on_node in remote_friends_by_node.items():
        node = get_node_by_hostname(hostname)
        if not node or node['status'] != 'connected' or not node['shared_secret']:
            continue

        friend_puids = [f['puid'] for f in friends_on_node]
        puid_to_friend = {f['puid']: f for f in friends_on_node}

        try:
            remote_url = get_remote_node_api_url(
                hostname,
                '/federation/api/v1/friend_birthdays',
                insecure_mode
            )
            payload = {'friend_puids': friend_puids}
            request_body = json.dumps(payload, sort_keys=True).encode('utf-8')
            signature = hmac_lib.new(
                node['shared_secret'].encode('utf-8'),
                msg=request_body,
                digestmod=hashlib.sha256
            ).hexdigest()
            headers = {
                'X-Node-Hostname': local_hostname,
                'X-Node-Signature': signature,
                'Content-Type': 'application/json'
            }
            response = requests.post(remote_url, data=request_body, headers=headers,
                                     timeout=5, verify=verify_ssl)
            response.raise_for_status()
            remote_results = response.json()

            for item in remote_results:
                puid = item.get('puid')
                dob = item.get('dob')
                if not puid or not dob:
                    continue
                # Use the local stub's profile picture if available,
                # otherwise fall back to whatever the remote sent
                local_stub = puid_to_friend.get(puid, {})
                raw_birthday_data.append({
                    'dob': dob,
                    'display_name': item.get('display_name') or local_stub.get('display_name'),
                    'username': item.get('username') or local_stub.get('username'),
                    'puid': puid,
                    'profile_picture_path': local_stub.get('profile_picture_path')
                                            or item.get('profile_picture_path'),
                    'hostname': hostname,
                })

        except requests.exceptions.RequestException as e:
            print(f"WARN: Could not fetch birthdays from {hostname}: {e}")
        except Exception as e:
            print(f"ERROR: Unexpected error fetching birthdays from {hostname}: {e}")

    # ------------------------------------------------------------------ #
    # Step 4: Calculate next birthday and filter to next 12 months
    # ------------------------------------------------------------------ #
    results = []
    try:
        cutoff = today.replace(year=today.year + 1)
    except ValueError:
        cutoff = date(today.year + 1, 3, 1)  # viewer's today is Feb 29

    for entry in raw_birthday_data:
        try:
            dob = datetime.strptime(entry['dob'], '%Y-%m-%d').date()
        except ValueError:
            continue

        try:
            this_year_bday = dob.replace(year=today.year)
        except ValueError:
            this_year_bday = date(today.year, 3, 1)  # Feb 29 → Mar 1

        if this_year_bday < today:
            try:
                next_birthday = dob.replace(year=today.year + 1)
            except ValueError:
                next_birthday = date(today.year + 1, 3, 1)
        else:
            next_birthday = this_year_bday

        if next_birthday > cutoff:
            continue

        results.append({
            'display_name': entry['display_name'],
            'username': entry['username'],
            'puid': entry['puid'],
            'profile_picture_path': entry['profile_picture_path'],
            'hostname': entry.get('hostname'),
            'dob_month': next_birthday.month,
            'dob_day': next_birthday.day,
            'next_birthday': next_birthday,
            'age_turning': next_birthday.year - dob.year,
        })

    results.sort(key=lambda x: x['next_birthday'])
    return results