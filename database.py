"""
database.py — EventHub PostgreSQL Version
==========================================
Complete updated version with all improvements:
- Updated 6 event categories (Technical/Creative/Cultural/Academic/Competition/Sports & Fitness)
- Single admin account (eventhub62@gmail.com)
- check_duplicate_event()
- bulk_approve_events() / bulk_reject_events()
- notifications table + full notification functions
- contact_messages table + save_contact_message()
- is_trusted column on users (auto-approval for trusted organizers)
- All existing functions preserved exactly
"""

import os
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash

# ── Database URL ──────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# ── Updated 6 category code prefixes ─────────────────────────────────────────
CATEGORY_CODES = {
    "Technical Events": "TEC",
    "Creative Events":  "CRE",
    "Cultural Events":  "CUL",
    "Academic Events":  "ACD",
    "Competition":      "CMP",
    "Sports & Fitness": "SPT",
}


def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL,
                            cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def generate_event_code(category, event_id):
    prefix = CATEGORY_CODES.get(category, "EVT")
    return f"{prefix}-{event_id:04d}"


# ── Database initialisation ───────────────────────────────────────────────────

def init_db():
    conn   = get_db_connection()
    cursor = conn.cursor()

    # users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          SERIAL PRIMARY KEY,
            fullname    TEXT        NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            mobile      TEXT        NOT NULL,
            role        TEXT        NOT NULL
                        CHECK(role IN ('Admin','Organizer','Participant')),
            password    TEXT        NOT NULL,
            is_trusted  BOOLEAN     DEFAULT FALSE,
            created_at  TIMESTAMP   DEFAULT NOW()
        )
    """)
    conn.commit()

    # is_trusted migration for existing databases
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_trusted BOOLEAN DEFAULT FALSE")
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()

    # events
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
                                        'Pending','Approved',
                                        'Registration Closed','Rejected','Completed'
                                    )),
            rejection_reason        TEXT,
            admin_comment           TEXT,
            event_code              TEXT,
            created_at              TIMESTAMP   DEFAULT NOW()
        )
    """)
    conn.commit()

    # reminder_sent migration for existing databases
    try:
        cursor.execute("ALTER TABLE events ADD COLUMN reminder_sent BOOLEAN DEFAULT FALSE")
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()

    # registrations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id            SERIAL PRIMARY KEY,
            event_id      INTEGER   NOT NULL REFERENCES events(id),
            user_id       INTEGER   NOT NULL REFERENCES users(id),
            registered_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(event_id, user_id)
        )
    """)
    conn.commit()

    # attended migration for existing databases
    try:
        cursor.execute("ALTER TABLE registrations ADD COLUMN attended BOOLEAN DEFAULT FALSE")
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()

    # feedback — one per registration, required (with attendance) to unlock a certificate
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id               SERIAL PRIMARY KEY,
            registration_id  INTEGER   NOT NULL UNIQUE REFERENCES registrations(id),
            event_id         INTEGER   NOT NULL REFERENCES events(id),
            user_id          INTEGER   NOT NULL REFERENCES users(id),
            rating           INTEGER   NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comments         TEXT,
            created_at       TIMESTAMP DEFAULT NOW(),
            updated_at       TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()

    # notifications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER   NOT NULL REFERENCES users(id),
            title       TEXT      NOT NULL,
            message     TEXT      NOT NULL,
            type        TEXT      DEFAULT 'info',
            is_read     BOOLEAN   DEFAULT FALSE,
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()

    # contact_messages
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contact_messages (
            id          SERIAL PRIMARY KEY,
            full_name   TEXT      NOT NULL,
            email       TEXT      NOT NULL,
            user_role   TEXT,
            subject     TEXT,
            message     TEXT      NOT NULL,
            is_read     BOOLEAN   DEFAULT FALSE,
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()

    # admin_reply migration for existing databases
    try:
        cursor.execute("ALTER TABLE contact_messages ADD COLUMN admin_reply TEXT")
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    try:
        cursor.execute("ALTER TABLE contact_messages ADD COLUMN replied_at TIMESTAMP")
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()

    # ── Single admin account ──────────────────────────────────────────────────
    admins = [
        ("EventHub Admin", "eventhub62@gmail.com", "9876543210", "Admin", "Admin@123"),
    ]

    for fullname, email, mobile, role, password in admins:
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO users (fullname, email, mobile, role, password, is_trusted)
                VALUES (%s, %s, %s, %s, %s, TRUE)
            """, (fullname, email, mobile, role, generate_password_hash(password)))
            print(f"✅ Seeded admin account: {email}")

    conn.commit()
    conn.close()
    print("🗄️  PostgreSQL database initialised successfully")


