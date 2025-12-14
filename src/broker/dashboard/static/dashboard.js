// Kafka Flow Dashboard - Client-side JavaScript

let ws;
let counts = { truck: 0, lp: 0, hz: 0, decision: 0 };
let allMessages = [];      // All events
let singleFlowMessages = []; // Current truck flow only
let currentTab = 'single';
const MAX_MESSAGES = 100;

function connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onopen = () => {
        document.getElementById('statusDot').classList.add('connected');
        document.getElementById('statusText').textContent = 'Connected';
    };

    ws.onclose = () => {
        document.getElementById('statusDot').classList.remove('connected');
        document.getElementById('statusText').textContent = 'Disconnected - Reconnecting...';
        setTimeout(connect, 3000);
    };

    ws.onerror = () => {
        document.getElementById('statusText').textContent = 'Connection Error';
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'kafka_message') {
            handleMessage(data);
        }
    };
}

function handleMessage(msg) {
    const topic = msg.topic;

    // Update counts
    if (topic.includes('truck-detected')) {
        counts.truck++;
        document.getElementById('count-truck').textContent = counts.truck;
        highlightStep('step-truck-detected');

        // Reset single flow when new truck is detected
        singleFlowMessages = [];
    } else if (topic.includes('lp-results')) {
        counts.lp++;
        document.getElementById('count-lp').textContent = counts.lp;
        highlightStep('step-lp-results');
    } else if (topic.includes('hz-results')) {
        counts.hz++;
        document.getElementById('count-hz').textContent = counts.hz;
        highlightStep('step-hz-results');
    } else if (topic.includes('decision')) {
        counts.decision++;
        document.getElementById('count-decision').textContent = counts.decision;
        highlightStep('step-decision');
    }

    // Add to both lists (newest at end for bottom display)
    allMessages.push(msg);
    singleFlowMessages.push(msg);

    // Limit all messages
    if (allMessages.length > MAX_MESSAGES) {
        allMessages = allMessages.slice(-MAX_MESSAGES);
    }

    renderMessages();
    scrollToBottom();
}

function highlightStep(stepId) {
    const step = document.getElementById(stepId);
    step.classList.add('active');
    setTimeout(() => step.classList.remove('active'), 1000);
}

function switchTab(tab) {
    currentTab = tab;

    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');

    renderMessages();
    scrollToBottom();
}

function scrollToBottom() {
    const list = document.getElementById('messagesList');
    list.scrollTop = list.scrollHeight;
}

function formatConfidence(conf) {
    if (conf === undefined || conf === null) return 'N/A';
    return (conf * 100).toFixed(1) + '%';
}

function formatTime(timestamp) {
    return new Date(timestamp).toLocaleTimeString();
}

function renderCardContent(msg) {
    const topic = msg.topic;
    const data = msg.data;

    // Truck Detected
    if (topic.includes('truck-detected')) {
        return `
            <div class="card-field">
                <span class="field-label">⏱️ Timestamp</span>
                <span class="field-value">${data.timestamp || formatTime(msg.timestamp)}</span>
            </div>
            <div class="card-field">
                <span class="field-label">📊 Confidence</span>
                <span class="field-value confidence">${formatConfidence(data.confidence)}</span>
            </div>
        `;
    }

    // License Plate
    if (topic.includes('lp-results')) {
        return `
            <div class="card-field">
                <span class="field-label">⏱️ Timestamp</span>
                <span class="field-value">${data.timestamp || formatTime(msg.timestamp)}</span>
            </div>
            <div class="card-field">
                <span class="field-label">🔢 License Plate</span>
                <span class="field-value plate">${data.licensePlate || 'N/A'}</span>
            </div>
            <div class="card-field">
                <span class="field-label">📊 Confidence</span>
                <span class="field-value confidence">${formatConfidence(data.confidence)}</span>
            </div>
            ${data.cropUrl ? `<div class="card-field"><span class="field-label">🖼️ Crop</span><a href="${data.cropUrl}" target="_blank" class="field-value link">View Image</a></div>` : ''}
        `;
    }

    // Hazard Plate
    if (topic.includes('hz-results')) {
        return `
            <div class="card-field">
                <span class="field-label">⏱️ Timestamp</span>
                <span class="field-value">${data.timestamp || formatTime(msg.timestamp)}</span>
            </div>
            <div class="card-field">
                <span class="field-label">☢️ UN Number</span>
                <span class="field-value hazard">${data.un || 'N/A'}</span>
            </div>
            <div class="card-field">
                <span class="field-label">⚠️ Kemler Code</span>
                <span class="field-value hazard">${data.kemler || 'N/A'}</span>
            </div>
            <div class="card-field">
                <span class="field-label">📊 Confidence</span>
                <span class="field-value confidence">${formatConfidence(data.confidence)}</span>
            </div>
        `;
    }

    // Decision
    if (topic.includes('decision')) {
        const decisionClass = data.decision === 'APPROVED' ? 'approved' : 'rejected';
        return `
            <div class="card-field">
                <span class="field-label">⏱️ Timestamp</span>
                <span class="field-value">${data.timestamp || formatTime(msg.timestamp)}</span>
            </div>
            <div class="card-field">
                <span class="field-label">🔢 License Plate</span>
                <span class="field-value plate">${data.licensePlate || 'N/A'}</span>
            </div>
            <div class="card-field">
                <span class="field-label">✅ Decision</span>
                <span class="field-value decision ${decisionClass}">${data.decision || 'PENDING'}</span>
            </div>
            ${data.UN ? `<div class="card-field"><span class="field-label">☢️ UN</span><span class="field-value">${data.UN}</span></div>` : ''}
            ${data.kemler ? `<div class="card-field"><span class="field-label">⚠️ Kemler</span><span class="field-value">${data.kemler}</span></div>` : ''}
        `;
    }

    // Fallback
    return `<div class="card-field"><span class="field-value">${JSON.stringify(data, null, 2)}</span></div>`;
}

function renderMessages() {
    const list = document.getElementById('messagesList');
    const messages = currentTab === 'single' ? singleFlowMessages : allMessages;

    if (messages.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" fill="currentColor">
                    <path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>
                </svg>
                <p>${currentTab === 'single' ? 'Waiting for new truck detection...' : 'Waiting for Kafka messages...'}</p>
                <p style="font-size: 12px; margin-top: 10px;">Messages will appear here in real-time</p>
            </div>
        `;
        return;
    }

    // Render messages (oldest first, newest at bottom)
    list.innerHTML = messages.map(msg => `
        <div class="message-card" style="border-color: ${msg.topicColor}">
            <div class="message-header">
                <span class="message-type" style="color: ${msg.topicColor}">${msg.topicName}</span>
                <span class="message-time">${formatTime(msg.timestamp)}</span>
            </div>
            <div class="message-truck">🚛 Truck ID: ${msg.truckId}</div>
            <div class="card-content">
                ${renderCardContent(msg)}
            </div>
        </div>
    `).join('');
}

function clearMessages() {
    allMessages = [];
    singleFlowMessages = [];
    counts = { truck: 0, lp: 0, hz: 0, decision: 0 };
    document.getElementById('count-truck').textContent = '0';
    document.getElementById('count-lp').textContent = '0';
    document.getElementById('count-hz').textContent = '0';
    document.getElementById('count-decision').textContent = '0';
    renderMessages();
}

// Initialize
connect();
