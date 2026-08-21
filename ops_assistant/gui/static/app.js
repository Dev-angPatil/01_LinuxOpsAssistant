// ==========================================================================
// LinuxOps Assistant — Luxury Avant-Garde Editorial Client Application Logic
// ==========================================================================

// Global state
let cpuChart = null;
let memoryChart = null;
let sseSource = null;
let allServices = [];
let pendingPermissionResolver = null;
let sfxEnabled = true;
let audioCtx = null;

// ==========================================================================
// LUXURY WEB AUDIO SYNTHESIZER
// ==========================================================================
function getAudioContext() {
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (AudioContextClass) audioCtx = new AudioContextClass();
  }
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume();
  }
  return audioCtx;
}

function playScifiSound(type) {
  if (!sfxEnabled) return;
  try {
    const ctx = getAudioContext();
    if (!ctx) return;
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    if (type === 'click' || type === 'tab') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, now);
      osc.frequency.exponentialRampToValueAtTime(1320, now + 0.04);
      gain.gain.setValueAtTime(0.04, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
      osc.start(now);
      osc.stop(now + 0.04);
    } else if (type === 'scan' || type === 'execute') {
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(440, now);
      osc.frequency.exponentialRampToValueAtTime(880, now + 0.08);
      gain.gain.setValueAtTime(0.05, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.10);
      osc.start(now);
      osc.stop(now + 0.10);
    } else if (type === 'success') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(523.25, now);
      osc.frequency.setValueAtTime(659.25, now + 0.05);
      osc.frequency.setValueAtTime(783.99, now + 0.10);
      gain.gain.setValueAtTime(0.04, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
      osc.start(now);
      osc.stop(now + 0.18);
    } else if (type === 'alert' || type === 'error') {
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(320, now);
      osc.frequency.exponentialRampToValueAtTime(160, now + 0.12);
      gain.gain.setValueAtTime(0.05, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
      osc.start(now);
      osc.stop(now + 0.12);
    } else if (type === 'voice_on') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(440, now);
      osc.frequency.exponentialRampToValueAtTime(880, now + 0.08);
      osc.frequency.exponentialRampToValueAtTime(1320, now + 0.16);
      gain.gain.setValueAtTime(0.04, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.16);
      osc.start(now);
      osc.stop(now + 0.16);
    } else if (type === 'voice_off') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, now);
      osc.frequency.exponentialRampToValueAtTime(440, now + 0.12);
      gain.gain.setValueAtTime(0.04, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
      osc.start(now);
      osc.stop(now + 0.12);
    }
  } catch (e) {
    // Fail silently
  }
}

function toggleSFX() {
  sfxEnabled = !sfxEnabled;
  const btn = document.getElementById('btn-toggle-sfx');
  if (btn) {
    btn.innerHTML = sfxEnabled 
      ? '<i data-lucide="volume-2" class="w-4 h-4 text-white"></i>'
      : '<i data-lucide="volume-x" class="w-4 h-4 text-slate-500"></i>';
    if (window.lucide) lucide.createIcons();
  }
  if (sfxEnabled) playScifiSound('click');
}

function updateTacticalClock() {
  const clockEl = document.getElementById('hud-tactical-clock');
  if (clockEl) {
    const d = new Date();
    const utc = d.toISOString().substring(11, 19) + ' UTC';
    const local = d.toTimeString().substring(0, 8);
    clockEl.textContent = `${local} [${utc}]`;
  }
}

function focusCommandDeck() {
  switchTab('home');
  const input = document.getElementById('agent-prompt-input');
  if (input) {
    input.scrollIntoView({ behavior: 'smooth', block: 'center' });
    input.focus();
  }
  playScifiSound('click');
}

// ==========================================================================
// VOICE ACTIVATION & SPEECH SYNTHESIS ENGINE
// ==========================================================================
let speechRecognition = null;
let isVoiceListening = false;
let ttsVoiceEnabled = false;
let speechFinalTranscript = '';
let mediaStreamAudio = null;

function isSpeechRecognitionSupported() {
  return ('SpeechRecognition' in window) || ('webkitSpeechRecognition' in window);
}

function updateVoiceUIState(listening) {
  const micBtn = document.getElementById('btn-voice-mic');
  const voiceLabel = document.getElementById('btn-voice-label');
  const hudContainer = document.getElementById('voice-hud-container');
  const statusEl = document.getElementById('voice-hud-status');
  const interimEl = document.getElementById('voice-hud-interim');

  if (micBtn) {
    if (listening) {
      micBtn.classList.add('listening');
      micBtn.innerHTML = '<i data-lucide="mic" class="w-4.5 h-4.5 text-cyan-300 animate-pulse"></i><span id="btn-voice-label" class="text-cyan-300 font-bold">Listening... 🔴</span>';
    } else {
      micBtn.classList.remove('listening');
      micBtn.innerHTML = '<i data-lucide="mic" class="w-4.5 h-4.5 text-cyan-300"></i><span id="btn-voice-label">Voice Command 🎙</span>';
    }
    if (window.lucide) lucide.createIcons();
  }

  if (hudContainer) {
    if (listening) {
      hudContainer.classList.remove('hidden');
      if (statusEl) statusEl.textContent = 'Listening...';
      if (interimEl) interimEl.textContent = 'Speak your sysadmin command...';
    } else {
      hudContainer.classList.add('hidden');
    }
  }
}

async function toggleVoiceActivation() {
  if (isVoiceListening) {
    stopVoiceActivation(true);
    return;
  }
  await startVoiceActivation();
}

async function startVoiceActivation() {
  // Step 1: Explicitly request microphone access
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    try {
      mediaStreamAudio = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      console.warn('Microphone permission error:', err);
      showToast('Microphone access required. Please allow microphone permissions in your browser.', 'error', 4000);
      return;
    }
  }

  // Step 2: Initialize Web Speech Recognition
  if (isSpeechRecognitionSupported()) {
    try {
      const SpeechRecognitionClass = window.SpeechRecognition || window.webkitSpeechRecognition;
      speechRecognition = new SpeechRecognitionClass();
      speechRecognition.continuous = false;
      speechRecognition.interimResults = true;
      speechRecognition.lang = 'en-US';

      speechRecognition.onstart = () => {
        isVoiceListening = true;
        updateVoiceUIState(true);
        playScifiSound('voice_on');
        showToast('Voice activation active. Speak your command...', 'info', 2500);
      };

      speechRecognition.onresult = (event) => {
        let interim = '';
        let final = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            final += event.results[i][0].transcript;
          } else {
            interim += event.results[i][0].transcript;
          }
        }

        const interimEl = document.getElementById('voice-hud-interim');
        const inputEl = document.getElementById('agent-prompt-input');

        if (interimEl) {
          interimEl.textContent = interim || final || 'Listening...';
        }

        if (final) {
          speechFinalTranscript = final.trim();
          if (inputEl) {
            inputEl.value = speechFinalTranscript;
            toggleClearPromptBtn(speechFinalTranscript);
          }
        } else if (interim && inputEl) {
          inputEl.value = interim;
          toggleClearPromptBtn(interim);
        }
      };

      speechRecognition.onerror = (event) => {
        console.warn('Speech recognition error:', event.error);
        isVoiceListening = false;
        updateVoiceUIState(false);
        if (event.error === 'not-allowed') {
          showToast('Microphone access was denied. Please allow microphone permissions.', 'error', 4000);
        } else if (event.error !== 'no-speech') {
          showToast(`Voice recognition: ${event.error}`, 'warning', 3000);
        }
      };

      speechRecognition.onend = () => {
        const wasListening = isVoiceListening;
        isVoiceListening = false;
        updateVoiceUIState(false);

        if (mediaStreamAudio) {
          mediaStreamAudio.getTracks().forEach(t => t.stop());
          mediaStreamAudio = null;
        }

        if (wasListening && speechFinalTranscript) {
          playScifiSound('success');
          const inputEl = document.getElementById('agent-prompt-input');
          const promptToRun = speechFinalTranscript;
          speechFinalTranscript = '';
          if (inputEl) {
            inputEl.value = promptToRun;
            toggleClearPromptBtn(promptToRun);
          }
          
          // Auto-submit voice instruction after a short pause
          setTimeout(() => {
            submitAgentPrompt(promptToRun);
          }, 350);
        } else {
          playScifiSound('voice_off');
        }
      };

      speechFinalTranscript = '';
      focusCommandDeck();
      speechRecognition.start();
    } catch (e) {
      console.error('Failed to start speech recognition', e);
      showToast('Could not start voice recognition: ' + e.message, 'error', 4000);
      updateVoiceUIState(false);
    }
  } else {
    showToast('Speech Recognition not supported in this browser. Please use Chrome, Edge, or Chromium.', 'warning', 4500);
  }
}