# ── User helpers ──────────────────────────────────────────────────────────────

def create_user(fullname, email, mobile, role, password):
    conn   = get_db_connection()
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
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user


def get_user_by_email_and_mobile(email, mobile):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM users WHERE email = %s AND mobile = %s", (email, mobile)
    )
    user = cursor.fetchone()
    conn.close()
    return user


def update_user_password(email, new_password):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password = %s WHERE email = %s",
        (generate_password_hash(new_password), email)
    )
    conn.commit()
    conn.close()


def set_organizer_trusted(organizer_id, trusted=True):
    """Mark/unmark an organizer as trusted (auto-approval)."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET is_trusted = %s WHERE id = %s AND role = 'Organizer'",
        (trusted, organizer_id)
    )
    conn.commit()
    conn.close()


def is_organizer_trusted(organizer_id):
    """Return True if the organizer is marked as trusted."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT is_trusted FROM users WHERE id = %s", (organizer_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return bool(row and row['is_trusted'])


# ── Event helpers ─────────────────────────────────────────────────────────────

def expire_events():
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events
        SET status = 'Completed'
        WHERE status IN ('Approved','Registration Closed')
          AND event_date::date < CURRENT_DATE
    """)
    conn.commit()
    conn.close()


def get_events_needing_reminder():
    """Events happening tomorrow that haven't had a reminder email sent yet."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM events
        WHERE status IN ('Approved','Registration Closed')
          AND (reminder_sent IS NULL OR reminder_sent = FALSE)
          AND event_date::date = (CURRENT_DATE + INTERVAL '1 day')::date
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_event_registrant_emails(event_id):
    """All registered participants' name + email for an event (system-level, no organizer scoping)."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.fullname, u.email
        FROM registrations r
        JOIN users u ON r.user_id = u.id
        WHERE r.event_id = %s
    """, (event_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def mark_reminder_sent(event_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE events SET reminder_sent = TRUE WHERE id=%s", (event_id,))
    conn.commit()
    conn.close()


def check_duplicate_event(title, event_date, venue):
    """
    Returns True if an event with the same title + date + venue already exists.
    Used to prevent duplicate submissions.
    """
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM events
        WHERE LOWER(title) = LOWER(%s)
          AND event_date   = %s
          AND LOWER(venue) = LOWER(%s)
        LIMIT 1
    """, (title, event_date, venue))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def create_event(title, category, event_date, event_time, venue, description,
                 capacity, registration_close_date, contact_number, organizer_id):
    """
    Create a new event.
    If the organizer is trusted → auto-approved immediately.
    Otherwise → Pending (requires Admin review).
    Returns event_id.
    """
    conn   = get_db_connection()
    cursor = conn.cursor()

    # Determine initial status
    trusted = is_organizer_trusted(organizer_id)
    initial_status = 'Approved' if trusted else 'Pending'

    cursor.execute("""
        INSERT INTO events
            (title, category, event_date, event_time, venue, description,
             capacity, registration_close_date, contact_number,
             organizer_id, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (title, category, event_date, event_time, venue, description,
          capacity, registration_close_date, contact_number,
          organizer_id, initial_status))

    event_id   = cursor.fetchone()['id']
    event_code = generate_event_code(category, event_id)
    cursor.execute(
        "UPDATE events SET event_code = %s WHERE id = %s",
        (event_code, event_id)
    )

    conn.commit()
    conn.close()
    return event_id


def get_pending_events_by_organizer(organizer_id):
    conn   = get_db_connection()
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
    conn   = get_db_connection()
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
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*,
               (SELECT COUNT(*) FROM registrations r
                WHERE r.event_id = e.id) AS registered_count
        FROM events e
        WHERE e.organizer_id = %s
          AND e.status IN ('Approved','Registration Closed','Completed')
        ORDER BY e.event_date ASC
    """, (organizer_id,))
    events = cursor.fetchall()
    conn.close()
    return events


def get_event_by_id(event_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE id = %s", (event_id,))
    event = cursor.fetchone()
    conn.close()
    return event


def update_pending_event(event_id, organizer_id, title, category, event_date,
                         event_time, venue, description, capacity,
                         registration_close_date, contact_number):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events
        SET title=%s, category=%s, event_date=%s, event_time=%s,
            venue=%s, description=%s, capacity=%s,
            registration_close_date=%s, contact_number=%s
        WHERE id=%s AND organizer_id=%s AND status='Pending'
    """, (title, category, event_date, event_time, venue, description,
          capacity, registration_close_date, contact_number,
          event_id, organizer_id))
    conn.commit()
    conn.close()


def resubmit_event(event_id, organizer_id, title, category, event_date,
                   event_time, venue, description, capacity,
                   registration_close_date, contact_number):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events
        SET title=%s, category=%s, event_date=%s, event_time=%s,
            venue=%s, description=%s, capacity=%s,
            registration_close_date=%s, contact_number=%s,
            status='Pending', rejection_reason=NULL, admin_comment=NULL
        WHERE id=%s AND organizer_id=%s AND status='Rejected'
    """, (title, category, event_date, event_time, venue, description,
          capacity, registration_close_date, contact_number,
          event_id, organizer_id))
    conn.commit()
    conn.close()


def delete_owned_event(event_id, organizer_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM events
        WHERE id=%s AND organizer_id=%s AND status IN ('Pending','Rejected')
    """, (event_id, organizer_id))
    conn.commit()
    conn.close()


def close_registration(event_id, organizer_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events SET status='Registration Closed'
        WHERE id=%s AND organizer_id=%s AND status='Approved'
    """, (event_id, organizer_id))
    conn.commit()
    conn.close()


def get_event_participants(event_id, organizer_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id AS registration_id, r.attended,
               u.fullname, u.email, u.mobile, r.registered_at
        FROM registrations r
        JOIN users  u ON r.user_id  = u.id
        JOIN events e ON r.event_id = e.id
        WHERE r.event_id=%s AND e.organizer_id=%s
        ORDER BY r.registered_at ASC
    """, (event_id, organizer_id))
    participants = cursor.fetchall()
    conn.close()
    return participants


def mark_attendance(registration_id, organizer_id, attended):
    """
    Toggle attendance for a registration, but only if the requesting
    organizer actually owns the underlying event.
    Returns True on success, False if not authorized / not found.
    """
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE registrations r
        SET attended = %s
        FROM events e
        WHERE r.id = %s
          AND r.event_id = e.id
          AND e.organizer_id = %s
    """, (attended, registration_id, organizer_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def get_visible_events_for_participants():
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*, u.fullname AS organizer_name,
               (SELECT COUNT(*) FROM registrations r
                WHERE r.event_id = e.id) AS registered_count
        FROM events e
        JOIN users u ON e.organizer_id = u.id
        WHERE e.status IN ('Approved','Registration Closed','Completed')
        ORDER BY e.event_date ASC
    """)
    events = cursor.fetchall()
    conn.close()
    return events


