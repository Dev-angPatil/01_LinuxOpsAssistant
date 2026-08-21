#!/usr/bin/env bash
# ==============================================================================
# AI-Powered Linux Operations Assistant (ops-assistant)
# One-Line Automated Installer & Hardware-Aware Configuration Engine
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Dev-angPatil/01_LinuxOpsAssistant/main/install.sh | bash
#   or locally:
#   chmod +x install.sh && ./install.sh
# ==============================================================================

set -eo pipefail

# ------------------------------------------------------------------------------
# 0. Terminal TTY & Color Setup
# ------------------------------------------------------------------------------
# If running via 'curl | bash', stdin is a pipe. Reconnect stdin to /dev/tty for interactive prompts.
if [ ! -t 0 ] && [ -e /dev/tty ]; then
    exec < /dev/tty
fi

# Detect color support
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    BOLD="\033[1m"
    DIM="\033[2m"
    RED="\033[0;31m"
    GREEN="\033[0;32m"
    YELLOW="\033[0;33m"
    BLUE="\033[0;34m"
    MAGENTA="\033[0;35m"
    CYAN="\033[0;36m"
    WHITE="\033[1;37m"
    BG_BLUE="\033[44m"
    RESET="\033[0m"
else
    BOLD=""
    DIM=""
    RED=""
    GREEN=""
    YELLOW=""
    BLUE=""
    MAGENTA=""
    CYAN=""
    WHITE=""
    BG_BLUE=""
    RESET=""
fi

REPO_URL="https://github.com/Dev-angPatil/01_LinuxOpsAssistant.git"
DEFAULT_INSTALL_DIR="$HOME/.local/share/ops-assistant"
BIN_DIR="$HOME/.local/bin"

print_banner() {
    clear 2>/dev/null || true
    echo -e "${CYAN}==============================================================================${RESET}"
    echo -e "${BOLD}${WHITE}       AI-POWERED LINUX OPERATIONS ASSISTANT (${GREEN}ops-assistant${WHITE})${RESET}"
    echo -e "       ${DIM}Autonomous • Explainable (XAI) • Hardware-Aware • Air-Gapped${RESET}"
    echo -e "${CYAN}==============================================================================${RESET}"
    echo ""
}

log_info() {
    echo -e "${CYAN}[*]${RESET} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${RESET} $1"
}

log_warn() {
    echo -e "${YELLOW}[!]${RESET} $1"
}

log_error() {
    echo -e "${RED}[✗]${RESET} $1"
}

print_banner

# ------------------------------------------------------------------------------
# 1. Distro & OS Detection
# ------------------------------------------------------------------------------
log_info "Profiling operating system and Linux distribution..."

OS_TYPE="$(uname -s)"
if [ "$OS_TYPE" != "Linux" ]; then
    log_error "This installer requires Linux (detected: $OS_TYPE). Aborting."
    exit 1
fi

DISTRO_ID="generic"
DISTRO_NAME="Generic Linux"
DISTRO_VERSION=""
PKG_MGR=""
INSTALL_CMD=""

