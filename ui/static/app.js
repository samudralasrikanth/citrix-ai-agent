/**
 * Citrix AI Vision Agent — Enterprise Dashboard JS
 * Handles SSE streaming, file management, step progress, and modals.
 */

// ── State ───────────────────────────────────────────────────────────────────
const state = {
    playbooks: [],
    currentId: null,
    currentFile: 'suite_config.json',
    currentWindow: null,
    isRunning: false,
    expandedTests: new Set(),
    eventSource: null,
    stepTotal: 0,
    stepDone: 0,
};

// ── DOM Refs ─────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const playbookList = $('playbook-list');
const terminal = $('terminal-output');
const statusPill = $('agent-status');
const titleHeader = $('current-playbook-name');
const progressFill = $('progress-fill');
const progressLabel = $('progress-label');
const stepCounter = $('step-counter');
const editorFilename = $('editor-filename');
const fileBadge = $('file-badge');
const editorArea = $('editor-area');

// ── Init ─────────────────────────────────────────────────────────────────────
async function init() {
    setupEventListeners();
    await fetchPlaybooks();
}

// ── Playbook List ─────────────────────────────────────────────────────────────
async function fetchPlaybooks() {
    try {
        const res = await fetch('/api/playbooks');
        state.playbooks = await res.json();
        renderPlaybookList();
    } catch (e) {
        logEntry('error', 'Failed to load playbooks from backend.');
    }
}

function renderPlaybookList() {
    playbookList.innerHTML = '';

    if (!state.playbooks.length) {
        playbookList.innerHTML = `
            <li class="nav-placeholder">
                <div class="placeholder-icon">📂</div>
                <span>No test suites yet</span>
            </li>`;
        return;
    }

    state.playbooks.forEach(pb => {
        const container = document.createElement('div');
        container.className = 'test-container';

        const row = document.createElement('li');
        row.className = 'nav-item';
        if (state.currentId === pb.id) row.classList.add('active');
        row.dataset.id = pb.id;

        row.innerHTML = `
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <span>${pb.name || pb.id}</span>
            <svg class="chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="9 18 15 12 9 6"/>
            </svg>`;

        const fileUl = document.createElement('ul');
        fileUl.className = 'file-list';
        if (!state.expandedTests.has(pb.id)) fileUl.style.display = 'none';
        else row.classList.add('open');

        row.addEventListener('click', async () => {
            const isOpen = state.expandedTests.has(pb.id);
            if (isOpen) {
                state.expandedTests.delete(pb.id);
                fileUl.style.display = 'none';
                row.classList.remove('open');
            } else {
                state.expandedTests.add(pb.id);
                fileUl.style.display = 'block';
                row.classList.add('open');
                await loadFileList(pb.id, fileUl);
            }
            loadPlaybook(pb.id);
            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            row.classList.add('active');
        });

        container.appendChild(row);
        container.appendChild(fileUl);
        playbookList.appendChild(container);
    });
}

async function loadFileList(testId, container) {
    container.innerHTML = '<li class="nav-item" style="opacity:.5;font-size:11px;padding:4px 12px;cursor:default">Loading…</li>';
    const res = await fetch(`/api/tests/${testId}/files`);
    const files = await res.json();
    renderFileItems(testId, files, container);
}

function renderFileItems(testId, files, container) {
    container.innerHTML = '';
    files.forEach(fileObj => {
        const file = fileObj.path;
        const li = document.createElement('li');
        li.className = 'file-item';
        li.dataset.test = testId;
        li.dataset.file = file;
        const isActive = (state.currentId === testId && state.currentFile === file);
        if (isActive) li.classList.add('active');

        const icon = file.endsWith('.png') ? '🖼' : file.endsWith('.json') ? '⚙' : '📄';
        li.innerHTML = `<span>${icon}</span><span>${file}</span>`;
        li.addEventListener('click', e => { e.stopPropagation(); loadPlaybook(testId, file); });
        container.appendChild(li);
    });
}

