import os
import sqlite3
import hashlib
import hmac
import secrets
import datetime
import http.cookies
import re

# ==============================================================================
# PUNORAI AUTHENTICATION & ROLE-BASED ACCESS CONTROL MODULE
# ==============================================================================

SESSION_COOKIE_NAME = "punorai_session"
DEFAULT_SESSION_HOURS = 24

MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'seller', 'buyer')),
    org_name TEXT NOT NULL,
    contact_name TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    location_name TEXT DEFAULT '',
    lat REAL DEFAULT 0.0,
    lon REAL DEFAULT 0.0,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'suspended', 'pending')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS purchase_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    buyer_id INTEGER NOT NULL REFERENCES users(id),
    lot_id INTEGER REFERENCES lots(id),
    batch_id INTEGER REFERENCES batches(id),
    requested_qty_kg REAL NOT NULL,
    offered_price_per_kg REAL DEFAULT 0.0,
    notes TEXT DEFAULT '',
    status TEXT DEFAULT 'pending_admin' CHECK(status IN ('pending_admin', 'admin_approved', 'rejected', 'fulfilled', 'cancelled')),
    admin_notes TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    request_id INTEGER REFERENCES purchase_requests(id),
    seller_id INTEGER NOT NULL REFERENCES users(id),
    buyer_id INTEGER NOT NULL REFERENCES users(id),
    lot_id INTEGER REFERENCES lots(id),
    batch_id INTEGER REFERENCES batches(id),
    qty_kg REAL NOT NULL,
    price_per_kg REAL NOT NULL,
    total_amount REAL NOT NULL,
    handover_status TEXT DEFAULT 'scheduled' CHECK(handover_status IN ('scheduled', 'in_transit', 'delivered', 'completed')),
    passport_code TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS saved_lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lot_id INTEGER NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, lot_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_purchase_requests_buyer ON purchase_requests(buyer_id);
CREATE INDEX IF NOT EXISTS idx_transactions_parties ON transactions(seller_id, buyer_id);
CREATE INDEX IF NOT EXISTS idx_saved_lots_user ON saved_lots(user_id);
"""

def run_migrations(conn):
    """
    Executes additive database migrations transactionally.
    Preserves all existing data in lots, buyers, batches, etc.
    """
    cursor = conn.cursor()
    cursor.executescript(MIGRATIONS_DDL)

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in cursor.fetchall()}

    # Additive columns on users
    if "users" in existing_tables:
        cursor.execute("PRAGMA table_info(users)")
        existing_user_cols = {row["name"] for row in cursor.fetchall()}
        if "phone" not in existing_user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''")
        if "contact_name" not in existing_user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN contact_name TEXT DEFAULT ''")

    # Additive columns on lots
    if "lots" in existing_tables:
        cursor.execute("PRAGMA table_info(lots)")
        existing_lot_cols = {row["name"] for row in cursor.fetchall()}
        if "seller_id" not in existing_lot_cols:
            cursor.execute("ALTER TABLE lots ADD COLUMN seller_id INTEGER REFERENCES users(id)")
        if "verified_by" not in existing_lot_cols:
            cursor.execute("ALTER TABLE lots ADD COLUMN verified_by INTEGER REFERENCES users(id)")
        if "verification_notes" not in existing_lot_cols:
            cursor.execute("ALTER TABLE lots ADD COLUMN verification_notes TEXT DEFAULT ''")
        if "asking_price_per_kg" not in existing_lot_cols:
            cursor.execute("ALTER TABLE lots ADD COLUMN asking_price_per_kg REAL DEFAULT 0.0")

    # Additive columns on buyers
    if "buyers" in existing_tables:
        cursor.execute("PRAGMA table_info(buyers)")
        existing_buyer_cols = {row["name"] for row in cursor.fetchall()}
        if "user_id" not in existing_buyer_cols:
            cursor.execute("ALTER TABLE buyers ADD COLUMN user_id INTEGER REFERENCES users(id)")

    conn.commit()


# ------------------------------------------------------------------------------
# Password Security (PBKDF2-HMAC-SHA256)
# ------------------------------------------------------------------------------

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """Hashes a password with PBKDF2-HMAC-SHA256 and 100,000 iterations."""
    if not salt:
        salt = secrets.token_hex(16)
    pwd_bytes = password.encode("utf-8")
    salt_bytes = salt.encode("utf-8")
    hash_hex = hashlib.pbkdf2_hmac("sha256", pwd_bytes, salt_bytes, iterations=100000).hex()
    return hash_hex, salt

def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verifies a password against the stored PBKDF2 hash using constant-time comparison."""
    if not password or not stored_hash or not salt:
        return False
    computed_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(computed_hash, stored_hash)


