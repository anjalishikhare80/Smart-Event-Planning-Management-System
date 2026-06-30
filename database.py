"""
database.py — EventHub PostgreSQL Version
==========================================
Converted from SQLite to PostgreSQL for production deployment on Render.

Key differences from SQLite version:
- Uses psycopg2 instead of sqlite3
- Placeholder syntax: %s instead of ?
- SERIAL PRIMARY KEY instead of INTEGER PRIMARY KEY AUTOINCREMENT
- CURRENT_DATE instead of date('now')
- NOW() instead of CURRENT_TIMESTAMP
- dict-based row access instead of sqlite3.Row
- Connection via DATABASE_URL environment variable
"""

import os
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash

# ── Database URL from environment variable (set on Render) ───────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')

# Render sometimes provides postgres:// but psycopg2 needs postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# ── Category code prefixes ────────────────────────────────────────────────────
CATEGORY_CODES = {
    "Technical Events":    "TEC",
    "Creative Events":  "CRE",
    "Cultural Events":       "CUL",
    "Academic Events":     "ACD",
    "Competition": "CMP",
    "Sports & Fitness":     "SPT",
}


# ── Connection ────────────────────────────────────────────────────────────────

def get_db_connection():
    """
    Return a psycopg2 connection using DATABASE_URL.
    RealDictCursor makes rows behave like dictionaries
    (same as sqlite3.Row — code that does row['column'] still works).
    """
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


# ── Event code generator ──────────────────────────────────────────────────────

def generate_event_code(category, event_id):
    """Generate a short, human-friendly event code, e.g. 'TEC-0007'."""
    prefix = CATEGORY_CODES.get(category, "EVT")
    return f"{prefix}-{event_id:04d}"


# ── Database initialisation ───────────────────────────────────────────────────

def init_db():
    """
    Create all tables (if they don't exist) and seed the two Admin accounts.
    Called once at app startup from app.py.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # ── users table ──────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          SERIAL PRIMARY KEY,
            fullname    TEXT        NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            mobile      TEXT        NOT NULL,
            role        TEXT        NOT NULL
                        CHECK(role IN ('Admin', 'Organizer', 'Participant')),
            password    TEXT        NOT NULL,
            created_at  TIMESTAMP   DEFAULT NOW()
        )
    """)

    # ── events table ─────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id                      SERIAL PRIMARY KEY,
            title                   TEXT        NOT NULL,
            category                TEXT        NOT NULL,
            event_date              TEXT        NOT NULL,
            event_time              TEXT,
            venue                   TEXT        NOT NULL,
            description             TEXT,
            capacity                INTEGER     NOT NULL,
            registration_close_date TEXT,
            contact_number          TEXT,
            organizer_id            INTEGER     NOT NULL REFERENCES users(id),
            status                  TEXT        NOT NULL DEFAULT 'Pending'
                                    CHECK(status IN (
                                        'Pending', 'Approved',
                                        'Registration Closed', 'Rejected', 'Completed'
                                    )),
            rejection_reason        TEXT,
            admin_comment           TEXT,
            event_code              TEXT,
            created_at              TIMESTAMP   DEFAULT NOW()
        )
    """)

    # ── registrations table ───────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id            SERIAL PRIMARY KEY,
            event_id      INTEGER   NOT NULL REFERENCES events(id),
            user_id       INTEGER   NOT NULL REFERENCES users(id),
            registered_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(event_id, user_id)
        )
    """)

    # ── Seed admin accounts ───────────────────────────────────────────────────
    admins = [
        ("Admin One", "admin1@eventhub.com", "9876543210", "Admin", "Admin@123"),
        ("Admin Two", "admin2@eventhub.com", "9876543211", "Admin", "Admin@456"),
    ]

    for fullname, email, mobile, role, password in admins:
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO users (fullname, email, mobile, role, password)
                VALUES (%s, %s, %s, %s, %s)
            """, (fullname, email, mobile, role, generate_password_hash(password)))
            print(f"✅ Seeded admin account: {email}")

    conn.commit()
    conn.close()
    print("🗄️  PostgreSQL database initialised successfully")


# ── User helpers ──────────────────────────────────────────────────────────────

def create_user(fullname, email, mobile, role, password):
    """Insert a new user with a hashed password. Returns False if email exists."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cursor.fetchone():
        conn.close()
        return False

    cursor.execute("""
        INSERT INTO users (fullname, email, mobile, role, password)
        VALUES (%s, %s, %s, %s, %s)
    """, (fullname, email, mobile, role, generate_password_hash(password)))

    conn.commit()
    conn.close()
    return True


