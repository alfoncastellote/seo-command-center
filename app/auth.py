"""Signed-cookie session handling and access-key checks."""
import hmac
import secrets

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import config

_serializer = URLSafeTimedSerializer(config.SESSION_SECRET, salt="svp-session")


def issue_token() -> str:
    return _serializer.dumps({"n": secrets.token_hex(8)})


def valid_token(token: str) -> bool:
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=config.SESSION_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


def check_access_key(submitted: str) -> bool:
    return bool(submitted) and hmac.compare_digest(submitted, config.ACCESS_KEY)