def get_all_events():
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*, u.fullname AS organizer_name,
               (SELECT COUNT(*) FROM registrations r
                WHERE r.event_id = e.id) AS registered_count
        FROM events e
        JOIN users u ON e.organizer_id = u.id
        ORDER BY e.created_at DESC
    """)
    events = cursor.fetchall()
    conn.close()
    return events


def admin_delete_event(event_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM feedback WHERE event_id = %s", (event_id,))
    cursor.execute("DELETE FROM registrations WHERE event_id = %s", (event_id,))
    cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))
    conn.commit()
    conn.close()


# ── Admin approval helpers ────────────────────────────────────────────────────

def get_pending_events_all():
    conn   = get_db_connection()
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
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events
        SET status='Approved', rejection_reason=NULL, admin_comment=NULL
        WHERE id=%s AND status='Pending'
    """, (event_id,))
    conn.commit()
    conn.close()


def reject_event(event_id, reason):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events SET status='Rejected', rejection_reason=%s
        WHERE id=%s AND status='Pending'
    """, (reason, event_id))
    conn.commit()
    conn.close()


def bulk_approve_events(event_ids):
    """Approve a list of pending events in one call."""
    if not event_ids:
        return
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events
        SET status='Approved', rejection_reason=NULL, admin_comment=NULL
        WHERE id = ANY(%s) AND status='Pending'
    """, (event_ids,))
    conn.commit()
    conn.close()


