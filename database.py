import sqlite3
import os
from werkzeug.security import generate_password_hash

# Database file - created automatically in the project folder
DB_NAME = "event_db.db"

# Prefix used when generating an Event Code for each category
CATEGORY_CODES = {
    "Workshop": "WKS",
    "Conference": "CNF",
    "Party": "PTY",
    "Wedding": "WED",
    "Competition": "CMP",
    "Concert": "CCT",
}


def get_db_connection():
    """Return a connection to the SQLite database with row access by column name."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def generate_event_code(category, event_id):
    """Generate a short, human-friendly event code, e.g. 'WKS-0007'."""
    prefix = CATEGORY_CODES.get(category, "EVT")
    return f"{prefix}-{event_id:04d}"


def init_db():
    """
    Create the database file (if it doesn't exist) and all tables.
    Also seeds exactly two fixed Admin accounts - Admin role cannot be
    created through the public signup form.
    """
    db_exists = os.path.exists(DB_NAME)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fullname TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            mobile TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Admin', 'Organizer', 'Participant')),
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            event_date TEXT NOT NULL,
            event_time TEXT,
            venue TEXT NOT NULL,
            description TEXT,
            capacity INTEGER NOT NULL,
            registration_close_date TEXT,
            contact_number TEXT,
            organizer_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending'
                CHECK(status IN ('Pending', 'Approved', 'Registration Closed', 'Rejected', 'Completed')),
            rejection_reason TEXT,
            admin_comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (organizer_id) REFERENCES users (id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(event_id, user_id),
            FOREIGN KEY (event_id) REFERENCES events (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    # ---- Migration: add event_code column for databases created before this feature ---- #
    try:
        cursor.execute("ALTER TABLE events ADD COLUMN event_code TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists

    # Backfill event_code for any existing events that don't have one yet
    rows_needing_code = cursor.execute(
        "SELECT id, category FROM events WHERE event_code IS NULL OR event_code = ''"
    ).fetchall()
    for row in rows_needing_code:
        code = generate_event_code(row["category"], row["id"])
        cursor.execute("UPDATE events SET event_code = ? WHERE id = ?", (code, row["id"]))

    # ---- Seed the two fixed admin accounts (only inserted if not present) ---- #
    admins = [
        ("Admin One", "admin1@eventhub.com", "9876543210", "Admin", "Admin@123"),
        ("Admin Two", "admin2@eventhub.com", "9876543211", "Admin", "Admin@456"),
    ]

    for fullname, email, mobile, role, password in admins:
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO users (fullname, email, mobile, role, password)
                VALUES (?, ?, ?, ?, ?)
            """, (fullname, email, mobile, role, generate_password_hash(password)))
            print(f"✅ Seeded admin account: {email}")

    conn.commit()
    conn.close()

    if not db_exists:
        print(f"🗄️  Created new database file: {DB_NAME}")
    else:
        print(f"🗄️  Using existing database file: {DB_NAME}")


# ============= USER HELPER FUNCTIONS ============= #

def create_user(fullname, email, mobile, role, password):
    """Insert a new user with a hashed password. Returns False if email exists."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        return False

    cursor.execute("""
        INSERT INTO users (fullname, email, mobile, role, password)
        VALUES (?, ?, ?, ?, ?)
    """, (fullname, email, mobile, role, generate_password_hash(password)))

    conn.commit()
    conn.close()
    return True


def get_user_by_email(email):
    """Fetch a single user row by email, or None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    return user


def get_user_by_email_and_mobile(email, mobile):
    """
    Fetch a user by email AND mobile number together.
    Used for the Forgot Password identity-verification step.
    Returns None if the combination doesn't match any user.
    """
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ? AND mobile = ?", (email, mobile)
    ).fetchone()
    conn.close()
    return user


def update_user_password(email, new_password):
    """
    Update a user's password (hashes it before storing).
    Used by the Forgot Password / Reset Password flow.
    """
    conn = get_db_connection()
    conn.execute(
        "UPDATE users SET password = ? WHERE email = ?",
        (generate_password_hash(new_password), email)
    )
    conn.commit()
    conn.close()


# ============= EVENT HELPER FUNCTIONS ============= #

def expire_events():
    """
    Move events whose date has passed into 'Completed' status.
    Called at the start of relevant dashboard requests since there's
    no background scheduler running.
    """
    conn = get_db_connection()
    conn.execute("""
        UPDATE events
        SET status = 'Completed'
        WHERE status IN ('Approved', 'Registration Closed')
          AND date(event_date) < date('now')
    """)
    conn.commit()
    conn.close()


