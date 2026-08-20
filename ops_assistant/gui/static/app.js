// ==========================================================================
// LinuxOps Assistant — Cyber Red & Blue Dual-Tone Client Application Logic
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
// SCI-FI WEB AUDIO SYNTHESIZER
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
      osc.frequency.setValueAtTime(820, now);
      osc.frequency.exponentialRampToValueAtTime(1450, now + 0.04);
      gain.gain.setValueAtTime(0.05, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
      osc.start(now);
      osc.stop(now + 0.04);
    } else if (type === 'scan' || type === 'execute') {
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(420, now);
      osc.frequency.exponentialRampToValueAtTime(1100, now + 0.09);
      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
      osc.start(now);
      osc.stop(now + 0.12);
    } else if (type === 'success') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(523.25, now);
      osc.frequency.setValueAtTime(659.25, now + 0.05);
      osc.frequency.setValueAtTime(783.99, now + 0.10);
      gain.gain.setValueAtTime(0.06, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.20);
      osc.start(now);
      osc.stop(now + 0.20);
    } else if (type === 'alert' || type === 'error') {
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(360, now);
      osc.frequency.exponentialRampToValueAtTime(150, now + 0.14);
      gain.gain.setValueAtTime(0.07, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.14);
      osc.start(now);
      osc.stop(now + 0.14);
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
      ? '<i data-lucide="volume-2" class="w-3.5 h-3.5 text-[#00D2FF]"></i><span class="text-[#00D2FF] text-[10px]">SFX ON</span>'
      : '<i data-lucide="volume-x" class="w-3.5 h-3.5 text-[#62759B]"></i><span class="text-[#62759B] text-[10px]">SFX OFF</span>';
    if (window.lucide) lucide.createIcons();
  }
  if (sfxEnabled) playScifiSound('click');
}