def get_user_by_email(email):
    """Fetch a single user row by email, or None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    conn.close()
    return user


def get_user_by_email_and_mobile(email, mobile):
    """
    Fetch a user by email AND mobile number together.
    Used for the Forgot Password identity-verification step.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM users WHERE email = %s AND mobile = %s", (email, mobile)
    )
    user = cursor.fetchone()
    conn.close()
    return user


def update_user_password(email, new_password):
    """Update a user's password (hashes it before storing)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password = %s WHERE email = %s",
        (generate_password_hash(new_password), email)
    )
    conn.commit()
    conn.close()


# ── Event helpers ─────────────────────────────────────────────────────────────

def expire_events():
    """
    Move events whose date has passed into 'Completed' status.
    Called at the start of every dashboard request.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events
        SET status = 'Completed'
        WHERE status IN ('Approved', 'Registration Closed')
          AND event_date::date < CURRENT_DATE
    """)
    conn.commit()
    conn.close()


def create_event(title, category, event_date, event_time, venue, description,
                 capacity, registration_close_date, contact_number, organizer_id):
    """
    Create a new event. Always starts as Pending.
    Generates and stores an Event Code (e.g. 'TEC-0007') immediately.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO events
            (title, category, event_date, event_time, venue, description,
             capacity, registration_close_date, contact_number, organizer_id, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pending')
        RETURNING id
    """, (title, category, event_date, event_time, venue, description,
          capacity, registration_close_date, contact_number, organizer_id))

    event_id = cursor.fetchone()['id']
    event_code = generate_event_code(category, event_id)
    cursor.execute(
        "UPDATE events SET event_code = %s WHERE id = %s", (event_code, event_id)
    )

    conn.commit()
    conn.close()


def get_pending_events_by_organizer(organizer_id):
    """Events this organizer submitted that are still awaiting Admin review."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM events
        WHERE organizer_id = %s AND status = 'Pending'
        ORDER BY created_at DESC
    """, (organizer_id,))
    events = cursor.fetchall()
    conn.close()
    return events


def get_rejected_events_by_organizer(organizer_id):
    """Events this organizer submitted that Admin rejected."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM events
        WHERE organizer_id = %s AND status = 'Rejected'
        ORDER BY created_at DESC
    """, (organizer_id,))
    events = cursor.fetchall()
    conn.close()
    return events


def get_my_events_by_organizer(organizer_id):
    """Approved / Registration Closed / Completed events with registration counts."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*,
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id) AS registered_count
        FROM events e
        WHERE e.organizer_id = %s
          AND e.status IN ('Approved', 'Registration Closed', 'Completed')
        ORDER BY e.event_date ASC
    """, (organizer_id,))
    events = cursor.fetchall()
    conn.close()
    return events


def get_event_by_id(event_id):
    """Fetch a single event by id, or None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE id = %s", (event_id,))
    event = cursor.fetchone()
    conn.close()
    return event


def update_pending_event(event_id, organizer_id, title, category, event_date,
                         event_time, venue, description, capacity,
                         registration_close_date, contact_number):
    """Edit an event that is still Pending (only the owning organizer)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events
        SET title = %s, category = %s, event_date = %s, event_time = %s,
            venue = %s, description = %s, capacity = %s,
            registration_close_date = %s, contact_number = %s
        WHERE id = %s AND organizer_id = %s AND status = 'Pending'
    """, (title, category, event_date, event_time, venue, description,
          capacity, registration_close_date, contact_number,
          event_id, organizer_id))
    conn.commit()
    conn.close()


def resubmit_event(event_id, organizer_id, title, category, event_date,
                   event_time, venue, description, capacity,
                   registration_close_date, contact_number):
    """Edit a Rejected event and send it back to Pending, clearing rejection info."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events
        SET title = %s, category = %s, event_date = %s, event_time = %s,
            venue = %s, description = %s, capacity = %s,
            registration_close_date = %s, contact_number = %s,
            status = 'Pending', rejection_reason = NULL, admin_comment = NULL
        WHERE id = %s AND organizer_id = %s AND status = 'Rejected'
    """, (title, category, event_date, event_time, venue, description,
          capacity, registration_close_date, contact_number,
          event_id, organizer_id))
    conn.commit()
    conn.close()


def delete_owned_event(event_id, organizer_id):
    """Delete a Pending or Rejected event owned by this organizer."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM events
        WHERE id = %s AND organizer_id = %s AND status IN ('Pending', 'Rejected')
    """, (event_id, organizer_id))
    conn.commit()
    conn.close()


