from flask import Flask, render_template, request, redirect, session, jsonify, send_file
from werkzeug.security import check_password_hash
import re
from io import BytesIO
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from openpyxl import Workbook

from database import (
    init_db, create_user, get_user_by_email, get_user_by_email_and_mobile, update_user_password,
    expire_events,
    create_event, get_event_by_id,
    get_pending_events_by_organizer, get_rejected_events_by_organizer, get_my_events_by_organizer,
    update_pending_event, resubmit_event, delete_owned_event, close_registration,
    get_event_participants, get_organizer_stats,
    get_visible_events_for_participants, get_all_events, admin_delete_event,
    get_pending_events_all, approve_event, reject_event,
    register_for_event, cancel_registration, get_user_registrations, get_registration_by_id,
    get_all_registrations_by_organizer, get_all_registrations_admin,
    get_all_users, get_admin_stats, delete_user
)

app = Flask(__name__)
app.secret_key = "eventhub_secret_key"  # change this to a random value in production


# ============= HELPER FUNCTIONS ============= #

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_mobile(mobile):
    """Validate mobile number (10 digits)"""
    return re.match(r'^\d{10}$', str(mobile)) is not None


def validate_password(password):
    """Validate password strength (minimum 6 characters)"""
    return len(password) >= 6


def validate_event_dates(event_date, registration_close_date):
    """
    Returns an error message string if the dates are invalid, otherwise None.
    - Event date cannot be in the past.
    - Registration close date (if given) must be on or before the event date.
    """
    try:
        event_dt = datetime.strptime(event_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return "Invalid event date"

    if event_dt < datetime.now().date():
        return "Event date cannot be in the past"

    if registration_close_date:
        try:
            close_dt = datetime.strptime(registration_close_date, "%Y-%m-%d").date()
        except ValueError:
            return "Invalid registration close date"

        if close_dt > event_dt:
            return "Registration closing date must be on or before the event date"

    return None


def is_user_logged_in():
    """Check if user is logged in"""
    return 'user_id' in session


def get_user_dashboard_route(role):
    """Get dashboard route based on user role"""
    routes = {
        "Admin": "/admin_dashboard",
        "Organizer": "/organizer_dashboard",
        "Participant": "/participant_dashboard"
    }
    return routes.get(role, "/login")


# ============= REPORT HELPER FUNCTIONS ============= #

def build_pdf_table(title, headers, rows):
    """Build a simple titled table PDF and return it as a BytesIO buffer."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    elements = [Paragraph(title, styles['Title']), Spacer(1, 16)]

    data = [headers] + [[str(cell) if cell is not None else '-' for cell in row] for row in rows]
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#11121a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f2f2f2')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))

    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer


def build_excel_table(headers, rows):
    """Build a simple worksheet with a header row and return it as a BytesIO buffer."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"

    ws.append(headers)
    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)

    for row in rows:
        ws.append([cell if cell is not None else '-' for cell in row])

    for col_idx, header in enumerate(headers, start=1):
        col_values = [str(header)] + [str(r[col_idx - 1]) for r in rows]
        max_len = max(len(v) for v in col_values)
        column_letter = ws.cell(row=1, column=col_idx).column_letter
        ws.column_dimensions[column_letter].width = max_len + 4

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ============= HOME PAGE ============= #

@app.route('/')
def home():
    """Render home page"""
    return render_template('home.html')