if [ -f /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    DISTRO_ID="${ID:-generic}"
    DISTRO_NAME="${PRETTY_NAME:-$NAME}"
    DISTRO_VERSION="${VERSION_ID:-}"
elif [ -f /etc/redhat-release ]; then
    DISTRO_ID="rhel"
    DISTRO_NAME="$(cat /etc/redhat-release)"
elif [ -f /etc/debian_version ]; then
    DISTRO_ID="debian"
    DISTRO_NAME="Debian GNU/Linux $(cat /etc/debian_version)"
elif [ -f /etc/alpine-release ]; then
    DISTRO_ID="alpine"
    DISTRO_NAME="Alpine Linux $(cat /etc/alpine-release)"
fi

# Detect Package Manager
if command -v apt-get >/dev/null 2>&1; then
    PKG_MGR="apt"
    INSTALL_CMD="sudo apt-get update && sudo apt-get install -y"
elif command -v dnf >/dev/null 2>&1; then
    PKG_MGR="dnf"
    INSTALL_CMD="sudo dnf install -y"
elif command -v yum >/dev/null 2>&1; then
    PKG_MGR="yum"
    INSTALL_CMD="sudo yum install -y"
elif command -v pacman >/dev/null 2>&1; then
    PKG_MGR="pacman"
    INSTALL_CMD="sudo pacman -Sy --noconfirm"
elif command -v apk >/dev/null 2>&1; then
    PKG_MGR="apk"
    INSTALL_CMD="sudo apk add"
elif command -v zypper >/dev/null 2>&1; then
    PKG_MGR="zypper"
    INSTALL_CMD="sudo zypper install -y"
fi

# Detect Init System
INIT_SYSTEM="unknown"
if [ -d /run/systemd/system ] || pidof systemd >/dev/null 2>&1; then
    INIT_SYSTEM="systemd"
elif [ -f /sbin/openrc ] || [ -d /run/openrc ]; then
    INIT_SYSTEM="OpenRC"
elif [ -d /run/runit ] || pidof runsvdir >/dev/null 2>&1; then
    INIT_SYSTEM="runit"
elif [ -f /sbin/init ]; then
    INIT_SYSTEM="SysVinit / Init"
fi

# ------------------------------------------------------------------------------
# 2. Hardware Telemetry & Resource Profiling
# ------------------------------------------------------------------------------
log_info "Profiling host hardware resources (CPU, RAM, GPU/VRAM, Storage)..."

# CPU
CPU_ARCH="$(uname -m)"
CPU_CORES="$(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null || echo 1)"
CPU_MODEL="$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | sed 's/^[ \t]*//' || echo "Generic CPU")"
HAS_AVX2="No"
if grep -q -w "avx2" /proc/cpuinfo 2>/dev/null; then HAS_AVX2="Yes"; fi
HAS_AVX512="No"
if grep -q -E "avx512f|avx512" /proc/cpuinfo 2>/dev/null; then HAS_AVX512="Yes"; fi

# RAM (in MB and GB)
TOTAL_RAM_KB="$(grep -m1 MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 0)"
TOTAL_RAM_MB=$(( TOTAL_RAM_KB / 1024 ))
TOTAL_RAM_GB=$(awk "BEGIN {printf \"%.1f\", $TOTAL_RAM_MB / 1024}")

AVAIL_RAM_KB="$(grep -m1 MemAvailable /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 0)"
AVAIL_RAM_MB=$(( AVAIL_RAM_KB / 1024 ))
AVAIL_RAM_GB=$(awk "BEGIN {printf \"%.1f\", $AVAIL_RAM_MB / 1024}")

# GPU & VRAM
GPU_NAME="None / Integrated"
GPU_VRAM_MB=0
GPU_TYPE="CPU"

if command -v nvidia-smi >/dev/null 2>&1; then
    NV_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1 || echo "")"
    NV_VRAM="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -n1 || echo 0)"
    if [ -n "$NV_NAME" ]; then
        GPU_NAME="NVIDIA $NV_NAME"
        GPU_VRAM_MB=$NV_VRAM
        GPU_TYPE="NVIDIA CUDA"
    fi
elif command -v rocm-smi >/dev/null 2>&1; then
    GPU_NAME="AMD Radeon ROCm"
    GPU_TYPE="AMD ROCm"
elif command -v lspci >/dev/null 2>&1; then
    LSPCI_GPU="$(lspci 2>/dev/null | grep -i -E 'vga|3d|display' | head -n1 | cut -d: -f3 | sed 's/^[ \t]*//' || echo "")"
    if [ -n "$LSPCI_GPU" ]; then
        GPU_NAME="$LSPCI_GPU"
    fi
fi
GPU_VRAM_GB=$(awk "BEGIN {printf \"%.1f\", $GPU_VRAM_MB / 1024}")

# Storage
FREE_DISK_GB="$(df -BG . 2>/dev/null | awk 'NR==2 {print $4}' | tr -d 'G' || echo 10)"