def bulk_reject_events(event_ids, reason):
    """Reject a list of pending events with a shared reason."""
    if not event_ids:
        return
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events
        SET status='Rejected', rejection_reason=%s
        WHERE id = ANY(%s) AND status='Pending'
    """, (reason, event_ids))
    conn.commit()
    conn.close()


def get_organizer_stats(organizer_id):
    conn   = get_db_connection()
    cursor = conn.cursor()

    def count(q, p=()):
        cursor.execute(q, p)
        return cursor.fetchone()['count']

    stats = {
        "total_events":       count("SELECT COUNT(*) FROM events WHERE organizer_id=%s", (organizer_id,)),
        "approved_events":    count("SELECT COUNT(*) FROM events WHERE organizer_id=%s AND status IN ('Approved','Registration Closed')", (organizer_id,)),
        "pending_events":     count("SELECT COUNT(*) FROM events WHERE organizer_id=%s AND status='Pending'", (organizer_id,)),
        "rejected_events":    count("SELECT COUNT(*) FROM events WHERE organizer_id=%s AND status='Rejected'", (organizer_id,)),
        "completed_events":   count("SELECT COUNT(*) FROM events WHERE organizer_id=%s AND status='Completed'", (organizer_id,)),
        "total_registrations":count("""
            SELECT COUNT(*) FROM registrations r
            JOIN events e ON r.event_id=e.id
            WHERE e.organizer_id=%s
        """, (organizer_id,)),
    }
    conn.close()
    return stats


# ── Registration helpers ──────────────────────────────────────────────────────

def register_for_event(event_id, user_id):
    """
    Registers a user for an event. Uses SELECT ... FOR UPDATE to lock the
    event row for the duration of the check+insert, so two concurrent
    registrations for the same event can't both slip in past capacity —
    the second one waits for the first to commit, then re-checks the
    (now up-to-date) count before deciding.
    """
    conn   = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT capacity,
                   (SELECT COUNT(*) FROM registrations r
                    WHERE r.event_id = events.id) AS registered_count
            FROM events
            WHERE id=%s
              AND status='Approved'
              AND event_date::date >= CURRENT_DATE
              AND (registration_close_date IS NULL
                   OR registration_close_date::date >= CURRENT_DATE)
            FOR UPDATE
        """, (event_id,))

        event = cursor.fetchone()
        if event is None or event['registered_count'] >= event['capacity']:
            conn.rollback()
            conn.close()
            return False

        cursor.execute(
            "INSERT INTO registrations (event_id, user_id) VALUES (%s, %s)",
            (event_id, user_id)
        )

        # Return new registration id
        cursor.execute(
            "SELECT id FROM registrations WHERE event_id=%s AND user_id=%s",
            (event_id, user_id)
        )
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return row['id'] if row else True

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        conn.close()
        return False