def create_event(title, category, event_date, event_time, venue, description,
                  capacity, registration_close_date, contact_number, organizer_id):
    """
    Create a new event request. Always starts as 'Pending' until Admin reviews it.
    Automatically generates and stores an Event Code (e.g. 'WKS-0007').
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO events
            (title, category, event_date, event_time, venue, description,
             capacity, registration_close_date, contact_number, organizer_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
    """, (title, category, event_date, event_time, venue, description,
          capacity, registration_close_date, contact_number, organizer_id))

    event_id = cursor.lastrowid
    event_code = generate_event_code(category, event_id)
    cursor.execute("UPDATE events SET event_code = ? WHERE id = ?", (event_code, event_id))

    conn.commit()
    conn.close()


def get_pending_events_by_organizer(organizer_id):
    """Events this organizer submitted that are still awaiting Admin review."""
    conn = get_db_connection()
    events = conn.execute("""
        SELECT * FROM events
        WHERE organizer_id = ? AND status = 'Pending'
        ORDER BY created_at DESC
    """, (organizer_id,)).fetchall()
    conn.close()
    return events


def get_rejected_events_by_organizer(organizer_id):
    """Events this organizer submitted that Admin rejected."""
    conn = get_db_connection()
    events = conn.execute("""
        SELECT * FROM events
        WHERE organizer_id = ? AND status = 'Rejected'
        ORDER BY created_at DESC
    """, (organizer_id,)).fetchall()
    conn.close()
    return events


def get_my_events_by_organizer(organizer_id):
    """Approved / Registration Closed / Completed events for this organizer, with registration counts."""
    conn = get_db_connection()
    events = conn.execute("""
        SELECT e.*,
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id) AS registered_count
        FROM events e
        WHERE e.organizer_id = ? AND e.status IN ('Approved', 'Registration Closed', 'Completed')
        ORDER BY e.event_date ASC
    """, (organizer_id,)).fetchall()
    conn.close()
    return events


def get_event_by_id(event_id):
    """Fetch a single event by id, or None."""
    conn = get_db_connection()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    return event


def update_pending_event(event_id, organizer_id, title, category, event_date, event_time,
                          venue, description, capacity, registration_close_date, contact_number):
    """Edit an event that is still Pending (only the owning organizer can edit)."""
    conn = get_db_connection()
    conn.execute("""
        UPDATE events
        SET title = ?, category = ?, event_date = ?, event_time = ?, venue = ?,
            description = ?, capacity = ?, registration_close_date = ?, contact_number = ?
        WHERE id = ? AND organizer_id = ? AND status = 'Pending'
    """, (title, category, event_date, event_time, venue, description,
          capacity, registration_close_date, contact_number, event_id, organizer_id))
    conn.commit()
    conn.close()


def resubmit_event(event_id, organizer_id, title, category, event_date, event_time,
                    venue, description, capacity, registration_close_date, contact_number):
    """Edit a Rejected event and send it back to Pending, clearing the old rejection info."""
    conn = get_db_connection()
    conn.execute("""
        UPDATE events
        SET title = ?, category = ?, event_date = ?, event_time = ?, venue = ?,
            description = ?, capacity = ?, registration_close_date = ?, contact_number = ?,
            status = 'Pending', rejection_reason = NULL, admin_comment = NULL
        WHERE id = ? AND organizer_id = ? AND status = 'Rejected'
    """, (title, category, event_date, event_time, venue, description,
          capacity, registration_close_date, contact_number, event_id, organizer_id))
    conn.commit()
    conn.close()


def delete_owned_event(event_id, organizer_id):
    """
    Delete an event owned by this organizer.
    Allowed for Pending or Rejected events only - approved events cannot be edited/deleted
    once participants may have registered.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM events
        WHERE id = ? AND organizer_id = ? AND status IN ('Pending', 'Rejected')
    """, (event_id, organizer_id))
    conn.commit()
    conn.close()


def close_registration(event_id, organizer_id):
    """Manually close registration for an Approved event owned by this organizer."""
    conn = get_db_connection()
    conn.execute("""
        UPDATE events
        SET status = 'Registration Closed'
        WHERE id = ? AND organizer_id = ? AND status = 'Approved'
    """, (event_id, organizer_id))
    conn.commit()
    conn.close()


def get_event_participants(event_id, organizer_id):
    """
    Return the participant list (registration id, name, email, mobile, registered_at)
    for one of this organizer's events.
    """
    conn = get_db_connection()
    participants = conn.execute("""
        SELECT r.id AS registration_id, u.fullname, u.email, u.mobile, r.registered_at
        FROM registrations r
        JOIN users u ON r.user_id = u.id
        JOIN events e ON r.event_id = e.id
        WHERE r.event_id = ? AND e.organizer_id = ?
        ORDER BY r.registered_at ASC
    """, (event_id, organizer_id)).fetchall()
    conn.close()
    return participants