function toggleScanlines() {
  const overlay = document.getElementById('scanline-layer');
  const btn = document.getElementById('btn-toggle-scanlines');
  if (overlay) {
    overlay.classList.toggle('hidden');
    const isHidden = overlay.classList.contains('hidden');
    if (btn) {
      btn.innerHTML = !isHidden
        ? '<i data-lucide="tv" class="w-3.5 h-3.5 text-[#FF0055]"></i><span class="text-[#FF0055] text-[10px]">SCANLINES</span>'
        : '<i data-lucide="tv" class="w-3.5 h-3.5 text-[#62759B]"></i><span class="text-[#62759B] text-[10px]">CLEAN HUD</span>';
      if (window.lucide) lucide.createIcons();
    }
  }
  playScifiSound('click');
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

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
  if (window.lucide) {
    lucide.createIcons();
  }
  initCharts();
  startTelemetrySSE();
  loadInitialData();

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
    // '/' to focus agent prompt
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
      e.preventDefault();
      const promptInput = document.getElementById('agent-prompt-input');
      if (promptInput) {
        switchTab('home');
        promptInput.focus();
        playScifiSound('click');
      }
    }
    // Escape to close modals
    if (e.key === 'Escape') {
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
  let iconColor = 'text-[#00D2FF]';
  if (type === 'success') {
    iconName = 'check-circle';
    iconColor = 'text-[#00D2FF]';
    playScifiSound('success');
  } else if (type === 'error') {
    iconName = 'alert-circle';
    iconColor = 'text-[#FF0055]';
    playScifiSound('alert');
  } else if (type === 'warning') {
    iconName = 'alert-triangle';
    iconColor = 'text-[#FFB800]';
    playScifiSound('alert');
  } else {
    playScifiSound('click');
  }

  toast.innerHTML = `
    <div class="mt-0.5 ${iconColor} shrink-0 drop-shadow-[0_0_6px_currentColor]">
      <i data-lucide="${iconName}" class="w-4 h-4"></i>
    </div>
    <div class="flex-1 text-xs text-[#F0F6FF] leading-relaxed break-words font-tech font-semibold">${escapeHtml(message)}</div>
    <button onclick="this.parentElement.remove()" class="text-[#62759B] hover:text-[#00D2FF] font-mono text-sm leading-none">&times;</button>
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

    // Handlers
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
  'home': 'AI Ops Deck',
  'health': 'System Health & PSI Telemetry',
  'services': 'Services & Process Management',
  'storage': 'Storage Matrix & Cleanup',
  'network': 'Network & Ports Control',
  'taxonomy': '16-Class Failure Taxonomy',
  'packages': 'Package Nexus',
  'desktop': 'Cyber Runner & Portals'
};

function switchTab(tabId) {
  playScifiSound('tab');
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));

  const activeContent = document.getElementById('tab-content-' + tabId);
  const activeBtn = document.getElementById('tab-btn-' + tabId);

  if (activeContent) activeContent.classList.remove('hidden');
  if (activeBtn) activeBtn.classList.add('active');

  const titleEl = document.getElementById('current-tab-title');
  if (titleEl && TAB_TITLES[tabId]) {
    titleEl.textContent = TAB_TITLES[tabId];
  }

  // Trigger lazy loading
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

  // Header
  const dInfo = snap.distro_info || {};
  const distroName = dInfo.distro_name || 'Linux';
  document.getElementById('header-hostname').textContent = (snap.hostname || 'localhost').toUpperCase();
  document.getElementById('header-distro').textContent = distroName;
  document.getElementById('header-kernel').textContent = 'Kernel ' + (snap.kernel_release || '');

  const pressureBadge = document.getElementById('header-pressure');
  pressureBadge.textContent = 'PSI: ' + (snap.pressure_status || 'NORMAL');
  if (snap.pressure_status === 'ELEVATED') {
    pressureBadge.className = 'font-mono text-[11px] font-bold text-[#FFB800] drop-shadow-[0_0_6px_rgba(255,184,0,0.5)]';
  } else if (snap.pressure_status === 'CRITICAL') {
    pressureBadge.className = 'font-mono text-[11px] font-bold text-[#FF0055] drop-shadow-[0_0_8px_rgba(255,0,85,0.7)]';
  } else {
    pressureBadge.className = 'font-mono text-[11px] font-bold text-[#00D2FF] drop-shadow-[0_0_6px_rgba(0,210,255,0.5)]';
  }

  // Health Cards
  const cpu = snap.cpu || {};
  const mem = snap.memory || {};
  const load = snap.load || {};

  const totalCpuPct = (cpu.user_pct || 0) + (cpu.system_pct || 0);
  document.getElementById('health-cpu-pct').textContent = totalCpuPct.toFixed(1) + '%';
  document.getElementById('health-cpu-cores').textContent = (cpu.core_count || 1) + ' Cores';
  document.getElementById('health-cpu-breakdown').textContent = `User: ${(cpu.user_pct||0).toFixed(1)}% | Sys: ${(cpu.system_pct||0).toFixed(1)}% | IO: ${(cpu.iowait_pct||0).toFixed(1)}%`;

  document.getElementById('health-ram-pct').textContent = (mem.used_percent || 0).toFixed(1) + '%';
  document.getElementById('health-ram-avail').textContent = Math.round(mem.used_mb||0) + ' / ' + Math.round(mem.total_mb||0) + ' MB';
  document.getElementById('health-swap-info').textContent = 'Swap: ' + (mem.swap_used_percent||0).toFixed(1) + '% used';

  document.getElementById('health-load-1m').textContent = (load.load_1m || 0).toFixed(2);
  document.getElementById('health-load-5m').textContent = `5m: ${(load.load_5m||0).toFixed(2)} | 15m: ${(load.load_15m||0).toFixed(2)}`;
  document.getElementById('health-procs-count').textContent = `${load.running_processes||0} running / ${load.total_processes||0} procs`;

  document.getElementById('health-psi-badge').textContent = snap.pressure_status || 'NORMAL';
  document.getElementById('health-zombie-count').textContent = (cpu.zombie_count || 0) + ' Zombies';
  document.getElementById('health-uptime-str').textContent = 'Uptime: ' + ((snap.uptime_seconds||0)/3600).toFixed(1) + ' hrs';

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

  // Update PSI & Disks tables
  renderPSITable(snap.psi_metrics);
  renderDisksTable(snap.disks);
}

function initCharts() {
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    scales: {
      y: { min: 0, max: 100, grid: { color: 'rgba(0,210,255,0.08)' }, ticks: { color: '#62759B', font: { family: 'JetBrains Mono', size: 10 } } },
      x: { grid: { color: 'rgba(0,210,255,0.08)' }, ticks: { color: '#62759B', font: { family: 'JetBrains Mono', size: 10 }, maxRotation: 0 } }
    },
    plugins: { legend: { labels: { color: '#F0F6FF', font: { family: 'Space Grotesk', size: 12, weight: 600 }, boxWidth: 12 } } }
  };

  const ctxCpu = document.getElementById('chart-cpu');
  if (ctxCpu) {
    cpuChart = new Chart(ctxCpu, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'CPU Total %', data: [], borderColor: '#00D2FF', backgroundColor: 'rgba(0, 210, 255, 0.16)', fill: true, tension: 0.25, borderWidth: 2 },
          { label: 'I/O Wait %', data: [], borderColor: '#FF0055', borderDash: [3, 3], fill: false, tension: 0.25, borderWidth: 1.5 }
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
          { label: 'RAM Used %', data: [], borderColor: '#FF0055', backgroundColor: 'rgba(255, 0, 85, 0.16)', fill: true, tension: 0.25, borderWidth: 2 },
          { label: 'Swap Used %', data: [], borderColor: '#0066FF', borderDash: [3, 3], fill: false, tension: 0.25, borderWidth: 1.5 }
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
    container.innerHTML = '<p class="text-[#62759B] font-mono">Kernel PSI metrics not available (/proc/pressure unmounted).</p>';
    return;
  }

  let html = '<div class="grid grid-cols-3 gap-2.5">';
  for (const [subsys, metrics] of Object.entries(psi)) {
    const avg10 = metrics.some_avg10 || 0;
    const colorClass = avg10 > 20 ? 'text-[#FF0055]' : (avg10 > 5 ? 'text-[#FFB800]' : 'text-[#00D2FF]');
    html += `<div class="p-3 rounded-lg bg-[#050711] border border-[#00D2FF]/20 space-y-1">
      <span class="font-display font-bold uppercase text-[#62759B] text-[10px]">${subsys}</span>
      <div class="text-xl font-bold font-mono ${colorClass} drop-shadow-[0_0_6px_currentColor]">${avg10.toFixed(2)}%</div>
      <p class="text-[10px] text-[#62759B] font-mono">60s: ${(metrics.some_avg60||0).toFixed(2)}% | 300s: ${(metrics.some_avg300||0).toFixed(2)}%</p>
    </div>`;
  }
  html += '</div>';
  container.innerHTML = html;
}

function renderDisksTable(disks) {
  const container = document.getElementById('disks-table-container');
  if (!container) return;
  if (!disks || disks.length === 0) {
    container.innerHTML = '<p class="text-[#62759B] font-mono">No filesystem mounts discovered.</p>';
    return;
  }

  let html = '<div class="space-y-2">';
  disks.slice(0, 4).forEach(d => {
    const color = d.used_percent > 85 ? 'bg-[#FF0055]' : (d.used_percent > 70 ? 'bg-[#FFB800]' : 'bg-[#00D2FF]');
    html += `<div class="p-2.5 rounded-lg bg-[#050711] border border-[#00D2FF]/20 space-y-1.5 font-mono text-xs">
      <div class="flex justify-between">
        <span class="text-white font-bold">${d.mountpoint}</span>
        <span class="text-[#00D2FF]">${d.used_gb.toFixed(1)} / ${d.total_gb.toFixed(1)} GB (${d.used_percent.toFixed(1)}%)</span>
      </div>
      <div class="w-full bg-black/80 h-1.5 rounded-full overflow-hidden border border-[#00D2FF]/20">
        <div class="${color} h-full transition-all duration-500 shadow-[0_0_8px_currentColor]" style="width: ${Math.min(100, d.used_percent)}%"></div>
      </div>
    </div>`;
  });
  html += '</div>';
  container.innerHTML = html;
}

// ==========================================================================
// AI OPS AGENT: CHAT, REASONING & COMMAND PERMISSION FEED
// ==========================================================================
function quickPrompt(text) {
  playScifiSound('click');
  const input = document.getElementById('agent-prompt-input');
  if (input) {
    input.value = text;
    submitAgentPrompt(text);
  }
}

async function submitAgentPrompt(promptText) {
  playScifiSound('execute');
  const feed = document.getElementById('agent-feed-container');
  const input = document.getElementById('agent-prompt-input');
  const btn = document.getElementById('btn-submit-prompt');

  if (!feed) return;

  // Append user prompt item
  const userCard = document.createElement('div');
  userCard.className = 'p-3.5 rounded-lg bg-[#080C1E] border border-[#00D2FF]/30 font-mono text-xs text-white space-y-1 shadow-[0_0_12px_rgba(0,210,255,0.15)]';
  userCard.innerHTML = `
    <div class="flex items-center justify-between text-[10px] text-[#00D2FF] font-display font-bold">
      <span class="flex items-center space-x-1">
        <i data-lucide="user" class="w-3 h-3 text-[#00D2FF]"></i>
        <span>SYSADMIN COMMAND VECTOR</span>
      </span>
      <span>${new Date().toLocaleTimeString()}</span>
    </div>
    <div class="text-xs text-[#F0F6FF] font-semibold pl-4 border-l-2 border-[#00D2FF]">${escapeHtml(promptText)}</div>
  `;
  feed.appendChild(userCard);

  // Append thinking placeholder
  const agentCard = document.createElement('div');
  agentCard.className = 'p-4 rounded-lg bg-[#0C1229] border border-[#00D2FF]/20 space-y-2';
  agentCard.innerHTML = `
    <div class="flex items-center space-x-2 text-xs font-display font-bold text-[#00D2FF]">
      <span class="inline-block w-2 h-2 rounded-full bg-[#00D2FF] animate-ping"></span>
      <span>AI-OS REASONING &amp; AST VALIDATION IN PROGRESS...</span>
    </div>
  `;
  feed.appendChild(agentCard);

  // Scroll feed to bottom
  feed.parentElement.scrollTop = feed.parentElement.scrollHeight;

  if (input) input.value = '';
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
  } catch (e) {
    agentCard.innerHTML = `
      <div class="text-xs text-[#FF0055] font-mono font-bold flex items-center space-x-2">
        <i data-lucide="alert-circle" class="w-4 h-4"></i>
        <span>Agent Dispatch Error: ${escapeHtml(e.message)}</span>
      </div>
    `;
  } finally {
    if (btn) btn.disabled = false;
    if (window.lucide) lucide.createIcons();
    feed.parentElement.scrollTop = feed.parentElement.scrollHeight;
  }
}

function renderAgentResponseCard(card, data) {
  playScifiSound('success');
  const safetyClass = getSafetyBadgeClass(data.safety_level || 'READ_ONLY');
  const isModifying = data.safety_level && data.safety_level !== 'READ_ONLY';
  const cardBorderClass = isModifying ? 'command-approval-card modifying' : 'scifi-card';

  card.className = `p-5 space-y-3.5 ${cardBorderClass}`;

  let stepsHtml = '';
  if (data.steps && data.steps.length > 0) {
    stepsHtml = `
      <div class="space-y-1 text-[11px] text-[#A0B3D6] font-mono border-l-2 border-[#00D2FF]/40 pl-3 py-0.5">
        ${data.steps.map(s => `<div>&bull; ${escapeHtml(s)}</div>`).join('')}
      </div>
    `;
  }

  // Planned Command Section
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
      <div class="space-y-2 pt-1">
        <div class="text-[10px] font-display font-bold uppercase tracking-wider text-[#00D2FF]">PLANNED COMMAND EXECUTION &amp; GUARDRAILS:</div>
        ${plannedCmds.map((c) => `
          <div class="p-3.5 rounded-lg bg-[#050711] border border-[#00D2FF]/25 space-y-2.5 shadow-[inset_0_0_12px_rgba(0,0,0,0.8)]">
            <div class="flex items-center justify-between">
              <span class="${getSafetyBadgeClass(c.safety_level)} text-[10px] font-mono px-2 py-0.5 rounded font-bold uppercase">${c.safety_level || 'READ_ONLY'}</span>
              <span class="text-[10px] font-mono text-[#00D2FF]">Risk Score: ${(c.risk_score || 0.05).toFixed(2)}</span>
            </div>

            <!-- Exact Command -->
            <div class="p-2.5 rounded bg-black/80 border border-[#00D2FF]/20 font-mono text-xs text-white flex items-start justify-between space-x-2">
              <div class="break-all select-all flex-1">
                <span class="text-[#00D2FF] select-none font-bold">$ </span>
                <span class="font-semibold">${escapeHtml(c.command)}</span>
              </div>
              <button onclick="navigator.clipboard.writeText('${escapeHtml(c.command)}'); showToast('Command copied', 'info', 2000);" class="text-[#00D2FF] hover:text-white px-1" title="Copy Command">
                <i data-lucide="copy" class="w-3.5 h-3.5"></i>
              </button>
            </div>

            <!-- Short Description of What It Will Do -->
            <div class="text-xs text-[#F0F6FF] font-sans leading-relaxed">
              <span class="text-[#62759B] text-[10px] font-display font-bold uppercase block">RATIONALE:</span>
              ${escapeHtml(c.description || 'Executes operation on the system.')}
            </div>

            ${c.rollback_command ? `
              <div class="text-[11px] font-mono text-[#A0B3D6]">
                <span class="text-[#FFB800] font-bold">Rollback:</span> ${escapeHtml(c.rollback_command)}
              </div>
            ` : ''}

            <!-- Permission Confirmation Buttons -->
            <div class="flex items-center space-x-2 pt-1 border-t border-[#00D2FF]/15">
              <button onclick="executeCommandDirect('${escapeHtml(c.command)}', '${escapeHtml(c.rollback_command || '')}', this.closest('.command-approval-card'))" class="btn btn-primary px-3.5 py-1.5 text-xs">
                <i data-lucide="play" class="w-3 h-3"></i>
                <span>AUTHORIZE &amp; EXECUTE</span>
              </button>
              <button onclick="executeDryRunSandbox('${escapeHtml(c.command)}')" class="btn btn-secondary px-3.5 py-1.5 text-xs">
                <i data-lucide="flask-conical" class="w-3 h-3"></i>
                <span>DRY-RUN SANDBOX</span>
              </button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // Diagnostic Report / Output JSON viewer
  let outputDetailsHtml = '';
  if (data.output && !plannedCmds.length) {
    outputDetailsHtml = `
      <pre class="p-3.5 rounded-lg bg-[#050711] border border-[#00D2FF]/25 text-[11px] font-mono text-[#00D2FF] overflow-x-auto max-h-48 whitespace-pre-wrap shadow-[inset_0_0_10px_rgba(0,0,0,0.8)]">${escapeHtml(JSON.stringify(data.output, null, 2))}</pre>
    `;
  }

  let rollbackBtnHtml = '';
  if (data.rollback_command && data.executed) {
    rollbackBtnHtml = `
      <button onclick="executeRollback('${escapeHtml(data.rollback_command)}')" class="btn btn-secondary px-3 py-1 text-xs">
        <i data-lucide="undo-2" class="w-3 h-3"></i>
        <span>Rollback State</span>
      </button>
    `;
  }

  card.innerHTML = `
    <div class="flex items-center justify-between text-xs border-b border-[#00D2FF]/20 pb-2 font-mono">
      <div class="flex items-center space-x-2">
        <span class="font-bold text-white flex items-center space-x-1.5">
          <i data-lucide="bot" class="w-4 h-4 text-[#00D2FF]"></i>
          <span class="font-display">INTENT: ${escapeHtml(data.intent || 'ACTION')}</span>
        </span>
        <span class="${safetyClass} text-[10px] px-2 py-0.5 rounded font-bold uppercase">${escapeHtml(data.safety_level || 'READ_ONLY')}</span>
      </div>
      <span class="text-[#62759B] text-[10px]">${new Date().toLocaleTimeString()}</span>
    </div>

    <div class="text-xs text-[#F0F6FF] font-sans font-semibold">${escapeHtml(data.summary || 'Analysis complete.')}</div>
    
    ${stepsHtml}
    ${commandSectionHtml}
    ${outputDetailsHtml}

    <div class="flex items-center justify-between pt-1 font-mono text-[10px] text-[#62759B]">
      <span>Risk Score: ${(data.risk_score || 0.05).toFixed(2)}</span>
      ${rollbackBtnHtml}
    </div>
  `;

  if (window.lucide) lucide.createIcons();
}