# ============= REGISTER ============= #

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration"""

    if request.method == 'POST':

        # Get form data
        fullname = request.form.get('fullname', '').strip()
        email = request.form.get('email', '').strip().lower()
        mobile = request.form.get('mobile', '').strip()
        role = request.form.get('role', '').strip()
        password = request.form.get('password', '').strip()

        # ============= VALIDATION ============= #

        if not all([fullname, email, mobile, role, password]):
            return jsonify({
                'success': False,
                'message': 'Please fill in all fields'
            }), 400

        if not validate_email(email):
            return jsonify({
                'success': False,
                'message': 'Invalid email format'
            }), 400

        if not validate_mobile(mobile):
            return jsonify({
                'success': False,
                'message': 'Mobile number must be exactly 10 digits'
            }), 400

        if not validate_password(password):
            return jsonify({
                'success': False,
                'message': 'Password must be at least 6 characters'
            }), 400

        # Admin accounts cannot be created through public signup
        if role not in ["Organizer", "Participant"]:
            return jsonify({
                'success': False,
                'message': 'Invalid role selected'
            }), 400

        # ============= DATABASE OPERATIONS ============= #

        try:
            created = create_user(fullname, email, mobile, role, password)

            if not created:
                return jsonify({
                    'success': False,
                    'message': 'Email already registered. Please login or use a different email.'
                }), 409

            return jsonify({
                'success': True,
                'message': 'Registration successful! Redirecting to login...',
                'redirect': '/login'
            }), 201

        except Exception as e:
            print(f"❌ REGISTER ERROR: {e}")
            return jsonify({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.'
            }), 500

    return render_template('register.html')


# ============= LOGIN ============= #

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""

    if request.method == 'POST':

        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()

        # ============= VALIDATION ============= #

        if not email or not password:
            return jsonify({
                'success': False,
                'message': 'Please enter both email and password'
            }), 400

        if not validate_email(email):
            return jsonify({
                'success': False,
                'message': 'Invalid email format'
            }), 400

        # ============= DATABASE OPERATIONS ============= #

        try:
            user = get_user_by_email(email)

            if user and check_password_hash(user['password'], password):
                # Login successful - create session
                session['user_id'] = user['id']
                session['user_name'] = user['fullname']
                session['email'] = user['email']
                session['role'] = user['role']

                dashboard_route = get_user_dashboard_route(user['role'])

                return jsonify({
                    'success': True,
                    'message': f'Login successful! Welcome, {user["fullname"]}',
                    'redirect': dashboard_route,
                    'role': user['role']
                }), 200

            else:
                return jsonify({
                    'success': False,
                    'message': 'Invalid email or password'
                }), 401

        except Exception as e:
            print(f"❌ LOGIN ERROR: {e}")
            return jsonify({
                'success': False,
                'message': 'Login failed. Please try again.'
            }), 500

    return render_template('login.html')


# ============= FORGOT PASSWORD ============= #

@app.route('/forgot_password', methods=['POST'])
def forgot_password():
    """
    Step 1 of password reset: verify identity using Email + Mobile Number.
    Works for Admin, Organizer, and Participant accounts alike.
    """

    email = request.form.get('email', '').strip().lower()
    mobile = request.form.get('mobile', '').strip()

    if not email or not mobile:
        return jsonify({
            'success': False,
            'message': 'Please enter both email and mobile number'
        }), 400

    if not validate_email(email):
        return jsonify({
            'success': False,
            'message': 'Invalid email format'
        }), 400

    if not validate_mobile(mobile):
        return jsonify({
            'success': False,
            'message': 'Mobile number must be exactly 10 digits'
        }), 400

    try:
        user = get_user_by_email_and_mobile(email, mobile)

        if user:
            return jsonify({
                'success': True,
                'message': 'Identity verified. Please set a new password.'
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Invalid Email Address or Mobile Number.'
            }), 401

    except Exception as e:
        print(f"❌ FORGOT PASSWORD ERROR: {e}")
        return jsonify({
            'success': False,
            'message': 'Something went wrong. Please try again.'
        }), 500


@app.route('/reset_password', methods=['POST'])
def reset_password():
    """
    Step 2 of password reset: re-verify Email + Mobile Number (don't trust
    client-side state alone), then update the password if both match
    and the new password meets requirements.
    """

    email = request.form.get('email', '').strip().lower()
    mobile = request.form.get('mobile', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    if not all([email, mobile, new_password, confirm_password]):
        return jsonify({
            'success': False,
            'message': 'Please fill in all fields'
        }), 400

    if new_password != confirm_password:
        return jsonify({
            'success': False,
            'message': 'Passwords do not match'
        }), 400

    if not validate_password(new_password):
        return jsonify({
            'success': False,
            'message': 'Password must be at least 6 characters'
        }), 400

    try:
        user = get_user_by_email_and_mobile(email, mobile)

        if not user:
            return jsonify({
                'success': False,
                'message': 'Invalid Email Address or Mobile Number.'
            }), 401

        update_user_password(email, new_password)

        return jsonify({
            'success': True,
            'message': 'Password updated successfully. Please log in.',
            'redirect': '/login'
        }), 200

    except Exception as e:
        print(f"❌ RESET PASSWORD ERROR: {e}")
        return jsonify({
            'success': False,
            'message': 'Something went wrong. Please try again.'
        }), 500


# ============= ROLE-BASED DASHBOARDS ============= #

@app.route('/participant_dashboard')
def participant_dashboard():
    """Render participant dashboard"""

    if not is_user_logged_in():
        return redirect('/login')

    if session.get('role') != 'Participant':
        return redirect('/')

    expire_events()

    visible_events = get_visible_events_for_participants()
    my_registrations = get_user_registrations(session['user_id'])
    registered_ids = {row['id'] for row in my_registrations}

    # "Discover Events" should only show events that are still open for registration
    discover_events = [
        e for e in visible_events
        if e['status'] == 'Approved' and e['registered_count'] < e['capacity']
    ]

    return render_template(
        'participant_dashboard.html',
        user_name=session.get('user_name'),
        email=session.get('email'),
        events=discover_events,
        my_registrations=my_registrations,
        registered_ids=registered_ids
    )


@app.route('/organizer_dashboard')
def organizer_dashboard():
    """Render organizer dashboard"""

    if not is_user_logged_in():
        return redirect('/login')

    if session.get('role') != 'Organizer':
        return redirect('/')

    expire_events()

    organizer_id = session['user_id']

    return render_template(
        'organizer_dashboard.html',
        user_name=session.get('user_name'),
        email=session.get('email'),
        stats=get_organizer_stats(organizer_id),
        events=get_my_events_by_organizer(organizer_id),
        pending_events=get_pending_events_by_organizer(organizer_id),
        rejected_events=get_rejected_events_by_organizer(organizer_id),
        all_registrations=get_all_registrations_by_organizer(organizer_id)
    )


@app.route('/admin_dashboard')
def admin_dashboard():
    """Render admin dashboard"""

    if not is_user_logged_in():
        return redirect('/login')

    if session.get('role') != 'Admin':
        return redirect('/')

    expire_events()

    return render_template(
        'admin_dashboard.html',
        user_name=session.get('user_name'),
        email=session.get('email'),
        stats=get_admin_stats(),
        users=get_all_users(),
        events=get_all_events(),
        pending_events=get_pending_events_all(),
        all_registrations=get_all_registrations_admin()
    )


# ============= ORGANIZER ACTIONS ============= #

@app.route('/organizer/create_event', methods=['POST'])
def create_event_route():
    """Create a new event request for the logged-in organizer (starts as Pending)"""

    if not is_user_logged_in() or session.get('role') != 'Organizer':
        return redirect('/login')

    title = request.form.get('title', '').strip()
    category = request.form.get('category', '').strip()
    event_date = request.form.get('event_date', '').strip()
    event_time = request.form.get('event_time', '').strip()
    venue = request.form.get('venue', '').strip()
    description = request.form.get('description', '').strip()
    capacity = request.form.get('capacity', '').strip()
    registration_close_date = request.form.get('registration_close_date', '').strip()
    contact_number = request.form.get('contact_number', '').strip()

    if all([title, category, event_date, venue, capacity]):
        try:
            capacity_int = int(capacity)
        except ValueError:
            capacity_int = 0

        if capacity_int > 0 and validate_event_dates(event_date, registration_close_date) is None:
            create_event(
                title, category, event_date, event_time, venue, description,
                capacity_int, registration_close_date or None, contact_number, session['user_id']
            )

    return redirect('/organizer_dashboard')


@app.route('/organizer/edit_pending/<int:event_id>', methods=['POST'])
def edit_pending_event_route(event_id):
    """Edit an event that is still Pending Approval"""

    if not is_user_logged_in() or session.get('role') != 'Organizer':
        return redirect('/login')

    title = request.form.get('title', '').strip()
    category = request.form.get('category', '').strip()
    event_date = request.form.get('event_date', '').strip()
    event_time = request.form.get('event_time', '').strip()
    venue = request.form.get('venue', '').strip()
    description = request.form.get('description', '').strip()
    capacity = request.form.get('capacity', '').strip()
    registration_close_date = request.form.get('registration_close_date', '').strip()
    contact_number = request.form.get('contact_number', '').strip()

    if all([title, category, event_date, venue, capacity]):
        try:
            capacity_int = int(capacity)
        except ValueError:
            capacity_int = 0

        if capacity_int > 0 and validate_event_dates(event_date, registration_close_date) is None:
            update_pending_event(
                event_id, session['user_id'], title, category, event_date, event_time,
                venue, description, capacity_int, registration_close_date or None, contact_number
            )

    return redirect('/organizer_dashboard')


@app.route('/organizer/resubmit/<int:event_id>', methods=['POST'])
def resubmit_event_route(event_id):
    """Edit a Rejected event and send it back to Pending Approval"""

    if not is_user_logged_in() or session.get('role') != 'Organizer':
        return redirect('/login')

    title = request.form.get('title', '').strip()
    category = request.form.get('category', '').strip()
    event_date = request.form.get('event_date', '').strip()
    event_time = request.form.get('event_time', '').strip()
    venue = request.form.get('venue', '').strip()
    description = request.form.get('description', '').strip()
    capacity = request.form.get('capacity', '').strip()
    registration_close_date = request.form.get('registration_close_date', '').strip()
    contact_number = request.form.get('contact_number', '').strip()

    if all([title, category, event_date, venue, capacity]):
        try:
            capacity_int = int(capacity)
        except ValueError:
            capacity_int = 0

        if capacity_int > 0 and validate_event_dates(event_date, registration_close_date) is None:
            resubmit_event(
                event_id, session['user_id'], title, category, event_date, event_time,
                venue, description, capacity_int, registration_close_date or None, contact_number
            )

    return redirect('/organizer_dashboard')


@app.route('/organizer/delete/<int:event_id>', methods=['POST'])
def delete_owned_event_route(event_id):
    """Delete an event owned by the organizer - only while Pending or Rejected"""

    if not is_user_logged_in() or session.get('role') != 'Organizer':
        return redirect('/login')

    delete_owned_event(event_id, session['user_id'])
    return redirect('/organizer_dashboard')


@app.route('/organizer/close_registration/<int:event_id>', methods=['POST'])
def close_registration_route(event_id):
    """Manually close registration on an Approved event"""

    if not is_user_logged_in() or session.get('role') != 'Organizer':
        return redirect('/login')

    close_registration(event_id, session['user_id'])
    return redirect('/organizer_dashboard')


@app.route('/organizer/event_participants/<int:event_id>')
def organizer_event_participants(event_id):
    """
    Return the participant list for one of this organizer's events as JSON.
    Intended for an AJAX-driven 'View Participants' panel on the dashboard.
    """

    if not is_user_logged_in() or session.get('role') != 'Organizer':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    event = get_event_by_id(event_id)

    if not event or event['organizer_id'] != session['user_id']:
        return jsonify({'success': False, 'message': 'Event not found'}), 404

    participants = get_event_participants(event_id, session['user_id'])

    return jsonify({
        'success': True,
        'event_title': event['title'],
        'event_code': event['event_code'],
        'participants': [
            {
                'registration_id': p['registration_id'],
                'fullname': p['fullname'],
                'email': p['email'],
                'mobile': p['mobile'],
                'registered_at': p['registered_at'],
            }
            for p in participants
        ]
    }), 200


# ============= PARTICIPANT ACTIONS ============= #

@app.route('/participant/register_event/<int:event_id>', methods=['POST'])
def register_event_route(event_id):
    """Register the logged-in participant for an event"""

    if not is_user_logged_in() or session.get('role') != 'Participant':
        return redirect('/login')

    register_for_event(event_id, session['user_id'])
    return redirect('/participant_dashboard')


@app.route('/participant/cancel_event/<int:event_id>', methods=['POST'])
def cancel_event_route(event_id):
    """Cancel the logged-in participant's registration for an event"""

    if not is_user_logged_in() or session.get('role') != 'Participant':
        return redirect('/login')

    cancel_registration(event_id, session['user_id'])
    return redirect('/participant_dashboard')


