# utils/auth.py
import os
import hmac
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash

# =============================================================================
# PASSWORD HASHING
# =============================================================================
# Nebulae originally stored passwords as bare, unsalted SHA-256 digests. That is
# a fast hash: a commodity GPU can try billions of candidates per second, and
# with no salt, one precomputed table cracks every node at once.
#
# Passwords are now hashed with scrypt (memory-hard, salted, via werkzeug).
# check_password() still accepts the old digests so that nobody is locked out on
# upgrade, and routes/auth.py silently re-hashes a user's password to scrypt the
# first time they log in after updating. Once your users have all logged in
# once, you can set NEBULAE_ALLOW_LEGACY_HASHES=False to refuse them outright.
# =============================================================================

# scrypt is the default: on the same hardware it verifies roughly 3x faster than
# pbkdf2 while being memory-hard, which is what actually frustrates GPU attacks.
# Overridable in case a particular Werkzeug/OpenSSL build has trouble with it -
# 'pbkdf2:sha256' is the safe fallback. See docs/admin-guide/post-install.md.
PASSWORD_HASH_METHOD = os.environ.get('PASSWORD_HASH_METHOD', 'scrypt')

# Set to False once every account has been migrated, to reject legacy hashes.
ALLOW_LEGACY_HASHES = os.environ.get(
    'NEBULAE_ALLOW_LEGACY_HASHES', 'True'
).lower() in ('true', '1', 't', 'yes')


def hash_password(password):
    """Hashes a password using a salted, memory-hard KDF."""
    return generate_password_hash(password, method=PASSWORD_HASH_METHOD)


def is_legacy_hash(stored_hash):
    """
    True if the stored value is a bare (pre-migration) SHA-256 hex digest.

    Werkzeug hashes always carry a method prefix and '$'-separated fields
    (e.g. 'scrypt:32768:8:1$salt$digest'), so a 64-character pure-hex string
    with no ':' or '$' can only be one of the old digests.
    """
    if not stored_hash or not isinstance(stored_hash, str):
        return False
    if len(stored_hash) != 64 or '$' in stored_hash or ':' in stored_hash:
        return False
    try:
        int(stored_hash, 16)
    except ValueError:
        return False
    return True


def check_password(hashed_password, provided_password):
    """
    Checks a password against a stored hash.

    Accepts both the current scrypt hashes and the legacy unsalted SHA-256
    digests. Argument order is unchanged from the original implementation
    (stored hash first), so every existing call site keeps working.
    """
    if not hashed_password or provided_password is None:
        return False

    if is_legacy_hash(hashed_password):
        if not ALLOW_LEGACY_HASHES:
            return False
        # compare_digest to avoid leaking information via comparison timing.
        legacy_digest = hashlib.sha256(provided_password.encode()).hexdigest()
        return hmac.compare_digest(legacy_digest, hashed_password)

    try:
        return check_password_hash(hashed_password, provided_password)
    except (ValueError, TypeError):
        # Malformed or unrecognised hash - fail closed rather than 500.
        return False


def self_test():
    """
    Verifies the configured KDF actually works in this environment.

    Some Werkzeug/OpenSSL combinations have shipped with a broken scrypt. If
    that happened silently, every password set after the upgrade would be
    unverifiable. Call this from a container shell before deploying:

        python -c "from utils.auth import self_test; self_test()"
    """
    sample = 'nebulae-self-test-password'
    digest = hash_password(sample)
    assert check_password(digest, sample), f"{PASSWORD_HASH_METHOD} verify failed"
    assert not check_password(digest, sample + 'x'), "wrong password accepted"

    legacy = hashlib.sha256(sample.encode()).hexdigest()
    assert is_legacy_hash(legacy), "legacy detection failed"
    assert check_password(legacy, sample) == ALLOW_LEGACY_HASHES, "legacy path wrong"
    assert not is_legacy_hash(digest), "new hash misread as legacy"

    print(f"OK: method={PASSWORD_HASH_METHOD} allow_legacy={ALLOW_LEGACY_HASHES}")
    return True
