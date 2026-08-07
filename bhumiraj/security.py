"""Password hashing and strength rules.

PBKDF2-HMAC-SHA256, per-user random salt, 200,000 iterations.
Stored format:  pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>

Legacy plain SHA-256 hashes (64 hex chars, from v1.x) still verify so an
existing database keeps working — they are transparently upgraded to PBKDF2
the next time the user logs in successfully.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets

ALGO = "pbkdf2_sha256"
ITERATIONS = 200_000
SALT_BYTES = 16


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    """Return a self-describing PBKDF2 hash string."""
    if password is None:
        password = ""
    salt = secrets.token_bytes(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGO}${iterations}${salt.hex()}${dk.hex()}"


def _legacy_sha256(password: str) -> str:
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verify against PBKDF2 or a legacy SHA-256 digest."""
    if not stored:
        return False
    stored = stored.strip()

    # Legacy v1 format: bare 64-char hex sha256
    if "$" not in stored:
        if len(stored) == 64 and re.fullmatch(r"[0-9a-fA-F]{64}", stored):
            return hmac.compare_digest(_legacy_sha256(password), stored.lower())
        return False

    try:
        algo, iters, salt_hex, hash_hex = stored.split("$", 3)
    except ValueError:
        return False
    if algo != ALGO:
        return False
    try:
        iterations = int(iters)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"),
                             salt, iterations)
    return hmac.compare_digest(dk, expected)


def needs_upgrade(stored: str) -> bool:
    """True when the stored hash is a legacy digest that should be re-hashed."""
    return bool(stored) and "$" not in stored.strip()


# ─── Strength rules ────────────────────────────────────────────────────────
def password_strength(pw: str):
    """Return (ok, message). Admin-grade rule: 8+ chars, upper, lower, digit."""
    pw = pw or ""
    if len(pw) < 8:
        return False, "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", pw):
        return False, "Password needs at least one UPPERCASE letter."
    if not re.search(r"[a-z]", pw):
        return False, "Password needs at least one lowercase letter."
    if not re.search(r"[0-9]", pw):
        return False, "Password needs at least one number."
    if pw.lower() in {"password", "admin@123", "12345678", "qwertyui"}:
        return False, "That password is too common — pick another."
    return True, "Strong password."


def staff_password_strength(pw: str):
    """Slightly relaxed rule for counter staff: 6+ chars, letter + number."""
    pw = pw or ""
    if len(pw) < 6:
        return False, "Password must be at least 6 characters."
    if not re.search(r"[A-Za-z]", pw):
        return False, "Password needs at least one letter."
    if not re.search(r"[0-9]", pw):
        return False, "Password needs at least one number."
    return True, "OK."


def strength_score(pw: str) -> int:
    """0-4 score for the live strength meter in the UI."""
    pw = pw or ""
    score = 0
    if len(pw) >= 6:
        score += 1
    if len(pw) >= 10:
        score += 1
    if re.search(r"[A-Z]", pw) and re.search(r"[a-z]", pw):
        score += 1
    if re.search(r"[0-9]", pw):
        score += 1
    if re.search(r"[^A-Za-z0-9]", pw):
        score += 1
    return min(score, 4)


def hash_answer(answer: str) -> str:
    """Security answers are normalised (trim + lowercase) then PBKDF2-hashed."""
    return hash_password((answer or "").strip().lower())


def verify_answer(answer: str, stored: str) -> bool:
    return verify_password((answer or "").strip().lower(), stored)


def new_pin_hash(pin: str) -> str:
    return hash_password(str(pin or "").strip())


def verify_pin(pin: str, stored: str) -> bool:
    return verify_password(str(pin or "").strip(), stored)


def random_password(length: int = 10) -> str:
    """Generate a readable temporary password for a new staff account."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    lower = "abcdefghijkmnopqrstuvwxyz"
    digits = "23456789"
    pick = [secrets.choice(alphabet), secrets.choice(lower), secrets.choice(digits)]
    pool = alphabet + lower + digits
    pick += [secrets.choice(pool) for _ in range(max(length - 3, 3))]
    secrets.SystemRandom().shuffle(pick)
    return "".join(pick)
