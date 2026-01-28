"""
Password hashing utilities.
Uses bcrypt for secure password hashing.
"""

from passlib.context import CryptContext

# Bcrypt context for password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        # Handle invalid hash format
        return False