def close_registration(event_id, organizer_id):
    """Manually close registration for an Approved event."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events SET status = 'Registration Closed'
        WHERE id = %s AND organizer_id = %s AND status = 'Approved'
    """, (event_id, organizer_id))
    conn.commit()
    conn.close()


def get_event_participants(event_id, organizer_id):
    """Return the participant list for one of this organizer's events."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id AS registration_id, u.fullname, u.email, u.mobile, r.registered_at
        FROM registrations r
        JOIN users u  ON r.user_id  = u.id
        JOIN events e ON r.event_id = e.id
        WHERE r.event_id = %s AND e.organizer_id = %s
        ORDER BY r.registered_at ASC
    """, (event_id, organizer_id))
    participants = cursor.fetchall()
    conn.close()
    return participants


def get_visible_events_for_participants():
    """Events participants are allowed to see (Approved / Reg.Closed / Completed)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*, u.fullname AS organizer_name,
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id) AS registered_count
        FROM events e
        JOIN users u ON e.organizer_id = u.id
        WHERE e.status IN ('Approved', 'Registration Closed', 'Completed')
        ORDER BY e.event_date ASC
    """)
    events = cursor.fetchall()
    conn.close()
    return events


def get_all_events():
    """Every event regardless of status — Admin view."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*, u.fullname AS organizer_name,
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id) AS registered_count
        FROM events e
        JOIN users u ON e.organizer_id = u.id
        ORDER BY e.created_at DESC
    """)
    events = cursor.fetchall()
    conn.close()
    return events


def admin_delete_event(event_id):
    """Delete any event — Admin, no ownership check."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registrations WHERE event_id = %s", (event_id,))
    cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))
    conn.commit()
    conn.close()


# ── Admin approval helpers ────────────────────────────────────────────────────

def get_pending_events_all():
    """All Pending events across all organizers — Admin queue."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*, u.fullname AS organizer_name
        FROM events e
        JOIN users u ON e.organizer_id = u.id
        WHERE e.status = 'Pending'
        ORDER BY e.created_at ASC
    """)
    events = cursor.fetchall()
    conn.close()
    return events


def approve_event(event_id):
    """Admin approves a Pending event."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events
        SET status = 'Approved', rejection_reason = NULL, admin_comment = NULL
        WHERE id = %s AND status = 'Pending'
    """, (event_id,))
    conn.commit()
    conn.close()


def reject_event(event_id, reason):
    """Admin rejects a Pending event with a required reason."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events SET status = 'Rejected', rejection_reason = %s
        WHERE id = %s AND status = 'Pending'
    """, (reason, event_id))
    conn.commit()
    conn.close()


def get_organizer_stats(organizer_id):
    """Summary counts for the organizer's overview cards."""
    conn = get_db_connection()
    cursor = conn.cursor()

    def count(q, p=()):
        cursor.execute(q, p)
        return cursor.fetchone()['count']

    stats = {
        "total_events": count(
            "SELECT COUNT(*) FROM events WHERE organizer_id = %s", (organizer_id,)),
        "approved_events": count(
            "SELECT COUNT(*) FROM events WHERE organizer_id = %s AND status IN ('Approved','Registration Closed')",
            (organizer_id,)),
        "pending_events": count(
            "SELECT COUNT(*) FROM events WHERE organizer_id = %s AND status = 'Pending'",
            (organizer_id,)),
        "rejected_events": count(
            "SELECT COUNT(*) FROM events WHERE organizer_id = %s AND status = 'Rejected'",
            (organizer_id,)),
        "completed_events": count(
            "SELECT COUNT(*) FROM events WHERE organizer_id = %s AND status = 'Completed'",
            (organizer_id,)),
        "total_registrations": count("""
            SELECT COUNT(*) FROM registrations r
            JOIN events e ON r.event_id = e.id
            WHERE e.organizer_id = %s
        """, (organizer_id,)),
    }
    conn.close()
    return stats


# ── Registration helpers ──────────────────────────────────────────────────────

def register_for_event(event_id, user_id):
    """
    Register a participant for an event.
    Returns False if already registered, or if registration rules are not met.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT capacity,
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = events.id) AS registered_count
        FROM events
        WHERE id = %s
          AND status = 'Approved'
          AND event_date::date >= CURRENT_DATE
          AND (registration_close_date IS NULL
               OR registration_close_date::date >= CURRENT_DATE)
    """, (event_id,))

    event = cursor.fetchone()

    if event is None or event['registered_count'] >= event['capacity']:
        conn.close()
        return False

    try:
        cursor.execute(
            "INSERT INTO registrations (event_id, user_id) VALUES (%s, %s)",
            (event_id, user_id)
        )
        conn.commit()
        success = True
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        success = False

    conn.close()
    return success