// ── Load Playbook / File ──────────────────────────────────────────────────────
async function loadPlaybook(id, filename = 'suite_config.json') {
    state.currentId = id;
    state.currentFile = filename;
    titleHeader.textContent = `${id} / ${filename}`;

    // Update filename display & badge
    editorFilename.textContent = filename;
    if (filename.endsWith('.yaml')) { fileBadge.textContent = 'YAML'; fileBadge.className = 'file-badge yaml-badge'; }
    else if (filename.endsWith('.json')) { fileBadge.textContent = 'JSON'; fileBadge.className = 'file-badge json-badge'; }
    else if (filename.endsWith('.png')) { fileBadge.textContent = 'IMG'; fileBadge.className = 'file-badge img-badge'; }
    else { fileBadge.textContent = 'FILE'; fileBadge.className = 'file-badge'; }

    if (filename.endsWith('.png')) {
        editorArea.innerHTML = `
            <div style="flex:1;display:flex;align-items:center;justify-content:center;
                        height:100%;background:var(--bg-base);overflow:hidden;">
                <img src="/api/tests/${id}/image/${filename}"
                     style="max-width:92%;max-height:92%;border-radius:6px;
                            box-shadow:0 0 40px rgba(0,224,90,0.12);border:1px solid var(--border);">
            </div>`;
    } else {
        if (!document.getElementById('playbook-editor')) {
            editorArea.innerHTML = `<textarea id="playbook-editor" spellcheck="false" placeholder="# Select a file to edit…"></textarea>`;
        }
        const fileRes = await fetch(`/api/playbooks/${id}?file=${filename}`);
        const data = await fileRes.json();
        document.getElementById('playbook-editor').value = data.content || '';
    }

    // Sync active states
    document.querySelectorAll('.file-item').forEach(e => e.classList.remove('active'));
    const activeEl = document.querySelector(`[data-test="${id}"][data-file="${filename}"]`);
    if (activeEl) activeEl.classList.add('active');

    // Show Scan UI button if we have an active suite
    $('btn-scan-ui').classList.toggle('hidden', !id);
}