def get_visible_events_for_participants():
    """
    Events participants are allowed to see at all:
    Approved, Registration Closed, or Completed (Pending/Rejected stay hidden).
    """
    conn = get_db_connection()
    events = conn.execute("""
        SELECT e.*, u.fullname AS organizer_name,
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id) AS registered_count
        FROM events e
        JOIN users u ON e.organizer_id = u.id
        WHERE e.status IN ('Approved', 'Registration Closed', 'Completed')
        ORDER BY e.event_date ASC
    """).fetchall()
    conn.close()
    return events


def get_all_events():
    """Return every event regardless of status, with organizer name and registration counts (Admin view)."""
    conn = get_db_connection()
    events = conn.execute("""
        SELECT e.*, u.fullname AS organizer_name,
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id) AS registered_count
        FROM events e
        JOIN users u ON e.organizer_id = u.id
        ORDER BY e.created_at DESC
    """).fetchall()
    conn.close()
    return events


def admin_delete_event(event_id):
    """Delete any event - used by Admin, no ownership check."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registrations WHERE event_id = ?", (event_id,))
    cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()


# ============= ADMIN APPROVAL FUNCTIONS ============= #

def get_pending_events_all():
    """All events across all organizers awaiting Admin review."""
    conn = get_db_connection()
    events = conn.execute("""
        SELECT e.*, u.fullname AS organizer_name
        FROM events e
        JOIN users u ON e.organizer_id = u.id
        WHERE e.status = 'Pending'
        ORDER BY e.created_at ASC
    """).fetchall()
    conn.close()
    return events


def approve_event(event_id):
    """Admin approves a pending event - becomes visible to participants."""
    conn = get_db_connection()
    conn.execute("""
        UPDATE events SET status = 'Approved', rejection_reason = NULL, admin_comment = NULL
        WHERE id = ? AND status = 'Pending'
    """, (event_id,))
    conn.commit()
    conn.close()


def reject_event(event_id, reason):
    """Admin rejects a pending event with a required reason."""
    conn = get_db_connection()
    conn.execute("""
        UPDATE events SET status = 'Rejected', rejection_reason = ?
        WHERE id = ? AND status = 'Pending'
    """, (reason, event_id))
    conn.commit()
    conn.close()


def get_organizer_stats(organizer_id):
    """Summary counts for the organizer's overview cards."""
    conn = get_db_connection()
    stats = {
        "total_events": conn.execute(
            "SELECT COUNT(*) FROM events WHERE organizer_id = ?", (organizer_id,)
        ).fetchone()[0],
        "approved_events": conn.execute(
            "SELECT COUNT(*) FROM events WHERE organizer_id = ? AND status IN ('Approved', 'Registration Closed')",
            (organizer_id,)
        ).fetchone()[0],
        "pending_events": conn.execute(
            "SELECT COUNT(*) FROM events WHERE organizer_id = ? AND status = 'Pending'", (organizer_id,)
        ).fetchone()[0],
        "rejected_events": conn.execute(
            "SELECT COUNT(*) FROM events WHERE organizer_id = ? AND status = 'Rejected'", (organizer_id,)
        ).fetchone()[0],
        "completed_events": conn.execute(
            "SELECT COUNT(*) FROM events WHERE organizer_id = ? AND status = 'Completed'", (organizer_id,)
        ).fetchone()[0],
        "total_registrations": conn.execute("""
            SELECT COUNT(*) FROM registrations r
            JOIN events e ON r.event_id = e.id
            WHERE e.organizer_id = ?
        """, (organizer_id,)).fetchone()[0],
    }
    conn.close()
    return stats


# ============= REGISTRATION HELPER FUNCTIONS ============= #

def register_for_event(event_id, user_id):
    """
    Register a participant for an event.
    Returns False if already registered, or if the event is not open for registration
    (not Approved, registration closed, event date passed, or capacity full).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    event = cursor.execute("""
        SELECT capacity,
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = events.id) AS registered_count
        FROM events WHERE id = ?
          AND status = 'Approved'
          AND date(event_date) >= date('now')
          AND (registration_close_date IS NULL OR date(registration_close_date) >= date('now'))
    """, (event_id,)).fetchone()

    if event is None or event['registered_count'] >= event['capacity']:
        conn.close()
        return False

    try:
        cursor.execute(
            "INSERT INTO registrations (event_id, user_id) VALUES (?, ?)",
            (event_id, user_id)
        )
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success


def cancel_registration(event_id, user_id):
    """Cancel a participant's registration for an event."""
    conn = get_db_connection()
    conn.execute(
        "DELETE FROM registrations WHERE event_id = ? AND user_id = ?",
        (event_id, user_id)
    )
    conn.commit()
    conn.close()


