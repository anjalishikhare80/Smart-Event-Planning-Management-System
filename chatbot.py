"""
chatbot.py — EventHub Rule-Based AI Assistant Blueprint
========================================================
Completely isolated module.
- No external API calls
- No new database tables
- No changes to existing routes or business logic
- Registered in app.py with two lines only

Route: POST /chatbot/message
Input:  { "message": "...", "role": "..." }
Output: { "reply": "...", "suggestions": [...] }
"""

from flask import Blueprint, request, jsonify, session
import re

# ── Blueprint ─────────────────────────────────────────────────────────────────
chatbot_bp = Blueprint('chatbot', __name__, url_prefix='/chatbot')


# ══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — all answers defined here
# ══════════════════════════════════════════════════════════════════════════════

KNOWLEDGE = {

    # ── GENERAL (all roles) ───────────────────────────────────────────────────

    "what_is_eventhub": {
        "patterns": [
            "what is eventhub", "about eventhub", "tell me about",
            "what does eventhub do", "what is this platform",
            "what is this system", "what is this app", "what is this website",
            "what is this", "explain eventhub", "eventhub kya hai"
        ],
        "responses": {
            "Guest":       "EventHub is a Smart Event Planning and Management System. It connects Organizers who create events with Participants who register for them. Admins oversee the entire platform. You can sign up as an Organizer or Participant to get started!",
            "Admin":       "EventHub is the platform you manage. It connects Organizers (who create events) with Participants (who register). You oversee approvals, users, and platform-wide analytics from your Admin Dashboard.",
            "Organizer":   "EventHub is the platform where you create and manage events. You submit events for Admin approval, then Participants can discover and register for your approved events.",
            "Participant": "EventHub is an event discovery and registration platform. You can browse approved events, register for them, and manage your registrations — all from your Participant Dashboard."
        },
        "suggestions": ["How do I login?", "How do I sign up?", "How do I navigate the dashboard?"]
    },

    "login": {
        "patterns": [
            "how do i login", "how to login", "sign in", "how to sign in",
            "login problem", "cant login", "cannot login", "login issue",
            "how do i access", "how to access dashboard", "login kaise kare"
        ],
        "responses": {
            "Guest":       "To login:\n1. Go to the homepage (/)\n2. Click the 'Log in' button (top right)\n3. Enter your registered email and password\n4. You will be redirected to your role-specific dashboard automatically.",
            "Admin":       "You are already logged in as Admin. Your dashboard is at /admin_dashboard. If you need to login again, click Logout first then use your admin credentials on the homepage.",
            "Organizer":   "You are already logged in as Organizer. Your dashboard is at /organizer_dashboard. If you face login issues, try the Forgot Password option on the login modal.",
            "Participant": "You are already logged in as Participant. Your dashboard is at /participant_dashboard. If you face login issues, try the Forgot Password option on the login modal."
        },
        "suggestions": ["How do I sign up?", "How do I reset my password?"]
    },

    "signup": {
        "patterns": [
            "how do i sign up", "how to register", "create account",
            "how to create account", "register account", "new account",
            "how to join", "sign up kaise kare", "registration kaise kare",
            "can i create admin account", "how to become admin",
            "signup", "register"
        ],
        "responses": {
            "Guest":       "To sign up:\n1. Go to the homepage (/)\n2. Click 'Get a pass' button\n3. Fill in your name, email, mobile number\n4. Select your role: Participant or Organizer\n5. Set a password (min 6 characters)\n6. Click 'Create Account'\n\nNote: Admin accounts cannot be created via signup — only 2 fixed Admin accounts exist.",
            "Admin":       "Admin accounts cannot be created via public signup. Only 2 fixed Admin accounts exist on this platform. New users can sign up as Organizer or Participant from the homepage.",
            "Organizer":   "You already have an Organizer account. New users can sign up from the homepage (/) by clicking 'Get a pass'. They can choose Organizer or Participant role.",
            "Participant": "You already have a Participant account. New users can sign up from the homepage (/) by clicking 'Get a pass'. They can choose Organizer or Participant role."
        },
        "suggestions": ["How do I login?", "What roles are available?", "How do I reset my password?"]
    },

    "forgot_password": {
        "patterns": [
            "forgot password", "reset password", "forgot my password",
            "change password", "recover password", "password reset",
            "i forgot my password", "cant remember password",
            "password bhul gaya", "password recovery", "reset kaise kare"
        ],
        "responses": {
            "Guest":       "To reset your password:\n1. Go to the homepage (/)\n2. Click 'Log in'\n3. Click 'Forgot your password?' link\n4. Enter your registered Email + Mobile Number\n5. If verified, set your new password\n6. Login with the new password\n\nThis works for all roles (Admin, Organizer, Participant).",
            "Admin":       "To reset your Admin password:\n1. Logout first\n2. On the homepage, click 'Log in'\n3. Click 'Forgot your password?'\n4. Enter your admin email + registered mobile number\n5. Set your new password",
            "Organizer":   "To reset your password:\n1. Logout first\n2. On the homepage, click 'Log in'\n3. Click 'Forgot your password?'\n4. Enter your email + registered mobile number\n5. Set your new password",
            "Participant": "To reset your password:\n1. Logout first\n2. On the homepage, click 'Log in'\n3. Click 'Forgot your password?'\n4. Enter your email + registered mobile number\n5. Set your new password"
        },
        "suggestions": ["How do I login?", "How do I sign up?"]
    },

    "logout": {
        "patterns": [
            "how do i logout", "how to logout", "sign out", "how to sign out",
            "logout kaise kare", "exit account", "how to exit"
        ],
        "responses": {
            "Guest":       "You are not currently logged in. Visit the homepage (/) to login or sign up.",
            "Admin":       "To logout: Click the 'Logout' button in the top-right corner of your Admin Dashboard. You will be returned to the homepage.",
            "Organizer":   "To logout: Click the 'Logout' button in the top-right corner of your Organizer Dashboard. You will be returned to the homepage.",
            "Participant": "To logout: Click the 'Logout' button in the top-right corner of your Participant Dashboard. You will be returned to the homepage."
        },
        "suggestions": ["How do I login again?"]
    },

    "roles": {
        "patterns": [
            "what roles are available", "types of users", "user roles",
            "what is admin", "what is organizer", "what is participant",
            "difference between roles", "roles in eventhub", "who can do what"
        ],
        "responses": {
            "Guest":       "EventHub has 3 roles:\n\n1. Admin — Platform controller. Reviews and approves events, manages all users. Only 2 fixed Admin accounts exist.\n\n2. Organizer — Creates and manages events. Submits events for Admin approval.\n\n3. Participant — Discovers and registers for approved events.\n\nYou can sign up as Organizer or Participant from the homepage.",
            "Admin":       "EventHub has 3 roles:\n\n1. Admin (you) — Full platform control, approve/reject events, manage users\n\n2. Organizer — Creates events, manages participants\n\n3. Participant — Discovers and registers for events\n\nOnly 2 Admin accounts exist and cannot be created via signup.",
            "Organizer":   "EventHub has 3 roles:\n\n1. Admin — Approves/rejects your submitted events\n\n2. Organizer (you) — Create events, manage participants, download reports\n\n3. Participant — Discovers and registers for your approved events",
            "Participant": "EventHub has 3 roles:\n\n1. Admin — Manages the platform\n\n2. Organizer — Creates events you can register for\n\n3. Participant (you) — Discover and register for events"
        },
        "suggestions": ["How do I sign up?", "What can I do as my role?"]
    },

    "navigation": {
        "patterns": [
            "how to navigate", "where to find", "how to go to",
            "dashboard navigation", "where is", "how to reach",
            "navigate kaise kare", "dashboard kahan hai", "menu",
            "where can i find", "how to access"
        ],
        "responses": {
            "Guest":       "Navigation guide:\n• Homepage: /\n• Login: Click 'Log in' on homepage\n• Sign Up: Click 'Get a pass' on homepage\n• Forgot Password: Inside the Login modal",
            "Admin":       "Admin Dashboard Navigation (/admin_dashboard):\n• Pending Approval — Review and approve/reject events\n• All Events — View every event on the platform\n• All Users — Manage all registered users\n• Registrations — System-wide registration data\n• Download Report — PDF/Excel system report",
            "Organizer":   "Organizer Dashboard Navigation (/organizer_dashboard):\n• Create Event — Submit a new event\n• My Events — Approved/Closed/Completed events\n• Pending Approval — Events waiting for Admin review\n• Rejected Events — Events rejected by Admin\n• Registrations — All participants across your events",
            "Participant": "Participant Dashboard Navigation (/participant_dashboard):\n• Discover Events — Browse open events\n• My Registrations — Events you registered for\n• Upcoming Events — Future registered events\n• Completed Events — Past events you attended"
        },
        "suggestions": ["What can I do from the dashboard?"]
    },

    # ── ORGANIZER TOPICS ──────────────────────────────────────────────────────

    "create_event": {
        "patterns": [
            "create event", "how to create", "new event", "add event",
            "submit event", "create new event", "event create karna",
            "how to add event", "post an event", "event banana hai",
            "make event", "how do i create", "start an event"
        ],
        "responses": {
            "Guest":       "You need to be logged in as an Organizer to create events. Sign up at the homepage (/) and select the Organizer role.",
            "Admin":       "Only Organizers can create events. As Admin, you review and approve events submitted by Organizers in the Pending Approval section.",
            "Organizer":   "To create an event:\n1. Go to /organizer_dashboard\n2. Scroll to 'Create a new event' section\n3. Fill in all required fields:\n   - Event Title\n   - Category (Technical Events/Creative Events/Cultural Events/Academic Events/Competition/Sports & Fitness)\n   - Venue\n   - Event Date (cannot be in the past)\n   - Event Time\n   - Maximum Participants\n   - Registration Closing Date (must be before event date)\n   - Contact Number\n   - Description\n4. Click 'Submit for approval'\n\nYour event will be sent to Admin for review and will show as 'Pending Approval'.",
            "Participant": "Only Organizers can create events. If you want to create events, you would need an Organizer account. You can sign up as an Organizer from the homepage."
        },
        "suggestions": ["What happens after I create an event?", "What is pending approval?", "What are the event categories?"]
    },

    "event_status": {
        "patterns": [
            "event status", "what is pending", "event approval", "status of event",
            "why is event pending", "event not visible", "event not showing",
            "event workflow", "event stages", "status kya hai",
            "pending approval kya hai", "what happens after creating"
        ],
        "responses": {
            "Guest":       "Event statuses in EventHub:\n• Pending — Submitted by Organizer, waiting for Admin review\n• Approved — Admin approved, visible to Participants\n• Registration Closed — Organizer stopped new registrations\n• Rejected — Admin rejected with reason\n• Completed — Event date has passed",
            "Admin":       "Event statuses you manage:\n• Pending — Events waiting for your review\n• Approved — You approved, now visible to Participants\n• Registration Closed — Organizer closed registrations\n• Rejected — You rejected with a reason\n• Completed — Event date has passed (auto-updated)",
            "Organizer":   "Your event goes through these stages:\n\n1. Pending — After you create it, Admin reviews it\n2. Approved — Admin approved, Participants can now register\n3. Registration Closed — You or the system closed registrations\n4. Rejected — Admin rejected with a reason (you can edit and resubmit)\n5. Completed — Event date has passed (automatic)\n\nOnly Approved events are visible to Participants.",
            "Participant": "Event statuses you might see:\n• Approved — Open for registration\n• Registration Closed — Cannot register anymore\n• Completed — Event has finished\n\nNote: Pending and Rejected events are never shown to Participants."
        },
        "suggestions": ["How do I get my event approved?", "What if my event is rejected?", "How do I resubmit a rejected event?"]
    },

    "pending_approval": {
        "patterns": [
            "pending approval", "waiting for approval", "admin review",
            "event under review", "when will event be approved",
            "how long approval takes", "pending events", "approval process",
            "event pending kab approve hoga", "approval kaise hota hai"
        ],
        "responses": {
            "Guest":       "When an Organizer creates an event, it goes to 'Pending Approval' and waits for Admin review before becoming visible to Participants.",
            "Admin":       "To review pending events:\n1. Go to /admin_dashboard\n2. Click 'Pending Approval' tab\n3. Review event details (title, category, date, venue, organizer)\n4. Click 'Approve' — event becomes visible to Participants\n   OR\n   Click 'Reject' — enter a rejection reason and submit\n\nAll pending events require your action before they go live.",
            "Organizer":   "Your pending events are waiting for Admin review.\n\nWhile Pending:\n• You CAN edit the event\n• You CAN delete the event\n• Participants CANNOT see the event\n\nTo view pending events: /organizer_dashboard → 'Pending Approval' section\n\nOnce Admin approves, it moves to 'My Events' and becomes visible to Participants.",
            "Participant": "Pending events are not visible to Participants. You will only see events that have been approved by Admin in the Discover Events section."
        },
        "suggestions": ["What if my event is rejected?", "Can I edit a pending event?", "How do I delete a pending event?"]
    },

    "edit_event": {
        "patterns": [
            "edit event", "update event", "modify event", "change event",
            "can i edit", "event edit karna", "update event details",
            "change event details", "how to edit", "event modify karna"
        ],
        "responses": {
            "Guest":       "Only Organizers can edit events. Login or sign up as an Organizer to manage events.",
            "Admin":       "Organizers can edit their events only when status is Pending or Rejected. Once an event is Approved, it cannot be edited (Participants may already be registered).",
            "Organizer":   "Event editing rules:\n\n✅ Pending events — You CAN edit\n   Go to 'Pending Approval' section → Click 'Edit' on the event\n\n✅ Rejected events — You CAN edit and resubmit\n   Go to 'Rejected Events' section → Click 'Edit & Resubmit'\n\n❌ Approved events — CANNOT be edited\n   Reason: Participants may already be registered with the original details\n\n❌ Completed events — CANNOT be edited (read-only)",
            "Participant": "Participants cannot edit events. Only the Organizer who created the event can edit it (only while it's Pending or Rejected)."
        },
        "suggestions": ["What is pending approval?", "How do I resubmit a rejected event?", "Can I delete an event?"]
    },

    "resubmit_event": {
        "patterns": [
            "resubmit event", "edit and resubmit", "rejected event",
            "event rejected", "why was my event rejected", "fix rejected event",
            "resubmit karna", "rejection reason", "event reject ho gaya",
            "how to fix rejection", "event rejected by admin"
        ],
        "responses": {
            "Guest":       "Rejected events can be edited and resubmitted by Organizers after addressing the Admin's rejection reason.",
            "Admin":       "When you reject an event, the Organizer sees the rejection reason and can fix issues then resubmit. The event returns to Pending status for your review again.",
            "Organizer":   "If your event is rejected:\n1. Go to /organizer_dashboard → 'Rejected Events' section\n2. Read the Admin's rejection reason carefully\n3. Click 'Edit & Resubmit'\n4. Fix the issues mentioned\n5. Click 'Resubmit for approval'\n\nThe event returns to 'Pending Approval' status and the old rejection reason is cleared. Admin will review it again.",
            "Participant": "Rejected events are not visible to Participants. The Organizer fixes the issues and resubmits for Admin approval."
        },
        "suggestions": ["What is event status?", "Can I edit an approved event?", "How does approval work?"]
    },

    "delete_event": {
        "patterns": [
            "delete event", "remove event", "cancel event",
            "how to delete", "event delete karna", "event remove karna",
            "can i delete"
        ],
        "responses": {
            "Guest":       "Only Organizers can delete their own events (Pending or Rejected only). Admins can delete any event.",
            "Admin":       "As Admin, you can delete ANY event regardless of status:\n1. Go to /admin_dashboard → 'All Events' tab\n2. Find the event\n3. Click the trash icon\n4. Confirm deletion\n\nNote: Deleting an event also removes all its registrations.",
            "Organizer":   "You can delete your events only when:\n✅ Status is Pending — Go to 'Pending Approval' → Click Delete\n✅ Status is Rejected — Go to 'Rejected Events' → Click Delete\n\n❌ Cannot delete Approved, Completed, or Registration Closed events\n\nDeleting removes the event permanently.",
            "Participant": "Participants cannot delete events. Contact the Organizer or Admin if you need an event removed."
        },
        "suggestions": ["Can I edit an event instead?", "What happens to registrations when event is deleted?"]
    },

    "close_registration": {
        "patterns": [
            "close registration", "stop registration", "end registration",
            "registration close karna", "how to close registration",
            "stop new registrations", "close sign ups"
        ],
        "responses": {
            "Guest":       "Only Organizers can close registrations for their approved events.",
            "Admin":       "Organizers can manually close registrations for their Approved events. You as Admin can also delete an event if needed.",
            "Organizer":   "To close registration for an event:\n1. Go to /organizer_dashboard → 'My Events' section\n2. Find the Approved event\n3. Click 'Close Registration'\n4. Confirm the action\n\nOnce closed:\n• No new Participants can register\n• Status changes to 'Registration Closed'\n• Already registered Participants are unaffected\n\nNote: Registration also closes automatically on the Registration Closing Date you set.",
            "Participant": "When an Organizer closes registration, no new registrations are accepted. If you haven't registered yet, you won't be able to join that event."
        },
        "suggestions": ["How do I view my participants?", "How do I download a report?"]
    },

    "view_participants": {
        "patterns": [
            "view participants", "see participants", "who registered",
            "participant list", "registered participants", "participants dekho",
            "who signed up", "registration list", "how many registered"
        ],
        "responses": {
            "Guest":       "Only Organizers can view participants for their events.",
            "Admin":       "To view all registrations system-wide:\n1. Go to /admin_dashboard\n2. Click 'Registrations' tab\n3. You can search by participant name, email, event, or organizer\n4. Download PDF/Excel report using the download buttons",
            "Organizer":   "To view participants for your events:\n\nEvent-wise:\n1. Go to /organizer_dashboard → 'My Events'\n2. Click 'Participants (count)' on any event card\n3. A panel shows all registered participants with:\n   - Registration ID, Name, Email, Mobile, Registration Date\n\nOverall (all events):\n1. Go to 'Registrations' tab in your dashboard\n2. Search participants by name, email, or event code\n3. Download event-wise or overall report (PDF/Excel)",
            "Participant": "Participants cannot see other participants. You can only view your own registrations in 'My Registrations' section."
        },
        "suggestions": ["How do I download a report?", "What is an event code?"]
    },

    "download_report": {
        "patterns": [
            "download report", "export report", "pdf report", "excel report",
            "download participants", "export participants", "report download karna",
            "download data", "export data", "get report"
        ],
        "responses": {
            "Guest":       "Reports can be downloaded by Organizers (event-wise and overall) and Admins (system-wide) after logging in.",
            "Admin":       "To download system-wide report:\n1. Go to /admin_dashboard → 'Registrations' tab\n2. Click 'PDF' for a PDF report\n   OR 'Excel' for an Excel (.xlsx) file\n\nReport includes: Registration ID, Participant details, Event details, Organizer name, Registration date",
            "Organizer":   "Download options available to you:\n\n1. Event-wise report:\n   → My Events → Click 'Participants' on an event → Download PDF or Excel\n\n2. Overall report (all events):\n   → 'Registrations' tab → Click PDF or Excel download button\n\nBoth reports include: Registration ID, Event Code, Participant name, Email, Mobile, Registration date",
            "Participant": "As a Participant, you can download your Registration Receipt:\n1. Go to /participant_dashboard\n2. Open 'My Registrations' section\n3. Find your registration\n4. Click 'Receipt' button to download PDF\n\nThe receipt includes your Registration ID, Event Code, event details, and your details."
        },
        "suggestions": ["What is a registration ID?", "What is an event code?"]
    },

    "event_code": {
        "patterns": [
            "event code", "what is event code", "event code kya hai",
            "event id", "event identifier", "TEC cmp cnf"
        ],
        "responses": {
            "Guest":       "Event codes are unique identifiers automatically assigned to each event (e.g. TEC-0001, CRE-0002).",
            "Admin":       "Event codes are auto-generated when an event is created:\n• TEC — Technical Events\n• CRE — Creative Events\n• CUL — Cultural Events\n• ACD — Academic Events\n• CMP — Competition\n• SPT — Sports & Fitness\n\nFormat: PREFIX-NNNN (e.g. TEC-0007). Visible in All Events table.",
            "Organizer":   "Each event gets an auto-generated Event Code when created:\n• TEC-0001 (Technical Events)\n• CRE-0001 (Creative Events)\n• CUL-0001 (Cultural Events)\n• ACD-0001 (Academic Events)\n• CMP-0001 (Competition)\n• SPT-0001 (Sports & Fitness)\n\nVisible on your event cards and in participant reports.",
            "Participant": "Each event has a unique Event Code (e.g. TEC-0007) shown on your:\n• My Registrations cards\n• Upcoming Events cards\n• Registration Receipt PDF"
        },
        "suggestions": ["What is a registration ID?", "How do I download my receipt?"]
    },

    # ── PARTICIPANT TOPICS ────────────────────────────────────────────────────

    "discover_events": {
        "patterns": [
            "discover events", "find events", "browse events", "see events",
            "available events", "events near me", "upcoming events list",
            "how to find events", "events kahan dekhein", "search events",
            "event search", "filter events", "event categories"
        ],
        "responses": {
            "Guest":       "To discover events, sign up as a Participant on the homepage (/). Once logged in, you can browse all approved events.",
            "Admin":       "Participants discover events through the Discover Events section of their dashboard — only Approved events with available seats are shown.",
            "Organizer":   "Participants discover your events in the Discover Events section once Admin approves them. Make sure your event details are clear and attractive.",
            "Participant": "To discover events:\n1. Go to /participant_dashboard → 'Discover Events' section\n2. Browse all approved events with open registration\n3. Use the search bar to find by name, venue, or organizer\n4. Filter by category: Technical Events, Creative Events, Cultural Events, Academic Events, Competitions, Sports & Fitness\n\nEach card shows: Event name, date, venue, available seats, and registration deadline.\n\nOnly events that are Approved + Open + Have seats available are shown here."
        },
        "suggestions": ["How do I register for an event?", "What are the event categories?", "How do I cancel a registration?"]
    },

    "register_event": {
        "patterns": [
            "how to register", "register for event", "join event",
            "how to join event", "event register karna", "book event",
            "enroll for event", "sign up for event", "i want to register"
        ],
        "responses": {
            "Guest":       "To register for events, sign up as a Participant on the homepage (/). Once logged in, browse Discover Events and click Register.",
            "Admin":       "Participants register for events through the Discover Events section of their dashboard. Registration is only possible for Approved events with available seats.",
            "Organizer":   "Participants register for your events after Admin approves them. You can track registrations in your 'Participants' section.",
            "Participant": "To register for an event:\n1. Go to /participant_dashboard → 'Discover Events'\n2. Find an event you like\n3. Click 'Register' button\n\nYou can register only when:\n✅ Event is Approved\n✅ Registration is open\n✅ Seats are available\n✅ Event date has not passed\n✅ Registration deadline has not passed\n\nAfter registering:\n• Event appears in 'My Registrations'\n• Event appears in 'Upcoming Events'\n• You get a Registration ID (REG-XXXXX)"
        },
        "suggestions": ["How do I cancel my registration?", "Where can I see my registrations?", "How do I download my receipt?"]
    },

    "cancel_registration": {
        "patterns": [
            "cancel registration", "unregister", "withdraw registration",
            "cancel event", "leave event", "registration cancel karna",
            "how to cancel", "cancel booking", "remove registration"
        ],
        "responses": {
            "Guest":       "To cancel a registration, you need to be logged in as a Participant. Sign up or login on the homepage.",
            "Admin":       "Participants can cancel their own registrations before the registration closing date. You can view all registrations in the Registrations tab.",
            "Organizer":   "Participants can cancel their registrations before the registration closing date. Cancelled registrations free up a seat. Check your participant list to see current registrations.",
            "Participant": "To cancel your registration:\n1. Go to /participant_dashboard → 'My Registrations'\n2. Find the event\n3. Click 'Cancel Registration'\n4. Confirm the cancellation\n\nImportant rules:\n✅ Can cancel BEFORE the registration closing date\n❌ Cannot cancel AFTER the registration closing date\n❌ Cannot cancel Completed events\n\nAfter cancellation, the seat becomes available for others."
        },
        "suggestions": ["Where can I see my registrations?", "What is the registration closing date?"]
    },

    "my_registrations": {
        "patterns": [
            "my registrations", "my events", "registered events",
            "events i joined", "where to see my registration",
            "my bookings", "meri registrations", "show my events",
            "view my registrations", "check my registration"
        ],
        "responses": {
            "Guest":       "Sign up and login as a Participant to view your registrations.",
            "Admin":       "Individual Participants view their registrations in the 'My Registrations' section of their dashboard.",
            "Organizer":   "Only Participants have a 'My Registrations' section. As Organizer, you view registrations per event in the 'Participants' panel.",
            "Participant": "To view your registrations:\n1. Go to /participant_dashboard\n2. Click 'My Registrations' tab\n\nEach registration card shows:\n• Event name, venue, date, time\n• Event Code (e.g. TEC-0007)\n• Registration ID (e.g. REG-00001)\n• Registration deadline\n• Status (Registered / Reg. Closed / Completed)\n• Receipt download button\n• Cancel button (if deadline not passed)"
        },
        "suggestions": ["How do I download my receipt?", "How do I cancel a registration?", "Where are my upcoming events?"]
    },

    "registration_id": {
        "patterns": [
            "registration id", "what is registration id", "reg id",
            "my registration number", "reg number", "registration number",
            "registration id kya hai", "booking id"
        ],
        "responses": {
            "Guest":       "Registration IDs (REG-XXXXX) are assigned to Participants when they register for events.",
            "Admin":       "Registration IDs are auto-generated (format: REG-00001) when a Participant registers. Visible in the Registrations table.",
            "Organizer":   "Each registration gets a unique ID (REG-00001 format). You can see Registration IDs in your Participants panel and downloaded reports.",
            "Participant": "Your Registration ID (format: REG-00001) is:\n• Shown on each event card in 'My Registrations'\n• Shown on 'Completed Events' cards\n• Included in your Registration Receipt PDF\n\nEach registration has a unique ID — keep it for your records."
        },
        "suggestions": ["How do I download my receipt?", "What is an event code?"]
    },

    "receipt": {
        "patterns": [
            "receipt", "download receipt", "registration receipt",
            "proof of registration", "certificate", "ticket download",
            "receipt download karna", "how to get receipt"
        ],
        "responses": {
            "Guest":       "Registration receipts are available to Participants for their registered events after logging in.",
            "Admin":       "Participants can download their Registration Receipt PDF from the 'My Registrations' section of their dashboard.",
            "Organizer":   "Participants can download receipts for their registrations. You as Organizer can download participant reports from your dashboard.",
            "Participant": "To download your Registration Receipt:\n1. Go to /participant_dashboard → 'My Registrations'\n2. Find the event\n3. Click the 'Receipt' button (PDF icon)\n\nYour receipt PDF includes:\n• Registration ID (REG-XXXXX)\n• Event Code\n• Event name, category, date, time, venue\n• Organizer name\n• Your name and email\n• Registration date\n\nReceipts are available for all registrations including Upcoming and Completed events."
        },
        "suggestions": ["What is my Registration ID?", "How do I view my registrations?"]
    },

    "registration_rules": {
        "patterns": [
            "registration rules", "when can i register", "registration conditions",
            "why cant i register", "register nahi ho raha", "cant register",
            "cannot register", "registration not working", "unable to register"
        ],
        "responses": {
            "Guest":       "To register for events, you need a Participant account. Sign up on the homepage.",
            "Admin":       "Registration rules enforced by the system:\n✅ Event must be Approved\n✅ Registration must be open\n✅ Seats must be available\n✅ Event date must be in future\n✅ Registration deadline must not have passed\n✅ Cannot register for same event twice",
            "Organizer":   "Participants can register for your events when:\n✅ Event is Approved\n✅ Seats available\n✅ Registration is open\n✅ Event date is in future\n✅ Registration deadline not passed",
            "Participant": "You can register for an event ONLY when:\n✅ Event status is 'Approved'\n✅ Registration is still open\n✅ Available seats > 0\n✅ Today's date < Event date\n✅ Today's date ≤ Registration closing date\n\nYou CANNOT register when:\n❌ Event is Pending Approval\n❌ Event is Rejected\n❌ Event is Completed\n❌ Registration is Closed\n❌ Event is Full\n❌ You already registered for this event"
        },
        "suggestions": ["How do I find open events?", "How do I cancel a registration?"]
    },

    # ── ADMIN TOPICS ──────────────────────────────────────────────────────────

    "approve_event": {
        "patterns": [
            "approve event", "how to approve", "approve karna",
            "event approve kaise kare", "accept event", "review event"
        ],
        "responses": {
            "Guest":       "Only Admins can approve events. Admins review events submitted by Organizers.",
            "Admin":       "To approve an event:\n1. Go to /admin_dashboard → 'Pending Approval' tab\n2. Review the event details carefully\n3. Click the green 'Approve' button\n4. Confirm the action\n\nAfter approval:\n• Event status changes to 'Approved'\n• Event is immediately visible to all Participants\n• Organizer sees it in their 'My Events' section",
            "Organizer":   "Your events are approved by the Admin from their Pending Approval queue. Once approved, your event becomes visible to Participants immediately.",
            "Participant": "Events are approved by Admin before becoming visible to you. You only see approved events in the Discover Events section."
        },
        "suggestions": ["How do I reject an event?", "What happens after approval?"]
    },

    "reject_event": {
        "patterns": [
            "reject event", "how to reject", "reject karna",
            "decline event", "deny event", "event reject kaise kare",
            "rejection reason"
        ],
        "responses": {
            "Guest":       "Only Admins can reject events. A rejection reason is required.",
            "Admin":       "To reject an event:\n1. Go to /admin_dashboard → 'Pending Approval' tab\n2. Find the event to reject\n3. Click 'Reject' button\n4. A text area appears — enter the rejection reason (required)\n5. Click 'Submit rejection'\n\nAfter rejection:\n• Event status changes to 'Rejected'\n• Organizer sees rejection reason in 'Rejected Events' section\n• Organizer can edit and resubmit\n• Event remains invisible to Participants",
            "Organizer":   "If Admin rejects your event, you will see the reason in the 'Rejected Events' section. Fix the issues mentioned and use 'Edit & Resubmit' to send it back for review.",
            "Participant": "Rejected events are never shown to Participants."
        },
        "suggestions": ["How do I approve an event?", "What can Organizers do after rejection?"]
    },

    "manage_users": {
        "patterns": [
            "manage users", "delete user", "remove user", "user management",
            "how to delete user", "user delete karna", "view all users",
            "user list", "ban user"
        ],
        "responses": {
            "Guest":       "User management is only available to Admins.",
            "Admin":       "To manage users:\n1. Go to /admin_dashboard → 'All Users' tab\n2. View all registered users with their roles\n3. To delete a user: Click the trash icon next to their name\n4. Confirm deletion\n\nImportant:\n• Admin accounts cannot be deleted from here\n• Deleting a user also deletes their events and registrations\n• This action is permanent",
            "Organizer":   "User management is an Admin-only feature. If you need a user removed, contact the Admin.",
            "Participant": "User management is an Admin-only feature."
        },
        "suggestions": ["How do I delete an event?", "How do I view all registrations?"]
    },

    "admin_stats": {
        "patterns": [
            "platform stats", "statistics", "how many users", "how many events",
            "total registrations", "platform analytics", "system stats",
            "dashboard stats", "overview", "how many participants"
        ],
        "responses": {
            "Guest":       "Platform statistics are visible to Admin users only.",
            "Admin":       "Your Admin Dashboard shows platform-wide statistics:\n• Total Users\n• Total Organizers\n• Total Participants\n• Pending Events (needs your action)\n• Approved Events\n• Rejected Events\n• Completed Events\n• Total Registrations\n\nAll stats update automatically as users and events are added.",
            "Organizer":   "Your Organizer Dashboard shows your personal stats:\n• Total Events Created\n• Approved Events\n• Pending Events\n• Rejected Events\n• Completed Events\n• Total Registrations across your events",
            "Participant": "Your Participant Dashboard shows your personal stats:\n• Registered Events\n• Upcoming Events\n• Attended/Completed Events\n• Open Events to Discover"
        },
        "suggestions": ["How do I download a report?", "How do I navigate the dashboard?"]
    },

    "event_categories": {
        "patterns": [
            "event categories", "types of events", "what events are available",
            "event types", "categories", "what kind of events",
            "Technical Events", "Creative Events", "Cultural Events", "Academic Events", "competition", "Sports & Fitness"
        ],
        "responses": {
            "Guest":       "EventHub supports 6 event categories:\n1. Technical Events — Interactive learning sessions\n2. Creative Events — Professional networking events\n3. Cultural Events — Social celebrations\n4. Academic Events — Special ceremonies\n5. Competitions — Contests and hackathons\n6. Sports & Fitness — Live performances",
            "Admin":       "EventHub supports 6 categories: Technical Events, Creative Events, Cultural Events, Academic Events, Competitions, Sports & Fitness. Event codes are prefixed accordingly (TEC, CRE, CUL, ACD, CMP, SPT).",
            "Organizer":   "When creating an event, choose from 6 categories:\n1. Technical Events (Code: TEC-XXXX)\n2. Creative Events (Code: CRE-XXXX)\n3. Cultural Events (Code: CUL-XXXX)\n4. Academic Events (Code: ACD-XXXX)\n5. Competition (Code: CMP-XXXX)\n6. Sports & Fitness (Code: SPT-XXXX)",
            "Participant": "You can filter Discover Events by 6 categories:\n1. Technical Events\n2. Creative Events\n3. ParCultural Eventsties\n4. Academic Events\n5. Competitions\n6. Sports & Fitness\n\nUse the filter buttons in the Discover Events section."
        },
        "suggestions": ["How do I discover events?", "How do I create an event?"]
    },

    "contact_support": {
        "patterns": [
            "contact support", "help", "support", "contact admin",
            "report problem", "bug", "issue", "problem", "not working",
            "technical issue", "error", "help me"
        ],
        "responses": {
            "Guest":       "For support, visit the homepage (/) and scroll to the 'Contact' section. You can send a message through the contact form. Email: info@eventhub.com | support@eventhub.com",
            "Admin":       "As Admin, you have full platform access. For technical issues, check the server console for error logs. Contact: support@eventhub.com",
            "Organizer":   "For support, visit the homepage (/) and use the Contact form, or email support@eventhub.com. For event approval issues, your event's rejection reason will guide you.",
            "Participant": "For support, visit the homepage (/) and use the Contact form, or email support@eventhub.com. For registration issues, check if the event is still Approved and has available seats."
        },
        "suggestions": ["How do I navigate the dashboard?", "What is EventHub?"]
    }
}


