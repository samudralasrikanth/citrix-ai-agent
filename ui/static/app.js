const state = {
    playbooks: [],
    regions: [],
    currentPlaybook: null,
    currentFile: 'playbook.yaml',
    currentWindow: null,
    expandedTests: new Set(),
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
    setupEventListeners();
}

// --- API Calls ---
async function fetchPlaybooks() {
    const res = await fetch('/api/playbooks');
    state.playbooks = await res.json();
    renderPlaybookList();
}

async function loadPlaybook(id, filename = 'playbook.yaml') {
    state.currentPlaybook = id;
    state.currentFile = filename;

    const editorArea = document.querySelector('.editor-area');

    if (filename.endsWith('.png')) {
        // Show image preview
        editorArea.innerHTML = `
            <div style="flex:1; display:flex; align-items:center; justify-content:center; background:#000; overflow:hidden;">
                <img src="/api/tests/${id}/image/${filename}" style="max-width:95%; max-height:95%; box-shadow:0 0 40px rgba(0,220,80,0.3); border-radius:4px;">
            </div>
        `;
        titleHeader.innerText = `${id} / ${filename} (Preview)`;
    } else {
        // Restore textarea if it was replaced by image
        if (!document.getElementById('playbook-editor')) {
            editorArea.innerHTML = '<textarea id="playbook-editor" spellcheck="false" placeholder="# Select a file to edit..."></textarea>';
        }

        const fileRes = await fetch(`/api/playbooks/${id}?file=${filename}`);
        const data = await fileRes.json();

        const currentEditor = document.getElementById('playbook-editor');
        currentEditor.value = data.content;
        titleHeader.innerText = `${id} / ${filename}`;
    }

    // Highlight active item
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
        logToTerminal(`\n✅ Saved: ${state.currentFile}`);
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
            if (state.expandedTests.has(pb.id)) {
                state.expandedTests.delete(pb.id);
                fileList.style.display = 'none';
            } else {
                state.expandedTests.add(pb.id);
                fileList.style.display = 'block';
                // Fetch files
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
        if (state.currentPlaybook === testId && state.currentFile === file) {
            li.classList.add('active');
        }

        li.onclick = (e) => {
            e.stopPropagation();
            loadPlaybook(testId, file);
        };
        container.appendChild(li);
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
        await fetchPlaybooks(); // Refresh the list
        await loadPlaybook(name); // Load it immediately
        logToTerminal(`\n✅ Test Case '${name}' created successfully.`);
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

    const btnNewTest = document.getElementById('btn-new-test');
    if (btnNewTest) {
        btnNewTest.onclick = openModal;
    }

    const btnSaveRegion = document.getElementById('btn-save-region');
    if (btnSaveRegion) {
        btnSaveRegion.onclick = saveRegion;
    }

    const btnClearTerminal = document.getElementById('btn-clear-terminal');
    if (btnClearTerminal) {
        btnClearTerminal.onclick = () => { terminal.innerHTML = ""; };
    }
}

init();