def get_user_registrations(user_id):
    """
    Return all events a participant has registered for, including the
    Registration ID and Event Code for display in 'My Registrations'.
    """
    conn = get_db_connection()
    events = conn.execute("""
        SELECT e.*, u.fullname AS organizer_name,
               r.id AS registration_id, r.registered_at AS registration_date
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN users u ON e.organizer_id = u.id
        WHERE r.user_id = ?
        ORDER BY e.event_date ASC
    """, (user_id,)).fetchall()
    conn.close()
    return events


def get_registration_by_id(registration_id, user_id):
    """
    Fetch full details for a single registration, scoped to the owning participant.
    Used to generate the Registration Receipt PDF. Returns None if not found
    or if it doesn't belong to this user.
    """
    conn = get_db_connection()
    row = conn.execute("""
        SELECT r.id AS registration_id, r.registered_at,
               u.fullname AS participant_name, u.email AS participant_email,
               e.title AS event_title, e.event_code, e.category,
               e.event_date, e.event_time, e.venue,
               o.fullname AS organizer_name
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN users u ON r.user_id = u.id
        JOIN users o ON e.organizer_id = o.id
        WHERE r.id = ? AND r.user_id = ?
    """, (registration_id, user_id)).fetchone()
    conn.close()
    return row


def get_all_registrations_by_organizer(organizer_id):
    """
    'Overall registration view' for an organizer - every registration across
    every event they own, newest event first.
    """
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT r.id AS registration_id, r.registered_at,
               u.fullname, u.email, u.mobile,
               e.id AS event_id, e.title AS event_title, e.event_code,
               e.category, e.event_date
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN users u ON r.user_id = u.id
        WHERE e.organizer_id = ?
        ORDER BY e.event_date ASC, r.registered_at ASC
    """, (organizer_id,)).fetchall()
    conn.close()
    return rows


def get_all_registrations_admin():
    """
    System-wide registration view for Admin - every registration across
    every event, with organizer name included.
    """
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT r.id AS registration_id, r.registered_at,
               u.fullname, u.email, u.mobile,
               e.id AS event_id, e.title AS event_title, e.event_code,
               e.category, e.event_date,
               o.fullname AS organizer_name
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN users u ON r.user_id = u.id
        JOIN users o ON e.organizer_id = o.id
        ORDER BY e.event_date ASC, r.registered_at ASC
    """).fetchall()
    conn.close()
    return rows


# ============= ADMIN HELPER FUNCTIONS ============= #

def get_all_users():
    """Return all registered users (without password hashes)."""
    conn = get_db_connection()
    users = conn.execute("""
        SELECT id, fullname, email, mobile, role, created_at
        FROM users
        ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    return users


def get_admin_stats():
    """Return summary counts for the admin dashboard."""
    conn = get_db_connection()
    stats = {
        "total_users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "total_organizers": conn.execute("SELECT COUNT(*) FROM users WHERE role = 'Organizer'").fetchone()[0],
        "total_participants": conn.execute("SELECT COUNT(*) FROM users WHERE role = 'Participant'").fetchone()[0],
        "total_events": conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        "pending_events": conn.execute("SELECT COUNT(*) FROM events WHERE status = 'Pending'").fetchone()[0],
        "approved_events": conn.execute("SELECT COUNT(*) FROM events WHERE status IN ('Approved', 'Registration Closed')").fetchone()[0],
        "rejected_events": conn.execute("SELECT COUNT(*) FROM events WHERE status = 'Rejected'").fetchone()[0],
        "completed_events": conn.execute("SELECT COUNT(*) FROM events WHERE status = 'Completed'").fetchone()[0],
        "total_registrations": conn.execute("SELECT COUNT(*) FROM registrations").fetchone()[0],
    }
    conn.close()
    return stats


def delete_user(user_id):
    """Delete a non-admin user, along with their events and registrations."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registrations WHERE user_id = ?", (user_id,))
    cursor.execute(
        "DELETE FROM registrations WHERE event_id IN (SELECT id FROM events WHERE organizer_id = ?)",
        (user_id,)
    )
    cursor.execute("DELETE FROM events WHERE organizer_id = ?", (user_id,))
    cursor.execute("DELETE FROM users WHERE id = ? AND role != 'Admin'", (user_id,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    # Run this file directly to (re)initialize the database:
    #   python database.py
    init_db()