function stopVoiceActivation(submit = true) {
  if (speechRecognition && isVoiceListening) {
    try {
      if (submit) {
        const inputEl = document.getElementById('agent-prompt-input');
        if (inputEl && inputEl.value.trim()) {
          speechFinalTranscript = inputEl.value.trim();
        }
      } else {
        speechFinalTranscript = '';
      }
      speechRecognition.stop();
    } catch (e) {}
  }
  if (mediaStreamAudio) {
    mediaStreamAudio.getTracks().forEach(t => t.stop());
    mediaStreamAudio = null;
  }
  isVoiceListening = false;
  updateVoiceUIState(false);
}

function toggleVoiceSpeech() {
  ttsVoiceEnabled = !ttsVoiceEnabled;
  const btn = document.getElementById('btn-toggle-tts');
  if (btn) {
    btn.innerHTML = ttsVoiceEnabled 
      ? '<i data-lucide="volume-2" class="w-4 h-4 text-cyan-300"></i>' 
      : '<i data-lucide="volume-x" class="w-4 h-4 text-slate-500"></i>';
    if (window.lucide) lucide.createIcons();
  }
  if (ttsVoiceEnabled) {
    playScifiSound('success');
    showToast('AI Voice Speech synthesis enabled', 'success', 2500);
    speakText('Voice synthesis online. Linux Operations Assistant ready.');
  } else {
    playScifiSound('click');
    showToast('AI Voice Speech synthesis disabled', 'info', 2000);
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
  }
}

function speakText(text) {
  if (!ttsVoiceEnabled || !('speechSynthesis' in window)) return;
  try {
    window.speechSynthesis.cancel();
    const cleanText = text
      .replace(/[*_#`~[\]()$]/g, '')
      .replace(/https?:\/\/\S+/g, 'link')
      .replace(/\s+/g, ' ')
      .trim();

    if (!cleanText) return;
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 1.05;
    utterance.pitch = 1.0;
    
    // Pick natural English voice if available
    const voices = window.speechSynthesis.getVoices();
    const englishVoice = voices.find(v => (v.name.includes('Google') || v.name.includes('Natural') || v.name.includes('Samantha') || v.lang.startsWith('en')));
    if (englishVoice) utterance.voice = englishVoice;

    window.speechSynthesis.speak(utterance);
  } catch (e) {
    console.warn('TTS error:', e);
  }
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
  if (window.lucide) {
    lucide.createIcons();
  }
  initCharts();
  startTelemetrySSE();
  loadInitialData();
  renderQueryHistory();

  updateTacticalClock();
  setInterval(updateTacticalClock, 1000);

  // Setup prompt form submit
  const form = document.getElementById('agent-prompt-form');
  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const input = document.getElementById('agent-prompt-input');
      if (input && input.value.trim()) {
        submitAgentPrompt(input.value.trim());
      }
    });
  }

  // Refresh button
  const btnRefresh = document.getElementById('btn-refresh-health');
  if (btnRefresh) {
    btnRefresh.addEventListener('click', () => {
      playScifiSound('scan');
      fetchHealthSnapshot();
    });
  }

  // Global Keyboard Shortcuts
  document.addEventListener('keydown', (e) => {
    // Alt+V or Ctrl+Space for Voice Activation
    if ((e.altKey && e.key.toLowerCase() === 'v') || (e.ctrlKey && e.code === 'Space')) {
      e.preventDefault();
      toggleVoiceActivation();
      return;
    }
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
      e.preventDefault();
      focusCommandDeck();
    }
    if (e.key === 'Escape') {
      stopVoiceActivation(false);
      closeModal('modal-permission');
      closeModal('modal-logs');
    }
  });
});

// ==========================================================================
// TOAST NOTIFICATION SYSTEM
// ==========================================================================
function showToast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast-item';

  let iconName = 'info';
  let iconColor = 'text-white';
  if (type === 'success') {
    iconName = 'check-circle';
    iconColor = 'text-emerald-400';
    playScifiSound('success');
  } else if (type === 'error') {
    iconName = 'alert-circle';
    iconColor = 'text-rose-400';
    playScifiSound('alert');
  } else if (type === 'warning') {
    iconName = 'alert-triangle';
    iconColor = 'text-amber-400';
    playScifiSound('alert');
  } else {
    playScifiSound('click');
  }

  toast.innerHTML = `
    <div class="mt-0.5 ${iconColor} shrink-0">
      <i data-lucide="${iconName}" class="w-4 h-4"></i>
    </div>
    <div class="flex-1 text-xs text-white leading-relaxed break-words font-sans font-medium">${escapeHtml(message)}</div>
    <button onclick="this.parentElement.remove()" class="text-slate-400 hover:text-white font-mono text-sm leading-none">&times;</button>
  `;

  container.appendChild(toast);
  if (window.lucide) lucide.createIcons();

  setTimeout(() => {
    toast.classList.add('toast-leave');
    setTimeout(() => {
      if (toast.parentElement) toast.remove();
    }, 200);
  }, duration);
}

// ==========================================================================
// COMMAND EXECUTION PERMISSION MODAL & GATE
// ==========================================================================
function requestCommandPermission(options) {
  const {
    command,
    description = 'Executes specified operation on the Linux host.',
    safetyLevel = 'MODIFYING',
    riskScore = 0.35,
    rollback = null,
    onApprove = null,
    onDryRun = null
  } = options;

  playScifiSound('alert');

  return new Promise((resolve) => {
    const modal = document.getElementById('modal-permission');
    const cmdEl = document.getElementById('modal-perm-command');
    const descEl = document.getElementById('modal-perm-description');
    const safetyEl = document.getElementById('modal-perm-safety');
    const riskEl = document.getElementById('modal-perm-risk');
    const rollbackBox = document.getElementById('modal-perm-rollback-box');
    const rollbackEl = document.getElementById('modal-perm-rollback');
    const approveBtn = document.getElementById('modal-perm-approve-btn');
    const dryRunBtn = document.getElementById('modal-perm-dryrun-btn');

    if (!modal) return resolve(false);

    cmdEl.textContent = command;
    descEl.textContent = description;
    safetyEl.textContent = safetyLevel;
    safetyEl.className = 'font-bold ' + getSafetyTextColor(safetyLevel);
    riskEl.textContent = (riskScore || 0.05).toFixed(2) + ' / 1.00';

    if (rollback) {
      rollbackBox.classList.remove('hidden');
      rollbackEl.textContent = rollback;
    } else {
      rollbackBox.classList.add('hidden');
    }

    const cleanup = () => {
      approveBtn.onclick = null;
      dryRunBtn.onclick = null;
      closeModal('modal-permission');
    };

    approveBtn.onclick = async () => {
      cleanup();
      playScifiSound('execute');
      if (onApprove) await onApprove();
      resolve(true);
    };

    dryRunBtn.onclick = async () => {
      cleanup();
      playScifiSound('scan');
      if (onDryRun) await onDryRun();
      else await executeDryRunSandbox(command);
      resolve(false);
    };

    openModal('modal-permission');
    if (window.lucide) lucide.createIcons();
  });
}

function copyModalCommand() {
  const cmd = document.getElementById('modal-perm-command')?.textContent;
  if (cmd) {
    navigator.clipboard.writeText(cmd);
    showToast('Command copied to clipboard', 'info', 2000);
  }
}

async function executeDryRunSandbox(cmd) {
  showToast('Testing command in ephemeral CoW sandbox...', 'info');
  try {
    const res = await fetch('/api/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cmd, dry_run: true })
    });
    const data = await res.json();
    if (data.blocked) {
      showToast('SANDBOX BLOCKED: ' + data.error, 'error', 5000);
    } else {
      showToast(`Sandbox Verified (Exit Code ${data.returncode}) in ${data.latency_ms || 0}ms`, 'success', 4000);
    }
  } catch (e) {
    showToast('Sandbox error: ' + e.message, 'error');
  }
}

// ==========================================================================
// TAB SWITCHING & INITIALIZATION
// ==========================================================================
const TAB_TITLES = {
  'home': 'Home / AI Ops Deck',
  'health': 'System Health & PSI Telemetry',
  'services': 'Services & Process Management',
  'storage': 'Storage Matrix & Cleanup',
  'network': 'Network & Ports Control',
  'taxonomy': '16-Class Failure Taxonomy',
  'packages': 'Package Nexus',
  'desktop': 'Runner & Portals'
};

