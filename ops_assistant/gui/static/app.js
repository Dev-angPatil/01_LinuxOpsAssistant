// ==========================================================================
// LinuxOps Assistant — Cyberpunk Obsidian Client Cockpit Engine (v3.0)
// ==========================================================================

// Global state
let cpuChart = null;
let memoryChart = null;
let sseSource = null;
let allServices = [];
let pendingPermissionResolver = null;

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
  if (window.lucide) {
    lucide.createIcons();
  }
  initCharts();
  startTelemetrySSE();
  loadInitialData();

  // Initialize Cockpit Subsystems
  ThemeManager.init();
  SoundFX.init();
  SparklineManager.init();
  HistorySidebar.init();
  MascotManager.init();
  CapabilityManager.init();
  CommandPalette.init();
  CommandCenter.init();

  // Show command bar initially (home tab is default)
  const ccBar = document.getElementById('cc-command-bar');
  if (ccBar) ccBar.classList.remove('hidden');

  // Refresh button
  const btnRefresh = document.getElementById('btn-refresh-health');
  if (btnRefresh) {
    btnRefresh.addEventListener('click', () => {
      SoundFX.play('click');
      fetchHealthSnapshot();
    });
  }

  // Global Keyboard Shortcuts
  document.addEventListener('keydown', (e) => {
    // Ctrl+K or Cmd+K for Command Palette
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      CommandPalette.open();
      return;
    }
    // Ctrl+B or Cmd+B for History Sidebar Toggle
    if ((e.ctrlKey || e.metaKey) && (e.key === 'b' || e.key === 'B')) {
      e.preventDefault();
      HistorySidebar.toggle();
      return;
    }
    // Ctrl+N or Cmd+N for New Chat Session
    if ((e.ctrlKey || e.metaKey) && (e.key === 'n' || e.key === 'N')) {
      e.preventDefault();
      HistorySidebar.newChat();
      return;
    }
    // '/' to focus command input when not in text field
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
      e.preventDefault();
      const ccInput = document.getElementById('cc-text-input');
      if (ccInput) {
        switchTab('home');
        ccInput.focus();
      }
    }
    // Escape to close open modals
    if (e.key === 'Escape') {
      CommandPalette.close();
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
  let iconColor = 'text-cyan-400';
  if (type === 'success') {
    iconName = 'check-circle';
    iconColor = 'text-emerald-400';
  } else if (type === 'error') {
    iconName = 'alert-circle';
    iconColor = 'text-rose-400';
  } else if (type === 'warning') {
    iconName = 'alert-triangle';
    iconColor = 'text-amber-400';
  }

  toast.innerHTML = `
    <div class="mt-0.5 ${iconColor} shrink-0">
      <i data-lucide="${iconName}" class="w-4 h-4"></i>
    </div>
    <div class="flex-1 text-xs text-zinc-200 leading-relaxed break-words">${escapeHtml(message)}</div>
    <button onclick="this.parentElement.remove()" class="text-zinc-500 hover:text-zinc-300 font-mono text-sm leading-none">&times;</button>
  `;

  container.appendChild(toast);
  if (window.lucide) lucide.createIcons();

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(-8px)';
    setTimeout(() => toast.remove(), 250);
  }, duration);
}

// ==========================================================================
// MODAL CONTROLLERS & PERMISSION DIALOG
// ==========================================================================
function openModal(modalId) {
  const m = document.getElementById(modalId);
  if (m) m.classList.remove('hidden');
  if (window.lucide) lucide.createIcons();
}

function closeModal(modalId) {
  const m = document.getElementById(modalId);
  if (m) m.classList.add('hidden');
  if (modalId === 'modal-permission' && pendingPermissionResolver) {
    pendingPermissionResolver(false);
    pendingPermissionResolver = null;
  }
}

function copyModalCommand() {
  const cmd = document.getElementById('modal-perm-command').textContent;
  if (cmd && cmd !== '-') {
    navigator.clipboard.writeText(cmd).then(() => {
      showToast('Command copied to clipboard', 'success', 2000);
      SoundFX.play('click');
    });
  }
}

// ==========================================================================
// TAB SWITCHING (RIGHT VERTICAL NAVIGATION)
// ==========================================================================
function switchTab(tabId) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.nav-vertical-btn, .nav-tab').forEach(el => el.classList.remove('active'));

  const activeContent = document.getElementById('tab-content-' + tabId);
  const activeBtn = document.getElementById('tab-btn-' + tabId);

  if (activeContent) activeContent.classList.remove('hidden');
  if (activeBtn) activeBtn.classList.add('active');

  // Show/hide CommandCenter bar on the home tab only
  const ccBar = document.getElementById('cc-command-bar');
  if (ccBar) ccBar.classList.toggle('hidden', tabId !== 'home');

  // Trigger lazy loading
  if (tabId === 'services') loadServices();
  if (tabId === 'network') loadNetwork();
  if (tabId === 'taxonomy') loadTaxonomyScenarios();

  SoundFX.play('click');

  if (window.lucide) {
    setTimeout(() => lucide.createIcons(), 50);
  }
}

async function loadInitialData() {
  await fetchHealthSnapshot();
  await loadTaxonomyScenarios();
}
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

  function safeSetText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  // Header
  const dInfo = snap.distro_info || {};
  const distroName = dInfo.distro_name || 'Linux';
  safeSetText('header-hostname', snap.hostname || 'localhost');
  safeSetText('header-distro', distroName);
  safeSetText('header-kernel', 'Kernel ' + (snap.kernel_release || ''));

  const pressureBadge = document.getElementById('header-pressure');
  if (pressureBadge) {
    pressureBadge.textContent = snap.pressure_status || 'NORMAL';
    if (snap.pressure_status === 'ELEVATED') {
      pressureBadge.className = 'font-mono text-[11px] font-semibold text-amber-400';
    } else if (snap.pressure_status === 'CRITICAL') {
      pressureBadge.className = 'font-mono text-[11px] font-semibold text-rose-400';
    } else {
      pressureBadge.className = 'font-mono text-[11px] font-semibold text-emerald-400';
    }
  }

  // Health Cards
  const cpu = snap.cpu || {};
  const mem = snap.memory || {};
  const load = snap.load || {};

  const totalCpuPct = (cpu.user_pct || 0) + (cpu.system_pct || 0);
  safeSetText('health-cpu-pct', totalCpuPct.toFixed(1) + '%');
  safeSetText('health-cpu-cores', (cpu.core_count || 1) + ' Cores');
  safeSetText('health-cpu-breakdown', `User: ${(cpu.user_pct||0).toFixed(1)}% | Sys: ${(cpu.system_pct||0).toFixed(1)}% | IO: ${(cpu.iowait_pct||0).toFixed(1)}%`);
  safeSetText('home-cpu-pct', totalCpuPct.toFixed(1) + '%');

  safeSetText('health-ram-pct', (mem.used_percent || 0).toFixed(1) + '%');
  safeSetText('health-ram-avail', Math.round(mem.used_mb||0) + ' / ' + Math.round(mem.total_mb||0) + ' MB');
  safeSetText('health-swap-info', 'Swap: ' + (mem.swap_used_percent||0).toFixed(1) + '% used');
  safeSetText('home-ram-pct', (mem.used_percent || 0).toFixed(1) + '%');

  safeSetText('health-load-1m', (load.load_1m || 0).toFixed(2));
  safeSetText('health-load-5m', `5m: ${(load.load_5m||0).toFixed(2)} | 15m: ${(load.load_15m||0).toFixed(2)}`);
  safeSetText('health-procs-count', `${load.running_processes||0} running / ${load.total_processes||0} procs`);

  safeSetText('health-psi-badge', snap.pressure_status || 'NORMAL');
  safeSetText('health-zombie-count', (cpu.zombie_count || 0) + ' Zombies');
  safeSetText('health-uptime-str', 'Uptime: ' + ((snap.uptime_seconds||0)/3600).toFixed(1) + ' hrs');

  // Push to Header Live Sparklines
  if (typeof SparklineManager !== 'undefined') {
    SparklineManager.pushCPU(totalCpuPct);
    SparklineManager.pushRAM(mem.used_percent || 0);
  }

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
      y: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#71717A', font: { family: 'JetBrains Mono', size: 10 } } },
      x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#71717A', font: { family: 'JetBrains Mono', size: 10 }, maxRotation: 0 } }
    },
    plugins: { legend: { labels: { color: '#D4D4D8', font: { family: 'Inter', size: 11 }, boxWidth: 12 } } }
  };

  const ctxCpu = document.getElementById('chart-cpu');
  if (ctxCpu) {
    cpuChart = new Chart(ctxCpu, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'CPU Total %', data: [], borderColor: '#FFFFFF', backgroundColor: 'rgba(255, 255, 255, 0.04)', fill: true, tension: 0.2, borderWidth: 1.5 },
          { label: 'I/O Wait %', data: [], borderColor: '#F59E0B', borderDash: [3, 3], fill: false, tension: 0.2, borderWidth: 1.5 }
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
          { label: 'RAM Used %', data: [], borderColor: '#22C55E', backgroundColor: 'rgba(34, 197, 94, 0.04)', fill: true, tension: 0.2, borderWidth: 1.5 },
          { label: 'Swap Used %', data: [], borderColor: '#A1A1AA', borderDash: [3, 3], fill: false, tension: 0.2, borderWidth: 1.5 }
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
    container.innerHTML = '<p class="text-zinc-600 font-mono">Kernel PSI metrics not available (/proc/pressure unmounted).</p>';
    return;
  }

  let html = '<div class="grid grid-cols-3 gap-2">';
  for (const [subsys, metrics] of Object.entries(psi)) {
    const avg10 = metrics.some_avg10 || 0;
    const colorClass = avg10 > 20 ? 'text-rose-400' : (avg10 > 5 ? 'text-amber-400' : 'text-emerald-400');
    html += `<div class="p-3 rounded-lg bg-[#060709] border border-white/[0.06] space-y-1">
      <span class="font-mono font-semibold uppercase text-zinc-500 text-[10px]">${subsys}</span>
      <div class="text-lg font-bold font-mono ${colorClass}">${avg10.toFixed(2)}%</div>
      <p class="text-[10px] text-zinc-600 font-mono">60s: ${(metrics.some_avg60||0).toFixed(2)}% | 300s: ${(metrics.some_avg300||0).toFixed(2)}%</p>
    </div>`;
  }
  html += '</div>';
  container.innerHTML = html;
}

