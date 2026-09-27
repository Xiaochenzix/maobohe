"""Password check for the application's phrase editor."""
import hashlib
import hmac

_PASSWORD_DIGEST = '7153083d187e1efc7e2db6c5f8425329534a3038e1fb28a90363af66e40732e2'


def verify_phrase_password(value):
    if not isinstance(value, str):
        return False
    return hmac.compare_digest(hashlib.sha256(value.encode('utf-8')).hexdigest(), _PASSWORD_DIGEST)