async function scanSuiteUI() {
    if (!state.currentId) return;
    const btn = $('btn-scan-ui');
    const oldHtml = btn.innerHTML;

    // If an image is open, scan the image instead of the window
    const isImage = state.currentFile && state.currentFile.endsWith('.png');
    const payload = isImage ? { file: state.currentFile } : {};

    btn.disabled = true;
    btn.innerHTML = '<div class="spinner" style="width:12px;height:12px;border-width:2px;margin-right:8px"></div> Scanning…';

    try {
        logEntry('info', `Starting UI scan for ${isImage ? 'file: ' + state.currentFile : 'target window'}…`);
        const res = await fetch(`/api/suites/${state.currentId}/scan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await res.json();

        if (res.ok && result.success) {
            logEntry('success', result.message);
            // Refresh file list to show memory/ui_map.json etc
            const container = document.querySelector(`.test-container .nav-item[data-id="${state.currentId}"]`).nextElementSibling;
            await loadFileList(state.currentId, container);
        } else {
            logEntry('error', `Scan failed: ${result.error || 'Server error'}`);
            alert('Scan failed: ' + (result.error || 'Check logs'));
        }
    } catch (e) {
        logEntry('error', `Network error during scan: ${e.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = oldHtml;
    }
}


// ── Save ──────────────────────────────────────────────────────────────────────
async function savePlaybook() {
    const editor = document.getElementById('playbook-editor');
    if (!state.currentId || !editor) return;
    await fetch(`/api/playbooks/${state.currentId}?file=${state.currentFile}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editor.value }),
    });
    logEntry('success', `Saved: ${state.currentFile}`);
}

// ── Run / Stop ────────────────────────────────────────────────────────────────
async function runPlaybook(dryRun = false) {
    if (!state.currentId || state.isRunning) return;
    state.isRunning = true;
    state.stepDone = 0;
    state.stepTotal = 0;

    // Toggle button visibility
    $('btn-run').classList.add('hidden');
    $('btn-dry-run').classList.add('hidden');
    $('btn-stop').classList.remove('hidden');

    setStatus(dryRun ? 'DRY RUN' : 'RUNNING', 'success');
    setProgress(0, dryRun ? 'Dry Run…' : 'Starting…');
    terminal.innerHTML = '';

    const runFile = state.currentFile || 'tests/main_flow.yaml';
    state.eventSource = new EventSource(`/api/run/${state.currentId}?dry_run=${dryRun}&file=${runFile}`);

    state.eventSource.onmessage = evt => {
        if (evt.data === '[DONE]') { finishRun(true); return; }
        try {
            const d = JSON.parse(evt.data);
            processLog(d);
        } catch {
            logEntry('raw', evt.data);
        }
    };

    state.eventSource.onerror = () => {
        finishRun(false);
        logEntry('error', 'Connection to backend lost. Verify the server is running.');
    };
}

function stopPlaybook() {
    if (state.eventSource) state.eventSource.close();
    fetch(`/api/run/${state.currentId}/stop`, { method: 'POST' }).catch(() => { });
    finishRun(false);
    logEntry('warning', 'Execution stopped by user.');
}

function finishRun(success) {
    state.isRunning = false;
    if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }

    $('btn-run').classList.remove('hidden');
    $('btn-dry-run').classList.remove('hidden');
    $('btn-stop').classList.add('hidden');

    setStatus('IDLE', 'idle');
    setProgress(success ? 100 : progressFill.style.width.replace('%', ''), success ? 'Done' : 'Stopped');
}

// ── Log processing ────────────────────────────────────────────────────────────
function processLog(d) {
    switch (d.status) {
        case 'heartbeat': return; // silent keepalive
        case 'step_start':
            state.stepTotal = d.total ?? state.stepTotal;
            state.stepDone = d.current ?? (state.stepDone + 1);
            const pct = state.stepTotal ? Math.round((state.stepDone / state.stepTotal) * 100) : 0;
            setProgress(pct, `Step ${state.stepDone}/${state.stepTotal}`);
            break;
        case 'step_success':
            break;
        case 'finish':
            setProgress(100, 'Complete');
            break;
    }
    logEntry(d.status, d.message, d.summary);
}

function logEntry(status, message, summary) {
    const wrap = document.createElement('div');
    wrap.className = 'log-entry';

    let color = 'var(--text-primary)';
    let prefix = '➤';
    switch (status) {
        case 'init': color = '#79c0ff'; prefix = '⚙'; break;
        case 'error': color = '#ff7b72'; prefix = '✗'; break;
        case 'warning': color = '#ffa657'; prefix = '⚠'; break;
        case 'step_start': color = '#d1d5db'; prefix = '⦿'; break;
        case 'step_success': color = 'var(--accent)'; prefix = '✓'; break;
        case 'finish': color = '#d2a8ff'; prefix = '🏁'; break;
        case 'success': color = 'var(--accent)'; prefix = '✓'; break;
        case 'raw': color = 'var(--text-muted)'; prefix = ''; break;
    }

    const now = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    wrap.innerHTML = `
        <span class="log-time">${now}</span>
        <span class="log-msg" style="color:${color}">${prefix ? prefix + ' ' : ''}${escHtml(message || '')}</span>`;

    if (summary) {
        const pre = document.createElement('pre');
        pre.textContent = JSON.stringify(summary, null, 2);
        wrap.querySelector('.log-msg').appendChild(pre);
    }

    terminal.appendChild(wrap);
    terminal.scrollTop = terminal.scrollHeight;

    // Update step counter
    const entries = terminal.querySelectorAll('.log-entry').length;
    stepCounter.textContent = `${entries} events`;
}

function escHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Progress bar ──────────────────────────────────────────────────────────────
function setProgress(pct, label) {
    progressFill.style.width = `${Math.min(100, Math.max(0, pct))}%`;
    progressLabel.textContent = label;
}

function setStatus(text, type) {
    statusPill.textContent = text;
    statusPill.className = `status-pill ${type}`;
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function openModal() {
    $('modal-setup').classList.add('active');
    $('new-region-name').value = '';
    state.currentWindow = null;
    fetchWindows();
}

function closeModal() {
    $('modal-setup').classList.remove('active');
}

// ── Record Modal — three states: idle → active → done ─────────────────────────
let _recordTestId = null;
let _recordPollTimer = null;
let _recordStepCount = 0;

function openRecordModal() {
    _recordTestId = null;
    _recordStepCount = 0;

    // If a test is selected, suggest it for appending
    if (state.currentId) {
        $('record-test-name').value = state.currentId;
        _recordTestId = state.currentId;
    } else {
        $('record-test-name').value = '';
    }

    _setRecordState('idle');
    $('modal-record').classList.add('active');
    setTimeout(() => $('record-test-name').focus(), 80);
}

function closeRecordModal() {
    $('modal-record').classList.remove('active');
    _stopRecordPoll();
}

function _setRecordState(s) {
    $('record-actions-idle').style.display = s === 'idle' ? 'flex' : 'none';
    $('record-actions-active').style.display = s === 'active' ? 'flex' : 'none';
    $('record-actions-done').style.display = s === 'done' ? 'flex' : 'none';
    $('record-info-box').style.display = s === 'active' ? 'flex' : 'none';
    $('record-done-box').style.display = s === 'done' ? 'flex' : 'none';
    if (s === 'idle') {
        $('btn-start-record').disabled = false;
        $('btn-start-record').innerHTML = '<span class="rec-dot" style="width:8px;height:8px"></span> Start Recording';
    }
}

async function startRecording() {
    const raw = $('record-test-name').value.trim();
    const name = raw.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
    if (!name) { $('record-test-name').focus(); return; }

    _recordTestId = name;
    _recordStepCount = 0;
    $('btn-start-record').disabled = true;
    $('btn-start-record').textContent = 'Starting…';

    try {
        const res = await fetch(`/api/record/${name}/start`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
        });
        const data = await res.json();
        if (data.success) {
            $('record-step-count').textContent = '0 steps recorded';
            _setRecordState('active');
            _startRecordPoll(name);
        } else {
            _setRecordState('idle');
            logEntry('error', `Recorder start failed: ${data.message || 'unknown error'}`);
        }
    } catch (e) {
        _setRecordState('idle');
        logEntry('error', `Recorder launch failed: ${e.message}`);
    }
}

async function captureRecordStep() {
    if (!_recordTestId) return;
    const btn = $('btn-capture-step');
    btn.disabled = true;

    // Countdown logic to allow user to move mouse to Citrix window
    let countdown = 2;
    const originalHtml = btn.innerHTML;

    const timer = setInterval(() => {
        if (countdown > 0) {
            btn.textContent = `Capturing in ${countdown}…`;
            countdown--;
        } else {
            clearInterval(timer);
            _performCapture(btn, originalHtml);
        }
    }, 700);
}

async function _performCapture(btn, originalHtml) {
    btn.textContent = 'Scanning…';
    try {
        const res = await fetch(`/api/record/${_recordTestId}/capture`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            _recordStepCount++;
            $('record-step-count').textContent =
                `${_recordStepCount} step${_recordStepCount !== 1 ? 's' : ''} recorded`;
            logEntry('success', `Captured step #${_recordStepCount} for ${_recordTestId}`);
        }
    } catch (_) { }

    setTimeout(() => {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
    }, 1000);
}

async function stopRecording() {
    if (!_recordTestId) return;
    _stopRecordPoll();
    const btn = $('btn-stop-record');
    btn.disabled = true;
    btn.textContent = 'Stopping…';
    try {
        await fetch(`/api/record/${_recordTestId}/stop`, { method: 'POST' });
    } catch (_) { }
    _onRecordingFinished();
}

function _onRecordingFinished() {
    _stopRecordPoll();
    const n = _recordTestId || 'test';
    $('record-done-msg').textContent =
        `Saved to tests/${n}/playbook.yaml — ${_recordStepCount} step${_recordStepCount !== 1 ? 's' : ''} recorded. You can run it from the sidebar.`;
    _setRecordState('done');
    fetchPlaybooks().then(() => {
        if (_recordTestId) {
            state.expandedTests.add(_recordTestId);
            renderPlaybookList();
            // If the recorded test is the one currently open, reload its content
            if (state.currentId === _recordTestId) {
                loadPlaybook(_recordTestId, 'playbook.yaml');
            }
        }
    });
}

function _startRecordPoll(testId) {
    _stopRecordPoll();
    _recordPollTimer = setInterval(async () => {
        try {
            const res = await fetch(`/api/record/${testId}/status`);
            const data = await res.json();
            if (!data.running && $('modal-record').classList.contains('active')) {
                _onRecordingFinished();
            }
        } catch (_) { }
    }, 3000);
}

function _stopRecordPoll() {
    if (_recordPollTimer) { clearInterval(_recordPollTimer); _recordPollTimer = null; }
}


async function fetchWindows() {
    const list = $('modal-window-list');
    list.innerHTML = '<li class="window-loading"><div class="spinner"></div> Detecting windows…</li>';
    try {
        const res = await fetch('/api/windows');
        const wins = await res.json();
        renderWindowList(wins);
    } catch {
        list.innerHTML = '<li class="window-loading" style="color:var(--danger)">⚠ Failed to load windows</li>';
    }
}

function renderWindowList(windows) {
    const list = $('modal-window-list');
    list.innerHTML = '';
    windows.forEach(w => {
        const li = document.createElement('li');
        li.className = 'window-item';
        li.innerHTML = `<strong>${w.name}</strong><p>${w.width}×${w.height} @ (${w.left}, ${w.top})</p>`;
        li.addEventListener('click', () => {
            document.querySelectorAll('.window-item').forEach(el => el.classList.remove('selected'));
            li.classList.add('selected');
            state.currentWindow = w;
        });
        list.appendChild(li);
    });
}

async function saveRegion() {
    const btn = $('btn-save-region');
    const name = $('new-region-name').value.trim();
    const platform = document.querySelector('input[name="platform"]:checked').value;
    const hasDb = $('cap-db').checked;
    const hasApi = $('cap-api').checked;

    if (!name) return alert('Enter a suite name.');
    if (platform !== 'web' && !state.currentWindow) return alert('Select a target window.');

    btn.disabled = true;
    btn.innerHTML = '<div class="spinner" style="width:14px;height:14px;border-width:2px;margin-right:8px"></div> Creating…';

    const payload = {
        name,
        platform,
        capabilities: { db: hasDb, api: hasApi },
        window: state.currentWindow
    };

    if (platform === 'web') {
        payload.web_config = {
            url: $('web-url').value,
            browser: $('web-browser').value
        };
    }

    try {
        const res = await fetch('/api/regions/setup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        const result = await res.json();

        if (res.ok && result.success) {
            closeModal();
            state.expandedTests.add(result.id);
            await fetchPlaybooks();
            await loadPlaybook(result.id, 'tests/main_flow.yaml');
            logEntry('success', `Test Suite '${result.id}' created.`);
        } else {
            console.error('Create Suite Failed:', result);
            alert('Failed to create suite: ' + (result.error || 'Server error'));
            logEntry('error', 'Failed to create test suite: ' + (result.error || 'Check console'));
        }
    } catch (e) {
        console.error('Fetch Error:', e);
        alert('Network error while creating suite.');
    } finally {
        $('btn-save-region').disabled = false;
        $('btn-save-region').innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg> Create Suite';
    }
}

// ── Event listeners ───────────────────────────────────────────────────────────
function setupEventListeners() {
    $('btn-save').addEventListener('click', savePlaybook);
    $('btn-run').addEventListener('click', () => runPlaybook(false));
    $('btn-dry-run').addEventListener('click', () => runPlaybook(true));
    $('btn-stop').addEventListener('click', stopPlaybook);
    $('btn-new-test').addEventListener('click', openModal);
    $('btn-save-region').addEventListener('click', saveRegion);
    $('btn-scan-ui').addEventListener('click', scanSuiteUI);

    // Platform toggle logic
    document.querySelectorAll('input[name="platform"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            const isWeb = e.target.value === 'web';
            $('web-config-section').classList.toggle('hidden', !isWeb);
            $('window-selection-group').classList.toggle('hidden', isWeb);
        });
    });

    // Cleanup dead record listeners (if any)
    const runSafe = (id, fn) => {
        const el = $(id);
        if (el) el.addEventListener('click', fn);
    };

    runSafe('btn-open-record', openRecordModal);
    runSafe('btn-start-record', startRecording);
    runSafe('btn-cancel-record', closeRecordModal);
    runSafe('btn-close-record', closeRecordModal);
    runSafe('btn-stop-record', stopRecording);
    runSafe('btn-capture-step', captureRecordStep);
    runSafe('btn-record-done', closeRecordModal);

    $('btn-clear-terminal').addEventListener('click', () => {
        terminal.innerHTML = '';
        stepCounter.textContent = '';
        setProgress(0, 'Idle');
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', e => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); savePlaybook(); }
        if (e.key === 'Escape') { closeModal(); closeRecordModal(); }
    });

    // Close modals on backdrop click
    $('modal-setup').addEventListener('click', e => { if (e.target === $('modal-setup')) closeModal(); });
    $('modal-record').addEventListener('click', e => { if (e.target === $('modal-record')) closeRecordModal(); });
}



// ── Bootstrap ─────────────────────────────────────────────────────────────────
init();
