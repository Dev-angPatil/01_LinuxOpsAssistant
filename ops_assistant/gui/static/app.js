// ==========================================================================
// LinuxOps Assistant — Linear-Inspired Client Application Logic & Guardrails
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
  checkSetupStatusOnLoad();

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
    btnRefresh.addEventListener('click', fetchHealthSnapshot);
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
      }
    }
    // Escape to close modals
    if (e.key === 'Escape') {
      closeModal('modal-permission');
      closeModal('modal-logs');
      closeModal('modal-setup-wizard');
    }
  });
});

// ==========================================================================
// TOAST NOTIFICATION SYSTEM (Replaces crude alert() dialogs)
// ==========================================================================
function showToast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast-item';

  let iconName = 'info';
  let iconColor = 'text-zinc-400';
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
    safetyEl.className = 'font-semibold ' + getSafetyTextColor(safetyLevel);
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
      if (onApprove) await onApprove();
      resolve(true);
    };

    dryRunBtn.onclick = async () => {
      cleanup();
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
  'home': 'AI Ops Agent',
  'health': 'System Health & PSI Telemetry',
  'services': 'Services & Process Management',
  'storage': 'Storage Analysis & Cleanup',
  'network': 'Network & Firewall Control',
  'taxonomy': '16-Class Failure Taxonomy',
  'packages': 'Package Management',
  'desktop': 'Desktop & Task Runner'
};

