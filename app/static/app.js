let currentFormat = 'mp3';
let pollingInterval = null;
let currentJobId = null;
let defaultPaths = {};
let lastCompletedFilePath = '';

// Load default paths & saved folder on startup
window.addEventListener('DOMContentLoaded', async () => {
  const saveFolderInput = document.getElementById('saveFolderInput');
  const savedFolder = localStorage.getItem('yt_save_folder');
  
  if (savedFolder) {
    saveFolderInput.value = savedFolder;
  }

  try {
    const res = await fetch('/api/default-paths');
    if (res.ok) {
      defaultPaths = await res.json();
      if (defaultPaths.is_local_desktop === false) {
        // Hide local Windows folder picker if running on cloud server
        const folderSection = document.getElementById('saveFolderSection');
        if (folderSection) folderSection.classList.add('hidden');
      } else {
        if (!saveFolderInput.value) {
          saveFolderInput.value = defaultPaths.downloads || '';
          localStorage.setItem('yt_save_folder', saveFolderInput.value);
        }
      }
    }
  } catch (err) {
    console.error('Failed to load default paths:', err);
  }
});

// Preset folder buttons
async function setPresetFolder(presetKey) {
  const saveFolderInput = document.getElementById('saveFolderInput');
  if (!defaultPaths[presetKey]) {
    try {
      const res = await fetch('/api/default-paths');
      if (res.ok) defaultPaths = await res.json();
    } catch (e) {}
  }
  if (defaultPaths[presetKey]) {
    saveFolderInput.value = defaultPaths[presetKey];
    localStorage.setItem('yt_save_folder', saveFolderInput.value);
  } else if (presetKey === 'project') {
    saveFolderInput.value = 'D:\\YT-MP3\\downloads';
    localStorage.setItem('yt_save_folder', saveFolderInput.value);
  }
}

// Save input changes to localStorage
document.getElementById('saveFolderInput').addEventListener('input', (e) => {
  localStorage.setItem('yt_save_folder', e.target.value.trim());
});

// Browse folder button (opens Windows folder dialog)
document.getElementById('browseFolderBtn').addEventListener('click', async () => {
  const btn = document.getElementById('browseFolderBtn');
  const originalHTML = btn.innerHTML;
  btn.innerHTML = `
    <svg class="animate-spin w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
    <span>កំពុងបើក...</span>
  `;
  btn.disabled = true;

  try {
    const res = await fetch('/api/browse-folder', { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      if (data.folder) {
        document.getElementById('saveFolderInput').value = data.folder;
        localStorage.setItem('yt_save_folder', data.folder);
      }
    } else {
      const errData = await res.json().catch(() => ({}));
      showAlert('កំហុសពេលបើក Folder: ' + (errData.detail || 'Failed'));
    }
  } catch (err) {
    showAlert('មិនអាចភ្ជាប់ទៅកាន់ Server: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHTML;
  }
});

// Open folder button (opens file in Windows Explorer)
document.getElementById('openFolderBtn').addEventListener('click', async () => {
  if (!lastCompletedFilePath) return;
  try {
    await fetch('/api/open-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: lastCompletedFilePath })
    });
  } catch (err) {
    console.error('Failed to open folder:', err);
  }
});

const formatOptions = {
  mp3: [
    { value: '320', label: '320 kbps (High Quality)' },
    { value: '192', label: '192 kbps (Standard)' },
    { value: '128', label: '128 kbps (Eco)' }
  ],
  mp4: [
    { value: 'best', label: 'Best Quality (Auto)' },
    { value: '1080', label: '1080p Full HD' },
    { value: '720', label: '720p HD' }
  ]
};

function selectFormat(format) {
  currentFormat = format;
  const btnMp3 = document.getElementById('btnFormatMp3');
  const btnMp4 = document.getElementById('btnFormatMp4');
  const qualitySelect = document.getElementById('qualitySelect');

  if (format === 'mp3') {
    btnMp3.className = 'format-btn active py-2 rounded-lg text-xs font-semibold transition flex items-center justify-center gap-2 bg-red-600 text-white shadow-sm';
    btnMp4.className = 'format-btn py-2 rounded-lg text-xs font-semibold transition flex items-center justify-center gap-2 text-slate-400 hover:text-white';
  } else {
    btnMp4.className = 'format-btn active py-2 rounded-lg text-xs font-semibold transition flex items-center justify-center gap-2 bg-indigo-600 text-white shadow-sm';
    btnMp3.className = 'format-btn py-2 rounded-lg text-xs font-semibold transition flex items-center justify-center gap-2 text-slate-400 hover:text-white';
  }

  // Populate qualities
  qualitySelect.innerHTML = '';
  formatOptions[format].forEach((opt, idx) => {
    const el = document.createElement('option');
    el.value = opt.value;
    el.textContent = opt.label;
    if (idx === 1) el.selected = true;
    qualitySelect.appendChild(el);
  });
}

// Update visibility of the Clear URL button
function updateClearBtnVisibility() {
  const url = document.getElementById('urlInput').value.trim();
  const clearBtn = document.getElementById('clearBtn');
  if (url.length > 0) {
    clearBtn.classList.remove('hidden');
  } else {
    clearBtn.classList.add('hidden');
  }
}

// Clear URL button handler
document.getElementById('clearBtn').addEventListener('click', () => {
  const urlInput = document.getElementById('urlInput');
  urlInput.value = '';
  updateClearBtnVisibility();

  // Reset preview and status cards
  document.getElementById('statusSection').classList.add('hidden');
  document.getElementById('alertBox').classList.add('hidden');
  document.getElementById('successBox').classList.add('hidden');
  document.getElementById('thumbImg').src = '';
  document.getElementById('videoTitle').textContent = '';
  urlInput.focus();
});

// Paste from clipboard
document.getElementById('pasteBtn').addEventListener('click', async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (text) {
      document.getElementById('urlInput').value = text.trim();
      updateClearBtnVisibility();
      fetchPreview(text.trim());
    }
  } catch (err) {
    console.warn('Clipboard read failed:', err);
  }
});