def cancel_registration(event_id, user_id):
    """
    Cancels a registration. Only allowed while the event hasn't completed yet
    (mirrors what the UI already hides) — this also guarantees no feedback
    row can exist yet, since feedback requires a Completed event, so there's
    no FK conflict to worry about here.
    Returns True if a registration was actually cancelled.
    """
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM registrations r
        USING events e
        WHERE r.event_id = e.id
          AND r.event_id = %s AND r.user_id = %s
          AND e.status != 'Completed'
    """, (event_id, user_id))
    cancelled = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return cancelled


def get_user_registrations(user_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*, u.fullname AS organizer_name,
               r.id AS registration_id,
               r.registered_at AS registration_date,
               r.attended,
               f.rating AS feedback_rating,
               f.comments AS feedback_comments,
               (f.id IS NOT NULL) AS feedback_submitted
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN users  u ON e.organizer_id = u.id
        LEFT JOIN feedback f ON f.registration_id = r.id
        WHERE r.user_id=%s
        ORDER BY e.event_date ASC
    """, (user_id,))
    events = cursor.fetchall()
    conn.close()
    return events


def get_registration_by_id(registration_id, user_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id AS registration_id, r.registered_at, r.attended,
               u.fullname AS participant_name,
               u.email    AS participant_email,
               e.id AS event_id, e.title AS event_title, e.event_code,
               e.status AS event_status,
               e.category, e.event_date, e.event_time, e.venue,
               o.fullname AS organizer_name,
               EXISTS(
                   SELECT 1 FROM feedback f WHERE f.registration_id = r.id
               ) AS feedback_submitted
        FROM registrations r
        JOIN events e ON r.event_id     = e.id
        JOIN users  u ON r.user_id      = u.id
        JOIN users  o ON e.organizer_id = o.id
        WHERE r.id=%s AND r.user_id=%s
    """, (registration_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return row


def get_all_registrations_by_organizer(organizer_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id AS registration_id, r.registered_at,
               u.fullname, u.email, u.mobile,
               e.id AS event_id, e.title AS event_title,
               e.event_code, e.category, e.event_date
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN users  u ON r.user_id  = u.id
        WHERE e.organizer_id=%s
        ORDER BY e.event_date ASC, r.registered_at ASC
    """, (organizer_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_all_registrations_admin():
    conn   = get_db_connection()
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
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, fullname, email, mobile, role, is_trusted, created_at
        FROM users
        ORDER BY created_at DESC
    """)
    users = cursor.fetchall()
    conn.close()
    return users


def get_admin_stats():
    conn   = get_db_connection()
    cursor = conn.cursor()

    def count(q):
        cursor.execute(q)
        return cursor.fetchone()['count']

    stats = {
        "total_users":         count("SELECT COUNT(*) FROM users"),
        "total_organizers":    count("SELECT COUNT(*) FROM users WHERE role='Organizer'"),
        "total_participants":  count("SELECT COUNT(*) FROM users WHERE role='Participant'"),
        "total_events":        count("SELECT COUNT(*) FROM events"),
        "pending_events":      count("SELECT COUNT(*) FROM events WHERE status='Pending'"),
        "approved_events":     count("SELECT COUNT(*) FROM events WHERE status IN ('Approved','Registration Closed')"),
        "rejected_events":     count("SELECT COUNT(*) FROM events WHERE status='Rejected'"),
        "completed_events":    count("SELECT COUNT(*) FROM events WHERE status='Completed'"),
        "total_registrations": count("SELECT COUNT(*) FROM registrations"),
        "unread_contacts":     count("SELECT COUNT(*) FROM contact_messages WHERE is_read=FALSE"),
    }
    conn.close()
    return stats


def delete_user(user_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notifications WHERE user_id=%s", (user_id,))
    cursor.execute("DELETE FROM feedback WHERE user_id=%s", (user_id,))
    cursor.execute("""
        DELETE FROM feedback
        WHERE event_id IN (SELECT id FROM events WHERE organizer_id=%s)
    """, (user_id,))
    cursor.execute("DELETE FROM registrations WHERE user_id=%s", (user_id,))
    cursor.execute("""
        DELETE FROM registrations
        WHERE event_id IN (SELECT id FROM events WHERE organizer_id=%s)
    """, (user_id,))
    cursor.execute("DELETE FROM events WHERE organizer_id=%s", (user_id,))
    cursor.execute(
        "DELETE FROM users WHERE id=%s AND role != 'Admin'", (user_id,)
    )
    conn.commit()
    conn.close()


# ── Notification helpers ──────────────────────────────────────────────────────

def create_notification(user_id, title, message, notif_type='info'):
    """Create a single in-app notification for a user."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notifications (user_id, title, message, type)
        VALUES (%s, %s, %s, %s)
    """, (user_id, title, message, notif_type))
    conn.commit()
    conn.close()


def get_notifications(user_id, limit=20):
    """Return the most recent notifications for a user."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM notifications
        WHERE user_id=%s
        ORDER BY created_at DESC
        LIMIT %s
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_unread_notification_count(user_id):
    """Return unread notification count for the bell badge."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM notifications
        WHERE user_id=%s AND is_read=FALSE
    """, (user_id,))
    count = cursor.fetchone()['count']
    conn.close()
    return count


def mark_notification_read(notification_id, user_id):
    """Mark a single notification as read."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE notifications SET is_read=TRUE
        WHERE id=%s AND user_id=%s
    """, (notification_id, user_id))
    conn.commit()
    conn.close()