# ------------------------------------------------------------------------------
# 3. Display Host Telemetry & Distro Confirmation
# ------------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${MAGENTA}┌───[ System & Hardware Diagnostics Profile ]─────────────────────────────────┐${RESET}"
printf "${MAGENTA}│${RESET}  ${BOLD}%-18s${RESET} : ${GREEN}%-54s${RESET}${MAGENTA}│${RESET}\n" "Linux Distribution" "$DISTRO_NAME ($DISTRO_ID)"
printf "${MAGENTA}│${RESET}  ${BOLD}%-18s${RESET} : ${WHITE}%-54s${RESET}${MAGENTA}│${RESET}\n" "Init & Pkg Manager" "$INIT_SYSTEM | $PKG_MGR"
printf "${MAGENTA}│${RESET}  ${BOLD}%-18s${RESET} : ${WHITE}%-54s${RESET}${MAGENTA}│${RESET}\n" "CPU Architecture" "$CPU_MODEL ($CPU_CORES cores, $CPU_ARCH, AVX2=$HAS_AVX2)"
printf "${MAGENTA}│${RESET}  ${BOLD}%-18s${RESET} : ${YELLOW}%-54s${RESET}${MAGENTA}│${RESET}\n" "System Memory" "${TOTAL_RAM_GB} GB Total (${AVAIL_RAM_GB} GB Available)"
printf "${MAGENTA}│${RESET}  ${BOLD}%-18s${RESET} : ${CYAN}%-54s${RESET}${MAGENTA}│${RESET}\n" "GPU & VRAM" "$GPU_NAME (VRAM: ${GPU_VRAM_GB} GB | $GPU_TYPE)"
printf "${MAGENTA}│${RESET}  ${BOLD}%-18s${RESET} : ${WHITE}%-54s${RESET}${MAGENTA}│${RESET}\n" "Storage Headroom" "${FREE_DISK_GB} GB Free"
echo -e "${BOLD}${MAGENTA}└─────────────────────────────────────────────────────────────────────────────┘${RESET}"
echo ""

# Confirm Distro Selection
echo -e "${BOLD}Target Distribution Profile:${RESET} [${GREEN}$DISTRO_ID${RESET}]"
echo -e "Press ${BOLD}[Enter]${RESET} to keep [${GREEN}$DISTRO_ID${RESET}], or select an override:"
echo -e "  ${DIM}1) debian/ubuntu  2) rhel/rocky/fedora  3) arch  4) alpine  5) opensuse${RESET}"
read -r -p "Select [Enter = $DISTRO_ID]: " DISTRO_CHOICE

case "$DISTRO_CHOICE" in
    1) TARGET_DISTRO="ubuntu" ;;
    2) TARGET_DISTRO="rhel" ;;
    3) TARGET_DISTRO="arch" ;;
    4) TARGET_DISTRO="alpine" ;;
    5) TARGET_DISTRO="opensuse" ;;
    *) TARGET_DISTRO="$DISTRO_ID" ;;
esac
log_success "Active distro profile set to: ${BOLD}$TARGET_DISTRO${RESET}"

# ------------------------------------------------------------------------------
# 4. Dependency Verification & Python Venv Setup
# ------------------------------------------------------------------------------
echo ""
log_info "Verifying required tools (python3, pip, venv, git, curl)..."

MISSING_PKGS=()
if ! command -v python3 >/dev/null 2>&1; then MISSING_PKGS+=("python3"); fi
if ! command -v git >/dev/null 2>&1; then MISSING_PKGS+=("git"); fi
if ! command -v curl >/dev/null 2>&1; then MISSING_PKGS+=("curl"); fi

# Check python version >= 3.9
if command -v python3 >/dev/null 2>&1; then
    PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    PY_MAJOR="$(echo "$PY_VER" | cut -d. -f1)"
    PY_MINOR="$(echo "$PY_VER" | cut -d. -f2)"
    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
        log_warn "Python version $PY_VER is older than 3.9. An updated Python 3 is required."
        MISSING_PKGS+=("python3")
    fi