function clearAgentFeed() {
  playScifiSound('click');
  const feed = document.getElementById('agent-feed-container');
  if (feed) {
    feed.innerHTML = '<p class="text-xs font-mono text-[#62759B] p-2">Tactical reasoning feed purged.</p>';
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

    // Append execution result box to card
    if (cardEl) {
      const resultBox = document.createElement('div');
      resultBox.className = 'p-3.5 rounded-lg bg-[#050711] border border-[#00D2FF]/30 space-y-1.5 font-mono text-xs shadow-[inset_0_0_10px_rgba(0,0,0,0.8)]';
      resultBox.innerHTML = `
        <div class="flex items-center justify-between text-[10px] text-[#62759B]">
          <span class="font-bold text-[#00D2FF]">&check; EXECUTION COMPLETE</span>
          <span>Exit: ${data.returncode} | Latency: ${data.latency_ms || 0}ms</span>
        </div>
        <pre class="text-[11px] text-[#00D2FF] overflow-x-auto max-h-36 whitespace-pre-wrap">${escapeHtml(data.stdout || data.stderr || '(No output returned)')}</pre>
        ${(rollbackCmd || data.rollback_command) ? `
          <div class="pt-1 flex justify-end">
            <button onclick="executeRollback('${escapeHtml(rollbackCmd || data.rollback_command)}')" class="btn btn-secondary px-2.5 py-1 text-[10px]">
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
    tbody.innerHTML = '<tr><td colspan="3" class="text-center text-[#62759B] py-6 font-mono">No matching services found.</td></tr>';
    return;
  }

  tbody.innerHTML = services.map(s => {
    const isRunning = s.active_state === 'active' || s.sub_state === 'running';
    const isFailed = s.active_state === 'failed';
    const statusColor = isFailed ? 'text-[#FF0055]' : (isRunning ? 'text-[#00D2FF]' : 'text-[#62759B]');
    const dotColor = isFailed ? 'bg-[#FF0055]' : (isRunning ? 'bg-[#00D2FF]' : 'bg-[#62759B]');

    return `
      <tr>
        <td class="font-semibold text-white">
          <div class="flex items-center space-x-2">
            <span class="w-2 h-2 rounded-full ${dotColor} drop-shadow-[0_0_4px_currentColor]"></span>
            <span>${escapeHtml(s.unit)}</span>
          </div>
        </td>
        <td class="${statusColor} font-bold">${escapeHtml(s.active_state)} (${escapeHtml(s.sub_state)})</td>
        <td class="text-right space-x-1.5">
          <button onclick="promptServiceAction('${escapeHtml(s.unit)}', '${isRunning ? 'restart' : 'start'}')" class="btn btn-secondary px-2.5 py-1 text-[11px]">
            ${isRunning ? 'Restart' : 'Start'}
          </button>
          ${isRunning ? `
            <button onclick="promptServiceAction('${escapeHtml(s.unit)}', 'stop')" class="btn btn-danger px-2.5 py-1 text-[11px]">
              Stop
            </button>
          ` : ''}
          <button onclick="viewServiceLogs('${escapeHtml(s.unit)}')" class="btn btn-ghost px-2 py-1 text-[11px] text-[#00D2FF]">
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

  if (title) title.textContent = `JOURNAL LOGS: ${svc}`;
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
          <td class="font-mono text-[#00D2FF]">${p.pid}</td>
          <td class="text-[#62759B]">${escapeHtml(p.user || 'root')}</td>
          <td class="font-bold text-white">${(p.cpu_pct||0).toFixed(1)}%</td>
          <td class="text-[#FF0055] font-bold">${(p.mem_pct||0).toFixed(1)}%</td>
          <td class="truncate max-w-[140px] text-white" title="${escapeHtml(p.command)}">${escapeHtml(p.command)}</td>
          <td class="text-right">
            <button onclick="promptKillProcess(${p.pid}, '${escapeHtml(p.command)}')" class="btn btn-danger px-2 py-0.5 text-[10px]">
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
  container.innerHTML = '<span class="text-[#00D2FF] font-mono">Analyzing target directory topology...</span>';

  try {
    const res = await fetch('/api/storage/organize/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: path })
    });
    const data = await res.json();
    if (data.success) {
      container.innerHTML = `
        <div class="space-y-1 text-xs">
          <div class="text-[#00D2FF] font-bold">Preview: Discovered ${data.total_files || 0} candidate files to organize:</div>
          <div class="space-y-0.5 text-[#F0F6FF]">
            ${(data.moves || []).slice(0, 10).map(m => `<div>&bull; ${escapeHtml(m.source)} &rarr; <span class="text-[#00D2FF]">${escapeHtml(m.destination)}</span></div>`).join('')}
            ${(data.moves || []).length > 10 ? `<div class="text-[#62759B]">...and ${data.moves.length - 10} more items</div>` : ''}
          </div>
        </div>
      `;
    } else {
      container.innerHTML = `<span class="text-[#FF0055]">Error: ${escapeHtml(data.error)}</span>`;
    }
  } catch (e) {
    container.innerHTML = `<span class="text-[#FF0055]">Error: ${escapeHtml(e.message)}</span>`;
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
    container.innerHTML = '<span class="text-[#00D2FF]">Scanning purge candidates...</span>';
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
        <div class="space-y-1 text-xs">
          <div class="text-[#00D2FF] font-bold">${dryRun ? 'Purge Preview' : 'Purge Executed'}:</div>
          <div>Reclaimable Space: <span class="text-white font-bold">${data.reclaimable_mb || 0} MB</span></div>
          <div class="text-[#62759B]">${escapeHtml(data.details || 'Cache analysis complete.')}</div>
        </div>
      `;
    }
  } catch (e) {
    if (container) container.innerHTML = `<span class="text-[#FF0055]">Error: ${escapeHtml(e.message)}</span>`;
  }
}

async function loadLargeFiles() {
  playScifiSound('scan');
  const container = document.getElementById('large-files-container');
  if (!container) return;

  container.innerHTML = '<p class="text-[#00D2FF] font-mono">Scanning filesystem tree for files &gt;100MB...</p>';

  try {
    const res = await fetch('/api/storage/large-files?min_mb=100');
    if (res.ok) {
      const files = await res.json();
      if (!files || files.length === 0) {
        container.innerHTML = '<p class="text-[#00D2FF] font-mono">No files larger than 100MB found.</p>';
        return;
      }
      container.innerHTML = files.map(f => `
        <div class="p-2 rounded-lg bg-[#050711] border border-[#00D2FF]/15 flex items-center justify-between text-xs font-mono">
          <span class="truncate max-w-[220px] text-white" title="${escapeHtml(f.path)}">${escapeHtml(f.path)}</span>
          <span class="text-[#FF0055] font-bold">${(f.size_mb||0).toFixed(1)} MB</span>
        </div>
      `).join('');
    }
  } catch (e) {
    container.innerHTML = `<p class="text-[#FF0055] font-mono">Error: ${escapeHtml(e.message)}</p>`;
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
            <td class="font-bold text-[#00D2FF] font-mono">${p.port}</td>
            <td class="text-[#62759B] uppercase font-mono">${p.proto}</td>
            <td class="text-white font-mono">${p.address}</td>
            <td class="text-[#FF0055] font-mono truncate max-w-[120px]">${escapeHtml(p.process || '-')}</td>
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
              <span class="w-2 h-2 rounded-full ${fw.active ? 'bg-[#00D2FF]' : 'bg-[#FF0055]'} drop-shadow-[0_0_4px_currentColor]"></span>
              <span class="font-bold text-white">${escapeHtml(fw.firewall_backend || 'UFW/NFT')}: ${fw.active ? 'ACTIVE & FILTERING' : 'INACTIVE'}</span>
            </div>
            <p class="text-[11px] text-[#62759B]">${escapeHtml(fw.summary || 'Firewall packet filtering active.')}</p>
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
        <button onclick="runTaxonomyScenario('${escapeHtml(sc.id)}')" class="p-3.5 rounded-lg bg-[#080C1E] hover:bg-gradient-to-r hover:from-[#00D2FF]/20 hover:to-[#FF0055]/20 border border-[#00D2FF]/20 text-left transition space-y-1 group shadow-[0_2px_8px_rgba(0,0,0,0.5)]">
          <div class="text-xs font-display font-bold text-white group-hover:text-[#00D2FF] flex items-center space-x-1.5">
            <i data-lucide="zap" class="w-3.5 h-3.5 text-[#FF0055]"></i>
            <span class="truncate">${escapeHtml(sc.name)}</span>
          </div>
          <div class="text-[10px] text-[#62759B] font-mono truncate">${escapeHtml(sc.category || 'System')}</div>
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
  document.getElementById('diag-report-title').textContent = `DIAGNOSING SCENARIO: ${scenarioId.toUpperCase()}...`;
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

    document.getElementById('diag-report-title').textContent = `XAI DIAGNOSIS // ${report.taxonomy_class || scenarioId.toUpperCase()}`;
    document.getElementById('diag-symptom').textContent = report.symptom || 'Anomaly detected.';
    document.getElementById('diag-root-cause').textContent = report.root_cause || 'Root cause isolated.';
    document.getElementById('diag-rationale').textContent = report.rationale || 'Topological analysis completed.';

    // Render Mermaid DAG if available
    const mermaidContainer = document.getElementById('mermaid-dag-container');
    if (mermaidContainer && report.mermaid_dag) {
      mermaidContainer.innerHTML = `<div class="mermaid">${escapeHtml(report.mermaid_dag)}</div>`;
      if (window.mermaid) {
        mermaid.init(undefined, mermaidContainer.querySelectorAll('.mermaid'));
      }
    } else if (mermaidContainer) {
      mermaidContainer.innerHTML = '<span class="text-xs font-mono text-[#62759B]">Topological Graph: InDegree=0 Root Isolated</span>';
    }

    // Render Remediation Commands
    const cmdsContainer = document.getElementById('diag-commands-container');
    if (cmdsContainer) {
      const cmds = report.remediation_commands || [];
      if (cmds.length === 0) {
        cmdsContainer.innerHTML = '<p class="text-xs text-[#00D2FF] font-mono">No mutating commands required. State is clean.</p>';
      } else {
        cmdsContainer.innerHTML = cmds.map(c => `
          <div class="p-3.5 rounded-lg bg-[#050711] border border-[#00D2FF]/25 space-y-2">
            <div class="flex items-center justify-between">
              <span class="${getSafetyBadgeClass(c.safety_level)} text-[10px] font-mono px-2 py-0.5 rounded font-bold uppercase">${c.safety_level || 'READ_ONLY'}</span>
              <span class="text-[10px] font-mono text-[#00D2FF]">Risk: ${(c.risk_score||0.05).toFixed(2)}</span>
            </div>
            <div class="p-2 rounded bg-black/80 font-mono text-xs text-white border border-[#00D2FF]/20 flex items-center justify-between">
              <span class="font-semibold text-[#00D2FF]">$ ${escapeHtml(c.command)}</span>
              <button onclick="promptExecuteRemediation('${escapeHtml(c.command)}', '${escapeHtml(c.rationale || '')}', '${escapeHtml(c.safety_level || 'READ_ONLY')}', ${c.risk_score || 0.05}, '${escapeHtml(c.rollback || '')}')" class="btn btn-primary px-3 py-1 text-xs">
                Execute
              </button>
            </div>
            <p class="text-xs text-[#A0B3D6] font-sans">${escapeHtml(c.rationale || 'Remediates root cause.')}</p>
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
  container.innerHTML = '<p class="text-[#00D2FF] font-mono">Querying multi-distro package repository...</p>';

  try {
    const res = await fetch(`/api/packages/search?query=${encodeURIComponent(pkg)}`);
    if (res.ok) {
      const data = await res.json();
      container.innerHTML = `
        <div class="space-y-2">
          <div class="flex items-center justify-between text-white font-bold">
            <span class="font-display">${escapeHtml(data.package || pkg)}</span>
            <span class="text-xs text-[#00D2FF]">${data.installed ? 'INSTALLED' : 'AVAILABLE IN REPO'}</span>
          </div>
          <p class="text-xs text-[#A0B3D6] font-sans">${escapeHtml(data.description || 'Package metadata located.')}</p>
          <div class="pt-2 flex space-x-2">
            ${!data.installed ? `
              <button onclick="requestCommandPermission({command: 'pacman -S --noconfirm ${pkg}', description: 'Installs package ${pkg}', safetyLevel: 'MODIFYING', riskScore: 0.35, onApprove: () => executeCommandDirect('pacman -S --noconfirm ${pkg}', 'pacman -R --noconfirm ${pkg}')})" class="btn btn-primary px-3 py-1 text-xs">
                Install Package
              </button>
            ` : `
              <button onclick="requestCommandPermission({command: 'pacman -R --noconfirm ${pkg}', description: 'Removes package ${pkg}', safetyLevel: 'MODIFYING', riskScore: 0.40, onApprove: () => executeCommandDirect('pacman -R --noconfirm ${pkg}', 'pacman -S --noconfirm ${pkg}')})" class="btn btn-danger px-3 py-1 text-xs">
                Remove Package
              </button>
            `}
          </div>
        </div>
      `;
    }
  } catch (e) {
    container.innerHTML = `<p class="text-[#FF0055] font-mono">Error: ${escapeHtml(e.message)}</p>`;
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
        container.innerHTML = '<span class="text-[#00D2FF]">Streaming bytes from remote host...</span>';
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
              <div class="text-[#00D2FF] font-bold">&check; Download completed: ${escapeHtml(data.filename || 'file')} (${(data.size_mb || 0).toFixed(2)} MB) in ${dest}</div>
            `;
          } else {
            container.innerHTML = `<span class="text-[#FF0055]">Download failed: ${escapeHtml(data.error)}</span>`;
          }
        }
      } catch (e) {
        if (container) container.innerHTML = `<span class="text-[#FF0055]">Error: ${escapeHtml(e.message)}</span>`;
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
  if (lvl === 'READ_ONLY') return 'text-[#00D2FF]';
  if (lvl === 'MODIFYING') return 'text-[#FFB800]';
  if (lvl === 'HIGH_RISK') return 'text-[#FF0055]';
  if (lvl === 'DESTRUCTIVE') return 'text-[#FF0055]';
  return 'text-[#00D2FF]';
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
