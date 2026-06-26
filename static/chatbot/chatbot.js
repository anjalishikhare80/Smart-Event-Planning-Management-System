/**
 * chatbot.js — EventHub Rule-Based Assistant
 * ============================================
 * Self-contained IIFE. No external dependencies.
 * Injects its own HTML. Reads data-role and data-username from <body>.
 * Calls /chatbot/message — no API key needed.
 */

(function () {
    'use strict';

    // ── Config ────────────────────────────────────────────────────────────────
    const API_ENDPOINT = '/chatbot/message';

    // ── State ─────────────────────────────────────────────────────────────────
    let isOpen      = false;
    let isBusy      = false;
    let unreadCount = 0;

    // ── Role / user from <body> data attributes ───────────────────────────────
    const role     = document.body.dataset.role     || 'Guest';
    const username = document.body.dataset.username || '';

    // ── Quick actions per role ────────────────────────────────────────────────
    const QUICK_ACTIONS = {
        Admin: [
            { label: 'Approve Event',   text: 'How do I approve an event?' },
            { label: 'Reject Event',    text: 'How do I reject an event?' },
            { label: 'Manage Users',    text: 'How do I delete a user?' },
            { label: 'Download Report', text: 'How do I download system report?' },
            { label: 'Platform Stats',  text: 'What platform statistics can I see?' },
        ],
        Organizer: [
            { label: 'Create Event',      text: 'How do I create a new event?' },
            { label: 'Pending Approval',  text: 'Why is my event in pending approval?' },
            { label: 'View Participants', text: 'How do I view participants for my event?' },
            { label: 'Download Report',   text: 'How do I download the participant report?' },
            { label: 'Rejected Event',    text: 'How do I resubmit a rejected event?' },
        ],
        Participant: [
            { label: 'Register',         text: 'How do I register for an event?' },
            { label: 'My Registrations', text: 'Where can I see my registrations?' },
            { label: 'Cancel',           text: 'How do I cancel my registration?' },
            { label: 'Receipt',          text: 'How do I download my registration receipt?' },
            { label: 'Upcoming Events',  text: 'Where can I see my upcoming events?' },
        ],
        Guest: [
            { label: 'About EventHub', text: 'What is EventHub?' },
            { label: 'Sign Up',        text: 'How do I sign up?' },
            { label: 'Login',          text: 'How do I login?' },
            { label: 'Forgot Password',text: 'How do I reset my password?' },
        ],
    };

    // ── Welcome messages ──────────────────────────────────────────────────────
    const WELCOME = {
        Admin:
            `Hi${username ? ' ' + username : ''}! 👋 I'm EventHub Assistant.\n\n` +
            `As **Admin**, I can help you with:\n` +
            `• Approving and rejecting events\n` +
            `• Managing users\n` +
            `• Viewing platform statistics\n` +
            `• Downloading system reports\n\n` +
            `What would you like to know?`,

        Organizer:
            `Hi${username ? ' ' + username : ''}! 👋 I'm EventHub Assistant.\n\n` +
            `As an **Organizer**, I can help you with:\n` +
            `• Creating and managing events\n` +
            `• Understanding the approval workflow\n` +
            `• Viewing and downloading participant reports\n\n` +
            `What can I help you with?`,

        Participant:
            `Hi${username ? ' ' + username : ''}! 👋 I'm EventHub Assistant.\n\n` +
            `As a **Participant**, I can help you with:\n` +
            `• Discovering and registering for events\n` +
            `• Managing your registrations\n` +
            `• Downloading your receipt\n\n` +
            `What would you like to know?`,

        Guest:
            `Hi there! 👋 I'm EventHub Assistant.\n\n` +
            `I can help you with:\n` +
            `• Signing up and logging in\n` +
            `• Resetting your password\n` +
            `• Understanding how EventHub works\n\n` +
            `What would you like to know?`,
    };

    // ── Role pill CSS class ───────────────────────────────────────────────────
    const ROLE_CLASS = {
        Admin:       'eh-role-admin',
        Organizer:   'eh-role-organizer',
        Participant: 'eh-role-participant',
        Guest:       'eh-role-guest',
    };

    // ── Build HTML ────────────────────────────────────────────────────────────
    function buildHTML() {
        const roleClass    = ROLE_CLASS[role]     || 'eh-role-guest';
        const actions      = QUICK_ACTIONS[role]  || QUICK_ACTIONS.Guest;
        const quickBtns    = actions
            .map(a => `<button class="eh-quick-btn" data-text="${esc(a.text)}">${a.label}</button>`)
            .join('');

        return `
<div class="eh-chatbot-root" id="ehChatRoot"
     role="dialog" aria-label="EventHub Assistant" aria-hidden="true">

    <!-- Header -->
    <div class="eh-chat-header">
        <div class="eh-chat-avatar">
            <svg viewBox="0 0 24 24">
                <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9
                         2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6
                         V9h12v2zm0-3H6V6h12v2z"/>
            </svg>
        </div>
        <div class="eh-chat-header-info">
            <span class="eh-chat-header-title">EventHub Assistant</span>
            <span class="eh-chat-header-sub">
                <span class="eh-online-dot"></span> Online &nbsp;·&nbsp; No AI cost
            </span>
        </div>
        <span class="eh-role-pill ${roleClass}">${role}</span>
        <button class="eh-chat-clear" id="ehClearBtn" title="Clear chat">Clear</button>
    </div>

    <!-- Messages -->
    <div class="eh-chat-messages" id="ehMessages"
         role="log" aria-live="polite" aria-label="Chat messages"></div>

    <!-- Quick actions -->
    <div class="eh-quick-actions" id="ehQuickActions">
        ${quickBtns}
    </div>

    <!-- Input bar -->
    <div class="eh-chat-input-bar">
        <textarea class="eh-chat-input" id="ehInput"
            placeholder="Ask me anything about EventHub..."
            rows="1" maxlength="400"
            aria-label="Your message to EventHub Assistant"></textarea>
        <button class="eh-send-btn" id="ehSendBtn"
                title="Send" aria-label="Send message">
            <svg viewBox="0 0 24 24">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
            </svg>
        </button>
    </div>
</div>

<!-- Floating trigger -->
<button class="eh-chat-trigger" id="ehTrigger"
        aria-label="Open EventHub Assistant" aria-expanded="false">
    <svg class="icon-chat" viewBox="0 0 24 24">
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9
                 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6
                 V9h12v2zm0-3H6V6h12v2z"/>
    </svg>
    <svg class="icon-close" viewBox="0 0 24 24">
        <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41
                 10.59 12 5 17.59 6.41 19 12 13.41
                 17.59 19 19 17.59 13.41 12z"/>
    </svg>
    <span class="eh-chat-badge" id="ehBadge" aria-hidden="true"></span>
</button>`;
    }

    function esc(str) {
        return str.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    // ── DOM references ────────────────────────────────────────────────────────
    let root, trigger, messagesEl, inputEl, sendBtn, clearBtn, quickActionsEl, badgeEl;

    function getRefs() {
        root           = document.getElementById('ehChatRoot');
        trigger        = document.getElementById('ehTrigger');
        messagesEl     = document.getElementById('ehMessages');
        inputEl        = document.getElementById('ehInput');
        sendBtn        = document.getElementById('ehSendBtn');
        clearBtn       = document.getElementById('ehClearBtn');
        quickActionsEl = document.getElementById('ehQuickActions');
        badgeEl        = document.getElementById('ehBadge');
    }

    // ── Open / close ──────────────────────────────────────────────────────────
    function openChat() {
        isOpen = true;
        root.classList.add('open');
        root.setAttribute('aria-hidden', 'false');
        trigger.classList.add('open');
        trigger.setAttribute('aria-expanded', 'true');
        clearBadge();
        setTimeout(() => inputEl && inputEl.focus(), 280);
    }

    function closeChat() {
        isOpen = false;
        root.classList.remove('open');
        root.setAttribute('aria-hidden', 'true');
        trigger.classList.remove('open');
        trigger.setAttribute('aria-expanded', 'false');
    }

    function toggleChat() { isOpen ? closeChat() : openChat(); }

    function clearBadge() {
        unreadCount = 0;
        badgeEl.textContent = '';
        badgeEl.classList.remove('visible');
    }

    function bumpBadge() {
        if (!isOpen) {
            unreadCount++;
            badgeEl.textContent = unreadCount > 9 ? '9+' : unreadCount;
            badgeEl.classList.add('visible');
        }
    }

    // ── Rendering ─────────────────────────────────────────────────────────────
    function appendMessage(sender, content) {
        const wrap = document.createElement('div');
        wrap.className = `eh-msg ${sender}`;

        const av = document.createElement('div');
        av.className = `eh-msg-avatar${sender === 'bot' ? ' bot' : ''}`;
        av.textContent = sender === 'bot'
            ? 'AI'
            : (username ? username[0].toUpperCase() : 'U');

        const bubble = document.createElement('div');
        bubble.className = 'eh-msg-bubble';
        bubble.innerHTML = formatText(content);

        wrap.appendChild(av);
        wrap.appendChild(bubble);
        messagesEl.appendChild(wrap);
        scrollBottom();
    }

    function appendSuggestions(suggestions) {
        if (!suggestions || !suggestions.length) return;

        const wrap = document.createElement('div');
        wrap.className = 'eh-msg bot eh-suggestion-row';

        const av = document.createElement('div');
        av.className = 'eh-msg-avatar bot';
        av.textContent = 'AI';

        const pills = document.createElement('div');
        pills.className = 'eh-suggestion-pills';

        suggestions.forEach(text => {
            const btn = document.createElement('button');
            btn.className = 'eh-suggest-pill';
            btn.textContent = text;
            btn.addEventListener('click', () => sendMessage(text));
            pills.appendChild(btn);
        });

        wrap.appendChild(av);
        wrap.appendChild(pills);
        messagesEl.appendChild(wrap);
        scrollBottom();
    }

    function showTyping() {
        const wrap = document.createElement('div');
        wrap.className = 'eh-msg bot';
        wrap.id = 'ehTyping';

        const av = document.createElement('div');
        av.className = 'eh-msg-avatar bot';
        av.textContent = 'AI';

        const dots = document.createElement('div');
        dots.className = 'eh-typing';
        dots.innerHTML = '<span></span><span></span><span></span>';

        wrap.appendChild(av);
        wrap.appendChild(dots);
        messagesEl.appendChild(wrap);
        scrollBottom();
    }

    function removeTyping() {
        const el = document.getElementById('ehTyping');
        if (el) el.remove();
    }

    function scrollBottom() {
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    // Convert plain text with simple markdown to HTML
    function formatText(text) {
        return text
            // Bold **text**
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            // Navigation paths /path → link
            .replace(/(\/[a-z_#]+)/g, m => `<a href="${m}" target="_top">${m}</a>`)
            // Lines starting with bullet markers
            .replace(/(?:^|\n)[✅❌•\-]\s(.+)/g, (_, p) => `\n<li>${p}</li>`)
            .replace(/(<li>[\s\S]*?<\/li>)+/g, m => `<ul>${m}</ul>`)
            // Numbered list  "1. ..."
            .replace(/(?:^|\n)\d+\.\s(.+)/g, (_, p) => `\n<li>${p}</li>`)
            // Newlines → <br>
            .replace(/\n(?!<)/g, '<br>');
    }

    // ── Send ──────────────────────────────────────────────────────────────────
    async function sendMessage(text) {
        text = (text || '').trim();
        if (!text || isBusy) return;

        // Hide quick-action bar once conversation starts
        if (quickActionsEl.style.display !== 'none') {
            quickActionsEl.style.display = 'none';
        }

        appendMessage('user', text);
        inputEl.value = '';
        autoResize();
        isBusy = true;
        sendBtn.disabled = true;
        showTyping();

        try {
            const res = await fetch(API_ENDPOINT, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ message: text })
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const data = await res.json();
            const reply       = data.reply       || "I couldn't process that. Please try again.";
            const suggestions = data.suggestions || [];

            removeTyping();
            appendMessage('bot', reply);

            if (suggestions.length) {
                appendSuggestions(suggestions);
            }

            bumpBadge();

        } catch (err) {
            removeTyping();
            appendMessage('bot',
                "I'm having trouble responding right now. Please try again in a moment.");
        } finally {
            isBusy = false;
            sendBtn.disabled = false;
            inputEl.focus();
        }
    }

    // ── Auto-resize textarea ──────────────────────────────────────────────────
    function autoResize() {
        if (!inputEl) return;
        inputEl.style.height = 'auto';
        inputEl.style.height = Math.min(inputEl.scrollHeight, 100) + 'px';
    }

    // ── Clear ─────────────────────────────────────────────────────────────────
    function clearChat() {
        messagesEl.innerHTML = '';
        quickActionsEl.style.display = '';
        showWelcome();
    }

    // ── Welcome ───────────────────────────────────────────────────────────────
    function showWelcome() {
        const msg = WELCOME[role] || WELCOME.Guest;
        setTimeout(() => {
            appendMessage('bot', msg);
        }, 500);
    }

    // ── Events ────────────────────────────────────────────────────────────────
    function bindEvents() {
        trigger.addEventListener('click', toggleChat);

        sendBtn.addEventListener('click', () => sendMessage(inputEl.value));

        inputEl.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage(inputEl.value);
            }
        });

        inputEl.addEventListener('input', autoResize);

        clearBtn.addEventListener('click', clearChat);

        // Quick-action buttons
        quickActionsEl.addEventListener('click', e => {
            const btn = e.target.closest('.eh-quick-btn');
            if (btn) sendMessage(btn.dataset.text);
        });

        // Close on outside click
        document.addEventListener('click', e => {
            if (isOpen && !root.contains(e.target) && !trigger.contains(e.target)) {
                closeChat();
            }
        });

        // Escape closes
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape' && isOpen) closeChat();
        });
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        // Link stylesheet dynamically if not already present
        if (!document.querySelector('link[href*="chatbot.css"]')) {
            const link = document.createElement('link');
            link.rel  = 'stylesheet';
            link.href = '/static/chatbot/chatbot.css';
            document.head.appendChild(link);
        }

        // Inject chatbot HTML
        const div = document.createElement('div');
        div.innerHTML = buildHTML();
        document.body.appendChild(div);

        getRefs();
        bindEvents();
        showWelcome();

        // Nudge badge after 4 s if user hasn't opened yet
        setTimeout(() => {
            if (!isOpen) {
                badgeEl.textContent = '1';
                badgeEl.classList.add('visible');
            }
        }, 4000);
    }

    // Boot after DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

}());