function renderDisksTable(disks) {
  const container = document.getElementById('disks-table-container');
  if (!container) return;
  if (!disks || disks.length === 0) {
    container.innerHTML = '<p class="text-zinc-600 font-mono">No filesystem mounts discovered.</p>';
    return;
  }

  let html = '<div class="space-y-2">';
  disks.slice(0, 4).forEach(d => {
    const color = d.used_percent > 85 ? 'bg-rose-500' : (d.used_percent > 70 ? 'bg-amber-500' : 'bg-white');
    html += `<div class="p-2.5 rounded-lg bg-[#060709] border border-white/[0.06] space-y-1.5 font-mono text-xs">
      <div class="flex justify-between">
        <span class="text-zinc-200 font-semibold">${d.mountpoint}</span>
        <span class="text-zinc-400">${d.used_gb.toFixed(1)} / ${d.total_gb.toFixed(1)} GB (${d.used_percent.toFixed(1)}%)</span>
      </div>
      <div class="w-full bg-white/[0.08] h-1.5 rounded-full overflow-hidden">
        <div class="${color} h-full" style="width: ${Math.min(100, d.used_percent)}%"></div>
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
  // Route through CommandCenter (new path) — keep old agent-prompt-input as fallback
  const ccInput = document.getElementById('cc-text-input');
  if (ccInput) {
    ccInput.value = text;
    CommandCenter.submitCommand(text);
    return;
  }
  const input = document.getElementById('agent-prompt-input');
  if (input) {
    input.value = text;
    submitAgentPrompt(text);
  }
}

async function submitAgentPrompt(promptText) {
  const feed = document.getElementById('agent-feed-container');
  const btn = document.getElementById('btn-submit-prompt');
  if (btn) btn.disabled = true;

  // Add User Message Card
  const userCard = document.createElement('div');
  userCard.className = 'p-3.5 rounded-lg bg-white/[0.03] border border-white/[0.08] space-y-1.5';
  userCard.innerHTML = `
    <div class="flex items-center justify-between text-xs font-mono">
      <span class="font-semibold text-zinc-300 flex items-center space-x-1.5">
        <i data-lucide="user" class="w-3.5 h-3.5 text-zinc-400"></i>
        <span>User Query</span>
      </span>
      <span class="text-zinc-600 text-[10px]">${new Date().toLocaleTimeString()}</span>
    </div>
    <p class="text-xs text-white font-mono">${escapeHtml(promptText)}</p>
  `;
  feed.prepend(userCard);

  // Add Agent Pending Card
  const agentCard = document.createElement('div');
  agentCard.className = 'p-4 rounded-lg bg-[#0E1015] border border-white/[0.08] space-y-3';
  agentCard.innerHTML = `
    <div class="flex items-center space-x-2 text-xs text-zinc-400 font-mono">
      <i data-lucide="loader-2" class="w-3.5 h-3.5 text-white animate-spin"></i>
      <span>Classifying intent & evaluating safety guardrails...</span>
    </div>
  `;
  feed.prepend(agentCard);
  if (window.lucide) lucide.createIcons();

  try {
    // Request agent analysis (stage first if modifying)
    const res = await fetch('/api/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: promptText, execute: false })
    });
    const data = await res.json();
    renderAgentResponseCard(agentCard, data);
  } catch (e) {
    agentCard.innerHTML = `
      <div class="text-xs text-rose-400 font-mono font-medium flex items-center space-x-2">
        <i data-lucide="alert-circle" class="w-4 h-4"></i>
        <span>Agent Dispatch Error: ${escapeHtml(e.message)}</span>
      </div>
    `;
  } finally {
    if (btn) btn.disabled = false;
    if (window.lucide) lucide.createIcons();
  }
}

function renderAgentResponseCard(card, data) {
  const safetyClass = getSafetyBadgeClass(data.safety_level || 'READ_ONLY');
  const isModifying = data.safety_level && data.safety_level !== 'READ_ONLY';
  const cardBorderClass = isModifying ? 'command-approval-card modifying' : 'linear-card';

  card.className = `p-4 space-y-3 ${cardBorderClass}`;

  let stepsHtml = '';
  if (data.steps && data.steps.length > 0) {
    stepsHtml = `
      <div class="space-y-1 text-[11px] text-zinc-400 font-mono border-l-2 border-white/20 pl-3 py-0.5">
        ${data.steps.map(s => `<div>&bull; ${escapeHtml(s)}</div>`).join('')}
      </div>
    `;
  }

  // Planned Command Section (The Main Feature: Show command + description + ask permission)
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
        <div class="text-[10px] font-mono uppercase tracking-wider text-zinc-400 font-semibold">Planned Command Execution & Guardrails:</div>
        ${plannedCmds.map((c, idx) => `
          <div class="p-3 rounded-lg bg-[#060709] border border-white/[0.10] space-y-2.5">
            <div class="flex items-center justify-between">
              <span class="${getSafetyBadgeClass(c.safety_level)} text-[10px] font-mono px-2 py-0.5 rounded font-semibold uppercase">${c.safety_level || 'READ_ONLY'}</span>
              <span class="text-[10px] font-mono text-zinc-500">Risk Score: ${(c.risk_score || 0.05).toFixed(2)}</span>
            </div>

            <!-- Exact Command -->
            <div class="p-2 rounded bg-black/60 border border-white/[0.06] font-mono text-xs text-zinc-100 flex items-start justify-between space-x-2">
              <div class="break-all select-all flex-1">
                <span class="text-zinc-600 select-none">$ </span>
                <span class="font-semibold">${escapeHtml(c.command)}</span>
              </div>
              <button onclick="navigator.clipboard.writeText('${escapeHtml(c.command)}'); showToast('Command copied', 'info', 2000);" class="text-zinc-500 hover:text-zinc-300 px-1" title="Copy Command">
                <i data-lucide="copy" class="w-3 h-3"></i>
              </button>
            </div>

            <!-- Short Description of What It Will Do -->
            <div class="text-xs text-zinc-300 font-sans leading-relaxed">
              <span class="text-zinc-500 text-[10px] font-mono uppercase block font-semibold">Description:</span>
              ${escapeHtml(c.description || 'Executes operation on the system.')}
            </div>

            ${c.rollback_command ? `
              <div class="text-[11px] font-mono text-zinc-500">
                <span class="text-zinc-600">Rollback:</span> ${escapeHtml(c.rollback_command)}
              </div>
            ` : ''}

            <!-- Permission Confirmation Buttons -->
            <div class="flex items-center space-x-2 pt-1 border-t border-white/[0.06]">
              <button onclick="executeCommandDirect('${escapeHtml(c.command)}', '${escapeHtml(c.rollback_command || '')}', this.closest('.command-approval-card'))" class="btn btn-primary px-3 py-1.5 text-xs">
                <i data-lucide="play" class="w-3 h-3"></i>
                <span>Approve & Execute</span>
              </button>
              <button onclick="executeDryRunSandbox('${escapeHtml(c.command)}')" class="btn btn-secondary px-3 py-1.5 text-xs">
                <i data-lucide="flask-conical" class="w-3 h-3"></i>
                <span>Dry-Run Sandbox</span>
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
      <pre class="p-3 rounded-lg bg-[#060709] border border-white/[0.06] text-[11px] font-mono text-zinc-300 overflow-x-auto max-h-48 whitespace-pre-wrap">${escapeHtml(JSON.stringify(data.output, null, 2))}</pre>
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
    <div class="flex items-center justify-between text-xs border-b border-white/[0.06] pb-2 font-mono">
      <div class="flex items-center space-x-2">
        <span class="font-semibold text-white flex items-center space-x-1.5">
          <i data-lucide="bot" class="w-3.5 h-3.5 text-zinc-300"></i>
          <span>Agent Intent: ${escapeHtml(data.intent || 'ACTION')}</span>
        </span>
        <span class="${safetyClass} text-[10px] px-2 py-0.5 rounded font-semibold uppercase">${escapeHtml(data.safety_level || 'READ_ONLY')}</span>
      </div>
      <span class="text-zinc-600 text-[10px]">${new Date().toLocaleTimeString()}</span>
    </div>

    <div class="text-xs text-zinc-200 font-sans font-medium">${escapeHtml(data.summary || 'Analysis complete.')}</div>
    
    ${stepsHtml}
    ${commandSectionHtml}
    ${outputDetailsHtml}

    <div class="flex items-center justify-between pt-1 font-mono text-[10px] text-zinc-500">
      <span>Risk Score: ${(data.risk_score || 0.05).toFixed(2)}</span>
      ${rollbackBtnHtml}
    </div>
  `;

  if (window.lucide) lucide.createIcons();
}

function clearAgentFeed() {
  const feed = document.getElementById('agent-feed-container');
  if (feed) {
    feed.innerHTML = '<p class="text-xs font-mono text-zinc-600 p-2">Feed cleared.</p>';
  }
}

// ==========================================================================
// COMMAND EXECUTION ENGINE & ROLLBACK
// ==========================================================================
async function executeCommandDirect(cmd, rollbackCmd, cardEl) {
  showToast('Executing: ' + cmd, 'info');

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
      showToast(`Command returned non-zero code (${data.returncode})`, 'warning');
    }

    // Append execution result box to card
    if (cardEl) {
      const resultBox = document.createElement('div');
      resultBox.className = 'p-3 rounded-lg bg-black border border-white/[0.12] space-y-1.5 font-mono text-xs';
      resultBox.innerHTML = `
        <div class="flex items-center justify-between text-[10px] text-zinc-400">
          <span class="font-semibold text-emerald-400">&check; Execution Complete</span>
          <span>Exit: ${data.returncode} | Latency: ${data.latency_ms || 0}ms</span>
        </div>
        <pre class="text-[11px] text-zinc-300 overflow-x-auto max-h-36 whitespace-pre-wrap">${escapeHtml(data.stdout || data.stderr || '(No output returned)')}</pre>
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
          showToast('Rollback executed successfully', 'success');
        } else {
          showToast('Rollback failed: ' + (data.stderr || 'Non-zero exit'), 'error');
        }
      } catch (e) {
        showToast('Rollback error: ' + e.message, 'error');
      }
    }
  });
}

// ==========================================================================
// SERVICES TAB ACTIONS (Hooked into Permission Modal)
// ==========================================================================
async function loadServices() {
  const tbody = document.getElementById('services-table-body');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="3" class="text-center text-zinc-600 py-6 font-mono">Loading service units...</td></tr>';

  try {
    const res = await fetch('/api/services');
    const data = await res.json();
    allServices = data.services || [];
    renderServicesTable(allServices);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3" class="text-center text-rose-400 py-4 font-mono">Failed to load services: ${escapeHtml(e.message)}</td></tr>`;
  }
}

function filterServices() {
  const query = (document.getElementById('service-search-input')?.value || '').toLowerCase();
  const filtered = allServices.filter(s => s.unit.toLowerCase().includes(query) || (s.description || '').toLowerCase().includes(query));
  renderServicesTable(filtered);
}

function renderServicesTable(services) {
  const tbody = document.getElementById('services-table-body');
  if (!tbody) return;

  if (services.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="text-center text-zinc-600 py-6 font-mono">No matching services found.</td></tr>';
    return;
  }

  tbody.innerHTML = services.slice(0, 50).map(s => {
    const isFailed = s.active === 'failed' || s.sub === 'failed';
    const isActive = s.active === 'active';
    const stateBadge = isFailed ? '<span class="px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20 text-[10px] font-mono font-semibold">FAILED</span>' :
                       (isActive ? '<span class="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] font-mono font-semibold">ACTIVE</span>' :
                       '<span class="px-1.5 py-0.5 rounded bg-zinc-500/10 text-zinc-400 border border-zinc-500/20 text-[10px] font-mono">INACTIVE</span>');

    return `
      <tr>
        <td class="font-mono text-zinc-200">${escapeHtml(s.unit)}</td>
        <td>${stateBadge}</td>
        <td class="text-right space-x-1.5">
          <button onclick="promptServiceAction('${escapeHtml(s.unit)}', 'restart')" class="btn btn-secondary px-2 py-1 text-[10px]">Restart</button>
          <button onclick="promptServiceAction('${escapeHtml(s.unit)}', 'stop')" class="btn btn-danger px-2 py-1 text-[10px]">Stop</button>
          <button onclick="promptServiceAction('${escapeHtml(s.unit)}', 'logs')" class="btn btn-ghost px-2 py-1 text-[10px]">Logs</button>
        </td>
      </tr>
    `;
  }).join('');
}

function promptServiceAction(svc, action) {
  if (action === 'logs') {
    openModal('modal-logs');
    document.getElementById('modal-logs-title').textContent = 'Journal Logs: ' + svc;
    document.getElementById('modal-logs-content').textContent = 'Loading logs...';
    fetch('/api/services/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ service: svc, action: 'logs' })
    })
    .then(r => r.json())
    .then(data => {
      document.getElementById('modal-logs-content').textContent = data.logs || 'No recent logs found for unit.';
    })
    .catch(e => {
      document.getElementById('modal-logs-content').textContent = 'Failed to load logs: ' + e.message;
    });
    return;
  }

  const cmd = `systemctl ${action} ${svc}`;
  const desc = `Sends '${action}' instruction to systemd unit '${svc}'. May restart active network connections or worker processes.`;

  requestCommandPermission({
    command: cmd,
    description: desc,
    safetyLevel: action === 'stop' ? 'HIGH_RISK' : 'MODIFYING',
    riskScore: action === 'stop' ? 0.60 : 0.35,
    rollback: `systemctl restart ${svc}`,
    onApprove: async () => {
      showToast(`Executing systemctl ${action} on ${svc}...`, 'info');
      try {
        const res = await fetch('/api/services/action', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ service: svc, action: action })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`Service ${svc} ${action}: SUCCESS`, 'success');
        } else {
          showToast(`Service ${svc} ${action}: FAILED (${data.error || 'error'})`, 'error');
        }
        loadServices();
      } catch (e) {
        showToast('Error: ' + e.message, 'error');
      }
    }
  });
}