function switchTab(tabId) {
  playScifiSound('tab');
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.nav-capsule-tab').forEach(el => el.classList.remove('active'));

  const activeContent = document.getElementById('tab-content-' + tabId);
  const activeBtn = document.getElementById('tab-btn-' + tabId);

  if (activeContent) activeContent.classList.remove('hidden');
  if (activeBtn) activeBtn.classList.add('active');

  if (tabId === 'services') loadServices();
  if (tabId === 'network') loadNetwork();
  if (tabId === 'taxonomy') loadTaxonomyScenarios();

  if (window.lucide) {
    setTimeout(() => lucide.createIcons(), 50);
  }
}

async function loadInitialData() {
  await fetchHealthSnapshot();
  await loadTaxonomyScenarios();
}

// ==========================================================================
// TELEMETRY & CHARTS
// ==========================================================================
function startTelemetrySSE() {
  if (window.EventSource) {
    try {
      sseSource = new EventSource('/api/stream/telemetry');
      sseSource.onmessage = (event) => {
        try {
          const snap = JSON.parse(event.data);
          updateTelemetryUI(snap);
        } catch (e) {
          console.error('Error parsing SSE telemetry', e);
        }
      };
      sseSource.onerror = () => {
        if (sseSource) sseSource.close();
        setInterval(fetchHealthSnapshot, 3000);
      };
    } catch (e) {
      setInterval(fetchHealthSnapshot, 3000);
    }
  } else {
    setInterval(fetchHealthSnapshot, 3000);
  }
}

async function fetchHealthSnapshot() {
  try {
    const res = await fetch('/api/health');
    if (res.ok) {
      const snap = await res.json();
      updateTelemetryUI(snap);
    }
  } catch (e) {
    console.error('Failed to fetch health snapshot', e);
  }
}

function updateTelemetryUI(snap) {
  if (!snap) return;

  // Header & Hero Stats
  const cpu = snap.cpu || {};
  const mem = snap.memory || {};
  const load = snap.load || {};

  const totalCpuPct = (cpu.user_pct || 0) + (cpu.system_pct || 0);

  // Hero Card Stats
  const heroCpu = document.getElementById('hero-cpu-stat');
  if (heroCpu) heroCpu.textContent = totalCpuPct.toFixed(1) + '%';
  const heroPsi = document.getElementById('hero-psi-stat');
  if (heroPsi) heroPsi.textContent = snap.pressure_status || 'NORMAL';

  // Health Elements
  const cpuPctEl = document.getElementById('health-cpu-pct');
  if (cpuPctEl) cpuPctEl.textContent = totalCpuPct.toFixed(1) + '%';
  const cpuCoresEl = document.getElementById('health-cpu-cores');
  if (cpuCoresEl) cpuCoresEl.textContent = (cpu.core_count || 1) + ' Cores';
  const cpuBreakdownEl = document.getElementById('health-cpu-breakdown');
  if (cpuBreakdownEl) cpuBreakdownEl.textContent = `User: ${(cpu.user_pct||0).toFixed(1)}% | Sys: ${(cpu.system_pct||0).toFixed(1)}% | IO: ${(cpu.iowait_pct||0).toFixed(1)}%`;

  const ramPctEl = document.getElementById('health-ram-pct');
  if (ramPctEl) ramPctEl.textContent = (mem.used_percent || 0).toFixed(1) + '%';
  const swapInfoEl = document.getElementById('health-swap-info');
  if (swapInfoEl) swapInfoEl.textContent = 'Swap: ' + (mem.swap_used_percent||0).toFixed(1) + '% used';

  const load1mEl = document.getElementById('health-load-1m');
  if (load1mEl) load1mEl.textContent = (load.load_1m || 0).toFixed(2);
  const load5mEl = document.getElementById('health-load-5m');
  if (load5mEl) load5mEl.textContent = `5m: ${(load.load_5m||0).toFixed(2)} | 15m: ${(load.load_15m||0).toFixed(2)}`;

  const psiBadge = document.getElementById('health-psi-badge');
  if (psiBadge) psiBadge.textContent = snap.pressure_status || 'NORMAL';
  const uptimeEl = document.getElementById('health-uptime-str');
  if (uptimeEl) uptimeEl.textContent = 'Uptime: ' + ((snap.uptime_seconds||0)/3600).toFixed(1) + ' hrs';

  // Update Charts
  const nowStr = new Date().toLocaleTimeString();
  if (cpuChart) {
    if (cpuChart.data.labels.length > 15) {
      cpuChart.data.labels.shift();
      cpuChart.data.datasets[0].data.shift();
      cpuChart.data.datasets[1].data.shift();
    }
    cpuChart.data.labels.push(nowStr);
    cpuChart.data.datasets[0].data.push(totalCpuPct);
    cpuChart.data.datasets[1].data.push(cpu.iowait_pct || 0);
    cpuChart.update('none');
  }

  if (memoryChart) {
    if (memoryChart.data.labels.length > 15) {
      memoryChart.data.labels.shift();
      memoryChart.data.datasets[0].data.shift();
      memoryChart.data.datasets[1].data.shift();
    }
    memoryChart.data.labels.push(nowStr);
    memoryChart.data.datasets[0].data.push(mem.used_percent || 0);
    memoryChart.data.datasets[1].data.push(mem.swap_used_percent || 0);
    memoryChart.update('none');
  }

  renderPSITable(snap.psi_metrics);
  renderDisksTable(snap.disks);
}

function initCharts() {
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    scales: {
      y: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.06)' }, ticks: { color: '#94A3B8', font: { family: 'JetBrains Mono', size: 11 } } },
      x: { grid: { color: 'rgba(255,255,255,0.06)' }, ticks: { color: '#94A3B8', font: { family: 'JetBrains Mono', size: 11 }, maxRotation: 0 } }
    },
    plugins: { legend: { labels: { color: '#F1F5F9', font: { family: 'Space Grotesk', size: 13, weight: 600 }, boxWidth: 14 } } }
  };

  const ctxCpu = document.getElementById('chart-cpu');
  if (ctxCpu) {
    cpuChart = new Chart(ctxCpu, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'CPU Total %', data: [], borderColor: '#00D2FF', backgroundColor: 'rgba(0, 210, 255, 0.12)', fill: true, tension: 0.3, borderWidth: 2.5, pointBackgroundColor: '#00D2FF', pointRadius: 2 },
          { label: 'I/O Wait %', data: [], borderColor: '#F59E0B', backgroundColor: 'rgba(245, 158, 11, 0.08)', borderDash: [4, 4], fill: true, tension: 0.3, borderWidth: 2, pointBackgroundColor: '#F59E0B', pointRadius: 2 }
        ]
      },
      options: chartOptions
    });
  }

  const ctxMem = document.getElementById('chart-memory');
  if (ctxMem) {
    memoryChart = new Chart(ctxMem, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'RAM Used %', data: [], borderColor: '#A855F7', backgroundColor: 'rgba(168, 85, 247, 0.12)', fill: true, tension: 0.3, borderWidth: 2.5, pointBackgroundColor: '#A855F7', pointRadius: 2 },
          { label: 'Swap Used %', data: [], borderColor: '#FB7185', backgroundColor: 'rgba(251, 113, 133, 0.08)', borderDash: [4, 4], fill: true, tension: 0.3, borderWidth: 2, pointBackgroundColor: '#FB7185', pointRadius: 2 }
        ]
      },
      options: chartOptions
    });
  }
}

function renderPSITable(psi) {
  const container = document.getElementById('psi-table-container');
  if (!container) return;
  if (!psi) {
    container.innerHTML = '<p class="text-slate-500 font-mono">Kernel PSI metrics not available (/proc/pressure unmounted).</p>';
    return;
  }

  let html = '<div class="grid grid-cols-3 gap-3">';
  for (const [subsys, metrics] of Object.entries(psi)) {
    const avg10 = metrics.some_avg10 || 0;
    const colorClass = avg10 > 20 ? 'text-rose-400 border-rose-500/40 bg-rose-500/10' : (avg10 > 5 ? 'text-amber-400 border-amber-500/40 bg-amber-500/10' : 'text-cyan-300 border-cyan-500/30 bg-cyan-500/5');
    const badgeColor = avg10 > 20 ? 'text-rose-400' : (avg10 > 5 ? 'text-amber-400' : 'text-emerald-400');
    html += `<div class="p-4 rounded-2xl border space-y-1.5 ${colorClass}">
      <div class="flex items-center justify-between">
        <span class="font-sans font-bold uppercase text-slate-300 text-xs tracking-wider">${subsys}</span>
        <span class="text-[10px] font-mono font-bold uppercase ${badgeColor}">${avg10 > 20 ? 'HIGH STALL' : (avg10 > 5 ? 'ELEVATED' : 'NORMAL')}</span>
      </div>
      <div class="font-editorial italic text-3xl ${badgeColor}">${avg10.toFixed(2)}%</div>
      <p class="text-xs text-slate-400 font-mono">60s: ${(metrics.some_avg60||0).toFixed(2)}% | 300s: ${(metrics.some_avg300||0).toFixed(2)}%</p>
    </div>`;
  }
  html += '</div>';
  container.innerHTML = html;
}

