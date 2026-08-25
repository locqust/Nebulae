# utils/throttle.py
"""
Auth throttling for Nebulae.

Slows down online guessing against login, 2FA and password reset without ever
locking an account permanently.

WHY NOT LOCKOUT: on a self-hosted household node there is no helpdesk. A
lockout would let anyone who knows a family member's email disable their
account on demand, and the recovery path is the admin in a SQLite shell at
midnight. Escalating cooldowns cost an attacker just as much while always
healing on their own.

WHY ACCOUNT-KEYED FIRST: Nebulae is normally behind a reverse proxy, so
request.remote_addr is the proxy's address unless ProxyFix is configured. IP
keying is therefore treated as a bonus, not the primary defence - every rule
here works correctly even when every request appears to come from one address.
"""

import time
from db import get_db

# scope -> how far back we count, and the escalating cooldown tiers.
# Tiers are (failures_at_or_above, cooldown_seconds), lowest first.
POLICIES = {
    # Password step. 5 quick typos cost a minute; sustained guessing costs 15.
    'login': {
        'window': 900,
        'tiers': [(5, 60), (10, 300), (15, 900)],
    },
    # TOTP step. Same shape - the real protection is that exhausting attempts
    # also clears the pending-2FA state, forcing the (throttled) password step
    # to be repeated.
    'twofa': {
        'window': 900,
        'tiers': [(5, 60), (10, 300), (15, 900)],
    },
    # Password reset requests. Counted per request, not per failure, because
    # the cost here is outbound email and token issuance.
    'reset': {
        'window': 3600,
        'tiers': [(3, 3600)],
    },
}

# Rows older than this are pruned opportunistically.
MAX_RETENTION = 86400


def _now():
    return int(time.time())


def _policy(scope):
    return POLICIES.get(scope, POLICIES['login'])


def _norm(identifier):
    """Identifiers are case-insensitive: usernames here are email addresses."""
    return (identifier or '').strip().lower()


def record_attempt(scope, identifier):
    """Record one failed (or, for 'reset', one issued) attempt."""
    identifier = _norm(identifier)
    if not identifier:
        return
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO auth_throttle (scope, identifier, failed_at) VALUES (?, ?, ?)",
        (scope, identifier, _now())
    )
    # Opportunistic cleanup so the table can't grow without bound.
    cursor.execute("DELETE FROM auth_throttle WHERE failed_at < ?", (_now() - MAX_RETENTION,))
    db.commit()


def seconds_remaining(scope, identifier):
    """
    How long the caller must wait, in seconds. 0 means proceed.

    Counts attempts inside the policy window, picks the highest tier reached,
    and measures the cooldown from the most recent attempt - so each further
    attempt while throttled restarts the clock.
    """
    identifier = _norm(identifier)
    if not identifier:
        return 0

    policy = _policy(scope)
    now = _now()
    cutoff = now - policy['window']

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT COUNT(*) AS n, MAX(failed_at) AS last FROM auth_throttle "
        "WHERE scope = ? AND identifier = ? AND failed_at >= ?",
        (scope, identifier, cutoff)
    )
    row = cursor.fetchone()
    if not row or not row['n']:
        return 0

    count = row['n']
    last = row['last'] or 0

    cooldown = 0
    for threshold, seconds in policy['tiers']:
        if count >= threshold:
            cooldown = seconds

    if not cooldown:
        return 0

    remaining = (last + cooldown) - now
    return remaining if remaining > 0 else 0


def clear(scope, identifier):
    """Wipe attempts for one identifier. Called on successful auth."""
    identifier = _norm(identifier)
    if not identifier:
        return
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "DELETE FROM auth_throttle WHERE scope = ? AND identifier = ?",
        (scope, identifier)
    )
    db.commit()


def describe_wait(seconds):
    """Human-friendly cooldown text for flash messages."""
    if seconds <= 0:
        return ""
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = (seconds + 59) // 60
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


# ---------------------------------------------------------------------------
# Admin helpers
# ---------------------------------------------------------------------------

def list_active():
    """
    Every identifier currently in a cooldown, for the admin screen.
    Returns dicts: scope, identifier, attempts, last_attempt, seconds_remaining.
    """
    db = get_db()
    cursor = db.cursor()
    now = _now()
    active = []

    for scope, policy in POLICIES.items():
        cutoff = now - policy['window']
        cursor.execute(
            "SELECT identifier, COUNT(*) AS n, MAX(failed_at) AS last "
            "FROM auth_throttle WHERE scope = ? AND failed_at >= ? "
            "GROUP BY identifier ORDER BY last DESC",
            (scope, cutoff)
        )
        for row in cursor.fetchall():
            remaining = seconds_remaining(scope, row['identifier'])
            if remaining > 0:
                active.append({
                    'scope': scope,
                    'identifier': row['identifier'],
                    'attempts': row['n'],
                    'last_attempt': row['last'],
                    'seconds_remaining': remaining,
                    'wait_text': describe_wait(remaining),
                })
    return active


def clear_all():
    """Release every throttle. The admin panic button."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM auth_throttle")
    db.commit()
    return cursor.rowcount
