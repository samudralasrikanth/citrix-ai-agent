/**
 * Hardened Frontend Dashboard for Citrix AI Vision Agent.
 * Handles structured JSON log streams and modular file management.
 */

const state = {
    playbooks: [],
    currentPlaybook: null,
    currentFile: 'playbook.yaml',
    currentWindow: null,
    isRunning: false,
    expandedTests: new Set()
};

// UI Elements
const playbookList = document.getElementById('playbook-list');
const terminal = document.getElementById('terminal-output');
const statusPill = document.getElementById('agent-status');
const titleHeader = document.querySelector('.header-title h1');

// --- Initialization ---
async function init() {
    setupEventListeners();
    await fetchPlaybooks();
}

async function fetchPlaybooks() {
    const res = await fetch('/api/playbooks');
    state.playbooks = await res.json();
    renderPlaybookList();
}

// --- Playbook Operations ---
async function loadPlaybook(id, filename = 'playbook.yaml') {
    state.currentPlaybook = id;
    state.currentFile = filename;

    const editorArea = document.querySelector('.editor-area');

    if (filename.endsWith('.png')) {
        editorArea.innerHTML = `
            <div style="flex:1; display:flex; align-items:center; justify-content:center; background:#000; overflow:hidden;">
                <img src="/api/tests/${id}/image/${filename}" style="max-width:95%; max-height:95%; box-shadow:0 0 40px rgba(0,220,80,0.3); border-radius:4px;">
            </div>
        `;
        titleHeader.innerText = `${id} / ${filename} (Preview)`;
    } else {
        if (!document.getElementById('playbook-editor')) {
            editorArea.innerHTML = '<textarea id="playbook-editor" spellcheck="false" placeholder="# Select a file to edit..."></textarea>';
        }

        const fileRes = await fetch(`/api/playbooks/${id}?file=${filename}`);
        const data = await fileRes.json();

        const currentEditor = document.getElementById('playbook-editor');
        currentEditor.value = data.content;
        titleHeader.innerText = `${id} / ${filename}`;
    }

    document.querySelectorAll('.file-item').forEach(el => el.classList.remove('active'));
    const fileEl = document.querySelector(`[data-test="${id}"][data-file="${filename}"]`);
    if (fileEl) fileEl.classList.add('active');
}