fi

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    log_warn "Missing required packages: ${MISSING_PKGS[*]}"
    if [ -n "$PKG_MGR" ]; then
        echo -e "${YELLOW}Would you like to auto-install dependencies using '$PKG_MGR'? [Y/n]${RESET}"
        read -r -p "> " DO_INSTALL
        if [[ "$DO_INSTALL" =~ ^[Nn]$ ]]; then
            log_error "Cannot continue without required dependencies. Please install ${MISSING_PKGS[*]} and re-run."
            exit 1
        fi
        
        case "$PKG_MGR" in
            apt)
                sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv git curl
                ;;
            dnf|yum)
                sudo "$PKG_MGR" install -y python3 python3-pip git curl
                ;;
            pacman)
                sudo pacman -Sy --noconfirm python python-pip git curl
                ;;
            apk)
                sudo apk add python3 py3-pip git curl bash
                ;;
            zypper)
                sudo zypper install -y python3 python3-pip git curl
                ;;
        esac
    else
        log_error "No supported package manager found. Please install ${MISSING_PKGS[*]} manually."
        exit 1
    fi
fi

# Determine source code location
CURRENT_DIR="$(pwd)"
if [ -f "$CURRENT_DIR/ops_assistant/__init__.py" ] && [ -f "$CURRENT_DIR/requirements.txt" ]; then
    # Already inside repository directory
    INSTALL_DIR="$CURRENT_DIR"
    log_info "Detected existing repository at: $INSTALL_DIR"
else
    # Install / Clone to target directory
    INSTALL_DIR="$DEFAULT_INSTALL_DIR"
    if [ -d "$INSTALL_DIR/.git" ]; then
        log_info "Updating existing repository at $INSTALL_DIR..."
        git -C "$INSTALL_DIR" pull --ff-only || true
    else
        log_info "Cloning repository into $INSTALL_DIR..."
        mkdir -p "$(dirname "$INSTALL_DIR")"
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
fi

# Set up Python Virtual Environment (avoids PEP 668 externally managed environment locks)
VENV_DIR="$INSTALL_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    log_info "Creating isolated Python virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR" || python3 -m venv --without-pip "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip"

# Ensure pip exists in venv
if [ ! -f "$VENV_PIP" ]; then
    log_info "Bootstrapping pip in virtual environment..."
    curl -sS https://bootstrap.pypa.io/get-pip.py | "$VENV_PY"
fi

log_info "Installing Python dependencies..."
"$VENV_PIP" install --quiet --upgrade pip
"$VENV_PIP" install --quiet -e "$INSTALL_DIR" 2>/dev/null || "$VENV_PIP" install --quiet -r "$INSTALL_DIR/requirements.txt"
export PYTHONPATH="$INSTALL_DIR:${PYTHONPATH:-}"
log_success "Environment & core dependencies installed successfully."

# ------------------------------------------------------------------------------
# 5. Hardware-Aware Model Recommendation & Model Selection Overview
# ------------------------------------------------------------------------------

# Determine Auto-Recommendation based on hardware profiling
REC_KEY="deterministic"
REC_NAME="Deterministic Rule Engine (0 MB)"
REC_REASON="Minimal footprint, instant sub-50ms triage."

if [ "$GPU_VRAM_MB" -ge 6000 ] || [ "$TOTAL_RAM_MB" -ge 16000 ]; then
    REC_KEY="deepseek-r1-distill-qwen-7b"
    REC_NAME="DeepSeek-R1-Distill-Qwen-7B (4.58 GB)"
    REC_REASON="High-spec host ($TOTAL_RAM_GB GB RAM, $GPU_NAME). Unlocks Chain-of-Thought causal proofs."