# ------------------------------------------------------------------------------
# User Operations
# ------------------------------------------------------------------------------

def validate_email(email: str) -> bool:
    if not email or len(email) > 120: return False
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return bool(re.match(pattern, email.strip()))

def register_user(conn, email: str, password: str, role: str, org_name: str, location_name: str = "", lat: float = 0.0, lon: float = 0.0) -> dict:
    """Public self-service registration. Strictly forbids admin role."""
    role = (role or "").strip().lower()
    if role == "admin":
        raise ValueError("Public registration as Admin is forbidden. Admin accounts are managed by platform governance.")
    if role not in ("seller", "buyer"):
        raise ValueError("Registration role must be either 'seller' or 'buyer'.")
    return create_user(conn, email, password, role, org_name, location_name, lat, lon)

def create_user(conn, email: str, password: str, role: str, org_name: str, location_name: str = "", lat: float = 0.0, lon: float = 0.0) -> dict:
    email = email.strip().lower()
    if not validate_email(email):
        raise ValueError("Invalid email format.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if role not in ("admin", "seller", "buyer"):
        raise ValueError("Invalid role specified.")
    if not org_name or not org_name.strip():
        raise ValueError("Organization or company name is required.")

    pwd_hash, salt = hash_password(password)
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (email, password_hash, salt, role, org_name, location_name, lat, lon, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
        """, (email, pwd_hash, salt, role, org_name.strip(), location_name.strip(), lat, lon, now_iso))
        conn.commit()
        user_id = cursor.lastrowid
        return get_safe_user_by_id(conn, user_id)
    except sqlite3.IntegrityError:
        try:
            conn.rollback()
        except Exception:
            pass
        raise ValueError("An account with this email address already exists.")

def get_safe_user_by_id(conn, user_id: int) -> dict | None:
    """Retrieves safe user information without exposing password hashes or salts."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, email, role, org_name,
               COALESCE(contact_name, '') as contact_name,
               COALESCE(phone, '') as phone,
               location_name, lat, lon, status, created_at
        FROM users WHERE id = ?
    """, (user_id,))
    row = cursor.fetchone()
    return dict(row) if row else None

def authenticate_user(conn, email: str, password: str) -> dict | None:
    """Authenticates credentials and returns safe user dict if valid."""
    email = email.strip().lower()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, email, password_hash, salt, role, org_name,
               COALESCE(contact_name, '') as contact_name,
               COALESCE(phone, '') as phone,
               location_name, lat, lon, status, created_at
        FROM users WHERE email = ?
    """, (email,))
    row = cursor.fetchone()
    if not row:
        return None
    if row["status"] != "active":
        return None
    if verify_password(password, row["password_hash"], row["salt"]):
        return {
            "id": row["id"],
            "email": row["email"],
            "role": row["role"],
            "org_name": row["org_name"],
            "contact_name": row["contact_name"],
            "phone": row["phone"],
            "location_name": row["location_name"],
            "lat": row["lat"],
            "lon": row["lon"],
            "status": row["status"],
            "created_at": row["created_at"]
        }
    return None


# ------------------------------------------------------------------------------
# Session Management
# ------------------------------------------------------------------------------

def create_session(conn, user_id: int, duration_hours: int = DEFAULT_SESSION_HOURS) -> dict:
    session_id = secrets.token_hex(32)
    csrf_token = secrets.token_hex(32)
    now = datetime.datetime.now(datetime.timezone.utc)
    expires = now + datetime.timedelta(hours=duration_hours)

    now_iso = now.strftime("%Y-%m-%d %H:%M:%S")
    expires_iso = expires.strftime("%Y-%m-%d %H:%M:%S")

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (session_id, user_id, csrf_token, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, user_id, csrf_token, now_iso, expires_iso))
    conn.commit()

    return {
        "session_id": session_id,
        "csrf_token": csrf_token,
        "expires_at": expires_iso,
        "user_id": user_id
    }