function renderDisksTable(disks) {
  const container = document.getElementById('disks-table-container');
  if (!container) return;
  if (!disks || disks.length === 0) {
    container.innerHTML = '<p class="text-slate-500 font-mono">No filesystem mounts discovered.</p>';
    return;
  }

  let html = '<div class="space-y-3">';
  disks.slice(0, 4).forEach(d => {
    const barColor = d.used_percent > 85 ? 'bg-rose-500 shadow-[0_0_12px_rgba(244,63,94,0.6)]' : (d.used_percent > 70 ? 'bg-amber-400 shadow-[0_0_12px_rgba(245,158,11,0.6)]' : 'bg-cyan-400 shadow-[0_0_12px_rgba(0,210,255,0.6)]');
    html += `<div class="p-4 rounded-2xl bg-black/40 border border-white/10 space-y-2.5 font-sans text-xs sm:text-sm">
      <div class="flex justify-between items-center">
        <span class="text-white font-semibold font-tech text-sm">${d.mountpoint}</span>
        <span class="text-cyan-300 font-mono font-bold">${d.used_gb.toFixed(1)} / ${d.total_gb.toFixed(1)} GB (${d.used_percent.toFixed(1)}%)</span>
      </div>
      <div class="w-full bg-white/10 h-2 rounded-full overflow-hidden">
        <div class="${barColor} h-full transition-all duration-500" style="width: ${Math.min(100, d.used_percent)}%"></div>
      </div>
    </div>`;
  });
  html += '</div>';
  container.innerHTML = html;
}

// ==========================================================================
// MISSION & INQUIRY HISTORY ENGINE
// ==========================================================================
const HISTORY_STORAGE_KEY = 'linuxops_mission_history_v1';

const DEFAULT_HISTORY = [
  { prompt: 'Why is port 80 blocked in firewall?', intent: 'DIAGNOSTIC', time: '18:20:10', safety: 'READ_ONLY' },
  { prompt: 'Show system health and pressure', intent: 'TELEMETRY', time: '18:15:42', safety: 'READ_ONLY' },
  { prompt: 'Why is NGINX failing to bind?', intent: 'DIAGNOSTIC', time: '18:10:05', safety: 'READ_ONLY' },
  { prompt: 'Organize my Downloads folder', intent: 'MUTATION', time: '17:55:20', safety: 'MUTATION_SAFE' },
  { prompt: 'Find large files over 100MB', intent: 'AUDIT', time: '17:42:18', safety: 'READ_ONLY' },
  { prompt: 'Audit SSH security configuration', intent: 'SECURITY', time: '17:30:00', safety: 'READ_ONLY' }
];

function getStoredHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch (e) {}
  return DEFAULT_HISTORY;
}

function saveQueryToHistory(promptText, intent = 'QUERY', safety = 'READ_ONLY') {
  if (!promptText || !promptText.trim()) return;
  const history = getStoredHistory().filter(h => h.prompt.toLowerCase() !== promptText.trim().toLowerCase());
  const now = new Date();
  const timeStr = now.toTimeString().split(' ')[0];
  
  history.unshift({
    prompt: promptText.trim(),
    intent: intent || 'QUERY',
    time: timeStr,
    safety: safety || 'READ_ONLY'
  });

  const trimmed = history.slice(0, 30);
  try {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(trimmed));
  } catch (e) {}

  renderQueryHistory();
}