// ==========================================================================
// PROCESSES TAB (Hooked into Permission Modal)
// ==========================================================================
async function loadProcesses() {
  const tbody = document.getElementById('processes-table-body');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" class="text-center text-zinc-600 py-6 font-mono">Loading active processes...</td></tr>';

  try {
    const res = await fetch('/api/processes?n=30');
    const data = await res.json();
    const procs = data.processes || [];
    if (procs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center text-zinc-600 py-6 font-mono">No processes returned.</td></tr>';
      return;
    }
    tbody.innerHTML = procs.map(p => `
      <tr>
        <td class="font-mono text-white font-semibold">${p.pid}</td>
        <td class="text-zinc-400 font-mono">${escapeHtml(p.user || '')}</td>
        <td class="font-mono ${p.cpu > 50 ? 'text-rose-400 font-bold' : 'text-zinc-300'}">${p.cpu.toFixed(1)}%</td>
        <td class="font-mono ${p.mem > 50 ? 'text-amber-400 font-bold' : 'text-zinc-300'}">${p.mem.toFixed(1)}%</td>
        <td class="font-mono text-zinc-300 truncate max-w-xs" title="${escapeHtml(p.command || '')}">${escapeHtml(p.command || '')}</td>
        <td class="text-right">
          <button onclick="promptKillProcess(${p.pid}, '${escapeHtml(p.command || '')}')" class="btn btn-danger px-2 py-1 text-[10px]">Kill</button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-rose-400 py-4 font-mono">Failed to load processes: ${escapeHtml(e.message)}</td></tr>`;
  }
}

function promptKillProcess(pid, cmdName) {
  const cmd = `kill -15 ${pid}`;
  const desc = `Sends SIGTERM (signal 15) to terminate process PID ${pid} (${cmdName || 'process'}). Allows application to execute cleanup handlers.`;

  requestCommandPermission({
    command: cmd,
    description: desc,
    safetyLevel: 'HIGH_RISK',
    riskScore: 0.70,
    onApprove: async () => {
      showToast(`Terminating process PID ${pid}...`, 'info');
      try {
        const res = await fetch('/api/processes/kill', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pid: pid, signal: 15 })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`Process PID ${pid} terminated`, 'success');
        } else {
          showToast(`Failed to kill PID ${pid}: ${data.error || 'error'}`, 'error');
        }
        loadProcesses();
      } catch (e) {
        showToast('Error: ' + e.message, 'error');
      }
    }
  });
}

// ==========================================================================
// STORAGE & CLEANUP TAB (Hooked into Permission Modal)
// ==========================================================================
async function previewOrganize() {
  const path = document.getElementById('organize-path-input').value.trim() || '~/Downloads';
  const out = document.getElementById('organize-result-container');
  out.classList.remove('hidden');
  out.innerHTML = '<p class="text-zinc-400">Computing directory categorization plan...</p>';

  try {
    const res = await fetch('/api/storage/organise', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: path, dry_run: true })
    });
    const data = await res.json();
    out.innerHTML = `
      <div class="font-semibold text-white">Dry-Run Preview for ${escapeHtml(data.directory || path)}:</div>
      <div>Files to categorize: <span class="text-white font-bold">${data.moved_count || 0}</span></div>
      <div class="max-h-40 overflow-y-auto space-y-1 pt-1 text-zinc-400">
        ${(data.moves || []).map(m => `<div>&rarr; ${escapeHtml(m.file)} &rArr; <span class="text-white">${escapeHtml(m.category)}/</span></div>`).join('')}
      </div>
    `;
  } catch (e) {
    out.innerHTML = `<p class="text-rose-400">Error: ${escapeHtml(e.message)}</p>`;
  }
}

function promptOrganizeNow() {
  const path = document.getElementById('organize-path-input').value.trim() || '~/Downloads';
  const cmd = `ops-assistant organise '${path}'`;
  const desc = `Moves cluttered files in '${path}' into categorized subdirectories (Images, Documents, Videos, Audio, Archives, Code).`;

  requestCommandPermission({
    command: cmd,
    description: desc,
    safetyLevel: 'MODIFYING',
    riskScore: 0.30,
    rollback: `ops-assistant organise-undo '${path}'`,
    onApprove: async () => {
      const out = document.getElementById('organize-result-container');
      out.classList.remove('hidden');
      out.innerHTML = '<p class="text-zinc-400">Executing directory organization...</p>';

      try {
        const res = await fetch('/api/storage/organise', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: path, dry_run: false })
        });
        const data = await res.json();
        out.innerHTML = `<div class="font-semibold text-emerald-400">&check; Successfully organized ${data.moved_count || 0} files in ${escapeHtml(data.directory || path)}!</div>`;
        showToast(`Organized ${data.moved_count || 0} files`, 'success');
      } catch (e) {
        out.innerHTML = `<p class="text-rose-400">Error: ${escapeHtml(e.message)}</p>`;
        showToast('Organize failed: ' + e.message, 'error');
      }
    }
  });
}

function promptCleanStorage() {
  const cmd = "journalctl --vacuum-size=200M && rm -rf /tmp/*";
  const desc = "Vacuums rotated systemd journal logs to 200MB and purges stale temporary files.";

  requestCommandPermission({
    command: cmd,
    description: desc,
    safetyLevel: 'MODIFYING',
    riskScore: 0.40,
    onApprove: async () => {
      await cleanStorage(false);
    }
  });
}

async function cleanStorage(dryRun) {
  const out = document.getElementById('clean-result-container');
  out.classList.remove('hidden');
  out.innerHTML = `<p class="text-zinc-400">${dryRun ? 'Scanning for purgeable logs...' : 'Cleaning logs and temp files...'}</p>`;

  try {
    const res = await fetch('/api/storage/clean', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dry_run: dryRun })
    });
    const data = await res.json();
    out.innerHTML = `
      <div class="font-semibold text-white">${dryRun ? 'Dry-Run Clean Preview:' : 'Clean Execution Complete:'}</div>
      <div>Cleanable Items: <span class="text-white font-bold">${data.cleaned_count || 0}</span></div>
      <div>Freed Space: <span class="text-emerald-400 font-bold">${data.freed_human || '0 MB'}</span></div>
    `;
    if (!dryRun) showToast(`Cleaned ${data.cleaned_count || 0} items (${data.freed_human || '0 MB'})`, 'success');
  } catch (e) {
    out.innerHTML = `<p class="text-rose-400">Error: ${escapeHtml(e.message)}</p>`;
    showToast('Clean error: ' + e.message, 'error');
  }
}

async function loadLargeFiles() {
  const container = document.getElementById('large-files-container');
  container.innerHTML = '<p class="text-zinc-400 font-mono">Scanning filesystem for files >100MB...</p>';
  try {
    const res = await fetch('/api/storage/analysis?path=/');
    const data = await res.json();
    const files = data.large_files || [];
    if (files.length === 0) {
      container.innerHTML = '<p class="text-zinc-600 font-mono">No large files (>100MB) found in scan.</p>';
      return;
    }
    container.innerHTML = files.map(f => `
      <div class="flex justify-between p-2 rounded bg-[#060709] border border-white/[0.06] font-mono text-xs">
        <span class="text-zinc-300 truncate max-w-sm">${escapeHtml(f.path)}</span>
        <span class="font-bold text-amber-400">${f.size_human}</span>
      </div>
    `).join('');
  } catch (e) {
    container.innerHTML = `<p class="text-rose-400 font-mono">Scan failed: ${escapeHtml(e.message)}</p>`;
  }
}

// ==========================================================================
// NETWORK & FIREWALL TAB
// ==========================================================================
async function loadNetwork() {
  try {
    const res = await fetch('/api/network/status');
    const data = await res.json();

    const portsBody = document.getElementById('network-ports-body');
    const ports = data.ports || [];
    if (portsBody) {
      if (ports.length === 0) {
        portsBody.innerHTML = '<tr><td colspan="4" class="text-center text-zinc-600 py-6 font-mono">No listening sockets.</td></tr>';
      } else {
        portsBody.innerHTML = ports.slice(0, 30).map(p => `
          <tr>
            <td class="font-mono font-semibold text-white">${p.port}</td>
            <td class="font-mono text-zinc-400 uppercase">${p.protocol || 'tcp'}</td>
            <td class="font-mono text-zinc-300">${p.address || '*'}</td>
            <td class="font-mono text-zinc-400">${escapeHtml(p.process || '-')}</td>
          </tr>
        `).join('');
      }
    }

    const fwCard = document.getElementById('firewall-status-card');
    const fw = data.firewall || {};
    if (fwCard) {
      fwCard.innerHTML = `
        <div class="flex justify-between font-mono font-semibold">
          <span>Tool: ${fw.tool || 'UFW'}</span>
          <span class="${fw.status === 'active' ? 'text-emerald-400' : 'text-amber-400'}">STATUS: ${(fw.status || 'inactive').toUpperCase()}</span>
        </div>
        <p class="text-zinc-500 mt-1 font-mono text-[11px]">Default: ${fw.default_incoming || 'drop'} incoming</p>
      `;
    }
  } catch (e) {
    console.error('Failed to load network status', e);
  }
}

function promptFirewallRule(action) {
  const port = document.getElementById('fw-port-input').value.trim();
  const proto = document.getElementById('fw-proto-select').value;
  if (!port) {
    showToast('Please specify a port number', 'warning');
    return;
  }

  const cmd = `ufw ${action} ${port}/${proto}`;
  const desc = `${action === 'allow' ? 'Opens' : 'Blocks'} inbound traffic on network port ${port}/${proto} in host firewall.`;

  requestCommandPermission({
    command: cmd,
    description: desc,
    safetyLevel: 'HIGH_RISK',
    riskScore: 0.65,
    rollback: `ufw delete ${action} ${port}/${proto}`,
    onApprove: async () => {
      showToast(`Updating firewall rule (${action} ${port}/${proto})...`, 'info');
      try {
        const res = await fetch('/api/network/firewall', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: action, port: port, proto: proto })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`Firewall ${action} port ${port}/${proto}: SUCCESS`, 'success');
        } else {
          showToast(`Firewall update failed: ${data.error || 'error'}`, 'error');
        }
        loadNetwork();
      } catch (e) {
        showToast('Error: ' + e.message, 'error');
      }
    }
  });
}

// ==========================================================================
// 16-CLASS TAXONOMY & DAG VISUALIZER
// ==========================================================================
async function loadTaxonomyScenarios() {
  const grid = document.getElementById('taxonomy-scenarios-grid');
  if (!grid) return;

  try {
    const res = await fetch('/api/taxonomy/scenarios');
    const data = await res.json();
    const scenarios = data.scenarios || [];

    grid.innerHTML = scenarios.map(s => `
      <div onclick="runTaxonomyScenario('${escapeHtml(s.id)}')" class="linear-card p-3 space-y-1.5 cursor-pointer hover:border-white/30 transition">
        <div class="flex items-center justify-between">
          <span class="text-[10px] font-mono font-bold text-zinc-400 uppercase">${escapeHtml(s.id)}</span>
          <i data-lucide="play" class="w-3 h-3 text-white"></i>
        </div>
        <p class="text-[11px] font-medium text-zinc-200 line-clamp-2">${escapeHtml(s.symptom)}</p>
      </div>
    `).join('');

    if (window.lucide) lucide.createIcons();
  } catch (e) {
    grid.innerHTML = '<p class="text-rose-400 text-xs p-3 col-span-4 font-mono">Failed to load taxonomy scenarios.</p>';
  }
}