def cancel_registration(event_id, user_id):
    """Cancel a participant's registration for an event."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM registrations WHERE event_id = %s AND user_id = %s",
        (event_id, user_id)
    )
    conn.commit()
    conn.close()


def get_user_registrations(user_id):
    """
    Return all events a participant has registered for,
    including Registration ID and Event Code.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*, u.fullname AS organizer_name,
               r.id AS registration_id, r.registered_at AS registration_date
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN users  u ON e.organizer_id = u.id
        WHERE r.user_id = %s
        ORDER BY e.event_date ASC
    """, (user_id,))
    events = cursor.fetchall()
    conn.close()
    return events


def get_registration_by_id(registration_id, user_id):
    """
    Fetch full details for a single registration scoped to the owning participant.
    Used to generate the Registration Receipt PDF.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id AS registration_id, r.registered_at,
               u.fullname  AS participant_name,
               u.email     AS participant_email,
               e.title     AS event_title,
               e.event_code, e.category, e.event_date, e.event_time, e.venue,
               o.fullname  AS organizer_name
        FROM registrations r
        JOIN events e ON r.event_id      = e.id
        JOIN users  u ON r.user_id       = u.id
        JOIN users  o ON e.organizer_id  = o.id
        WHERE r.id = %s AND r.user_id = %s
    """, (registration_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return row


def get_all_registrations_by_organizer(organizer_id):
    """Overall registration view for an organizer across all their events."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id AS registration_id, r.registered_at,
               u.fullname, u.email, u.mobile,
               e.id AS event_id, e.title AS event_title,
               e.event_code, e.category, e.event_date
        FROM registrations r
        JOIN events e ON r.event_id  = e.id
        JOIN users  u ON r.user_id   = u.id
        WHERE e.organizer_id = %s
        ORDER BY e.event_date ASC, r.registered_at ASC
    """, (organizer_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_all_registrations_admin():
    """System-wide registration view for Admin."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id AS registration_id, r.registered_at,
               u.fullname, u.email, u.mobile,
               e.id AS event_id, e.title AS event_title,
               e.event_code, e.category, e.event_date,
               o.fullname AS organizer_name
        FROM registrations r
        JOIN events e ON r.event_id     = e.id
        JOIN users  u ON r.user_id      = u.id
        JOIN users  o ON e.organizer_id = o.id
        ORDER BY e.event_date ASC, r.registered_at ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


# ── Admin helpers ─────────────────────────────────────────────────────────────

def get_all_users():
    """Return all registered users (without password hashes)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, fullname, email, mobile, role, created_at
        FROM users
        ORDER BY created_at DESC
    """)
    users = cursor.fetchall()
    conn.close()
    return users


def get_admin_stats():
    """Return summary counts for the admin dashboard."""
    conn = get_db_connection()
    cursor = conn.cursor()

    def count(q):
        cursor.execute(q)
        return cursor.fetchone()['count']

    stats = {
        "total_users":        count("SELECT COUNT(*) FROM users"),
        "total_organizers":   count("SELECT COUNT(*) FROM users WHERE role = 'Organizer'"),
        "total_participants": count("SELECT COUNT(*) FROM users WHERE role = 'Participant'"),
        "total_events":       count("SELECT COUNT(*) FROM events"),
        "pending_events":     count("SELECT COUNT(*) FROM events WHERE status = 'Pending'"),
        "approved_events":    count("SELECT COUNT(*) FROM events WHERE status IN ('Approved','Registration Closed')"),
        "rejected_events":    count("SELECT COUNT(*) FROM events WHERE status = 'Rejected'"),
        "completed_events":   count("SELECT COUNT(*) FROM events WHERE status = 'Completed'"),
        "total_registrations":count("SELECT COUNT(*) FROM registrations"),
    }
    conn.close()
    return stats


def delete_user(user_id):
    """Delete a non-admin user along with their events and registrations."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registrations WHERE user_id = %s", (user_id,))
    cursor.execute("""
        DELETE FROM registrations
        WHERE event_id IN (SELECT id FROM events WHERE organizer_id = %s)
    """, (user_id,))
    cursor.execute("DELETE FROM events WHERE organizer_id = %s", (user_id,))
    cursor.execute(
        "DELETE FROM users WHERE id = %s AND role != 'Admin'", (user_id,)
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()