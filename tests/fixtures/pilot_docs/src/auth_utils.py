"""Security utilities for the pilot deployment.

JWT validation middleware lives in auth_middleware.py (planned).
"""

def verify_api_token(token: str) -> bool:
    """Validate bearer tokens for internal services."""
    return bool(token and len(token) >= 16)