# ============= ADMIN ACTIONS ============= #

@app.route('/admin/approve_event/<int:event_id>', methods=['POST'])
def approve_event_route(event_id):
    """Admin approves a pending event"""

    if not is_user_logged_in() or session.get('role') != 'Admin':
        return redirect('/login')

    approve_event(event_id)
    return redirect('/admin_dashboard')


@app.route('/admin/reject_event/<int:event_id>', methods=['POST'])
def reject_event_route(event_id):
    """Admin rejects a pending event with a required reason"""

    if not is_user_logged_in() or session.get('role') != 'Admin':
        return redirect('/login')

    reason = request.form.get('reason', '').strip()
    if reason:
        reject_event(event_id, reason)

    return redirect('/admin_dashboard')


@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def admin_delete_user_route(user_id):
    """Delete a non-admin user (and their events/registrations)"""

    if not is_user_logged_in() or session.get('role') != 'Admin':
        return redirect('/login')

    delete_user(user_id)
    return redirect('/admin_dashboard')


@app.route('/admin/delete_event/<int:event_id>', methods=['POST'])
def admin_delete_event_route(event_id):
    """Delete any event"""

    if not is_user_logged_in() or session.get('role') != 'Admin':
        return redirect('/login')

    admin_delete_event(event_id)
    return redirect('/admin_dashboard')