async function runTaxonomyScenario(scenarioId) {
  const container = document.getElementById('taxonomy-report-container');
  container.classList.remove('hidden');
  document.getElementById('diag-report-title').textContent = 'Triage Scenario: ' + scenarioId;
  document.getElementById('diag-symptom').textContent = 'Diagnosing scenario...';
  document.getElementById('diag-root-cause').textContent = 'Computing causal DAG...';
  document.getElementById('diag-rationale').textContent = '...';

  try {
    const res = await fetch('/api/diagnose', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: scenarioId })
    });
    const data = await res.json();
    const exp = data.explanation || {};

    document.getElementById('diag-symptom').textContent = exp.symptom || scenarioId;
    document.getElementById('diag-root-cause').textContent = exp.root_cause || '-';
    document.getElementById('diag-rationale').textContent = exp.rationale || '-';

    // Mermaid DAG
    const dagContainer = document.getElementById('mermaid-dag-container');
    const mermaidStr = data.causality_dag?.mermaid || 'graph TD\nRootCause["Root Cause"] --> Symptom["Symptom"]';
    dagContainer.innerHTML = '<div class="mermaid">' + mermaidStr + '</div>';
    if (window.mermaid) {
      mermaid.run({ nodes: dagContainer.querySelectorAll('.mermaid') });
    }

    // Proposed Remediation Commands
    const cmdContainer = document.getElementById('diag-commands-container');
    const cmds = exp.proposed_commands || [];
    cmdContainer.innerHTML = cmds.map(c => `
      <div class="p-3.5 rounded-lg bg-[#060709] border border-white/[0.10] space-y-2.5">
        <div class="flex items-center justify-between">
          <span class="${getSafetyBadgeClass(c.safety_level)} text-[10px] font-mono px-2 py-0.5 rounded font-semibold uppercase">${c.safety_level}</span>
          <span class="text-[10px] font-mono text-zinc-500">Risk: ${c.risk_score.toFixed(2)} | Sandbox: ${c.sandbox_verified ? 'Verified' : 'Simulated'}</span>
        </div>
        <div class="p-2 rounded bg-black/60 border border-white/[0.06] font-mono text-xs text-zinc-100 flex items-start justify-between space-x-2">
          <div class="break-all select-all flex-1">
            <span class="text-zinc-600 select-none">$ </span>
            <span class="font-semibold">${escapeHtml(c.command)}</span>
          </div>
          <button onclick="navigator.clipboard.writeText('${escapeHtml(c.command)}'); showToast('Copied', 'info', 2000);" class="text-zinc-500 hover:text-zinc-300 px-1">
            <i data-lucide="copy" class="w-3 h-3"></i>
          </button>
        </div>
        <p class="text-xs text-zinc-300 font-sans leading-relaxed">${escapeHtml(c.rationale)}</p>
        <div class="flex space-x-2 pt-1 border-t border-white/[0.06]">
          <button onclick="promptExecuteRemediation('${escapeHtml(c.command)}', '${escapeHtml(c.rationale)}', '${c.safety_level}', ${c.risk_score}, '${escapeHtml(c.rollback_command || '')}')" class="btn btn-primary px-3 py-1.5 text-xs">
            <i data-lucide="play" class="w-3 h-3"></i>
            <span>Execute With Permission</span>
          </button>
          ${c.rollback_command ? `
            <button onclick="executeRollback('${escapeHtml(c.rollback_command)}')" class="btn btn-secondary px-3 py-1.5 text-xs">
              <i data-lucide="undo-2" class="w-3 h-3"></i>
              <span>Rollback</span>
            </button>
          ` : ''}
        </div>
      </div>
    `).join('');

    if (window.lucide) lucide.createIcons();
  } catch (e) {
    showToast('Diagnosis error: ' + e.message, 'error');
  }
}

function promptExecuteRemediation(command, description, safetyLevel, riskScore, rollbackCommand) {
  requestCommandPermission({
    command: command,
    description: description,
    safetyLevel: safetyLevel,
    riskScore: riskScore,
    rollback: rollbackCommand,
    onApprove: async () => {
      await executeCommandDirect(command, rollbackCommand, null);
    }
  });
}

// ==========================================================================
// PACKAGE MANAGER TAB
// ==========================================================================
async function searchPackage() {
  const pkg = document.getElementById('pkg-search-input').value.trim();
  const out = document.getElementById('pkg-result-container');
  if (!pkg) {
    showToast('Please enter a package name', 'warning');
    return;
  }
  out.innerHTML = `<p class="text-zinc-400">Searching repositories for ${escapeHtml(pkg)}...</p>`;

  try {
    const res = await fetch('/api/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: 'search package ' + pkg, execute: true })
    });
    const data = await res.json();
    out.innerHTML = `
      <div class="font-semibold text-white">Repository search result for '${escapeHtml(pkg)}':</div>
      <pre class="pt-2 text-zinc-300 whitespace-pre-wrap">${escapeHtml(JSON.stringify(data.output || data.summary, null, 2))}</pre>
    `;
  } catch (e) {
    out.innerHTML = `<p class="text-rose-400">Error: ${escapeHtml(e.message)}</p>`;
  }
}

// ==========================================================================
// DESKTOP & DIRECT RUNNER TAB
// ==========================================================================
function promptDirectCommand() {
  const cmd = document.getElementById('direct-cmd-input').value.trim();
  if (!cmd) {
    showToast('Please enter a command to run', 'warning');
    return;
  }

  requestCommandPermission({
    command: cmd,
    description: `Executes '${cmd}' on the local system with AST safety validation and ephemeral namespace verification.`,
    safetyLevel: 'MODIFYING',
    riskScore: 0.35,
    onApprove: async () => {
      await executeCommandDirect(cmd, null, null);
    }
  });
}

function promptDownload() {
  const url = document.getElementById('download-url-input').value.trim();
  const dest = document.getElementById('download-dest-input').value.trim() || '~/Downloads';
  const autoExtract = document.getElementById('download-auto-extract').checked;

  if (!url) {
    showToast('Please enter a download URL', 'warning');
    return;
  }

  const cmd = `curl -fsSL -O '${url}' --output-dir '${dest}'`;
  const desc = `Streams file download from '${url}' into destination '${dest}' with auto-extraction (${autoExtract ? 'enabled' : 'disabled'}).`;

  requestCommandPermission({
    command: cmd,
    description: desc,
    safetyLevel: 'MODIFYING',
    riskScore: 0.20,
    rollback: `rm -f '${dest}/downloaded_file'`,
    onApprove: async () => {
      const out = document.getElementById('download-result-container');
      out.classList.remove('hidden');
      out.innerHTML = `<p class="text-zinc-400">Connecting and streaming download from ${escapeHtml(url)}...</p>`;

      try {
        const res = await fetch('/api/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: url, destination_dir: dest, auto_extract: autoExtract })
        });
        const data = await res.json();
        if (data.success) {
          out.innerHTML = `
            <div class="font-semibold text-emerald-400">&check; ${escapeHtml(data.message)}</div>
            <div>Size: <span class="text-white font-bold">${data.size_human}</span></div>
            <div>Saved to: <span class="text-zinc-300 font-mono">${escapeHtml(data.file_path)}</span></div>
            ${data.extraction ? `<div class="text-zinc-400 pt-1">&check; ${escapeHtml(data.extraction.message)}</div>` : ''}
          `;
          showToast('Download completed successfully', 'success');
        } else {
          out.innerHTML = `<p class="text-rose-400">&cross; Download Failed: ${escapeHtml(data.error)}</p>`;
          showToast('Download failed: ' + data.error, 'error');
        }
      } catch (e) {
        out.innerHTML = `<p class="text-rose-400">Network error: ${escapeHtml(e.message)}</p>`;
        showToast('Download network error: ' + e.message, 'error');
      }
    }
  });
}

async function desktopAction(action, params) {
  try {
    const res = await fetch('/api/desktop/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action, ...params })
    });
    const data = await res.json();
    showToast(data.message || data.error || 'Action dispatched', data.success !== false ? 'success' : 'error');
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}

// ==========================================================================
// MODAL & HELPER UTILITIES
// ==========================================================================
function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove('hidden');
}

function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add('hidden');
}

function getSafetyBadgeClass(lvl) {
  if (lvl === 'READ_ONLY') return 'badge-readonly';
  if (lvl === 'MODIFYING') return 'badge-modifying';
  if (lvl === 'HIGH_RISK') return 'badge-highrisk';
  if (lvl === 'DESTRUCTIVE') return 'badge-destructive';
  return 'badge-readonly';
}

function getSafetyTextColor(lvl) {
  if (lvl === 'READ_ONLY') return 'text-emerald-400';
  if (lvl === 'MODIFYING') return 'text-amber-400';
  if (lvl === 'HIGH_RISK') return 'text-rose-400';
  if (lvl === 'DESTRUCTIVE') return 'text-rose-500';
  return 'text-emerald-400';
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ==========================================================================

// ==========================================================================
// THEME MANAGER
// ==========================================================================
const ThemeManager = {
  init() {
    const saved = localStorage.getItem('ops-theme') || 'cyan';
    this.setTheme(saved, true);
  },
  setTheme(name, silent = false) {
    document.documentElement.setAttribute('data-theme', name);
    const sel = document.getElementById('theme-selector');
    if (sel) sel.value = name;
    localStorage.setItem('ops-theme', name);
    if (!silent) {
      SoundFX.play('click');
      showToast(`Theme switched to ${name.toUpperCase()}`, 'info', 1500);
    }
  }
};

// ==========================================================================
// SYNTHETIC AUDIO FEEDBACK (WEB AUDIO API)
// ==========================================================================
const SoundFX = {
  ctx: null,
  enabled: true,
  init() {
    const saved = localStorage.getItem('ops-sound');
    this.enabled = saved !== 'false';
    this.updateIcon();
  },
  toggle() {
    this.enabled = !this.enabled;
    localStorage.setItem('ops-sound', String(this.enabled));
    this.updateIcon();
    if (this.enabled) this.play('click');
    showToast(`Audio FX ${this.enabled ? 'Enabled' : 'Muted'}`, 'info', 1500);
  },
  updateIcon() {
    const icon = document.getElementById('sound-icon');
    if (icon) {
      icon.setAttribute('data-lucide', this.enabled ? 'volume-2' : 'volume-x');
      icon.className = `w-3.5 h-3.5 ${this.enabled ? 'text-cyan-400' : 'text-zinc-600'}`;
      if (window.lucide) lucide.createIcons();
    }
  },
  _getCtx() {
    if (!this.ctx && (window.AudioContext || window.webkitAudioContext)) {
      const AC = window.AudioContext || window.webkitAudioContext;
      this.ctx = new AC();
    }
    if (this.ctx && this.ctx.state === 'suspended') {
      this.ctx.resume().catch(() => {});
    }
    return this.ctx;
  },
  play(type) {
    if (!this.enabled) return;
    try {
      const ctx = this._getCtx();
      if (!ctx) return;
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);

      if (type === 'click') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(800, now);
        osc.frequency.exponentialRampToValueAtTime(500, now + 0.035);
        gain.gain.setValueAtTime(0.04, now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.035);
        osc.start(now);
        osc.stop(now + 0.035);
      } else if (type === 'mic-start') {
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(440, now);
        osc.frequency.exponentialRampToValueAtTime(880, now + 0.12);
        gain.gain.setValueAtTime(0.06, now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.12);
        osc.start(now);
        osc.stop(now + 0.12);
      } else if (type === 'mic-stop') {
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(880, now);
        osc.frequency.exponentialRampToValueAtTime(440, now + 0.12);
        gain.gain.setValueAtTime(0.06, now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.12);
        osc.start(now);
        osc.stop(now + 0.12);
      } else if (type === 'success') {
        [523.25, 659.25, 783.99].forEach((freq, i) => {
          const o = ctx.createOscillator();
          const g = ctx.createGain();
          o.type = 'sine';
          o.frequency.setValueAtTime(freq, now + i * 0.06);
          g.gain.setValueAtTime(0.05, now + i * 0.06);
          g.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.06 + 0.2);
          o.connect(g);
          g.connect(ctx.destination);
          o.start(now + i * 0.06);
          o.stop(now + i * 0.06 + 0.2);
        });
      } else if (type === 'warning') {
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(260, now);
        osc.frequency.linearRampToValueAtTime(200, now + 0.15);
        gain.gain.setValueAtTime(0.04, now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.15);
        osc.start(now);
        osc.stop(now + 0.15);
      } else if (type === 'error') {
        osc.type = 'square';
        osc.frequency.setValueAtTime(160, now);
        gain.gain.setValueAtTime(0.05, now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.15);
        osc.start(now);
        osc.stop(now + 0.15);
      }
    } catch (e) {}
  }
};