function switchTab(tabId) {
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
  document.getElementById('header-hostname').textContent = snap.hostname || 'localhost';
  document.getElementById('header-distro').textContent = distroName;
  document.getElementById('header-kernel').textContent = 'Kernel ' + (snap.kernel_release || '');

  const pressureBadge = document.getElementById('header-pressure');
  pressureBadge.textContent = snap.pressure_status || 'NORMAL';
  if (snap.pressure_status === 'ELEVATED') {
    pressureBadge.className = 'font-mono text-[11px] font-semibold text-amber-400';
  } else if (snap.pressure_status === 'CRITICAL') {
    pressureBadge.className = 'font-mono text-[11px] font-semibold text-rose-400';
  } else {
    pressureBadge.className = 'font-mono text-[11px] font-semibold text-emerald-400';
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
// HARDWARE SETUP & MODEL CONFIGURATION WIZARD
// ==========================================================================
let currentSetupData = null;
let downloadPollInterval = null;

async function checkSetupStatusOnLoad() {
  try {
    const res = await fetch('/api/setup/status');
    const data = await res.json();
    currentSetupData = data;
    // Auto-open wizard if setup is not completed and no model is installed
    if (!data.setup_completed && !data.has_models) {
      setTimeout(() => {
        openSetupWizard();
      }, 500);
    }
  } catch (e) {
    console.warn('Could not check setup status:', e);
  }
}

async function openSetupWizard() {
  openModal('modal-setup-wizard');
  try {
    const res = await fetch('/api/setup/status');
    const data = await res.json();
    currentSetupData = data;
    renderSetupModalData(data);
  } catch (e) {
    showToast('Failed to load hardware advisory: ' + e.message, 'error');
  }
}

function renderSetupModalData(data) {
  if (!data) return;
  const hw = data.hardware || {};
  const rec = data.recommended_model || {};
  const cfg = data.config || {};
  const installed = data.installed_models || {};
  const catalog = data.catalog || {};

  // 1. Hardware Badges & Specs
  const tierBadge = document.getElementById('setup-tier-badge');
  if (tierBadge && hw.compute_tier) {
    tierBadge.textContent = `${hw.compute_tier} (${(hw.hardware_score || 0).toFixed(1)}/100)`;
  }

  const cpuInfo = document.getElementById('setup-cpu-info');
  const cpuCores = document.getElementById('setup-cpu-cores');
  if (cpuInfo && hw.cpu) {
    cpuInfo.textContent = hw.cpu.model_name || 'CPU';
    cpuCores.textContent = `${hw.cpu.logical_cores || 1} cores • AVX2: ${hw.cpu.has_avx2 ? 'Yes' : 'No'}`;
  }

  const ramInfo = document.getElementById('setup-ram-info');
  const ramHeadroom = document.getElementById('setup-ram-headroom');
  if (ramInfo && hw.memory) {
    ramInfo.textContent = `${hw.memory.total_gb || 0} GB RAM (${hw.memory.available_gb || 0} GB Free)`;
    ramHeadroom.textContent = `Safe AI Headroom: ${(hw.memory.safe_model_headroom_mb || 0).toFixed(0)} MB`;
  }

  const gpuInfo = document.getElementById('setup-gpu-info');
  const gpuVram = document.getElementById('setup-gpu-vram');
  if (gpuInfo && hw.gpu) {
    gpuInfo.textContent = hw.gpu.device_name || 'No Dedicated GPU';
    gpuVram.textContent = hw.gpu.present ? `${hw.gpu.total_vram_gb || 0} GB VRAM • ${hw.gpu.compute_api}` : 'CPU Multithreaded Fallback';
  }

  const diskInfo = document.getElementById('setup-disk-info');
  const diskFree = document.getElementById('setup-disk-free');
  if (diskInfo && hw.storage) {
    diskInfo.textContent = `${hw.storage.available_gb || 0} GB Free`;
    diskFree.textContent = `Target: ${hw.storage.target_path || '/'}`;
  }

  // 2. Recommended Model Card
  const recName = document.getElementById('setup-rec-name');
  const recReason = document.getElementById('setup-rec-reason');
  const recSize = document.getElementById('setup-rec-size');
  const recTier = document.getElementById('setup-rec-tier');
  const recAccel = document.getElementById('setup-rec-accel-badge');
  const recConfigHint = document.getElementById('setup-rec-config-hint');
  const btnInstallRec = document.getElementById('setup-btn-install-rec');

  if (recName) recName.textContent = rec.name || 'Deterministic Rule Engine';
  if (recReason) recReason.textContent = rec.reason || 'Optimal offline Linux diagnostic engine.';
  if (recSize) recSize.textContent = rec.size_mb ? `~${rec.size_mb} MB` : '0 MB';
  if (recTier) recTier.textContent = rec.tier || 'Tier 0';
  if (recAccel) recAccel.textContent = rec.acceleration || 'Zero Memory Footprint';
  if (recConfigHint) {
    recConfigHint.textContent = `Config: ${cfg.recommended_threads || 4} threads, ${cfg.recommended_ctx_size || 2048} ctx size`;
  }

  if (btnInstallRec) {
    if (rec.model_key && installed[rec.model_key] && installed[rec.model_key].is_downloaded) {
      btnInstallRec.innerHTML = `<i data-lucide="check" class="w-4 h-4"></i><span>Active &amp; Ready</span>`;
      btnInstallRec.className = 'btn btn-secondary px-5 py-2 text-xs font-semibold flex items-center space-x-2 text-emerald-400 border-emerald-500/30';
    } else if (!rec.download_required) {
      btnInstallRec.innerHTML = `<i data-lucide="check-circle" class="w-4 h-4"></i><span>Activate Deterministic</span>`;
      btnInstallRec.className = 'btn btn-primary px-5 py-2 text-xs font-semibold flex items-center space-x-2';
    } else {
      btnInstallRec.innerHTML = `<i data-lucide="download" class="w-4 h-4"></i><span>1-Click Install &amp; Activate</span>`;
      btnInstallRec.className = 'btn btn-primary px-5 py-2 text-xs font-semibold flex items-center space-x-2 shadow-md shadow-cyan-500/10';
    }
  }

  // 3. Status text
  const statusText = document.getElementById('setup-active-status-text');
  if (statusText) {
    const mode = cfg.provider || 'auto';
    const model = cfg.active_model_key ? `Model: ${cfg.active_model_key}` : 'Deterministic Engine';
    statusText.textContent = `Current Mode: ${mode.toUpperCase()} (${model}) • Setup: ${data.setup_completed ? 'Configured' : 'First-Run Pending'}`;
  }

  // 4. Populate Full Catalog list
  renderCatalogList(catalog, installed);

  if (window.lucide) lucide.createIcons();
}

function renderCatalogList(catalog, installed) {
  const container = document.getElementById('catalog-list-container');
  if (!container) return;
  container.innerHTML = '';

  Object.entries(catalog).forEach(([key, info]) => {
    const isDl = installed[key] && installed[key].is_downloaded;
    const sizeMb = (info.size_bytes / (1024 * 1024)).toFixed(0);
    const item = document.createElement('div');
    item.className = 'p-3 rounded-lg bg-black/40 border border-white/[0.06] flex items-center justify-between space-x-3 text-xs';
    
    item.innerHTML = `
      <div class="space-y-0.5 min-w-0">
        <div class="flex items-center space-x-2">
          <span class="font-semibold text-white truncate">${escapeHtml(info.name)}</span>
          <span class="px-1.5 py-0.2 rounded text-[9px] font-mono bg-white/10 text-zinc-400">${escapeHtml(info.tier)}</span>
          ${isDl ? '<span class="px-1.5 py-0.2 rounded text-[9px] font-mono bg-emerald-500/20 text-emerald-300">Installed</span>' : ''}
        </div>
        <p class="text-[11px] text-zinc-400 truncate">${escapeHtml(info.description)}</p>
        <div class="text-[10px] font-mono text-zinc-500">
          Size: ~${sizeMb} MB • RAM required: ${info.ram_required_mb} MB • Min cores: ${info.min_cores}
        </div>
      </div>
      <div class="shrink-0">
        ${isDl 
          ? `<button onclick="applySetupMode('gguf', '${key}')" class="btn btn-secondary px-3 py-1 text-xs text-emerald-300">Activate</button>`
          : `<button onclick="downloadCatalogModel('${key}')" class="btn btn-primary px-3 py-1 text-xs flex items-center space-x-1">
              <i data-lucide="download" class="w-3.5 h-3.5"></i>
              <span>Install</span>
            </button>`
        }
      </div>
    `;
    container.appendChild(item);
  });
}

function toggleModelCatalogList() {
  const container = document.getElementById('catalog-list-container');
  const chevron = document.getElementById('catalog-chevron');
  if (container) {
    const isHidden = container.classList.contains('hidden');
    if (isHidden) {
      container.classList.remove('hidden');
      if (chevron) chevron.style.transform = 'rotate(180deg)';
    } else {
      container.classList.add('hidden');
      if (chevron) chevron.style.transform = 'rotate(0deg)';
    }
  }
}

async function installRecommendedModel() {
  if (!currentSetupData) return;
  const rec = currentSetupData.recommended_model;
  if (!rec) return;

  if (!rec.download_required || !rec.model_key) {
    // Deterministic mode
    await applySetupMode('deterministic');
    return;
  }

  const mkey = rec.model_key;
  await downloadCatalogModel(mkey);
}

async function downloadCatalogModel(modelKey) {
  const progressBox = document.getElementById('setup-download-container');
  const modelNameEl = document.getElementById('setup-download-model-name');
  if (progressBox) progressBox.classList.remove('hidden');
  if (modelNameEl) modelNameEl.textContent = `Downloading ${modelKey}...`;

  try {
    const res = await fetch('/api/models/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_key: modelKey, force: false })
    });
    const data = await res.json();
    if (!data.success && data.status !== 'already_downloading') {
      showToast('Download failed to start: ' + (data.error || 'Unknown error'), 'error');
      if (progressBox) progressBox.classList.add('hidden');
      return;
    }

    showToast(`Download started for ${modelKey}...`, 'info');
    startProgressPolling(modelKey);
  } catch (e) {
    showToast('Download error: ' + e.message, 'error');
    if (progressBox) progressBox.classList.add('hidden');
  }
}

function startProgressPolling(modelKey) {
  if (downloadPollInterval) clearInterval(downloadPollInterval);

  const progressBox = document.getElementById('setup-download-container');
  const progressBar = document.getElementById('setup-download-progress-bar');
  const pctEl = document.getElementById('setup-download-pct');
  const bytesEl = document.getElementById('setup-download-bytes');
  const speedEl = document.getElementById('setup-download-speed');
  const statusEl = document.getElementById('setup-download-status');

  downloadPollInterval = setInterval(async () => {
    try {
      const res = await fetch('/api/models/download/progress');
      const data = await res.json();
      const downloads = data.downloads || {};
      const prog = downloads[modelKey];

      if (!prog) return;

      const pct = prog.percent || 0.0;
      const dlMb = ((prog.downloaded_bytes || 0) / (1024 * 1024)).toFixed(1);
      const totMb = ((prog.total_bytes || 0) / (1024 * 1024)).toFixed(1);
      const speed = prog.speed_mbps || 0.0;

      if (progressBar) progressBar.style.width = `${Math.min(100, Math.max(0, pct))}%`;
      if (pctEl) pctEl.textContent = `${pct.toFixed(1)}%`;
      if (bytesEl) bytesEl.textContent = `${dlMb} / ${totMb} MB`;
      if (speedEl) speedEl.textContent = `${speed.toFixed(1)} MB/s`;

      if (prog.status === 'completed') {
        clearInterval(downloadPollInterval);
        downloadPollInterval = null;
        if (statusEl) statusEl.textContent = '✓ Download Completed!';
        showToast(`Model ${modelKey} downloaded and verified successfully!`, 'success');
        
        // Auto-apply setup with the downloaded model
        await applySetupMode('gguf', modelKey);
        
        setTimeout(() => {
          if (progressBox) progressBox.classList.add('hidden');
          openSetupWizard();
        }, 1200);
      } else if (prog.status === 'failed') {
        clearInterval(downloadPollInterval);
        downloadPollInterval = null;
        if (statusEl) statusEl.textContent = '❌ Download Failed';
        showToast(`Download failed: ${prog.error}`, 'error');
      }
    } catch (e) {
      console.warn('Progress poll error:', e);
    }
  }, 600);
}

async function applySetupMode(provider, modelKey = null) {
  try {
    const body = { provider };
    if (modelKey) body.model_key = modelKey;

    const res = await fetch('/api/setup/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Configuration updated: ${provider.toUpperCase()}` + (modelKey ? ` (${modelKey})` : ''), 'success');
      // Refresh status
      const statRes = await fetch('/api/setup/status');
      const statData = await statRes.json();
      currentSetupData = statData;
      renderSetupModalData(statData);
    } else {
      showToast('Failed to apply configuration: ' + (data.error || 'Unknown error'), 'error');
    }
  } catch (e) {
    showToast('Error applying setup: ' + e.message, 'error');
  }
}