# ══════════════════════════════════════════════════════════════════════════════
# INTENT MATCHING ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def normalize(text):
    """Lowercase, remove punctuation, strip extra spaces."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def match_intent(message):
    """
    Match user message against knowledge base patterns.
    Returns (intent_key, score) or (None, 0) if no match.
    Uses word-level matching for better accuracy.
    """
    norm_msg = normalize(message)
    msg_words = set(norm_msg.split())

    best_intent = None
    best_score  = 0

    for intent_key, data in KNOWLEDGE.items():
        for pattern in data["patterns"]:
            norm_pattern = normalize(pattern)
            pattern_words = set(norm_pattern.split())

            # Exact phrase match — highest priority
            if norm_pattern in norm_msg:
                score = len(pattern_words) * 10
                if score > best_score:
                    best_score  = score
                    best_intent = intent_key
                continue

            # Word overlap scoring
            overlap = msg_words & pattern_words
            if not overlap:
                continue

            # Score = overlap size × average word length (longer words = more specific)
            avg_word_len = sum(len(w) for w in overlap) / len(overlap)
            score = len(overlap) * avg_word_len

            if score > best_score:
                best_score  = score
                best_intent = intent_key

    return best_intent, best_score


def get_response(message, role):
    """
    Main engine:
    1. Match intent
    2. Get role-specific response
    3. Return reply + suggestions
    """
    if not message or not message.strip():
        return {
            "reply": "I didn't catch that. Could you please type your question?",
            "suggestions": ["What is EventHub?", "How do I login?", "How do I navigate the dashboard?"]
        }

    intent_key, score = match_intent(message)

    # Minimum confidence threshold
    if intent_key is None or score < 4:
        return _fallback_response(role)

    data = KNOWLEDGE[intent_key]
    responses = data["responses"]

    # Get role-specific reply, fallback to Guest if role not found
    reply = responses.get(role, responses.get("Guest", "I'm not sure about that. Please check your dashboard for more information."))
    suggestions = data.get("suggestions", [])

    return {
        "reply": reply,
        "suggestions": suggestions[:3]  # max 3 suggestions
    }


def _fallback_response(role):
    """Return a helpful fallback when no intent matches."""
    role_hints = {
        "Admin": [
            "How do I approve an event?",
            "How do I manage users?",
            "How do I download system report?"
        ],
        "Organizer": [
            "How do I create an event?",
            "Why is my event pending?",
            "How do I view my participants?"
        ],
        "Participant": [
            "How do I register for an event?",
            "How do I cancel my registration?",
            "How do I download my receipt?"
        ],
        "Guest": [
            "What is EventHub?",
            "How do I sign up?",
            "How do I login?"
        ]
    }

    suggestions = role_hints.get(role, role_hints["Guest"])

    reply = (
        "I'm not sure I understood that. I'm EventHub Assistant and I can help with:\n\n"
        "• Event registration and management\n"
        "• Event creation and approval workflow\n"
        "• Dashboard navigation\n"
        "• Reports and downloads\n"
        "• Account and password help\n\n"
        "Could you rephrase your question, or try one of the suggestions below?"
    )

    return {
        "reply": reply,
        "suggestions": suggestions
    }


# ══════════════════════════════════════════════════════════════════════════════
# ROUTE
# ══════════════════════════════════════════════════════════════════════════════

@chatbot_bp.route('/message', methods=['POST'])
def chat_message():
    """
    Accept: { "message": "...", "role": "..." }
    Return: { "reply": "...", "suggestions": [...] }
    Role is read from Flask session (server-side — cannot be spoofed).
    """
    data = request.get_json(silent=True) or {}
    message = data.get('message', '').strip()

    # Role from session (authoritative), fallback to Guest
    role = session.get('role', 'Guest')

    result = get_response(message, role)

    return jsonify(result), 200