// ==========================================================================
// LIVE HEADER SPARKLINE MANAGER
// ==========================================================================
const SparklineManager = {
  cpuBuffer: Array(14).fill(0),
  ramBuffer: Array(14).fill(0),
  init() {
    this.draw('sparkline-cpu', this.cpuBuffer, '#06b6d4');
    this.draw('sparkline-ram', this.ramBuffer, '#10b981');
  },
  pushCPU(pct) {
    this.cpuBuffer.push(pct);
    if (this.cpuBuffer.length > 14) this.cpuBuffer.shift();
    this.draw('sparkline-cpu', this.cpuBuffer, '#06b6d4');
    const el = document.getElementById('spark-cpu-val');
    if (el) el.textContent = Math.round(pct) + '%';
  },
  pushRAM(pct) {
    this.ramBuffer.push(pct);
    if (this.ramBuffer.length > 14) this.ramBuffer.shift();
    this.draw('sparkline-ram', this.ramBuffer, '#10b981');
    const el = document.getElementById('spark-ram-val');
    if (el) el.textContent = Math.round(pct) + '%';
  },
  draw(canvasId, buffer, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    if (buffer.length < 2) return;

    ctx.beginPath();
    const step = W / (buffer.length - 1);
    buffer.forEach((v, i) => {
      const y = H - (Math.min(100, Math.max(0, v)) / 100) * (H - 3) - 1.5;
      const x = i * step;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = 'round';
    ctx.stroke();
  }
};

// ==========================================================================
// LEFT COLLAPSIBLE HISTORY SIDEBAR
// ==========================================================================
const HistorySidebar = {
  sessions: [],
  init() {
    const savedState = localStorage.getItem('ops-sidebar');
    if (savedState === 'collapsed') {
      const sb = document.getElementById('sidebar-history');
      if (sb) sb.classList.add('collapsed');
      document.body.classList.add('sidebar-collapsed');
    }
    this.loadSessions();
  },
  toggle() {
    const sb = document.getElementById('sidebar-history');
    if (!sb) return;
    sb.classList.toggle('collapsed');
    const isCollapsed = sb.classList.contains('collapsed');
    document.body.classList.toggle('sidebar-collapsed', isCollapsed);
    localStorage.setItem('ops-sidebar', isCollapsed ? 'collapsed' : 'expanded');
    SoundFX.play('click');
    if (window.lucide) lucide.createIcons();
  },
  newChat() {
    SoundFX.play('click');
    switchTab('home');
    CommandCenter.clearTranscript();
    const inp = document.getElementById('cc-text-input');
    if (inp) inp.focus();
    MascotManager.setMood('OBSERVING', 'New session started. Ready for sysadmin operations.');
    showToast('New session started', 'info', 1500);
  },
  saveSession(session) {
    this.sessions = [session, ...this.sessions.filter(s => s.id !== session.id)].slice(0, 30);
    localStorage.setItem('cc-history-sessions', JSON.stringify(this.sessions));
    this.renderList();
  },
  async loadSessions() {
    try {
      const res = await fetch('/api/history/sessions');
      if (res.ok) {
        const data = await res.json();
        if (data.sessions && data.sessions.length > 0) {
          this.sessions = data.sessions.map(s => ({
            id: s.id,
            title: s.title || s.query || 'Session',
            timestamp: s.created_at ? new Date(s.created_at).getTime() : Date.now()
          }));
          localStorage.setItem('cc-history-sessions', JSON.stringify(this.sessions));
          this.renderList();
          return;
        }
      }
    } catch (err) {
      console.warn('Backend history sync unavailable, using local history:', err);
    }
    try {
      const raw = localStorage.getItem('cc-history-sessions');
      this.sessions = raw ? JSON.parse(raw) : [];
    } catch (e) { this.sessions = []; }
    this.renderList();
  },
  async deleteSession(id, e) {
    if (e) e.stopPropagation();
    this.sessions = this.sessions.filter(s => s.id !== id);
    localStorage.setItem('cc-history-sessions', JSON.stringify(this.sessions));
    this.renderList();
    SoundFX.play('click');
    try {
      await fetch('/api/history/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: id })
      });
    } catch (err) {}
  },
  async clearAll() {
    if (confirm('Clear all recent chat history?')) {
      this.sessions = [];
      localStorage.removeItem('cc-history-sessions');
      this.renderList();
      SoundFX.play('click');
      showToast('Chat history cleared', 'info', 2000);
      try {
        await fetch('/api/history/clear', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      } catch (err) {}
    }
  },
  filter(query) {
    const q = (query || '').toLowerCase().trim();
    const items = document.querySelectorAll('.history-item');
    items.forEach(el => {
      const title = (el.dataset.title || '').toLowerCase();
      el.classList.toggle('hidden', !title.includes(q));
    });
  },
  renderList() {
    const list = document.getElementById('history-sessions-list');
    if (!list) return;
    if (!this.sessions.length) {
      list.innerHTML = `<p class="text-[11px] text-zinc-600 text-center py-6 font-mono">No previous sessions</p>`;
      return;
    }
    list.innerHTML = this.sessions.map(s => {
      const timeStr = this._relativeTime(s.timestamp);
      return `
        <div class="history-item" data-id="${escapeHtml(s.id)}" data-title="${escapeHtml(s.title)}" onclick="HistorySidebar.selectSession('${escapeHtml(s.id)}', '${escapeHtml(s.title)}')">
          <div class="flex items-center space-x-2 min-w-0 flex-1">
            <i data-lucide="message-square" class="w-3.5 h-3.5 text-zinc-500 shrink-0"></i>
            <span class="truncate font-medium">${escapeHtml(s.title)}</span>
          </div>
          <div class="flex items-center space-x-1 shrink-0 ml-2">
            <span class="text-[9px] text-zinc-600 font-mono">${timeStr}</span>
            <button onclick="HistorySidebar.deleteSession('${escapeHtml(s.id)}', event)" class="text-zinc-600 hover:text-rose-400 p-0.5 rounded transition" title="Delete">
              <i data-lucide="x" class="w-3 h-3"></i>
            </button>
          </div>
        </div>
      `;
    }).join('');
    if (window.lucide) lucide.createIcons();
  },
  selectSession(id, title) {
    SoundFX.play('click');
    switchTab('home');
    const inp = document.getElementById('cc-text-input');
    if (inp) { inp.value = title; }
    showToast(`Loaded query: "${title}"`, 'info', 2000);
  },
  _relativeTime(ts) {
    if (!ts) return '';
    const diff = Math.floor((Date.now() - ts) / 1000);
    if (diff < 60) return 'Just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return Math.floor(diff / 86400) + 'd ago';
  }
};

// ==========================================================================
// DYNAMIC MASCOT AVATAR & TYPEWRITER SPEECH BUBBLE
// ==========================================================================
const MascotManager = {
  avatars: [
    {
      id: 'l',
      name: 'L (Death Note)',
      img: '/static/assets/mascot_l.jpg',
      mood: 'OBSERVING',
      pillClass: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
      quotes: [
        'Observing system telemetry... zero anomalous causal loops detected.',
        'Analyzing kernel signatures and process hierarchy.',
        'Topological DAG ready for sub-50ms root cause isolation.'
      ]
    },
    {
      id: 'tux',
      name: 'Tux (Linux Penguin)',
      img: '/static/assets/mascot_tux.svg',
      mood: 'NOMINAL',
      pillClass: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
      quotes: [
        'Kernel PSI pressure is nominal. Systemd units operational.',
        'Filesystem mounts verified. Inodes healthy.',
        'Ready for elevated sysadmin diagnostics.'
      ]
    },
    {
      id: 'cyber',
      name: 'Cyber Hacker Anime',
      img: '/static/assets/mascot_cyber.svg',
      mood: 'STANDBY',
      pillClass: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
      quotes: [
        'AST safety guardrails primed. Sandboxed execution enabled.',
        'Listening sockets & firewall tables indexed.',
        'Air-gapped local LLM provider standby.'
      ]
    },
    {
      id: 'matrix',
      name: 'Matrix Terminal Tux',
      img: '/static/assets/mascot_matrix.svg',
      mood: 'SYNCED',
      pillClass: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
      quotes: [
        'Sub-50ms deterministic triage active.',
        'System call tracing enabled via procfs and dmesg.',
        'All 16 failure taxonomy classifiers loaded.'
      ]
    }
  ],
  currentIndex: 0,
  typewriterTimer: null,
  init() {
    // Pick random mascot on page load / visit!
    this.currentIndex = Math.floor(Math.random() * this.avatars.length);
    this.applyAvatar(false);
  },
  cycle() {
    SoundFX.play('click');
    const btn = document.getElementById('mascot-avatar-btn');
    if (btn) {
      btn.classList.add('flip');
      setTimeout(() => btn.classList.remove('flip'), 500);
    }
    this.currentIndex = (this.currentIndex + 1) % this.avatars.length;
    this.applyAvatar(true);
  },
  applyAvatar(isCycle = false) {
    const cur = this.avatars[this.currentIndex];
    const img = document.getElementById('mascot-avatar-img');
    const moodText = document.getElementById('mascot-mood-text');
    const moodPill = document.getElementById('mascot-mood-pill');

    if (img) img.src = cur.img;
    if (moodText) moodText.textContent = `${cur.name.split(' ')[0].toUpperCase()} • ${cur.mood}`;
    if (moodPill) moodPill.className = `mascot-mood-pill ${cur.pillClass} font-mono`;

    const randomQuote = cur.quotes[Math.floor(Math.random() * cur.quotes.length)];
    this.typewrite(randomQuote);
    if (isCycle) showToast(`Switched avatar to ${cur.name}`, 'info', 1500);
  },
  setMood(mood, text) {
    const cur = this.avatars[this.currentIndex];
    const moodText = document.getElementById('mascot-mood-text');
    const moodPill = document.getElementById('mascot-mood-pill');
    
    let pillClass = 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20';
    if (mood === 'THINKING') {
      pillClass = 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    } else if (mood === 'GATED') {
      pillClass = 'bg-rose-500/10 text-rose-400 border-rose-500/20';
    } else if (mood === 'SUCCESS') {
      pillClass = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    }

    if (moodText) moodText.textContent = `${cur.name.split(' ')[0].toUpperCase()} • ${mood}`;
    if (moodPill) moodPill.className = `mascot-mood-pill ${pillClass} font-mono`;
    if (text) this.typewrite(text);
  },
  typewrite(text) {
    const el = document.getElementById('mascot-speech-text');
    if (!el) return;
    if (this.typewriterTimer) clearInterval(this.typewriterTimer);
    el.textContent = '';
    let i = 0;
    this.typewriterTimer = setInterval(() => {
      if (i < text.length) {
        el.textContent += text.charAt(i);
        i++;
      } else {
        clearInterval(this.typewriterTimer);
        this.typewriterTimer = null;
      }
    }, 16);
  }
};

// ==========================================================================
// BOTTOM 4-CATEGORY CAPABILITY ACTION BAR
// ==========================================================================
const CapabilityManager = {
  categories: {
    explore: [
      { label: '📁 Explore ~/Downloads', cmd: 'Explore the ~/Downloads folder and list recent items' },
      { label: '🔍 Find Space Hogs >100MB', cmd: 'Find all files larger than 100MB across root filesystem' },
      { label: '🌐 Check Open Ports', cmd: 'List all listening TCP and UDP ports and sockets' },
      { label: '⚙️ List Active Services', cmd: 'List all running systemd services and units' },
      { label: '💾 Check Disk Partitions', cmd: 'Show all mounted filesystems and available disk space' }
    ],
    optimize: [
      { label: '🧹 Vacuum System Journal', cmd: 'Vacuum journalctl logs older than 7 days' },
      { label: '📦 Clear Package Cache', cmd: 'Clean apt package cache and obsolete archives' },
      { label: '💽 Trim SSD Partitions', cmd: 'Run fstrim to trim all mounted SSD filesystems' },
      { label: '⚡ Free Memory Buffers', cmd: 'Inspect RAM buffers and compact memory' },
      { label: '🔄 Audit Zombie Processes', cmd: 'Find and clean orphaned or zombie processes' }
    ],
    monitor: [
      { label: '📊 System Health & PSI', cmd: 'Inspect system health, CPU PSI, and memory pressure' },
      { label: '🔥 Top CPU Processes', cmd: 'Show top 10 CPU-consuming processes right now' },
      { label: '🧠 Memory Leak Audit', cmd: 'Audit top memory consumers and inspect potential leaks' },
      { label: '🔬 Inspect Disk I/O Wait', cmd: 'Why is disk I/O spiking or waiting?' },
      { label: '🛡️ Audit Failed Units', cmd: 'Diagnose any failed systemd services or units' }
    ],
    launch: [
      { label: '🌐 Launch Web Browser', cmd: 'Launch default browser' },
      { label: '💻 Open Linux Terminal', cmd: 'Open terminal emulator' },
      { label: '🛡️ Audit SSH Security', cmd: 'Audit SSH configuration and detect brute-force attempts' },
      { label: '🔧 Restart NGINX Service', cmd: 'Restart the nginx service gracefully' },
      { label: '📈 Analyze System Boot Time', cmd: 'Analyze system boot time using systemd-analyze' }
    ]
  },
  currentCategory: 'explore',
  init() {
    this.renderChips();
  },
  switchCategory(cat) {
    this.currentCategory = cat;
    SoundFX.play('click');
    document.querySelectorAll('.capability-cat-btn').forEach(btn => btn.classList.remove('active'));
    const tabBtn = document.getElementById('cap-tab-' + cat);
    if (tabBtn) tabBtn.classList.add('active');
    this.renderChips();
  },
  renderChips() {
    const grid = document.getElementById('capability-chips-grid');
    if (!grid) return;
    const chips = this.categories[this.currentCategory] || [];
    grid.innerHTML = chips.map(c => `
      <button class="capability-chip" onclick="CapabilityManager.dispatch('${escapeHtml(c.cmd)}')">
        <span>${escapeHtml(c.label)}</span>
      </button>
    `).join('');
  },
  dispatch(cmd) {
    SoundFX.play('click');
    switchTab('home');
    const inp = document.getElementById('cc-text-input');
    if (inp) inp.value = cmd;
    CommandCenter.submitCommand(cmd);
  }
};

// ==========================================================================
// SPOTLIGHT COMMAND PALETTE (CTRL+K)
// ==========================================================================
const CommandPalette = {
  isOpen: false,
  actions: [
    { title: '🤖 Switch to AI Ops Agent', category: 'Navigation', icon: 'bot', action: () => switchTab('home') },
    { title: '📊 View Health & PSI Telemetry', category: 'Navigation', icon: 'activity', action: () => switchTab('health') },
    { title: '⚙️ Manage Services & Processes', category: 'Navigation', icon: 'cpu', action: () => switchTab('services') },
    { title: '💾 Storage & Disk Cleanup', category: 'Navigation', icon: 'hard-drive', action: () => switchTab('storage') },
    { title: '🌐 Network & Firewall Inspection', category: 'Navigation', icon: 'network', action: () => switchTab('network') },
    { title: '🛡️ 16-Class Taxonomy Playground', category: 'Navigation', icon: 'shield-alert', action: () => switchTab('taxonomy') },
    { title: '📦 Manage Packages', category: 'Navigation', icon: 'package', action: () => switchTab('packages') },
    { title: '💻 Desktop App Launcher', category: 'Navigation', icon: 'terminal', action: () => switchTab('desktop') },
    { title: '➕ Start New Chat Session', category: 'Chat', icon: 'plus', action: () => HistorySidebar.newChat() },
    { title: '🎤 Switch to Voice Input Mode', category: 'Input', icon: 'mic', action: () => { switchTab('home'); CommandCenter.setMode('voice'); } },
    { title: '⌨️ Switch to Text Input Mode', category: 'Input', icon: 'type', action: () => { switchTab('home'); CommandCenter.setMode('text'); } },
    { title: '🎨 Theme: Neon Cyan', category: 'Theme', icon: 'palette', action: () => ThemeManager.setTheme('cyan') },
    { title: '🎨 Theme: Matrix Emerald', category: 'Theme', icon: 'palette', action: () => ThemeManager.setTheme('emerald') },
    { title: '🎨 Theme: Tokyo Purple', category: 'Theme', icon: 'palette', action: () => ThemeManager.setTheme('purple') },
    { title: '🎨 Theme: Sunset Amber', category: 'Theme', icon: 'palette', action: () => ThemeManager.setTheme('amber') },
    { title: '🔊 Toggle Audio FX Feedback', category: 'Audio', icon: 'volume-2', action: () => SoundFX.toggle() }
  ],
  init() {
    this.renderList(this.actions);
  },
  open() {
    this.isOpen = true;
    SoundFX.play('click');
    const modal = document.getElementById('modal-command-palette');
    if (modal) modal.classList.remove('hidden');
    const inp = document.getElementById('palette-search-input');
    if (inp) {
      inp.value = '';
      inp.focus();
    }
    this.renderList(this.actions);
  },
  close() {
    this.isOpen = false;
    const modal = document.getElementById('modal-command-palette');
    if (modal) modal.classList.add('hidden');
  },
  filter(query) {
    const q = (query || '').toLowerCase().trim();
    if (!q) {
      this.renderList(this.actions);
      return;
    }
    const filtered = this.actions.filter(a =>
      a.title.toLowerCase().includes(q) || a.category.toLowerCase().includes(q)
    );
    this.renderList(filtered);
  },
  renderList(items) {
    const res = document.getElementById('palette-results');
    if (!res) return;
    if (!items.length) {
      res.innerHTML = `<p class="text-xs text-zinc-500 text-center py-6 font-mono">No matching commands found</p>`;
      return;
    }
    res.innerHTML = items.map((item, idx) => `
      <div class="palette-item" onclick="CommandPalette.exec(${idx})">
        <div class="flex items-center space-x-2.5">
          <i data-lucide="${item.icon}" class="w-4 h-4 text-cyan-400"></i>
          <span class="font-medium text-xs">${escapeHtml(item.title)}</span>
        </div>
        <span class="text-[10px] font-mono uppercase text-zinc-500 bg-white/[0.04] px-1.5 py-0.5 rounded border border-white/[0.06]">${escapeHtml(item.category)}</span>
      </div>
    `).join('');
    this._currentItems = items;
    if (window.lucide) lucide.createIcons();
  },
  exec(idx) {
    if (this._currentItems && this._currentItems[idx]) {
      const item = this._currentItems[idx];
      this.close();
      item.action();
    }
  }
};

// ==========================================================================
// COMMAND CENTER — Voice + Text Input, SSE Reasoning Panel
// ==========================================================================
function ccToggleStage(headerBtn) {
  const stage = headerBtn.closest('.cc-stage');
  if (stage) stage.classList.toggle('collapsed');
  SoundFX.play('click');
}

const CommandCenter = (function () {

  const INTENT_HINTS = [
    'Restart the nginx service',
    'Show memory usage',
    'Why is disk I/O spiking?',
    'List listening ports',
    'Audit SSH security',
    'Find files larger than 100MB',
    'Show top CPU processes',
    'Check disk space',
    'Tail the system journal',
    'Flush DNS cache',
    'List running Docker containers',
    'Show boot time analysis',
  ];

  const PLACEHOLDERS = [
    'Restart the nginx service...',
    'Show me memory usage for the last hour...',
    'Why is disk I/O spiking?',
    'List all listening ports...',
    'Audit SSH security configuration...',
    'Find files larger than 100 MB...',
    'Show top CPU-consuming processes...',
    'Check available disk space...',
  ];

  const state = {
    mode: 'text',
    sessionId: null,
    sseSource: null,
    isListening: false,
    finalTranscript: '',
    interimTranscript: '',
    recognition: null,
    audioCtx: null,
    analyser: null,
    animFrameId: null,
    micStream: null,
    commandHistory: [],
    cards: new Map(),
    placeholderIdx: 0,
    placeholderTimer: null,
  };

  // ── Public: init ──────────────────────────────────────────────────────────
  function init() {
    _loadHistory();
    const savedMode = _storageGet('cc-mode') || 'text';
    setMode(savedMode, true);
    _bindTextInput();
    _checkVoiceSupport();
    _startPlaceholderRotation();
    if (window.lucide) lucide.createIcons();
  }

  // ── Public: setMode ────────────────────────────────────────────────────────
  function setMode(mode, silent) {
    state.mode = mode;
    if (!silent) {
      _storageSet('cc-mode', mode);
      SoundFX.play('click');
    }

    const textBtn  = document.getElementById('cc-btn-text');
    const voiceBtn = document.getElementById('cc-btn-voice');
    const textPanel  = document.getElementById('cc-text-panel');
    const voicePanel = document.getElementById('cc-voice-panel');

    if (textBtn)  { textBtn.classList.toggle('active', mode === 'text'); textBtn.setAttribute('aria-pressed', String(mode === 'text')); }
    if (voiceBtn) { voiceBtn.classList.toggle('active', mode === 'voice'); voiceBtn.setAttribute('aria-pressed', String(mode === 'voice')); }
    if (textPanel)  textPanel.classList.toggle('hidden', mode !== 'text');
    if (voicePanel) voicePanel.classList.toggle('hidden', mode !== 'voice');

    if (mode !== 'voice' && state.isListening) _stopListening(false);
    if (window.lucide) lucide.createIcons();
  }

  // ── Public: submitCommand ─────────────────────────────────────────────────
  async function submitCommand(text) {
    text = (text || '').trim();
    if (!text) return;

    SoundFX.play('click');
    MascotManager.setMood('THINKING', `Analyzing: "${text}"...`);

    state.commandHistory = [text, ...state.commandHistory.filter(h => h !== text)].slice(0, 20);
    _storageSet('cc-history', JSON.stringify(state.commandHistory));

    const transcript = document.getElementById('cc-transcript');
    if (transcript) {
      const empty = transcript.querySelector('.cc-empty-state');
      if (empty) empty.remove();
    }

    const tempId = 'tmp-' + Date.now();
    const card = _createCard(tempId, text);
    if (transcript) {
      transcript.prepend(card);
      card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    if (window.lucide) lucide.createIcons();

    const inp = document.getElementById('cc-text-input');
    if (inp) { inp.value = ''; inp.style.height = 'auto'; }

    try {
      _setStage(card, 'understanding', 'loading');

      const res = await fetch('/api/command/interpret', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error('Interpret failed: HTTP ' + res.status);
      const data = await res.json();

      const sid = data.session_id;
      state.sessionId = sid;
      card.dataset.sessionId = sid;
      state.cards.set(sid, card);

      // Save to Left Sidebar History
      HistorySidebar.saveSession({
        id: sid,
        title: text,
        timestamp: Date.now(),
        safety_level: data.safety_level
      });

      _updateUnderstanding(card, data.understanding);
      _setStage(card, 'understanding', 'done');
      _renderPlanSteps(card, data.plan_steps || []);

      if (data.requires_confirmation) {
        _setStage(card, 'plan', 'active');
        _showConfirmUI(card, sid, data.safety_level, data.plan_steps || []);
        MascotManager.setMood('GATED', 'Safety check: Confirmation required before execution.');
        SoundFX.play('warning');
      } else {
        _setStage(card, 'plan', 'active');
        _openSSEStream(sid);
        await _executeCommand(sid, false);
      }
    } catch (err) {
      _setCardError(card, err.message || 'Unknown error');
      MascotManager.setMood('GATED', 'Command interpretation failed.');
      SoundFX.play('error');
    }
  }

  // ── Public: clearTranscript ───────────────────────────────────────────────
  function clearTranscript() {
    const t = document.getElementById('cc-transcript');
    if (!t) return;
    t.innerHTML = `
      <div class="cc-empty-state">
        <div class="w-12 h-12 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mx-auto mb-3 shadow-lg shadow-cyan-500/10">
          <i data-lucide="sparkles" class="w-6 h-6 text-cyan-400"></i>
        </div>
        <p class="text-sm font-semibold text-zinc-200 mb-1">Linux Operations Copilot Ready</p>
        <p class="text-xs text-zinc-500 max-w-md mx-auto leading-relaxed">
          Enter any query below or tap the microphone to speak. Every operation produces an Explainable AI <strong class="text-cyan-400">Understanding &rarr; Plan &rarr; Result</strong> trace with safety guardrails.
        </p>
      </div>`;
    state.cards.clear();
    SoundFX.play('click');
    if (window.lucide) lucide.createIcons();
  }

  // ── Private: text input ───────────────────────────────────────────────────
  function _bindTextInput() {
    const inp  = document.getElementById('cc-text-input');
    const send = document.getElementById('cc-send-btn');
    if (!inp) return;

    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const v = inp.value.trim();
        if (v) submitCommand(v);
      }
    });

    inp.addEventListener('input', () => {
      inp.style.height = 'auto';
      inp.style.height = Math.min(inp.scrollHeight, 160) + 'px';
    });

    if (send) send.addEventListener('click', () => { const v = inp.value.trim(); if (v) submitCommand(v); });
  }

  function _startPlaceholderRotation() {
    if (state.placeholderTimer) return;
    state.placeholderTimer = setInterval(() => {
      const inp = document.getElementById('cc-text-input');
      if (inp && document.activeElement !== inp) {
        inp.placeholder = PLACEHOLDERS[state.placeholderIdx % PLACEHOLDERS.length];
        state.placeholderIdx++;
      }
    }, 4000);
  }

  // ── Private: voice support ────────────────────────────────────────────────
  function _checkVoiceSupport() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) {
      _showFallback('Your browser does not support the Web Speech API. Using Text mode.');
      const vBtn = document.getElementById('cc-btn-voice');
      if (vBtn) vBtn.disabled = true;
      return;
    }
    _initVoice(SpeechRec);
  }

  function _showFallback(msg) {
    const banner = document.getElementById('cc-voice-fallback');
    const msgEl  = document.getElementById('cc-voice-fallback-msg');
    if (banner) banner.classList.remove('hidden');
    if (msgEl)  msgEl.textContent = msg;
  }

  function _initVoice(SpeechRec) {
    const rec = new SpeechRec();
    rec.continuous     = true;
    rec.interimResults = true;
    rec.lang           = navigator.language || 'en-US';

    rec.onresult = evt => {
      let interim = '', final = '';
      for (let i = evt.resultIndex; i < evt.results.length; i++) {
        const t = evt.results[i][0].transcript;
        if (evt.results[i].isFinal) final += t; else interim += t;
      }
      if (final) state.finalTranscript += final;
      state.interimTranscript = interim;
      const preview = document.getElementById('cc-voice-preview');
      const txt = state.finalTranscript + interim;
      if (preview) { preview.textContent = txt; preview.classList.toggle('hidden', !txt); preview.classList.toggle('active', state.isListening); }
    };

    rec.onerror = evt => {
      if (evt.error === 'not-allowed') {
        _showFallback('Microphone access denied. Please allow mic permission in your browser.');
        _stopListening(false); setMode('text');
      } else {
        showToast('Speech recognition error: ' + evt.error, 'error');
        _stopListening(false);
      }
    };

    rec.onend = () => { if (state.isListening) { try { rec.start(); } catch (e) {} } };
    state.recognition = rec;

    const micBtn = document.getElementById('cc-mic-btn');
    if (micBtn) {
      micBtn.addEventListener('click', () => {
        if (state.isListening) _stopListening(true); else _startListening();
      });
    }
  }

  function _startListening() {
    if (!state.recognition) return;
    SoundFX.play('mic-start');
    MascotManager.setMood('THINKING', 'Listening to voice query...');
    state.isListening = true;
    state.finalTranscript = '';
    state.interimTranscript = '';
    const preview = document.getElementById('cc-voice-preview');
    if (preview) { preview.textContent = ''; preview.classList.add('hidden'); }
    try { state.recognition.start(); } catch (e) {}
    _setMicState('recording');
    _startWaveform();
  }

  function _stopListening(submit) {
    SoundFX.play('mic-stop');
    state.isListening = false;
    if (state.recognition) { try { state.recognition.stop(); } catch (e) {} }
    _stopWaveform();
    _setMicState('idle');
    if (submit) {
      const text = (state.finalTranscript + ' ' + (state.interimTranscript || '')).trim();
      state.finalTranscript = ''; state.interimTranscript = '';
      const preview = document.getElementById('cc-voice-preview');
      if (preview) preview.classList.add('hidden');
      if (text) submitCommand(text);
    }
  }

  function _setMicState(s) {
    const btn   = document.getElementById('cc-mic-btn');
    const label = document.getElementById('cc-mic-label');
    if (!btn) return;
    btn.classList.remove('cc-mic-idle', 'cc-mic-recording', 'cc-mic-processing');
    btn.classList.add('cc-mic-' + s);
    const icon = btn.querySelector('.cc-mic-icon');
    if (icon) { icon.setAttribute('data-lucide', s === 'processing' ? 'loader-2' : 'mic'); if (window.lucide) lucide.createIcons(); }
    const canvas = document.getElementById('cc-waveform-canvas');
    if (canvas) canvas.classList.toggle('hidden', s !== 'recording');
    if (label) label.textContent = s === 'recording' ? 'Tap to stop & send' : 'Tap to speak';
  }

  // ── Private: waveform ─────────────────────────────────────────────────────
  async function _startWaveform() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx    = new AudioContext();
      const src    = ctx.createMediaStreamSource(stream);
      const anlsr  = ctx.createAnalyser();
      anlsr.fftSize = 64;
      src.connect(anlsr);
      state.audioCtx = ctx; state.analyser = anlsr; state.micStream = stream;
      _drawWaveform();
    } catch (e) {}
  }

  function _stopWaveform() {
    if (state.animFrameId) { cancelAnimationFrame(state.animFrameId); state.animFrameId = null; }
    if (state.audioCtx)   { state.audioCtx.close(); state.audioCtx = null; state.analyser = null; }
    if (state.micStream)  { state.micStream.getTracks().forEach(t => t.stop()); state.micStream = null; }
    const canvas = document.getElementById('cc-waveform-canvas');
    if (canvas) { const cx = canvas.getContext('2d'); cx.clearRect(0, 0, canvas.width, canvas.height); }
  }

  function _drawWaveform() {
    const canvas = document.getElementById('cc-waveform-canvas');
    if (!canvas || !state.analyser) return;
    const cx = canvas.getContext('2d');
    const buf = new Uint8Array(state.analyser.frequencyBinCount);
    const draw = () => {
      if (!state.isListening || !state.analyser) return;
      state.animFrameId = requestAnimationFrame(draw);
      state.analyser.getByteFrequencyData(buf);
      const W = canvas.width, H = canvas.height;
      cx.clearRect(0, 0, W, H);
      const BARS = 14, barW = (W / BARS) - 1.5;
      for (let i = 0; i < BARS; i++) {
        const v = buf[Math.floor(i * buf.length / BARS)] / 255;
        const h = Math.max(3, v * H);
        const x = i * (barW + 1.5), y = (H - h) / 2;
        cx.fillStyle = `rgba(6, 182, 212, ${0.35 + v * 0.65})`;
        cx.beginPath();
        if (cx.roundRect) cx.roundRect(x, y, barW, h, 2); else cx.rect(x, y, barW, h);
        cx.fill();
      }
    };
    draw();
  }

  // ── Private: execute ──────────────────────────────────────────────────────
  async function _executeCommand(sid, confirmed) {
    try {
      const res = await fetch('/api/command/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sid, confirmed }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const card = state.cards.get(sid);
        if (card) _setCardError(card, err.error || 'Execution blocked (HTTP ' + res.status + ')');
      }
    } catch (e) {
      const card = state.cards.get(sid);
      if (card) _setCardError(card, 'Network error: ' + e.message);
    }
  }

  // ── Private: SSE stream ───────────────────────────────────────────────────
  function _openSSEStream(sid) {
    if (state.sseSource) { state.sseSource.close(); state.sseSource = null; }
    const src = new EventSource('/api/command/stream/' + sid);
    state.sseSource = src;
    ['understanding', 'plan_step', 'confirmation_required', 'result', 'error', 'done'].forEach(type => {
      src.addEventListener(type, e => {
        try { _handleSSEEvent(sid, type, type === 'done' ? {} : JSON.parse(e.data)); } catch (err) {}
      });
    });
    src.onerror = () => { src.close(); state.sseSource = null; };
  }

  function _handleSSEEvent(sid, type, data) {
    const card = state.cards.get(sid);
    if (!card) return;

    if (type === 'understanding') {
      _updateUnderstanding(card, data.text || '');
      _setStage(card, 'understanding', 'done');
      MascotManager.setMood('THINKING', data.text || 'Planning execution...');
    } else if (type === 'plan_step') {
      _upsertPlanStep(card, data);
      if (data.status === 'running') _setStage(card, 'plan', 'active');
      if (data.status === 'done' || data.status === 'failed') {
        const allSteps = [...card.querySelectorAll('.cc-step')];
        if (allSteps.length && allSteps.every(s => s.dataset.status === 'done' || s.dataset.status === 'failed'))
          _setStage(card, 'plan', 'done');
      }
    } else if (type === 'confirmation_required') {
      _showConfirmUI(card, sid, data.safety_level, null);
      MascotManager.setMood('GATED', 'Safety check: Action requires operator confirmation.');
      SoundFX.play('warning');
    } else if (type === 'result') {
      _setStage(card, 'plan', 'done');
      _setStage(card, 'result', 'active');
      _updateResult(card, data);
      _setStage(card, 'result', data.success ? 'done' : 'failed');
      if (data.success) {
        MascotManager.setMood('SUCCESS', data.summary || 'Command execution finished successfully.');
        SoundFX.play('success');
      } else {
        MascotManager.setMood('GATED', data.summary || 'Command encountered an error.');
        SoundFX.play('error');
      }
      if (state.sseSource) { state.sseSource.close(); state.sseSource = null; }
    } else if (type === 'error') {
      _setCardError(card, data.message || 'An error occurred');
      MascotManager.setMood('GATED', data.message || 'Execution error');
      SoundFX.play('error');
      if (state.sseSource) { state.sseSource.close(); state.sseSource = null; }
    } else if (type === 'done') {
      if (state.sseSource) { state.sseSource.close(); state.sseSource = null; }
    }
    if (window.lucide) lucide.createIcons();
  }

  // ── Private: card DOM builders ────────────────────────────────────────────
  function _createCard(tempId, queryText) {
    const card = document.createElement('div');
    card.className = 'cc-reasoning-card';
    card.dataset.sessionId = tempId;
    card.innerHTML = `
      <div class="cc-card-header">
        <div class="flex items-center gap-2 min-w-0">
          <i data-lucide="user" class="w-3.5 h-3.5 text-cyan-400 shrink-0"></i>
          <span class="text-xs font-semibold text-zinc-200 truncate">${escapeHtml(queryText)}</span>
        </div>
        <span class="text-[10px] text-zinc-500 font-mono shrink-0 ml-2">${new Date().toLocaleTimeString()}</span>
      </div>
      <div class="cc-stage active" data-stage="understanding">
        <button class="cc-stage-header" onclick="ccToggleStage(this)" aria-expanded="true">
          <div class="flex items-center gap-2">
            <span class="cc-stage-num">1</span>
            <i data-lucide="brain-circuit" class="w-3.5 h-3.5 text-cyan-400"></i>
            <span>What I understood</span>
          </div>
          <i data-lucide="chevron-down" class="cc-chevron w-3.5 h-3.5"></i>
        </button>
        <div class="cc-stage-body">
          <div class="cc-understanding-text text-zinc-400 italic text-xs flex items-center gap-1.5">
            <i data-lucide="loader-2" class="w-3 h-3 cc-spin text-cyan-400"></i> Classifying intent and parsing semantics...
          </div>
        </div>
      </div>
      <div class="cc-stage collapsed" data-stage="plan">
        <button class="cc-stage-header" onclick="ccToggleStage(this)" aria-expanded="false">
          <div class="flex items-center gap-2">
            <span class="cc-stage-num">2</span>
            <i data-lucide="list-checks" class="w-3.5 h-3.5 text-emerald-400"></i>
            <span>What I'm about to do</span>
          </div>
          <i data-lucide="chevron-down" class="cc-chevron w-3.5 h-3.5"></i>
        </button>
        <div class="cc-stage-body">
          <div class="cc-plan-steps space-y-0"></div>
          <div class="cc-confirm-ui hidden mt-3"></div>
        </div>
      </div>
      <div class="cc-stage collapsed" data-stage="result">
        <button class="cc-stage-header" onclick="ccToggleStage(this)" aria-expanded="false">
          <div class="flex items-center gap-2">
            <span class="cc-stage-num">3</span>
            <i data-lucide="check-circle" class="w-3.5 h-3.5 text-emerald-400"></i>
            <span>What I did / found</span>
          </div>
          <i data-lucide="chevron-down" class="cc-chevron w-3.5 h-3.5"></i>
        </button>
        <div class="cc-stage-body">
          <div class="cc-result-content"></div>
        </div>
      </div>`;
    return card;
  }

  function _setStage(card, stageName, stateStr) {
    const stage = card.querySelector(`[data-stage="${stageName}"]`);
    if (!stage) return;
    stage.classList.remove('active', 'done', 'failed', 'collapsed');
    const header = stage.querySelector('.cc-stage-header');
    if (stateStr === 'active' || stateStr === 'loading' || stateStr === 'confirm') {
      stage.classList.add('active');
      if (header) header.setAttribute('aria-expanded', 'true');
    } else if (stateStr === 'pending') {
      stage.classList.add('collapsed');
      if (header) header.setAttribute('aria-expanded', 'false');
    } else if (stateStr === 'done') {
      stage.classList.add('done', 'collapsed');
      if (header) header.setAttribute('aria-expanded', 'false');
    } else if (stateStr === 'failed') {
      stage.classList.add('failed', 'collapsed');
      if (header) header.setAttribute('aria-expanded', 'false');
    }
  }

  function _updateUnderstanding(card, text) {
    const el = card.querySelector('.cc-understanding-text');
    if (el) el.innerHTML = `<span class="text-zinc-200 leading-relaxed font-medium">${escapeHtml(text)}</span>`;
  }

  function _renderPlanSteps(card, steps) {
    _setStage(card, 'plan', 'active');
    const container = card.querySelector('.cc-plan-steps');
    if (!container) return;
    container.innerHTML = '';
    steps.forEach(step => _upsertPlanStep(card, { ...step, status: 'pending' }));
  }

  function _upsertPlanStep(card, data) {
    const container = card.querySelector('.cc-plan-steps');
    if (!container) return;
    const idx = data.index, status = data.status || 'pending';
    let el = container.querySelector(`[data-step-idx="${idx}"]`);
    if (!el) { el = document.createElement('div'); el.className = 'cc-step'; el.dataset.stepIdx = idx; container.appendChild(el); }
    el.dataset.status = status;

    const icons = {
      pending: `<i data-lucide="circle" class="w-3.5 h-3.5 text-zinc-600 shrink-0"></i>`,
      running: `<i data-lucide="loader-2" class="w-3.5 h-3.5 text-cyan-400 cc-spin shrink-0"></i>`,
      done:    `<i data-lucide="check-circle" class="w-3.5 h-3.5 text-emerald-400 shrink-0"></i>`,
      failed:  `<i data-lucide="alert-circle" class="w-3.5 h-3.5 text-rose-400 shrink-0"></i>`,
    };
    const badge = (data.safety_level && data.safety_level !== 'READ_ONLY')
      ? `<span class="${getSafetyBadgeClass(data.safety_level)} text-[9px] font-mono px-1.5 py-0.5 rounded uppercase">${escapeHtml(data.safety_level)}</span>` : '';
    const outHtml = ((status === 'done' || status === 'failed') && data.output)
      ? `<div class="cc-step-cmd mt-1 opacity-80 max-h-32 overflow-y-auto">${escapeHtml(data.output.slice(0, 300))}${data.output.length > 300 ? '…' : ''}</div>` : '';

    el.innerHTML = `
      ${icons[status] || icons.pending}
      <div class="flex-1 min-w-0">
        <div class="flex items-center flex-wrap gap-1.5">
          <span class="text-xs text-zinc-200 font-medium">${escapeHtml(data.description || data.command || '')}</span>
          ${badge}
        </div>
        ${data.command ? `<div class="cc-step-cmd">$ ${escapeHtml(data.command)}</div>` : ''}
        ${outHtml}
      </div>`;
    if (window.lucide) lucide.createIcons();
  }

  function _showConfirmUI(card, sid, safetyLevel, steps) {
    const ui = card.querySelector('.cc-confirm-ui');
    if (!ui) return;
    ui.classList.remove('hidden');
    const col = safetyLevel === 'DESTRUCTIVE' ? 'text-rose-400' : 'text-amber-400';
    ui.innerHTML = `
      <div class="w-full p-3.5 rounded-lg bg-rose-500/10 border border-rose-500/20">
        <div class="flex items-center gap-2 text-xs">
          <i data-lucide="alert-triangle" class="w-4 h-4 text-rose-400 shrink-0"></i>
          <span>This is a <strong class="${col} font-bold">${escapeHtml(safetyLevel)}</strong> operation. Review the steps above carefully.</span>
        </div>
        <div class="flex items-center gap-2.5 mt-3">
          <button class="btn btn-ghost px-3.5 py-1.5 text-xs border border-white/10"
                  onclick="CommandCenter._cancelExecution('${escapeHtml(sid)}')">
            <i data-lucide="x" class="w-3.5 h-3.5"></i><span>Cancel</span>
          </button>
          <button class="btn btn-primary px-4 py-1.5 text-xs font-semibold ${safetyLevel === 'DESTRUCTIVE' ? 'bg-rose-600 hover:bg-rose-500 border-rose-500' : ''}"
                  onclick="CommandCenter._confirmExecution('${escapeHtml(sid)}')">
            <i data-lucide="check" class="w-3.5 h-3.5"></i><span>Confirm &amp; Execute</span>
          </button>
        </div>
      </div>`;
    if (window.lucide) lucide.createIcons();
  }

  function _confirmExecution(sid) {
    SoundFX.play('click');
    const card = state.cards.get(sid);
    const ui = card && card.querySelector('.cc-confirm-ui');
    if (ui) ui.classList.add('hidden');
    MascotManager.setMood('THINKING', 'Executing confirmed operations...');
    _openSSEStream(sid);
    _executeCommand(sid, true);
  }

  function _cancelExecution(sid) {
    SoundFX.play('click');
    const card = state.cards.get(sid);
    if (!card) return;
    const ui = card.querySelector('.cc-confirm-ui');
    if (ui) ui.innerHTML = `<span class="text-xs text-zinc-500 italic">Operation cancelled by operator.</span>`;
    _setStage(card, 'plan', 'failed');
    MascotManager.setMood('OBSERVING', 'Operation cancelled.');
    showToast('Command execution cancelled', 'info', 2000);
  }

  function _updateResult(card, data) {
    const el = card.querySelector('.cc-result-content');
    if (!el) return;
    const icon = data.success
      ? `<i data-lucide="check-circle" class="w-4 h-4 text-emerald-400 shrink-0 mt-0.5"></i>`
      : `<i data-lucide="alert-circle" class="w-4 h-4 text-rose-400 shrink-0 mt-0.5"></i>`;
    
    const paragraphText = data.paragraph || data.summary || 'Command execution finished.';
    
    const paragraphHtml = paragraphText ? `
      <div class="mt-2.5 p-3 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-xs text-cyan-100 leading-relaxed shadow-sm">
        <div class="flex items-center gap-1.5 text-cyan-300 font-semibold mb-1 text-[11px] uppercase tracking-wider">
          <i data-lucide="sparkles" class="w-3.5 h-3.5 text-cyan-400"></i>
          <span>Natural Language Explanation & Impact</span>
        </div>
        <p class="text-zinc-200 text-xs font-normal leading-relaxed">${escapeHtml(paragraphText)}</p>
      </div>` : '';

    const raw = data.raw_output ? `
      <details class="cc-result-details mt-2 p-2 bg-[#08090e] rounded-lg border border-white/[0.06]">
        <summary class="text-xs text-zinc-400 font-mono cursor-pointer hover:text-zinc-200 select-none">Technical Details ▾</summary>
        <pre class="cc-result-raw text-xs font-mono mt-1 text-zinc-300 overflow-x-auto whitespace-pre-wrap p-2 bg-black/40 rounded">${escapeHtml(data.raw_output)}</pre>
      </details>` : '';

    el.innerHTML = `
      <div class="flex items-start gap-2">${icon}<p class="text-xs text-zinc-200 leading-relaxed font-medium">${escapeHtml(data.summary || 'Done.')}</p></div>
      ${paragraphHtml}
      ${raw}`;

    // Update Persistent Explanation Banner directly above Command Input Textarea
    const banner = document.getElementById('cc-explanation-banner');
    const bannerText = document.getElementById('cc-explanation-text');
    if (banner && bannerText && paragraphText) {
      bannerText.textContent = paragraphText;
      banner.classList.remove('hidden');
    }

    if (window.lucide) lucide.createIcons();
  }

  function _setCardError(card, message) {
    const existing = card.querySelector('.cc-card-error');
    if (existing) existing.remove();
    const err = document.createElement('div');
    err.className = 'cc-card-error flex items-center gap-2 px-4 py-2.5 text-xs text-rose-400 border-t border-rose-400/20 bg-rose-500/5';
    err.innerHTML = `<i data-lucide="alert-circle" class="w-3.5 h-3.5 shrink-0"></i><span>${escapeHtml(message)}</span>`;
    card.appendChild(err);
    if (window.lucide) lucide.createIcons();
  }

  // ── Private: storage helpers ───────────────────────────────────────────────
  function _storageGet(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function _storageSet(key, val) { try { localStorage.setItem(key, val); } catch (e) {} }
  function _loadHistory() {
    try { const r = _storageGet('cc-history'); state.commandHistory = r ? JSON.parse(r) : []; }
    catch (e) { state.commandHistory = []; }
  }

  // ── Public exports ─────────────────────────────────────────────────────────
  return { init, setMode, submitCommand, clearTranscript, _confirmExecution, _cancelExecution };

})();

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