def get_session_and_user(conn, session_id: str) -> tuple[dict | None, str | None]:
    """Returns (safe_user_dict, csrf_token) if session is valid and unexpired; else (None, None)."""
    if not session_id or len(session_id) != 64:
        return None, None

    cursor = conn.cursor()
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        SELECT s.session_id, s.csrf_token, s.expires_at, u.id, u.email, u.role, u.org_name,
               COALESCE(u.contact_name, '') as contact_name,
               COALESCE(u.phone, '') as phone,
               u.location_name, u.lat, u.lon, u.status, u.created_at
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.session_id = ?
    """, (session_id,))
    row = cursor.fetchone()
    if not row:
        return None, None

    # Check expiration
    if row["expires_at"] < now_iso:
        # Expired: invalidate immediately
        cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        return None, None

    if row["status"] != "active":
        return None, None

    user = {
        "id": row["id"],
        "email": row["email"],
        "role": row["role"],
        "org_name": row["org_name"],
        "contact_name": row["contact_name"],
        "phone": row["phone"],
        "location_name": row["location_name"],
        "lat": row["lat"],
        "lon": row["lon"],
        "status": row["status"],
        "created_at": row["created_at"]
    }
    return user, row["csrf_token"]

def delete_session(conn, session_id: str) -> bool:
    if not session_id: return False
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise

def purge_expired_sessions(conn) -> int:
    cursor = conn.cursor()
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor.execute("DELETE FROM sessions WHERE expires_at < ?", (now_iso,))
        conn.commit()
        return cursor.rowcount
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


# ------------------------------------------------------------------------------
# Cookie & CSRF Utilities
# ------------------------------------------------------------------------------

def make_session_cookie(session_id: str, max_age: int = 86400, is_secure: bool = False) -> str:
    cookie = f"{SESSION_COOKIE_NAME}={session_id}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax"
    if is_secure:
        cookie += "; Secure"
    return cookie

def make_delete_cookie(is_secure: bool = False) -> str:
    cookie = f"{SESSION_COOKIE_NAME}=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; SameSite=Lax"
    if is_secure:
        cookie += "; Secure"
    return cookie

def extract_session_id(headers) -> str | None:
    cookie_str = headers.get("Cookie", "") if hasattr(headers, "get") else ""
    if not cookie_str:
        return None
    try:
        cookie = http.cookies.SimpleCookie()
        cookie.load(cookie_str)
        if SESSION_COOKIE_NAME in cookie:
            return cookie[SESSION_COOKIE_NAME].value
    except Exception:
        pass
    return None

def verify_csrf(session_csrf_token: str, submitted_token: str) -> bool:
    if not session_csrf_token or not submitted_token:
        return False
    return hmac.compare_digest(session_csrf_token, submitted_token)


# ------------------------------------------------------------------------------
# Demo Account Provisioning
# ------------------------------------------------------------------------------

DEMO_ACCOUNTS = [
    {
        "email": "admin@punorai.com",
        "password": "Admin@Punor2026!",
        "role": "admin",
        "org_name": "PunorAI Operations Control",
        "location_name": "Dhaka HQ",
        "lat": 23.8103,
        "lon": 90.4125
    },
    {
        "email": "seller@shanto.com",
        "password": "Seller@Punor2026!",
        "role": "seller",
        "org_name": "Shanto Knitwear Ltd",
        "location_name": "Gazipur",
        "lat": 23.9999,
        "lon": 90.4203
    },
    {
        "email": "buyer@recycler.com",
        "password": "Buyer@Punor2026!",
        "role": "buyer",
        "org_name": "Recycler X (Dhaka)",
        "location_name": "Dhaka",
        "lat": 23.8103,
        "lon": 90.4125
    }
]

def seed_demo_users(conn):
    """Provisions default secure demo accounts if they do not already exist."""
    cursor = conn.cursor()
    for acc in DEMO_ACCOUNTS:
        cursor.execute("SELECT id FROM users WHERE email = ?", (acc["email"],))
        if not cursor.fetchone():
            pwd_hash, salt = hash_password(acc["password"])
            now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO users (email, password_hash, salt, role, org_name, location_name, lat, lon, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """, (acc["email"], pwd_hash, salt, acc["role"], acc["org_name"], acc["location_name"], acc["lat"], acc["lon"], now_iso))
    conn.commit()