# ============= DOWNLOADABLE REPORTS ============= #

@app.route('/participant/receipt/<int:registration_id>')
def download_receipt(registration_id):
    """Download a Registration Receipt (PDF) for one of the participant's own registrations."""

    if not is_user_logged_in() or session.get('role') != 'Participant':
        return redirect('/login')

    reg = get_registration_by_id(registration_id, session['user_id'])

    if not reg:
        return redirect('/participant_dashboard')

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    elements = [
        Paragraph("EventHub - Registration Receipt", styles['Title']),
        Spacer(1, 16),
    ]

    rows = [
        ['Registration ID', f"REG-{reg['registration_id']:05d}"],
        ['Event Code', reg['event_code'] or '-'],
        ['Event Title', reg['event_title']],
        ['Category', reg['category']],
        ['Date', reg['event_date']],
        ['Time', reg['event_time'] or '-'],
        ['Venue', reg['venue']],
        ['Organizer', reg['organizer_name']],
        ['Participant', reg['participant_name']],
        ['Email', reg['participant_email']],
        ['Registered On', reg['registered_at']],
    ]

    table = Table(rows, colWidths=[160, 320])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    elements.append(table)
    doc.build(elements)
    buffer.seek(0)

    filename = f"receipt_{reg['event_code'] or registration_id}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')