elif [ "$GPU_VRAM_MB" -ge 4000 ] || [ "$TOTAL_RAM_MB" -ge 12000 ]; then
    REC_KEY="qwen2.5-coder-7b"
    REC_NAME="Qwen2.5-Coder-7B-Instruct (4.36 GB)"
    REC_REASON="High RAM ($TOTAL_RAM_GB GB). State-of-the-art Linux scripting & deep triage."
elif [ "$TOTAL_RAM_MB" -ge 8000 ]; then
    REC_KEY="llama-3.2-3b"
    REC_NAME="Llama-3.2-3B-Instruct (1.92 GB)"
    REC_REASON="Balanced system ($TOTAL_RAM_GB GB). Fast multi-step incident reasoning."
elif [ "$TOTAL_RAM_MB" -ge 4000 ]; then
    REC_KEY="qwen2.5-coder-1.5b"
    REC_NAME="Qwen2.5-Coder-1.5B-Instruct (986 MB)"
    REC_REASON="Standard server ($TOTAL_RAM_GB GB). High-accuracy bash syntax and triage."
elif [ "$TOTAL_RAM_MB" -ge 2000 ]; then
    REC_KEY="qwen2.5-coder-0.5b"
    REC_NAME="Qwen2.5-Coder-0.5B-Instruct (379 MB)"
    REC_REASON="Constrained node ($TOTAL_RAM_GB GB). Fast edge log pattern analysis."
elif [ "$TOTAL_RAM_MB" -ge 1000 ]; then
    REC_KEY="smollm2-360m"
    REC_NAME="SmolLM2-360M-Instruct (218 MB)"
    REC_REASON="Low-memory embedded node ($TOTAL_RAM_GB GB). Compact footprint."
fi

# Print Model Comparison and Capabilities Matrix Table
echo ""
echo -e "${BOLD}${CYAN}================================================================================================${RESET}"
echo -e "${BOLD}${WHITE}                   OPEN-SOURCE MODEL CATALOG & HARDWARE REQUIREMENTS OVERVIEW                    ${RESET}"
echo -e "${DIM}               Select an AI model tailored to your workload or use Deterministic-Only mode              ${RESET}"
echo -e "${BOLD}${CYAN}================================================================================================${RESET}"
echo ""
printf " ${BOLD}%-3s %-32s %-16s %-12s %-28s${RESET}\n" "No." "Model / Engine" "Disk Size" "Req. RAM" "Unlocked Features & Capabilities"
echo -e "${DIM}────────────────────────────────────────────────────────────────────────────────────────────────${RESET}"

# Row 1: Deterministic
D_REC=""
if [ "$REC_KEY" = "deterministic" ]; then D_REC=" ${GREEN}[RECOMMENDED]${RESET}"; fi
printf " ${BOLD}%-3s${RESET} %-32b %-16s %-12s %-28s\n" \
  "1." "${GREEN}Deterministic-Only Engine${RESET}$D_REC" "0 MB (None)" "<50 MB" "Sub-50ms, 16 Core Taxonomies, XAI, CoW Sandbox"

# Row 2: SmolLM2-360M
S_REC=""
if [ "$REC_KEY" = "smollm2-360m" ]; then S_REC=" ${GREEN}[RECOMMENDED]${RESET}"; fi
printf " ${BOLD}%-3s${RESET} %-32b %-16s %-12s %-28s\n" \
  "2." "SmolLM2-360M-Instruct$S_REC" "218 MB" "800 MB" "Ultra-lightweight edge triage & micro-VM queries"

# Row 3: Qwen 0.5B
Q0_REC=""
if [ "$REC_KEY" = "qwen2.5-coder-0.5b" ]; then Q0_REC=" ${GREEN}[RECOMMENDED]${RESET}"; fi
printf " ${BOLD}%-3s${RESET} %-32b %-16s %-12s %-28s\n" \
  "3." "Qwen2.5-Coder-0.5B$Q0_REC" "379 MB" "1.2 GB" "Fast command syntax parsing & log triage"