function renderQueryHistory(filterText = '') {
  const container = document.getElementById('history-items-container');
  if (!container) return;

  const history = getStoredHistory();
  const filtered = filterText 
    ? history.filter(h => h.prompt.toLowerCase().includes(filterText.toLowerCase()) || (h.intent && h.intent.toLowerCase().includes(filterText.toLowerCase())))
    : history;

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="p-4 rounded-2xl bg-white/[0.02] border border-white/10 text-center text-xs text-slate-500 font-mono">
        ${filterText ? 'No matching inquiries found' : 'No mission history yet'}
      </div>
    `;
    return;
  }

  let html = '';
  filtered.forEach((item) => {
    const escaped = escapeHtml(item.prompt);
    const intentClass = getIntentBadgeClass(item.intent);
    html += `
      <div class="history-item flex items-center justify-between group space-x-2" onclick="loadHistoryPrompt('${escaped.replace(/'/g, "\\'")}')">
        <div class="flex-1 min-w-0 space-y-1">
          <div class="flex items-center space-x-1.5">
            <span class="${intentClass} text-[9px] font-mono px-2 py-0.5 rounded-full uppercase font-bold">${escapeHtml(item.intent || 'QUERY')}</span>
            <span class="text-[10px] text-slate-500 font-mono">${escapeHtml(item.time || '')}</span>
          </div>
          <p class="text-xs text-slate-200 font-mono truncate group-hover:text-white">${escaped}</p>
        </div>
        <button 
          type="button" 
          onclick="event.stopPropagation(); quickPrompt('${escaped.replace(/'/g, "\\'")}');" 
          title="Re-run Mission" 
          class="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-slate-300 hover:text-white transition shrink-0">
          <i data-lucide="play" class="w-3.5 h-3.5 text-cyan-300"></i>
        </button>
      </div>
    `;
  });

  container.innerHTML = html;
  if (window.lucide) lucide.createIcons();
}

function filterHistoryList(query) {
  renderQueryHistory(query);
}

function clearQueryHistory() {
  playScifiSound('click');
  try {
    localStorage.removeItem(HISTORY_STORAGE_KEY);
  } catch (e) {}
  renderQueryHistory();
  showToast('Mission history cleared', 'info', 2000);
}

function loadHistoryPrompt(promptText) {
  playScifiSound('click');
  const input = document.getElementById('agent-prompt-input');
  if (input) {
    input.value = promptText;
    toggleClearPromptBtn(promptText);
    input.focus();
  }
}

function toggleClearPromptBtn(val) {
  const btn = document.getElementById('btn-clear-prompt');
  if (btn) {
    if (val && val.trim().length > 0) {
      btn.classList.remove('hidden');
    } else {
      btn.classList.add('hidden');
    }
  }
}

function clearPromptInput() {
  playScifiSound('click');
  const input = document.getElementById('agent-prompt-input');
  if (input) {
    input.value = '';
    input.focus();
    toggleClearPromptBtn('');
  }
}

function getIntentBadgeClass(intent) {
  const norm = (intent || '').toUpperCase();
  if (norm.includes('DIAGNOSTIC') || norm.includes('DIAGNOSE')) return 'bg-amber-400/20 text-amber-300 border border-amber-400/30';
  if (norm.includes('MUTATION') || norm.includes('ACTION')) return 'bg-cyan-400/20 text-cyan-300 border border-cyan-400/30';
  if (norm.includes('SECURITY') || norm.includes('AUDIT')) return 'bg-rose-400/20 text-rose-300 border border-rose-400/30';
  if (norm.includes('TELEMETRY') || norm.includes('HEALTH')) return 'bg-emerald-400/20 text-emerald-300 border border-emerald-400/30';
  return 'bg-white/10 text-slate-300 border border-white/20';
}

// ==========================================================================
// AI OPS AGENT: CHAT & TACTICAL STREAM
// ==========================================================================
function quickPrompt(text) {
  playScifiSound('click');
  const input = document.getElementById('agent-prompt-input');
  if (input) {
    input.value = text;
    toggleClearPromptBtn(text);
    submitAgentPrompt(text);
  }
}

async function submitAgentPrompt(promptText) {
  playScifiSound('execute');
  const feed = document.getElementById('agent-feed-container');
  const input = document.getElementById('agent-prompt-input');
  const btn = document.getElementById('btn-submit-prompt');
  const statusEl = document.getElementById('working-stream-status');

  if (!feed) return;

  // Keep query explicitly visible on the search bar
  if (input) {
    input.value = promptText;
    toggleClearPromptBtn(promptText);
  }

  if (statusEl) {
    statusEl.innerHTML = '<span class="text-cyan-300 animate-pulse">⚡ Reasoning &amp; AST Checking...</span>';
  }

  const userCard = document.createElement('div');
  userCard.className = 'p-4 sm:p-5 rounded-2xl bg-white/[0.03] border border-white/15 font-mono text-xs text-white space-y-2';
  userCard.innerHTML = `
    <div class="flex items-center justify-between text-[10px] text-slate-400 font-sans uppercase tracking-wider">
      <span class="flex items-center space-x-1.5">
        <i data-lucide="user" class="w-3.5 h-3.5 text-slate-300"></i>
        <span>Sysadmin Inquirer</span>
      </span>
      <span>${new Date().toLocaleTimeString()}</span>
    </div>
    <div class="text-xs sm:text-[13px] text-white font-semibold pl-3 border-l-2 border-cyan-400 leading-relaxed">${escapeHtml(promptText)}</div>
  `;
  feed.appendChild(userCard);

  const agentCard = document.createElement('div');
  agentCard.className = 'p-5 rounded-2xl bg-white/[0.04] border border-white/10 space-y-3';
  agentCard.innerHTML = `
    <div class="flex items-center space-x-2.5 text-xs font-sans text-slate-300">
      <span class="inline-block w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
      <span>Reasoning &amp; AST validation in progress...</span>
    </div>
  `;
  feed.appendChild(agentCard);

  feed.scrollTop = feed.scrollHeight;
  if (btn) btn.disabled = true;
  if (window.lucide) lucide.createIcons();

  try {
    const res = await fetch('/api/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: promptText, execute: false })
    });
    const data = await res.json();
    renderAgentResponseCard(agentCard, data);

    // Save to history
    saveQueryToHistory(promptText, data.intent || 'QUERY', data.safety_level || 'READ_ONLY');

    if (statusEl) {
      statusEl.innerHTML = `<span class="text-emerald-400">🟢 Verified (${new Date().toLocaleTimeString()})</span>`;
    }
  } catch (e) {
    agentCard.innerHTML = `
      <div class="text-xs text-rose-400 font-mono font-bold flex items-center space-x-2">
        <i data-lucide="alert-circle" class="w-4 h-4"></i>
        <span>Agent Error: ${escapeHtml(e.message)}</span>
      </div>
    `;
    if (statusEl) {
      statusEl.innerHTML = `<span class="text-rose-400">⚠️ Error</span>`;
    }
  } finally {
    if (btn) btn.disabled = false;
    if (window.lucide) lucide.createIcons();
    feed.scrollTop = feed.scrollHeight;
  }
}

function renderAgentResponseCard(card, data) {
  playScifiSound('success');
  const safetyClass = getSafetyBadgeClass(data.safety_level || 'READ_ONLY');

  card.className = 'avant-card-elevated p-5 sm:p-6 space-y-4';

  let stepsHtml = '';
  if (data.steps && data.steps.length > 0) {
    stepsHtml = `
      <div class="space-y-1 text-[11px] text-slate-300 font-mono border-l-2 border-white/30 pl-3 py-0.5 leading-relaxed">
        ${data.steps.map(s => `<div>&bull; ${escapeHtml(s)}</div>`).join('')}
      </div>
    `;
  }

  let commandSectionHtml = '';
  const plannedCmds = data.planned_commands || (data.command ? [{
    command: data.command,
    description: data.command_description || data.summary,
    safety_level: data.safety_level,
    risk_score: data.risk_score,
    rollback_command: data.rollback_command
  }] : []);

  if (plannedCmds.length > 0) {
    commandSectionHtml = `
      <div class="space-y-3 pt-1">
        <div class="text-[10px] font-sans font-semibold uppercase tracking-wider text-slate-400">Planned Command Execution &amp; Guardrails:</div>
        ${plannedCmds.map((c) => `
          <div class="p-4 rounded-2xl bg-black/60 border border-white/10 space-y-2.5">
            <div class="flex items-center justify-between">
              <span class="${getSafetyBadgeClass(c.safety_level)} text-[10px] font-mono px-2.5 py-0.5 rounded-full uppercase font-bold">${c.safety_level || 'READ_ONLY'}</span>
              <span class="text-[10px] font-mono text-slate-400">Risk: ${(c.risk_score || 0.05).toFixed(2)}</span>
            </div>

            <div class="p-3 rounded-xl bg-black/80 border border-white/10 font-mono text-xs text-white flex items-start justify-between space-x-2">
              <div class="break-all select-all flex-1 font-semibold text-white">
                <span class="text-slate-500 select-none">$ </span>
                ${escapeHtml(c.command)}
              </div>
              <button onclick="navigator.clipboard.writeText('${escapeHtml(c.command)}'); showToast('Command copied', 'info', 2000);" class="text-slate-400 hover:text-white px-1" title="Copy Command">
                <i data-lucide="copy" class="w-3.5 h-3.5"></i>
              </button>
            </div>

            <div class="text-xs text-slate-200 font-sans leading-relaxed">
              <span class="text-slate-500 text-[10px] font-semibold uppercase block mb-0.5">Rationale:</span>
              ${escapeHtml(c.description || 'Executes operation on the system.')}
            </div>

            ${c.rollback_command ? `
              <div class="text-[11px] font-mono text-slate-400">
                <span class="text-amber-400 font-bold">Rollback:</span> ${escapeHtml(c.rollback_command)}
              </div>
            ` : ''}

            <div class="flex items-center space-x-2 pt-2 border-t border-white/10">
              <button onclick="executeCommandDirect('${escapeHtml(c.command)}', '${escapeHtml(c.rollback_command || '')}', this.closest('.avant-card-elevated'))" class="btn-editorial-primary !py-1.5 !px-3 text-xs">
                <i data-lucide="play" class="w-3 h-3"></i>
                <span>Execute</span>
              </button>
              <button onclick="executeDryRunSandbox('${escapeHtml(c.command)}')" class="btn-editorial-secondary !py-1.5 !px-3 text-xs">
                <i data-lucide="flask-conical" class="w-3 h-3"></i>
                <span>Dry-Run</span>
              </button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  let outputDetailsHtml = '';
  if (data.output && !plannedCmds.length) {
    outputDetailsHtml = `
      <pre class="p-4 rounded-2xl bg-black/60 border border-white/10 text-[11px] font-mono text-slate-300 overflow-x-auto max-h-48 whitespace-pre-wrap leading-relaxed">${escapeHtml(JSON.stringify(data.output, null, 2))}</pre>
    `;
  }

  let rollbackBtnHtml = '';
  if (data.rollback_command && data.executed) {
    rollbackBtnHtml = `
      <button onclick="executeRollback('${escapeHtml(data.rollback_command)}')" class="btn-editorial-secondary !py-1 !px-2.5 text-xs">
        <i data-lucide="undo-2" class="w-3 h-3"></i>
        <span>Rollback</span>
      </button>
    `;
  }

  card.innerHTML = `
    <div class="flex items-center justify-between text-xs border-b border-white/10 pb-2.5 font-sans">
      <div class="flex items-center space-x-2">
        <span class="font-semibold text-white flex items-center space-x-1.5">
          <i data-lucide="bot" class="w-4 h-4 text-cyan-300"></i>
          <span>${escapeHtml(data.intent || 'ACTION')}</span>
        </span>
        <span class="${safetyClass} text-[9px] font-mono px-2.5 py-0.5 rounded-full uppercase font-bold">${escapeHtml(data.safety_level || 'READ_ONLY')}</span>
      </div>
      <span class="text-slate-500 text-[10px]">${new Date().toLocaleTimeString()}</span>
    </div>

    <div class="text-xs sm:text-sm text-white font-sans font-medium leading-relaxed">${escapeHtml(data.summary || 'Analysis complete.')}</div>
    
    ${stepsHtml}
    ${commandSectionHtml}
    ${outputDetailsHtml}

    <div class="flex items-center justify-between pt-1 font-mono text-[10px] text-slate-500">
      <span>Risk Score: ${(data.risk_score || 0.05).toFixed(2)}</span>
      ${rollbackBtnHtml}
    </div>
  `;

  if (window.lucide) lucide.createIcons();

  // Optional Voice TTS Output
  if (voiceSpeechEnabled && data.summary) {
    speakText(data.summary);
  }
}

function clearAgentFeed() {
  playScifiSound('click');
  const feed = document.getElementById('agent-feed-container');
  if (feed) {
    feed.innerHTML = '<p class="text-xs font-mono text-slate-500 p-2">Tactical reasoning feed purged.</p>';
  }
}

// ==========================================================================
// COMMAND EXECUTION ENGINE & ROLLBACK
// ==========================================================================
async function executeCommandDirect(cmd, rollbackCmd, cardEl) {
  showToast('Executing command: ' + cmd, 'info');

  try {
    const res = await fetch('/api/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cmd, dry_run: false })
    });
    const data = await res.json();

    if (data.blocked) {
      showToast('BLOCKED BY SAFETY MATRIX: ' + data.error, 'error', 5000);
      return;
    }

    if (data.success) {
      showToast(`Command executed successfully (Exit Code ${data.returncode}) in ${data.latency_ms || 0}ms`, 'success');
    } else {
      showToast(`Command returned non-zero exit code (${data.returncode})`, 'warning');
    }

    if (cardEl) {
      const resultBox = document.createElement('div');
      resultBox.className = 'p-4 sm:p-5 rounded-2xl bg-black/70 border border-white/10 space-y-2 font-mono text-xs leading-relaxed';
      resultBox.innerHTML = `
        <div class="flex items-center justify-between text-[10px] text-slate-500">
          <span class="font-bold text-white">&check; Execution Complete</span>
          <span>Exit: ${data.returncode} | Latency: ${data.latency_ms || 0}ms</span>
        </div>
        <pre class="text-[11px] text-slate-200 overflow-x-auto max-h-36 whitespace-pre-wrap">${escapeHtml(data.stdout || data.stderr || '(No output returned)')}</pre>
        ${(rollbackCmd || data.rollback_command) ? `
          <div class="pt-2 flex justify-end">
            <button onclick="executeRollback('${escapeHtml(rollbackCmd || data.rollback_command)}')" class="btn-editorial-secondary !py-1 !px-2.5 text-[10px]">
              <i data-lucide="undo-2" class="w-3 h-3"></i>
              <span>Rollback</span>
            </button>
          </div>
        ` : ''}
      `;
      cardEl.appendChild(resultBox);
      if (window.lucide) lucide.createIcons();
    }
  } catch (e) {
    showToast('Execution failed: ' + e.message, 'error');
  }
}

async function executeRollback(rollbackCmd) {
  if (!rollbackCmd) return;

  requestCommandPermission({
    command: rollbackCmd,
    description: 'Reverts previous operation by executing state rollback command.',
    safetyLevel: 'MODIFYING',
    riskScore: 0.30,
    onApprove: async () => {
      showToast('Executing rollback: ' + rollbackCmd, 'info');
      try {
        const res = await fetch('/api/rollback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ rollback_command: rollbackCmd })
        });
        const data = await res.json();
        if (data.success) {
          showToast('Rollback completed successfully', 'success');
        } else {
          showToast('Rollback error: ' + (data.error || 'Failed'), 'error');
        }
      } catch (e) {
        showToast('Rollback error: ' + e.message, 'error');
      }
    }
  });
}

// ==========================================================================
// SERVICES & PROCESSES
// ==========================================================================
async function loadServices() {
  try {
    const res = await fetch('/api/services');
    if (res.ok) {
      allServices = await res.json();
      renderServicesTable(allServices);
    }
  } catch (e) {
    console.error('Failed to load services', e);
  }
}

function filterServices() {
  const query = (document.getElementById('service-search-input')?.value || '').toLowerCase();
  const filtered = allServices.filter(s => (s.unit || '').toLowerCase().includes(query) || (s.description || '').toLowerCase().includes(query));
  renderServicesTable(filtered);
}

function renderServicesTable(services) {
  const tbody = document.getElementById('services-table-body');
  if (!tbody) return;

  if (!services || services.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="text-center text-slate-500 py-6 font-mono">No matching services found.</td></tr>';
    return;
  }

  tbody.innerHTML = services.map(s => {
    const isRunning = s.active_state === 'active' || s.sub_state === 'running';
    const isFailed = s.active_state === 'failed';
    const statusColor = isFailed ? 'text-rose-400' : (isRunning ? 'text-emerald-400' : 'text-slate-500');
    const dotColor = isFailed ? 'bg-rose-400' : (isRunning ? 'bg-emerald-400' : 'bg-slate-600');

    return `
      <tr>
        <td class="font-semibold text-white">
          <div class="flex items-center space-x-2">
            <span class="w-1.5 h-1.5 rounded-full ${dotColor}"></span>
            <span>${escapeHtml(s.unit)}</span>
          </div>
        </td>
        <td class="${statusColor} font-bold">${escapeHtml(s.active_state)} (${escapeHtml(s.sub_state)})</td>
        <td class="text-right space-x-1.5">
          <button onclick="promptServiceAction('${escapeHtml(s.unit)}', '${isRunning ? 'restart' : 'start'}')" class="btn-editorial-secondary !py-1 !px-2.5 text-[11px]">
            ${isRunning ? 'Restart' : 'Start'}
          </button>
          ${isRunning ? `
            <button onclick="promptServiceAction('${escapeHtml(s.unit)}', 'stop')" class="btn-editorial-primary !py-1 !px-2.5 text-[11px]">
              Stop
            </button>
          ` : ''}
          <button onclick="viewServiceLogs('${escapeHtml(s.unit)}')" class="btn-editorial-ghost !py-1 !px-2 text-[11px]">
            Logs
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

function promptServiceAction(svc, action) {
  const cmd = `systemctl ${action} ${svc}`;
  const rollbackCmd = action === 'start' ? `systemctl stop ${svc}` : (action === 'stop' ? `systemctl start ${svc}` : null);

  requestCommandPermission({
    command: cmd,
    description: `${action.toUpperCase()} system service unit ${svc}.`,
    safetyLevel: 'MODIFYING',
    riskScore: 0.35,
    rollback: rollbackCmd,
    onApprove: async () => {
      showToast(`Executing: ${cmd}`, 'info');
      try {
        const res = await fetch('/api/services/control', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ unit: svc, action: action })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`Service ${svc} ${action}ed successfully`, 'success');
          loadServices();
        } else {
          showToast(`Failed to ${action} ${svc}: ` + (data.error || 'Error'), 'error');
        }
      } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
      }
    }
  });
}