@app.route('/organizer/report/event/<int:event_id>')
def organizer_event_report(event_id):
    """Download an Event-wise Registered Participants Report (PDF or Excel)."""

    if not is_user_logged_in() or session.get('role') != 'Organizer':
        return redirect('/login')

    event = get_event_by_id(event_id)

    if not event or event['organizer_id'] != session['user_id']:
        return redirect('/organizer_dashboard')

    fmt = request.args.get('format', 'pdf')
    participants = get_event_participants(event_id, session['user_id'])

    headers = ['Reg. ID', 'Name', 'Email', 'Mobile', 'Registered On']
    rows = [
        [f"REG-{p['registration_id']:05d}", p['fullname'], p['email'], p['mobile'], p['registered_at']]
        for p in participants
    ]

    event_code = event['event_code'] or f"EVT-{event_id:04d}"
    title = f"{event['title']} ({event_code}) - Registered Participants"

    if fmt == 'excel':
        buffer = build_excel_table(headers, rows)
        return send_file(
            buffer, as_attachment=True,
            download_name=f"{event_code}_participants.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    buffer = build_pdf_table(title, headers, rows)
    return send_file(buffer, as_attachment=True, download_name=f"{event_code}_participants.pdf", mimetype='application/pdf')


@app.route('/organizer/report/overall')
def organizer_overall_report():
    """Download an Overall Registered Participants Report (PDF or Excel) across all of this organizer's events."""

    if not is_user_logged_in() or session.get('role') != 'Organizer':
        return redirect('/login')

    fmt = request.args.get('format', 'pdf')
    registrations = get_all_registrations_by_organizer(session['user_id'])

    headers = ['Reg. ID', 'Event Code', 'Event', 'Category', 'Date', 'Participant', 'Email', 'Mobile', 'Registered On']
    rows = [
        [
            f"REG-{r['registration_id']:05d}", r['event_code'], r['event_title'], r['category'],
            r['event_date'], r['fullname'], r['email'], r['mobile'], r['registered_at']
        ]
        for r in registrations
    ]

    title = "Overall Registered Participants Report"

    if fmt == 'excel':
        buffer = build_excel_table(headers, rows)
        return send_file(
            buffer, as_attachment=True,
            download_name="overall_registrations.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    buffer = build_pdf_table(title, headers, rows)
    return send_file(buffer, as_attachment=True, download_name="overall_registrations.pdf", mimetype='application/pdf')


@app.route('/admin/report/all')
def admin_all_report():
    """Download a System-wide Registered Participants Report (PDF or Excel)."""

    if not is_user_logged_in() or session.get('role') != 'Admin':
        return redirect('/login')

    fmt = request.args.get('format', 'pdf')
    registrations = get_all_registrations_admin()

    headers = ['Reg. ID', 'Event Code', 'Event', 'Category', 'Date', 'Organizer', 'Participant', 'Email', 'Mobile', 'Registered On']
    rows = [
        [
            f"REG-{r['registration_id']:05d}", r['event_code'], r['event_title'], r['category'],
            r['event_date'], r['organizer_name'], r['fullname'], r['email'], r['mobile'], r['registered_at']
        ]
        for r in registrations
    ]

    title = "System-wide Registered Participants Report"

    if fmt == 'excel':
        buffer = build_excel_table(headers, rows)
        return send_file(
            buffer, as_attachment=True,
            download_name="system_registrations.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    buffer = build_pdf_table(title, headers, rows)
    return send_file(buffer, as_attachment=True, download_name="system_registrations.pdf", mimetype='application/pdf')


# ============= LOGOUT ============= #

@app.route('/logout')
def logout():
    """Handle user logout"""

    session.clear()

    return jsonify({
        'success': True,
        'message': 'Logged out successfully!',
        'redirect': '/'
    }), 200


# ============= ERROR HANDLERS ============= #

@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors"""
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(e):
    """Handle 500 errors"""
    return render_template('500.html'), 500


# ============= RUN APP ============= #

if __name__ == '__main__':
    init_db()  # auto-creates event_db.db and the users table on first run
    print("🚀 EVENTHUB SERVER STARTING...")
    app.run(debug=True, host='127.0.0.1', port=5000)