# Row 4: Qwen 1.5B
Q1_REC=""
if [ "$REC_KEY" = "qwen2.5-coder-1.5b" ]; then Q1_REC=" ${GREEN}[RECOMMENDED]${RESET}"; fi
printf " ${BOLD}%-3s${RESET} %-32b %-16s %-12s %-28s\n" \
  "4." "Qwen2.5-Coder-1.5B$Q1_REC" "986 MB" "2.5 GB" "Balanced speed/precision, awk/sed/grep synthesis"

# Row 5: Llama 3.2 3B
L3_REC=""
if [ "$REC_KEY" = "llama-3.2-3b" ]; then L3_REC=" ${GREEN}[RECOMMENDED]${RESET}"; fi
printf " ${BOLD}%-3s${RESET} %-32b %-16s %-12s %-28s\n" \
  "5." "Llama-3.2-3B-Instruct$L3_REC" "1.92 GB" "4.5 GB" "Multi-step incident reasoning & structured JSON"

# Row 6: Qwen 7B
Q7_REC=""
if [ "$REC_KEY" = "qwen2.5-coder-7b" ]; then Q7_REC=" ${GREEN}[RECOMMENDED]${RESET}"; fi
printf " ${BOLD}%-3s${RESET} %-32b %-16s %-12s %-28s\n" \
  "6." "Qwen2.5-Coder-7B-Instruct$Q7_REC" "4.36 GB" "8.5 GB" "Deep Linux internals, SELinux, bash scripting"

# Row 7: Mistral 7B
M7_REC=""
if [ "$REC_KEY" = "mistral-7b-instruct" ]; then M7_REC=" ${GREEN}[RECOMMENDED]${RESET}"; fi
printf " ${BOLD}%-3s${RESET} %-32b %-16s %-12s %-28s\n" \
  "7." "Mistral-7B-Instruct-v0.3$M7_REC" "4.07 GB" "8.0 GB" "Multi-daemon log correlation & interactive REPL"

# Row 8: DeepSeek R1 7B
D7_REC=""
if [ "$REC_KEY" = "deepseek-r1-distill-qwen-7b" ]; then D7_REC=" ${GREEN}[RECOMMENDED]${RESET}"; fi
printf " ${BOLD}%-3s${RESET} %-32b %-16s %-12s %-28s\n" \
  "8." "DeepSeek-R1-Distill-7B$D7_REC" "4.58 GB" "9.0 GB" "Chain-of-Thought (CoT) root cause formal proofs"

# Row 9: Local Ollama
printf " ${BOLD}%-3s${RESET} %-32b %-16s %-12s %-28s\n" \
  "9." "${BLUE}Local Ollama Instance${RESET}" "Self-hosted" "Custom" "Connects to existing http://localhost:11434"

echo -e "${DIM}────────────────────────────────────────────────────────────────────────────────────────────────${RESET}"
echo -e " ${BOLD}Host Detection:${RESET} ${YELLOW}${TOTAL_RAM_GB} GB RAM${RESET} | ${CYAN}${GPU_NAME}${RESET} | ${WHITE}${FREE_DISK_GB} GB Disk Free${RESET}"
echo -e " ${BOLD}System Recommendation:${RESET} ${GREEN}${REC_NAME}${RESET} (${REC_REASON})"
echo ""

echo -e "${BOLD}Select your preferred AI Engine / Model [1-9]:${RESET}"
echo -e "  ${DIM}• Press [Enter] to accept the recommended model (${GREEN}${REC_KEY}${DIM})${RESET}"
read -r -p "Enter choice [1-9] (default = recommended): " MODEL_CHOICE

CHOSEN_MODEL=""
PROVIDER="gguf"

if [ -z "$MODEL_CHOICE" ]; then
    CHOSEN_MODEL="$REC_KEY"
