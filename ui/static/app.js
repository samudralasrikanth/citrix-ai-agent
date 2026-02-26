const state = {
    playbooks: [],
    regions: [],
    currentPlaybook: null,
    currentWindow: null,
    isRunning: false
};

// --- DOM Elements ---
const playbookList = document.getElementById('playbook-list');
const regionList = document.getElementById('region-list');
const modalWindowList = document.getElementById('modal-window-list');
const modalSetup = document.getElementById('modal-setup');
const editor = document.getElementById('playbook-editor');
const terminal = document.getElementById('terminal-output');
const statusPill = document.getElementById('agent-status');
const titleHeader = document.getElementById('current-playbook-name');

// --- Initialization ---
async function init() {
    await fetchPlaybooks();
    await fetchRegions();
    setupEventListeners();
}

// --- API Calls ---
async function fetchPlaybooks() {
    const res = await fetch('/api/playbooks');
    state.playbooks = await res.json();
    renderPlaybookList();
}

async function fetchRegions() {
    const res = await fetch('/api/regions');
    state.regions = await res.json();
    renderRegionList();
}

async function loadPlaybook(id) {
    const res = await fetch(`/api/playbooks/${id}`);
    const data = await res.json();
    state.currentPlaybook = id;
    editor.value = data.content;
    titleHeader.innerText = id;

    // Highlight active item
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.querySelector(`[data-id="${id}"]`).classList.add('active');
}

async function savePlaybook() {
    if (!state.currentPlaybook) return;
    const res = await fetch(`/api/playbooks/${state.currentPlaybook}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editor.value })
    });
    if (res.ok) {
        logToTerminal('\n✅ Playbook saved successfully.');
    }
}

function runPlaybook(dryRun = false) {
    if (!state.currentPlaybook || state.isRunning) return;

    state.isRunning = true;
    statusPill.innerText = dryRun ? 'DRY RUNNING' : 'RUNNING';
    statusPill.className = 'status-pill success';
    terminal.innerHTML = ''; // Clear logs
    logToTerminal(`🚀 Starting ${state.currentPlaybook} ${dryRun ? '(Dry Run)' : ''}...\n`);

    const eventSource = new EventSource(`/api/run/${state.currentPlaybook}?dry_run=${dryRun}`);

    eventSource.onmessage = (event) => {
        if (event.data === '[DONE]') {
            eventSource.close();
            state.isRunning = false;
            statusPill.innerText = 'IDLE';
            statusPill.className = 'status-pill idle';
            logToTerminal('\n🏁 Execution finished.');
        } else {
            logToTerminal(event.data);
        }
    };

    eventSource.onerror = () => {
        eventSource.close();
        state.isRunning = false;
        logToTerminal('\n❌ Connection lost or error occurred.');
    };
}

// --- Rendering ---
function renderPlaybookList() {
    playbookList.innerHTML = '';
    state.playbooks.forEach(pb => {
        const li = document.createElement('li');
        li.className = 'nav-item';
        li.dataset.id = pb.id;
        li.innerHTML = `<span>📄 ${pb.id}</span>`;
        li.onclick = () => loadPlaybook(pb.id);
        playbookList.appendChild(li);
    });
}

function renderRegionList() {
    regionList.innerHTML = '';
    state.regions.forEach(reg => {
        const li = document.createElement('li');
        li.className = 'nav-item';
        li.innerHTML = `<span>🎯 ${reg.name}</span> <small style="display:block; font-size:10px; opacity:0.5">${reg.window || ''}</small>`;
        regionList.appendChild(li);
    });
}

function renderModalWindowList(windows) {
    modalWindowList.innerHTML = '';
    windows.forEach((win, index) => {
        const li = document.createElement('li');
        li.className = 'window-item';
        li.innerHTML = `
            <div>${win.name}</div>
            <p>${win.width}x${win.height} at (${win.left}, ${win.top})</p>
        `;
        li.onclick = () => {
            document.querySelectorAll('.window-item').forEach(el => el.classList.remove('selected'));
            li.classList.add('selected');
            state.currentWindow = win;
        };
        modalWindowList.appendChild(li);
    });
}

function openModal() {
    modalSetup.classList.add('active');
    fetchWindows();
}

function closeModal() {
    modalSetup.classList.remove('active');
    state.currentWindow = null;
    document.getElementById('new-region-name').value = '';
}

async function fetchWindows() {
    modalWindowList.innerHTML = '<div style="padding:20px; text-align:center;">Scanning windows...</div>';
    const res = await fetch('/api/windows');
    const windows = await res.json();
    renderModalWindowList(windows);
}

async function saveRegion() {
    const name = document.getElementById('new-region-name').value;
    if (!name || !state.currentWindow) {
        alert('Please provide a name and select a window.');
        return;
    }

    const res = await fetch('/api/regions/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, window: state.currentWindow })
    });

    if (res.ok) {
        closeModal();
        fetchRegions();
        logToTerminal(`\n✅ Region '${name}' saved successfully.`);
    }
}

function logToTerminal(text) {
    const span = document.createElement('div');
    span.innerText = text;
    terminal.appendChild(span);
    terminal.scrollTop = terminal.scrollHeight;
}

// --- Events ---
function setupEventListeners() {
    document.getElementById('btn-save').onclick = savePlaybook;
    document.getElementById('btn-run').onclick = () => runPlaybook(false);
    document.getElementById('btn-dry-run').onclick = () => runPlaybook(true);

    document.getElementById('btn-new-playbook').onclick = async () => {
        const name = prompt('Playbook name:');
        if (!name) return;
        const res = await fetch('/api/playbooks/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (res.ok) {
            await fetchPlaybooks();
            const data = await res.json();
            loadPlaybook(data.id);
        }
    };

    document.getElementById('btn-setup-region').onclick = openModal;
    document.getElementById('btn-save-region').onclick = saveRegion;
}

init();