async function savePlaybook() {
    if (!state.currentPlaybook || state.currentFile.endsWith('.png')) return;
    const currentEditor = document.getElementById('playbook-editor');
    if (!currentEditor) return;

    const res = await fetch(`/api/playbooks/${state.currentPlaybook}?file=${state.currentFile}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: currentEditor.value })
    });
    if (res.ok) {
        logToTerminal({ status: "success", message: `Saved: ${state.currentFile}` });
    }
}

async function runPlaybook(dryRun = false) {
    if (!state.currentPlaybook || state.isRunning) return;

    state.isRunning = true;
    updateStatusPill(dryRun ? 'DRY RUNNING' : 'RUNNING', 'success');
    terminal.innerHTML = '';

    const eventSource = new EventSource(`/api/run/${state.currentPlaybook}?dry_run=${dryRun}`);

    eventSource.onmessage = (event) => {
        if (event.data === '[DONE]') {
            eventSource.close();
            state.isRunning = false;
            updateStatusPill('IDLE', 'idle');
            return;
        }

        try {
            const data = JSON.parse(event.data);
            logToTerminal(data);
        } catch (e) {
            logToTerminal({ status: "raw", message: event.data });
        }
    };

    eventSource.onerror = () => {
        eventSource.close();
        state.isRunning = false;
        logToTerminal({ status: "error", message: "Hardened connection lost. Verify backend health." });
    };
}

// --- Rendering ---
function renderPlaybookList() {
    playbookList.innerHTML = '';
    state.playbooks.forEach(pb => {
        const testContainer = document.createElement('div');
        testContainer.className = 'test-container';

        const folderLi = document.createElement('li');
        folderLi.className = 'nav-item';
        folderLi.innerHTML = `
            <div style="display:flex; align-items:center; gap:8px;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                <span>${pb.id}</span>
            </div>
        `;

        const fileList = document.createElement('ul');
        fileList.className = 'file-list';
        if (!state.expandedTests.has(pb.id)) fileList.style.display = 'none';

        folderLi.onclick = async () => {
            loadPlaybook(pb.id);
            if (state.expandedTests.has(pb.id)) {
                state.expandedTests.delete(pb.id);
                fileList.style.display = 'none';
            } else {
                state.expandedTests.add(pb.id);
                fileList.style.display = 'block';
                const res = await fetch(`/api/tests/${pb.id}/files`);
                const files = await res.json();
                renderFileList(pb.id, files, fileList);
            }
        };

        testContainer.appendChild(folderLi);
        testContainer.appendChild(fileList);
        playbookList.appendChild(testContainer);
    });
}

function renderFileList(testId, files, container) {
    container.innerHTML = '';
    files.forEach(file => {
        const li = document.createElement('li');
        li.className = 'file-item';
        li.dataset.test = testId;
        li.dataset.file = file;

        let icon = '📄';
        if (file.endsWith('.png')) icon = '🖼️';
        if (file.endsWith('.json')) icon = '⚙️';

        li.innerHTML = `<span>${icon} ${file}</span>`;
        if (state.currentPlaybook === testId && state.currentFile === file) li.classList.add('active');

        li.onclick = (e) => {
            e.stopPropagation();
            loadPlaybook(testId, file);
        };
        container.appendChild(li);
    });
}

// --- Terminal Log Processing ---
function logToTerminal(data) {
    const entry = document.createElement('div');
    entry.style.marginBottom = '4px';
    entry.style.fontSize = '0.85rem';

    let prefix = '➤ ';
    let color = '#00dc50';

    switch (data.status) {
        case 'init': color = '#79c0ff'; prefix = '⚙ '; break;
        case 'error': color = '#ff7b72'; prefix = '❌ '; break;
        case 'warning': color = '#ffa657'; prefix = '⚠️ '; break;
        case 'step_start': color = '#d1d5db'; prefix = '⦿ '; break;
        case 'step_success': color = '#00dc50'; prefix = '✓ '; break;
        case 'finish': color = '#d2a8ff'; prefix = '🏁 '; break;
        case 'raw': color = '#8b949e'; prefix = ''; break;
    }

    entry.style.color = color;
    entry.innerHTML = `<span style="opacity:0.6">${new Date().toLocaleTimeString()}</span> ${prefix} ${data.message}`;

    if (data.summary) {
        const pre = document.createElement('pre');
        pre.style.marginTop = '4px';
        pre.style.paddingLeft = '15px';
        pre.style.color = '#79c0ff';
        pre.innerText = JSON.stringify(data.summary, null, 2);
        entry.appendChild(pre);
    }

    terminal.appendChild(entry);
    terminal.scrollTop = terminal.scrollHeight;
}

function updateStatusPill(text, type) {
    statusPill.innerText = text;
    statusPill.className = `status-pill ${type}`;
}

// --- Modal & Window Handling ---
function openModal() {
    document.getElementById('modal-setup').classList.add('active');
    fetchWindows();
}

function closeModal() {
    document.getElementById('modal-setup').classList.remove('active');
}

async function fetchWindows() {
    const res = await fetch('/api/windows');
    const windows = await res.json();
    renderModalWindowList(windows);
}

function renderModalWindowList(windows) {
    const container = document.getElementById('modal-window-list');
    container.innerHTML = '';
    windows.forEach(win => {
        const div = document.createElement('div');
        div.className = 'window-item';
        div.innerHTML = `<strong>${win.name}</strong><p>${win.width}x${win.height} at [${win.left}, ${win.top}]</p>`;
        div.onclick = () => {
            document.querySelectorAll('.window-item').forEach(el => el.classList.remove('selected'));
            div.classList.add('selected');
            state.currentWindow = win;
        };
        container.appendChild(div);
    });
}

async function saveRegion() {
    const name = document.getElementById('new-region-name').value;
    if (!name || !state.currentWindow) return alert('Provide a name and select a window.');

    const res = await fetch('/api/regions/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, window: state.currentWindow })
    });

    if (res.ok) {
        closeModal();
        state.expandedTests.add(name);
        await fetchPlaybooks();
        await loadPlaybook(name);
        logToTerminal({ status: "success", message: `Test Case '${name}' created successfully.` });
    }
}

// --- Events ---
function setupEventListeners() {
    document.getElementById('btn-save').onclick = savePlaybook;
    document.getElementById('btn-run').onclick = () => runPlaybook(false);
    document.getElementById('btn-dry-run').onclick = () => runPlaybook(true);
    document.getElementById('btn-new-test').onclick = openModal;
    document.getElementById('btn-save-region').onclick = saveRegion;
    document.getElementById('btn-clear-terminal').onclick = () => terminal.innerHTML = '';
}

// Bootstrap
init();