else
    case "$MODEL_CHOICE" in
        1) CHOSEN_MODEL="deterministic"; PROVIDER="deterministic" ;;
        2) CHOSEN_MODEL="smollm2-360m" ;;
        3) CHOSEN_MODEL="qwen2.5-coder-0.5b" ;;
        4) CHOSEN_MODEL="qwen2.5-coder-1.5b" ;;
        5) CHOSEN_MODEL="llama-3.2-3b" ;;
        6) CHOSEN_MODEL="qwen2.5-coder-7b" ;;
        7) CHOSEN_MODEL="mistral-7b-instruct" ;;
        8) CHOSEN_MODEL="deepseek-r1-distill-qwen-7b" ;;
        9) CHOSEN_MODEL="ollama"; PROVIDER="ollama" ;;
        *) log_warn "Invalid selection. Defaulting to recommended model: $REC_KEY"; CHOSEN_MODEL="$REC_KEY" ;;
    esac
fi

if [ "$CHOSEN_MODEL" = "deterministic" ]; then
    PROVIDER="deterministic"
fi

# ------------------------------------------------------------------------------
# 6. Model Download & Configuration
# ------------------------------------------------------------------------------
echo ""
if [ "$PROVIDER" = "deterministic" ]; then
    log_success "Configuring Deterministic-Only Engine (0 MB download, sub-50ms latency, zero RAM overhead)."
    "$VENV_PY" -c "
from ops_assistant.config import set_setup_completed
set_setup_completed(provider='deterministic')
print('✓ Deterministic engine configured in config.json')
"
elif [ "$PROVIDER" = "ollama" ]; then
    log_info "Configuring Local Ollama provider..."
    OLLAMA_MODEL="llama3:8b"
    echo -e "Enter Ollama model name (default: ${GREEN}$OLLAMA_MODEL${RESET}):"
    read -r -p "> " USER_OLLAMA_MODEL
    if [ -n "$USER_OLLAMA_MODEL" ]; then
        OLLAMA_MODEL="$USER_OLLAMA_MODEL"
    fi
    "$VENV_PY" -c "
from ops_assistant.config import set_setup_completed, get_config, ConfigManager
cfg = get_config()
cfg['provider'] = 'ollama'
cfg['ollama_model'] = '$OLLAMA_MODEL'
cfg['setup_completed'] = True
ConfigManager().save(cfg)
print('✓ Configured Ollama with model: $OLLAMA_MODEL')
"
else
    # GGUF Model Download & Setup
    log_info "Selected model: ${BOLD}$CHOSEN_MODEL${RESET}"
    log_info "Checking / downloading model weights..."
    
    # Run the Python downloader inside the venv
    "$VENV_PY" -c "
import sys
from ops_assistant.model_manager.downloader import ModelDownloader
from ops_assistant.config import set_setup_completed
from ops_assistant.hardware.advisor import MODEL_CATALOG, HardwareAdvisor

mkey = '$CHOSEN_MODEL'
dl = ModelDownloader()
avail = dl.list_available_models()

if mkey in avail and avail[mkey]['is_downloaded']:
    print(f'✓ Model {mkey} is already downloaded.')
    mpath = avail[mkey]['local_path']
else:
    print(f'[*] Downloading {mkey} from Hugging Face...')
    last_p = -1
    def progress(cur, total, pct):
        nonlocal last_p
        ipct = int(pct)
        if ipct % 10 == 0 and ipct != last_p:
            last_p = ipct
            print(f'    Downloading: {ipct}% ({cur // (1024*1024)}MB / {total // (1024*1024)}MB)')
    
    mpath = str(dl.download_model(mkey, progress_callback=progress))
    print(f'✓ Successfully downloaded to {mpath}')

adv = HardwareAdvisor()
prof = adv.profiler.profile()
caps = adv.generate_capability_matrix(prof)

set_setup_completed(
    provider='gguf',
    model_key=mkey,
    model_path=mpath,
    hardware_tier=prof.compute_tier,
    threads=caps.recommended_threads,
    ctx_size=caps.recommended_ctx_size,
    gpu_layers=caps.recommended_gpu_layers
)
print('✓ Setup configuration persisted.')
"
fi