// Auto-fetch preview on input change
let debounceTimeout;
document.getElementById('urlInput').addEventListener('input', (e) => {
  updateClearBtnVisibility();
  clearTimeout(debounceTimeout);
  const val = e.target.value.trim();
  if (val.startsWith('http')) {
    debounceTimeout = setTimeout(() => fetchPreview(val), 600);
  } else if (!val) {
    document.getElementById('statusSection').classList.add('hidden');
  }
});

async function fetchPreview(url) {
  if (!url) return;
  try {
    const res = await fetch(`/api/info?url=${encodeURIComponent(url)}`);
    if (res.ok) {
      const data = await res.json();
      document.getElementById('statusSection').classList.remove('hidden');
      document.getElementById('thumbImg').src = data.thumbnail || '';
      document.getElementById('videoTitle').textContent = data.title;
      document.getElementById('videoChannel').textContent = data.channel;
      document.getElementById('videoDuration').textContent = data.duration;
      document.getElementById('alertBox').classList.add('hidden');
    }
  } catch (e) {
    console.error('Failed to preview', e);
  }
}

// Start download
document.getElementById('startBtn').addEventListener('click', async () => {
  const url = document.getElementById('urlInput').value.trim();
  const quality = document.getElementById('qualitySelect').value;
  const saveFolder = document.getElementById('saveFolderInput').value.trim();

  if (!url) {
    showAlert('សូមបញ្ចូល Link YouTube ជាមុនសិន! (Please enter a YouTube URL)');
    return;
  }

  const startBtn = document.getElementById('startBtn');
  const startText = document.getElementById('startText');
  const statusSection = document.getElementById('statusSection');
  const progressBar = document.getElementById('progressBar');
  const progressStatus = document.getElementById('progressStatus');
  const progressDetails = document.getElementById('progressDetails');
  const alertBox = document.getElementById('alertBox');
  const successBox = document.getElementById('successBox');

  const cancelBtn = document.getElementById('cancelBtn');

  // UI State: Loading
  startBtn.disabled = true;
  startText.textContent = 'កំពុងដំណើរការ... (Processing)';
  statusSection.classList.remove('hidden');
  cancelBtn.classList.remove('hidden');
  alertBox.classList.add('hidden');
  successBox.classList.add('hidden');
  progressBar.style.width = '5%';
  progressStatus.textContent = 'កំពុងភ្ជាប់ទៅកាន់ YouTube... (Connecting)';
  progressDetails.textContent = '0%';

  try {
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: url,
        format: currentFormat,
        quality: quality,
        save_folder: saveFolder
      })
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || 'បរាជ័យក្នុងការចាប់ផ្ដើមទាញយក');
    }

    const { job_id } = await res.json();
    currentJobId = job_id;

    // Start polling status
    clearInterval(pollingInterval);
    pollingInterval = setInterval(async () => {
      try {
        const sRes = await fetch(`/api/status/${job_id}`);
        if (!sRes.ok) return;

        const job = await sRes.json();

        if (job.status === 'downloading') {
          const percent = job.percent || 0;
          progressBar.style.width = `${Math.max(5, percent)}%`;
          progressStatus.textContent = `កំពុងទាញយក... (${job.speed || ''})`;
          progressDetails.textContent = `${percent}% • ETA: ${job.eta || ''}`;
        } else if (job.status === 'converting') {
          progressBar.style.width = '95%';
          progressStatus.textContent = 'កំពុង Convert & Merge file ជាមួយ FFmpeg...';
          progressDetails.textContent = 'សូមរង់ចាំ...';
        } else if (job.status === 'ready') {
          clearInterval(pollingInterval);
          cancelBtn.classList.add('hidden');
          progressBar.style.width = '100%';
          progressStatus.textContent = 'រួចរាល់ 100%!';
          progressDetails.textContent = 'Completed';
          
          lastCompletedFilePath = job.file_path || '';
          document.getElementById('successPathMsg').textContent = job.file_path || 'Saved successfully.';
          successBox.classList.remove('hidden');
          resetButton();

          // If running on cloud or not a custom folder, trigger browser download to client
          if (defaultPaths.is_local_desktop === false || !job.is_custom_folder) {
            window.location.href = `/api/file/${job_id}`;
          }
        } else if (job.status === 'cancelled') {
          clearInterval(pollingInterval);
          cancelBtn.classList.add('hidden');
          resetButton();
          progressStatus.textContent = 'ការទាញយកត្រូវបានបោះបង់ (Cancelled)';
          progressDetails.textContent = '';
          progressBar.style.width = '0%';
        } else if (job.status === 'error') {
          clearInterval(pollingInterval);
          cancelBtn.classList.add('hidden');
          resetButton();
          showAlert(`កំហុស (Error): ${job.error || 'Download failed.'}`);
        }
      } catch (pollErr) {
        console.error(pollErr);
      }
    }, 800);

  } catch (err) {
    cancelBtn.classList.add('hidden');
    resetButton();
    showAlert(err.message || 'Error occurred');
  }
});