def mark_all_notifications_read(user_id):
    """Mark all notifications as read for a user."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE notifications SET is_read=TRUE WHERE user_id=%s", (user_id,)
    )
    conn.commit()
    conn.close()


# ── Contact message helpers ───────────────────────────────────────────────────

def save_contact_message(full_name, email, user_role, subject, message):
    """Store a contact form submission in the database."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO contact_messages (full_name, email, user_role, subject, message)
        VALUES (%s, %s, %s, %s, %s)
    """, (full_name, email, user_role, subject, message))
    conn.commit()
    conn.close()


def get_contact_messages():
    """Return all contact messages for Admin view."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM contact_messages
        ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def mark_contact_read(message_id):
    """Mark a contact message as read."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE contact_messages SET is_read=TRUE WHERE id=%s", (message_id,)
    )
    conn.commit()
    conn.close()


def get_contact_message_by_id(message_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contact_messages WHERE id=%s", (message_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def reply_to_contact_message(message_id, reply_text):
    """Saves the admin's reply text and marks the message read + replied."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE contact_messages
        SET admin_reply = %s, replied_at = NOW(), is_read = TRUE
        WHERE id = %s
    """, (reply_text, message_id))
    conn.commit()
    conn.close()


# ── Feedback helpers ───────────────────────────────────────────────────────────

def submit_feedback(registration_id, event_id, user_id, rating, comments):
    """
    Records or updates feedback for a registration (participants can edit
    their feedback anytime — the certificate stays unlocked once feedback
    exists, it doesn't re-lock on edit).
    Only allowed if the caller owns the registration, attended the event,
    and the event is completed. Returns True if a row was written.
    """
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO feedback (registration_id, event_id, user_id, rating, comments)
        SELECT r.id, r.event_id, r.user_id, %s, %s
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        WHERE r.id = %s AND r.user_id = %s
          AND r.attended = TRUE
          AND e.status = 'Completed'
        ON CONFLICT (registration_id) DO UPDATE
        SET rating = EXCLUDED.rating,
            comments = EXCLUDED.comments,
            updated_at = NOW()
        RETURNING id
    """, (rating, comments, registration_id, user_id))
    written = cursor.fetchone() is not None
    conn.commit()
    conn.close()
    return written


def get_feedback_by_registration(registration_id, user_id):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.* FROM feedback f
        JOIN registrations r ON f.registration_id = r.id
        WHERE f.registration_id = %s AND r.user_id = %s
    """, (registration_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return row


def get_event_feedback(event_id, organizer_id):
    """All feedback for one of an organizer's own events (for their dashboard)."""
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.rating, f.comments, f.created_at, u.fullname
        FROM feedback f
        JOIN registrations r ON f.registration_id = r.id
        JOIN events e        ON f.event_id = e.id
        JOIN users u         ON f.user_id = u.id
        WHERE f.event_id = %s AND e.organizer_id = %s
        ORDER BY f.created_at DESC
    """, (event_id, organizer_id))
    rows = cursor.fetchall()
    conn.close()
    return rows


if __name__ == "__main__":
    init_db()