# ------------------------------------------------------------------------------
# 7. Create Global CLI Launcher Wrapper
# ------------------------------------------------------------------------------
log_info "Creating global CLI executable..."

mkdir -p "$BIN_DIR"
WRAPPER_FILE="$BIN_DIR/ops-assistant"

cat << WRAPPER_EOF > "$WRAPPER_FILE"
#!/usr/bin/env bash
# Wrapper for AI-Powered Linux Operations Assistant
export PYTHONPATH="$INSTALL_DIR:\${PYTHONPATH:-}"
exec "$VENV_PY" -m ops_assistant.cli "\$@"
WRAPPER_EOF

chmod +x "$WRAPPER_FILE"
log_success "Executable wrapper created at: $WRAPPER_FILE"

# If root / sudo writable, create symlink in /usr/local/bin
if [ -w /usr/local/bin ]; then
    ln -sf "$WRAPPER_FILE" /usr/local/bin/ops-assistant 2>/dev/null || true
    log_success "Global symlink created in /usr/local/bin/ops-assistant"
elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    sudo ln -sf "$WRAPPER_FILE" /usr/local/bin/ops-assistant 2>/dev/null || true
    log_success "Global symlink created in /usr/local/bin/ops-assistant (via sudo)"
fi

# Verify if ~/.local/bin is in PATH
PATH_EXPORT_NEEDED=false
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) PATH_EXPORT_NEEDED=true ;;
esac

if [ "$PATH_EXPORT_NEEDED" = true ]; then
    log_warn "$BIN_DIR is not currently in your PATH."
    # Add to shell profile
    SHELL_PROFILE=""
    if [ -n "$BASH_VERSION" ] || [ -f "$HOME/.bashrc" ]; then
        SHELL_PROFILE="$HOME/.bashrc"
    elif [ -n "$ZSH_VERSION" ] || [ -f "$HOME/.zshrc" ]; then
        SHELL_PROFILE="$HOME/.zshrc"
    elif [ -f "$HOME/.profile" ]; then
        SHELL_PROFILE="$HOME/.profile"
    fi
    
    if [ -n "$SHELL_PROFILE" ]; then
        if ! grep -q "$BIN_DIR" "$SHELL_PROFILE" 2>/dev/null; then
            echo "" >> "$SHELL_PROFILE"
            echo '# Added by ops-assistant installer' >> "$SHELL_PROFILE"
            echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$SHELL_PROFILE"
            log_info "Added $BIN_DIR to $SHELL_PROFILE. (Run: source $SHELL_PROFILE)"
        fi
    fi
fi

# ------------------------------------------------------------------------------
# 8. Post-Installation Verification & Health Check
# ------------------------------------------------------------------------------
echo ""
echo -e "${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${GREEN}                INSTALLATION & SETUP COMPLETED SUCCESSFULLY!                  ${RESET}"
echo -e "${CYAN}==============================================================================${RESET}"
echo ""

# Quick health snapshot test
log_info "Running quick post-install health verification..."
"$VENV_PY" -m ops_assistant.cli --inspect-health || true

echo ""
echo -e "${BOLD}${WHITE}Quick Command Reference:${RESET}"
echo -e "  ${GREEN}ops-assistant${RESET} ${DIM}\"Why is port 80 failing to bind?\"${RESET}  # Diagnostic query"
echo -e "  ${GREEN}ops-assistant -i${RESET}                                   # Interactive Sysadmin REPL"
echo -e "  ${GREEN}ops-assistant --inspect-health${RESET}                     # Real-time PSI & Health Dashboard"
echo -e "  ${GREEN}ops-assistant --diagnose-failed${RESET}                    # Scan & diagnose crashed services"
echo -e "  ${GREEN}ops-assistant --gui${RESET}                                # Launch Web Dashboard GUI"
echo -e "  ${GREEN}ops-assistant --setup${RESET}                              # Re-run hardware & model wizard"
echo ""
echo -e "${BOLD}Enjoy autonomous, explainable Linux operations!${RESET}"
echo ""