// Cancel button handler
document.getElementById('cancelBtn').addEventListener('click', async () => {
  if (!currentJobId) return;

  const cancelBtn = document.getElementById('cancelBtn');
  cancelBtn.disabled = true;
  cancelBtn.innerHTML = `
    <svg class="animate-spin w-3.5 h-3.5" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
    <span>កំពុងបោះបង់...</span>
  `;

  try {
    await fetch(`/api/cancel/${currentJobId}`, { method: 'POST' });
  } catch (e) {
    console.error('Cancel request error:', e);
  } finally {
    clearInterval(pollingInterval);
    cancelBtn.disabled = false;
    cancelBtn.classList.add('hidden');
    cancelBtn.innerHTML = `
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
      <span>បោះបង់ (Cancel)</span>
    `;
    resetButton();
    document.getElementById('progressBar').style.width = '0%';
    document.getElementById('progressStatus').textContent = 'ការទាញយកត្រូវបានបោះបង់ (Download cancelled)';
    document.getElementById('progressDetails').textContent = '';
  }
});

function showAlert(msg) {
  const alertBox = document.getElementById('alertBox');
  alertBox.textContent = msg;
  alertBox.classList.remove('hidden');
}

function resetButton() {
  const startBtn = document.getElementById('startBtn');
  const startText = document.getElementById('startText');
  startBtn.disabled = false;
  startText.textContent = 'ទាញយក (Download Now)';
}