async function viewServiceLogs(svc) {
  playScifiSound('scan');
  const modal = document.getElementById('modal-logs');
  const title = document.getElementById('modal-logs-title');
  const content = document.getElementById('modal-logs-content');

  if (title) title.textContent = `Journal Logs: ${svc}`;
  if (content) content.textContent = 'Streaming journal logs from journalctl...';
  openModal('modal-logs');

  try {
    const res = await fetch(`/api/services/logs?unit=${encodeURIComponent(svc)}&lines=100`);
    if (res.ok) {
      const logs = await res.json();
      content.textContent = (logs.lines || []).join('\n') || '(No journal logs recorded for unit)';
    } else {
      content.textContent = 'Failed to fetch journal logs.';
    }
  } catch (e) {
    content.textContent = 'Error: ' + e.message;
  }
}

async function loadProcesses() {
  playScifiSound('scan');
  try {
    const res = await fetch('/api/processes');
    if (res.ok) {
      const procs = await res.json();
      const tbody = document.getElementById('processes-table-body');
      if (!tbody) return;

      tbody.innerHTML = (procs || []).slice(0, 30).map(p => `
        <tr>
          <td class="font-mono text-white">${p.pid}</td>
          <td class="text-slate-400">${escapeHtml(p.user || 'root')}</td>
          <td class="font-bold text-white">${(p.cpu_pct||0).toFixed(1)}%</td>
          <td class="text-slate-300 font-bold">${(p.mem_pct||0).toFixed(1)}%</td>
          <td class="truncate max-w-[140px] text-white" title="${escapeHtml(p.command)}">${escapeHtml(p.command)}</td>
          <td class="text-right">
            <button onclick="promptKillProcess(${p.pid}, '${escapeHtml(p.command)}')" class="btn-editorial-primary !py-0.5 !px-2 text-[10px]">
              Kill
            </button>
          </td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error('Failed to load processes', e);
  }
}

function promptKillProcess(pid, cmdName) {
  const cmd = `kill -15 ${pid}`;

  requestCommandPermission({
    command: cmd,
    description: `Terminates active process PID ${pid} (${cmdName}).`,
    safetyLevel: 'HIGH_RISK',
    riskScore: 0.65,
    onApprove: async () => {
      showToast(`Killing process ${pid}...`, 'info');
      try {
        const res = await fetch('/api/processes/kill', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pid: pid, signal: 15 })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`Process ${pid} terminated`, 'success');
          loadProcesses();
        } else {
          showToast(`Failed to kill process: ` + (data.error || 'Error'), 'error');
        }
      } catch (e) {
        showToast('Error: ' + e.message, 'error');
      }
    }
  });
}

// ==========================================================================
// STORAGE & CLEANUP
// ==========================================================================
async function previewOrganize() {
  playScifiSound('scan');
  const path = document.getElementById('organize-path-input')?.value || '~/Downloads';
  const container = document.getElementById('organize-result-container');
  if (!container) return;

  container.classList.remove('hidden');
  container.innerHTML = '<span class="text-slate-400 font-mono">Analyzing target directory topology...</span>';

  try {
    const res = await fetch('/api/storage/organize/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: path })
    });
    const data = await res.json();
    if (data.success) {
      container.innerHTML = `
        <div class="space-y-1.5 text-xs font-sans">
          <div class="text-white font-bold">Preview: Discovered ${data.total_files || 0} candidate files to organize:</div>
          <div class="space-y-1 text-slate-300 font-mono">
            ${(data.moves || []).slice(0, 10).map(m => `<div>&bull; ${escapeHtml(m.source)} &rarr; <span class="text-white">${escapeHtml(m.destination)}</span></div>`).join('')}
            ${(data.moves || []).length > 10 ? `<div class="text-slate-500">...and ${data.moves.length - 10} more items</div>` : ''}
          </div>
        </div>
      `;
    } else {
      container.innerHTML = `<span class="text-rose-400">Error: ${escapeHtml(data.error)}</span>`;
    }
  } catch (e) {
    container.innerHTML = `<span class="text-rose-400">Error: ${escapeHtml(e.message)}</span>`;
  }
}

function promptOrganizeNow() {
  const path = document.getElementById('organize-path-input')?.value || '~/Downloads';

  requestCommandPermission({
    command: `ops-assistant organize --path "${path}"`,
    description: `Categorizes loose files in ${path} into dedicated subdirectories.`,
    safetyLevel: 'MODIFYING',
    riskScore: 0.35,
    onApprove: async () => {
      showToast('Organizing directory...', 'info');
      try {
        const res = await fetch('/api/storage/organize/execute', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: path })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`Organized ${data.moved_count || 0} files successfully`, 'success');
          previewOrganize();
        } else {
          showToast('Error: ' + data.error, 'error');
        }
      } catch (e) {
        showToast('Error: ' + e.message, 'error');
      }
    }
  });
}

function promptCleanStorage() {
  requestCommandPermission({
    command: 'journalctl --vacuum-time=7d && rm -rf /tmp/* && sync',
    description: 'Purges old rotated journal logs, temporary scratch files, and frees system disk sectors.',
    safetyLevel: 'MODIFYING',
    riskScore: 0.40,
    onApprove: () => cleanStorage(false)
  });
}

async function cleanStorage(dryRun) {
  playScifiSound('scan');
  const container = document.getElementById('clean-result-container');
  if (container) {
    container.classList.remove('hidden');
    container.innerHTML = '<span class="text-slate-400">Scanning purge candidates...</span>';
  }

  try {
    const res = await fetch('/api/storage/clean', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dry_run: dryRun })
    });
    const data = await res.json();
    if (container) {
      container.innerHTML = `
        <div class="space-y-1.5 text-xs font-sans">
          <div class="text-white font-bold">${dryRun ? 'Purge Preview' : 'Purge Executed'}:</div>
          <div>Reclaimable Space: <span class="text-white font-bold">${data.reclaimable_mb || 0} MB</span></div>
          <div class="text-slate-400">${escapeHtml(data.details || 'Cache analysis complete.')}</div>
        </div>
      `;
    }
  } catch (e) {
    if (container) container.innerHTML = `<span class="text-rose-400">Error: ${escapeHtml(e.message)}</span>`;
  }
}

async function loadLargeFiles() {
  playScifiSound('scan');
  const container = document.getElementById('large-files-container');
  if (!container) return;

  container.innerHTML = '<p class="text-slate-400 font-mono">Scanning filesystem tree for files &gt;100MB...</p>';

  try {
    const res = await fetch('/api/storage/large-files?min_mb=100');
    if (res.ok) {
      const files = await res.json();
      if (!files || files.length === 0) {
        container.innerHTML = '<p class="text-slate-400 font-mono">No files larger than 100MB found.</p>';
        return;
      }
      container.innerHTML = files.map(f => `
        <div class="p-3 rounded-xl bg-black/40 border border-white/10 flex items-center justify-between text-xs font-mono">
          <span class="truncate max-w-[220px] text-white" title="${escapeHtml(f.path)}">${escapeHtml(f.path)}</span>
          <span class="text-white font-bold">${(f.size_mb||0).toFixed(1)} MB</span>
        </div>
      `).join('');
    }
  } catch (e) {
    container.innerHTML = `<p class="text-rose-400 font-mono">Error: ${escapeHtml(e.message)}</p>`;
  }
}

// ==========================================================================
// NETWORK & FIREWALL
// ==========================================================================
async function loadNetwork() {
  playScifiSound('scan');
  try {
    const res = await fetch('/api/network/ports');
    if (res.ok) {
      const ports = await res.json();
      const tbody = document.getElementById('network-ports-body');
      if (tbody) {
        tbody.innerHTML = (ports || []).map(p => `
          <tr>
            <td class="font-bold text-white font-mono">${p.port}</td>
            <td class="text-slate-400 uppercase font-mono">${p.proto}</td>
            <td class="text-slate-300 font-mono">${p.address}</td>
            <td class="text-slate-400 font-mono truncate max-w-[120px]">${escapeHtml(p.process || '-')}</td>
          </tr>
        `).join('');
      }
    }

    const fwRes = await fetch('/api/network/firewall/status');
    if (fwRes.ok) {
      const fw = await fwRes.json();
      const card = document.getElementById('firewall-status-card');
      if (card) {
        card.innerHTML = `
          <div class="space-y-1">
            <div class="flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full ${fw.active ? 'bg-emerald-400' : 'bg-rose-400'}"></span>
              <span class="font-bold text-white">${escapeHtml(fw.firewall_backend || 'UFW/NFT')}: ${fw.active ? 'ACTIVE & FILTERING' : 'INACTIVE'}</span>
            </div>
            <p class="text-[11px] text-slate-400">${escapeHtml(fw.summary || 'Firewall packet filtering active.')}</p>
          </div>
        `;
      }
    }
  } catch (e) {
    console.error('Failed to load network state', e);
  }
}

function promptFirewallRule(action) {
  const port = document.getElementById('fw-port-input')?.value;
  const proto = document.getElementById('fw-proto-select')?.value || 'tcp';

  if (!port) {
    showToast('Please specify a target port number', 'warning');
    return;
  }

  const cmd = `ufw ${action} ${port}/${proto}`;
  const rollbackCmd = action === 'allow' ? `ufw delete allow ${port}/${proto}` : `ufw delete deny ${port}/${proto}`;

  requestCommandPermission({
    command: cmd,
    description: `Modifies firewall rule matrix to ${action.toUpperCase()} ingress port ${port}/${proto}.`,
    safetyLevel: 'MODIFYING',
    riskScore: 0.45,
    rollback: rollbackCmd,
    onApprove: async () => {
      showToast(`Applying firewall rule: ${cmd}`, 'info');
      try {
        const res = await fetch('/api/network/firewall/rule', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: action, port: parseInt(port, 10), proto: proto })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`Firewall rule applied successfully`, 'success');
          loadNetwork();
        } else {
          showToast('Failed to apply firewall rule: ' + data.error, 'error');
        }
      } catch (e) {
        showToast('Error: ' + e.message, 'error');
      }
    }
  });
}

// ==========================================================================
// 16-CLASS FAILURE TAXONOMY & CAUSALITY DAG
// ==========================================================================
async function loadTaxonomyScenarios() {
  try {
    const res = await fetch('/api/taxonomy');
    if (res.ok) {
      const scenarios = await res.json();
      const grid = document.getElementById('taxonomy-scenarios-grid');
      if (!grid) return;

      grid.innerHTML = (scenarios || []).map(sc => `
        <button onclick="runTaxonomyScenario('${escapeHtml(sc.id)}')" class="p-4 rounded-2xl bg-white/[0.03] hover:bg-white/[0.08] border border-white/10 text-left transition space-y-1.5 group">
          <div class="text-xs font-semibold text-white group-hover:text-slate-200 flex items-center space-x-1.5">
            <i data-lucide="zap" class="w-3.5 h-3.5 text-white"></i>
            <span class="truncate">${escapeHtml(sc.name)}</span>
          </div>
          <div class="text-[10px] text-slate-500 font-mono truncate">${escapeHtml(sc.category || 'System')}</div>
        </button>
      `).join('');
      if (window.lucide) lucide.createIcons();
    }
  } catch (e) {
    console.error('Failed to load taxonomy scenarios', e);
  }
}

async function runTaxonomyScenario(scenarioId) {
  playScifiSound('scan');
  const reportContainer = document.getElementById('taxonomy-report-container');
  if (!reportContainer) return;

  reportContainer.classList.remove('hidden');
  document.getElementById('diag-report-title').textContent = `Diagnosing Scenario: ${scenarioId.toUpperCase()}...`;
  document.getElementById('diag-symptom').textContent = 'Correlating multi-vector telemetry across journald, dmesg, and PSI metrics...';
  document.getElementById('diag-root-cause').textContent = 'Constructing directed causality DAG...';
  document.getElementById('diag-rationale').textContent = 'Calculating topological in-degree minimization...';

  try {
    const res = await fetch('/api/taxonomy/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario_id: scenarioId })
    });
    const report = await res.json();
    playScifiSound('success');

    document.getElementById('diag-report-title').textContent = `XAI Diagnosis: ${report.taxonomy_class || scenarioId.toUpperCase()}`;
    document.getElementById('diag-symptom').textContent = report.symptom || 'Anomaly detected.';
    document.getElementById('diag-root-cause').textContent = report.root_cause || 'Root cause isolated.';
    document.getElementById('diag-rationale').textContent = report.rationale || 'Topological analysis completed.';

    const mermaidContainer = document.getElementById('mermaid-dag-container');
    if (mermaidContainer && report.mermaid_dag) {
      mermaidContainer.innerHTML = `<div class="mermaid">${escapeHtml(report.mermaid_dag)}</div>`;
      if (window.mermaid) {
        mermaid.init(undefined, mermaidContainer.querySelectorAll('.mermaid'));
      }
    } else if (mermaidContainer) {
      mermaidContainer.innerHTML = '<span class="text-xs font-mono text-slate-500">Topological Graph: InDegree=0 Root Isolated</span>';
    }

    const cmdsContainer = document.getElementById('diag-commands-container');
    if (cmdsContainer) {
      const cmds = report.remediation_commands || [];
      if (cmds.length === 0) {
        cmdsContainer.innerHTML = '<p class="text-xs text-white font-mono">No mutating commands required. State is clean.</p>';
      } else {
        cmdsContainer.innerHTML = cmds.map(c => `
          <div class="p-4 rounded-2xl bg-black/50 border border-white/10 space-y-2.5">
            <div class="flex items-center justify-between">
              <span class="${getSafetyBadgeClass(c.safety_level)} text-[10px] font-mono px-3 py-0.5 rounded-full uppercase">${c.safety_level || 'READ_ONLY'}</span>
              <span class="text-[10px] font-mono text-slate-400">Risk: ${(c.risk_score||0.05).toFixed(2)}</span>
            </div>
            <div class="p-3 rounded-xl bg-black/80 font-mono text-xs text-white border border-white/10 flex items-center justify-between">
              <span class="font-semibold text-white">$ ${escapeHtml(c.command)}</span>
              <button onclick="promptExecuteRemediation('${escapeHtml(c.command)}', '${escapeHtml(c.rationale || '')}', '${escapeHtml(c.safety_level || 'READ_ONLY')}', ${c.risk_score || 0.05}, '${escapeHtml(c.rollback || '')}')" class="btn-editorial-primary !py-1 !px-3 text-xs">
                Execute
              </button>
            </div>
            <p class="text-xs text-slate-300 font-sans leading-relaxed">${escapeHtml(c.rationale || 'Remediates root cause.')}</p>
          </div>
        `).join('');
      }
    }
  } catch (e) {
    showToast('Simulation error: ' + e.message, 'error');
  }
}

function promptExecuteRemediation(command, description, safetyLevel, riskScore, rollbackCommand) {
  requestCommandPermission({
    command: command,
    description: description,
    safetyLevel: safetyLevel,
    riskScore: riskScore,
    rollback: rollbackCommand,
    onApprove: () => executeCommandDirect(command, rollbackCommand, null)
  });
}

// ==========================================================================
// PACKAGE MANAGER
// ==========================================================================
async function searchPackage() {
  playScifiSound('scan');
  const pkg = document.getElementById('pkg-search-input')?.value;
  const container = document.getElementById('pkg-result-container');

  if (!pkg || !container) return;
  container.innerHTML = '<p class="text-slate-400 font-mono">Querying multi-distro package repository...</p>';

  try {
    const res = await fetch(`/api/packages/search?query=${encodeURIComponent(pkg)}`);
    if (res.ok) {
      const data = await res.json();
      container.innerHTML = `
        <div class="space-y-2.5 font-sans">
          <div class="flex items-center justify-between text-white font-bold">
            <span class="font-editorial italic text-base">${escapeHtml(data.package || pkg)}</span>
            <span class="text-xs text-slate-400 font-mono">${data.installed ? 'INSTALLED' : 'AVAILABLE IN REPO'}</span>
          </div>
          <p class="text-xs text-slate-300 leading-relaxed">${escapeHtml(data.description || 'Package metadata located.')}</p>
          <div class="pt-2 flex space-x-2.5">
            ${!data.installed ? `
              <button onclick="requestCommandPermission({command: 'pacman -S --noconfirm ${pkg}', description: 'Installs package ${pkg}', safetyLevel: 'MODIFYING', riskScore: 0.35, onApprove: () => executeCommandDirect('pacman -S --noconfirm ${pkg}', 'pacman -R --noconfirm ${pkg}')})" class="btn-editorial-primary !py-1.5 !px-3.5 text-xs">
                Install Package
              </button>
            ` : `
              <button onclick="requestCommandPermission({command: 'pacman -R --noconfirm ${pkg}', description: 'Removes package ${pkg}', safetyLevel: 'MODIFYING', riskScore: 0.40, onApprove: () => executeCommandDirect('pacman -R --noconfirm ${pkg}', 'pacman -S --noconfirm ${pkg}')})" class="btn-editorial-primary !py-1.5 !px-3.5 text-xs">
                Remove Package
              </button>
            `}
          </div>
        </div>
      `;
    }
  } catch (e) {
    container.innerHTML = `<p class="text-rose-400 font-mono">Error: ${escapeHtml(e.message)}</p>`;
  }
}

// ==========================================================================
// DIRECT COMMAND RUNNER & DESKTOP TOOLS
// ==========================================================================
function promptDirectCommand() {
  const cmd = document.getElementById('direct-cmd-input')?.value;
  if (!cmd) {
    showToast('Enter a command to run', 'warning');
    return;
  }

  requestCommandPermission({
    command: cmd,
    description: 'Direct shell execution requested through AST safety gate.',
    safetyLevel: 'MODIFYING',
    riskScore: 0.35,
    onApprove: () => executeCommandDirect(cmd, null, null)
  });
}

function promptDownload() {
  const url = document.getElementById('download-url-input')?.value;
  const dest = document.getElementById('download-dest-input')?.value || '~/Downloads';
  const autoExtract = document.getElementById('download-auto-extract')?.checked;

  if (!url) {
    showToast('Please specify a download URL', 'warning');
    return;
  }

  requestCommandPermission({
    command: `ops-assistant download "${url}" --dest "${dest}" ${autoExtract ? '--auto-extract' : ''}`,
    description: `Downloads file from ${url} into ${dest} with hash integrity verification.`,
    safetyLevel: 'MODIFYING',
    riskScore: 0.30,
    onApprove: async () => {
      showToast('Starting stream download...', 'info');
      const container = document.getElementById('download-result-container');
      if (container) {
        container.classList.remove('hidden');
        container.innerHTML = '<span class="text-slate-400">Streaming bytes from remote host...</span>';
      }
      try {
        const res = await fetch('/api/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: url, destination: dest, auto_extract: autoExtract })
        });
        const data = await res.json();
        if (container) {
          if (data.success) {
            container.innerHTML = `
              <div class="text-white font-bold">&check; Download completed: ${escapeHtml(data.filename || 'file')} (${(data.size_mb || 0).toFixed(2)} MB) in ${dest}</div>
            `;
          } else {
            container.innerHTML = `<span class="text-rose-400">Download failed: ${escapeHtml(data.error)}</span>`;
          }
        }
      } catch (e) {
        if (container) container.innerHTML = `<span class="text-rose-400">Error: ${escapeHtml(e.message)}</span>`;
      }
    }
  });
}

async function desktopAction(action, params) {
  playScifiSound('execute');
  try {
    const res = await fetch('/api/desktop/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action, ...params })
    });
    const data = await res.json();
    if (data.success) {
      showToast('Desktop action triggered', 'success');
    } else {
      showToast('Failed to trigger action: ' + data.error, 'error');
    }
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}

// ==========================================================================
// MODAL & UTILITY HELPERS
// ==========================================================================
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove('hidden');
}

function closeModal(id) {
  playScifiSound('click');
  const modal = document.getElementById(id);
  if (modal) modal.classList.add('hidden');
}

function getSafetyBadgeClass(lvl) {
  if (lvl === 'READ_ONLY') return 'badge-readonly';
  if (lvl === 'MODIFYING') return 'badge-modifying';
  if (lvl === 'HIGH_RISK') return 'badge-highrisk';
  if (lvl === 'DESTRUCTIVE') return 'badge-destructive';
  return 'badge-readonly';
}

function getSafetyTextColor(lvl) {
  if (lvl === 'READ_ONLY') return 'text-sky-400';
  if (lvl === 'MODIFYING') return 'text-amber-400';
  if (lvl === 'HIGH_RISK') return 'text-rose-400';
  if (lvl === 'DESTRUCTIVE') return 'text-rose-500';
  return 'text-white';
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
