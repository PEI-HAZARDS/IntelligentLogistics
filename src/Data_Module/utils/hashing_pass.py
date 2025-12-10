import hashlib

# ==================== PASSWORD HASHING ====================

def hash_password(password: str) -> str:
    """Hash simples com SHA-256 (para MVP; usar bcrypt em produção)."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se password corresponde ao hash."""
    return hash_password(plain_password) == hashed_password
