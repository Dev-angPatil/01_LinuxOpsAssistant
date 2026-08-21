#!/usr/bin/env bash
# ==============================================================================
# AI-Powered Linux Operations Assistant (ops-assistant)
# Uninstallation & Resource Cleanup Utility
#
# Usage:
#   ./uninstall.sh [--purge] [--yes|-y]
# ==============================================================================

set -eo pipefail

# Detect color support
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    BOLD="\033[1m"
    DIM="\033[2m"
    RED="\033[0;31m"
    GREEN="\033[0;32m"
    YELLOW="\033[0;33m"
    CYAN="\033[0;36m"
    WHITE="\033[1;37m"
    RESET="\033[0m"
else
    BOLD=""
    DIM=""
    RED=""
    GREEN=""
    YELLOW=""
    CYAN=""
    WHITE=""
    RESET=""
fi

log_info() { echo -e "${CYAN}[*]${RESET} $1"; }
log_success() { echo -e "${GREEN}[✓]${RESET} $1"; }
log_warn() { echo -e "${YELLOW}[!]${RESET} $1"; }
log_error() { echo -e "${RED}[✗]${RESET} $1"; }

AUTO_YES=false
PURGE=false

for arg in "$@"; do
    case "$arg" in
        -y|--yes) AUTO_YES=true ;;
        --purge) PURGE=true ;;
        -h|--help)
            echo "Usage: ./uninstall.sh [OPTIONS]"
            echo "Options:"
            echo "  -y, --yes    Skip confirmation prompts"
            echo "  --purge      Also remove ~/.ops_assistant (config, downloaded models, history)"
            echo "  -h, --help   Show this help message"
            exit 0
            ;;
        *)
            log_warn "Unknown option: $arg"
            ;;
    esac
done

echo -e "${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${WHITE}       AI-POWERED LINUX OPERATIONS ASSISTANT (${RED}UNINSTALLER${WHITE})${RESET}"
echo -e "${CYAN}==============================================================================${RESET}"
echo ""

if [ "$AUTO_YES" = false ]; then
    echo -e "${YELLOW}Are you sure you want to uninstall ops-assistant? [y/N]${RESET}"
    read -r -p "> " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        log_info "Uninstallation cancelled."
        exit 0
    fi
fi

# Detect SUDO
SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
fi

# 1. Stop and remove systemd user unit if running
if command -v systemctl >/dev/null 2>&1; then
    if systemctl --user is-active ops-assistant-gui.service >/dev/null 2>&1; then
        log_info "Stopping ops-assistant-gui systemd service..."
        systemctl --user stop ops-assistant-gui.service 2>/dev/null || true
        systemctl --user disable ops-assistant-gui.service 2>/dev/null || true
    fi
fi
SERVICE_FILE="$HOME/.config/systemd/user/ops-assistant-gui.service"
if [ -f "$SERVICE_FILE" ]; then
    rm -f "$SERVICE_FILE"
    if command -v systemctl >/dev/null 2>&1; then
        systemctl --user daemon-reload 2>/dev/null || true
    fi
    log_success "Removed systemd service: $SERVICE_FILE"
fi

# 2. Remove Desktop Entry
DESKTOP_FILE="$HOME/.local/share/applications/ops-assistant-gui.desktop"
if [ -f "$DESKTOP_FILE" ]; then
    rm -f "$DESKTOP_FILE"
    log_success "Removed desktop launcher: $DESKTOP_FILE"
fi

# 3. Remove Shell Completions
BASH_COMP="$HOME/.local/share/bash-completion/completions/ops-assistant"
if [ -f "$BASH_COMP" ]; then
    rm -f "$BASH_COMP"
    log_success "Removed Bash autocompletion: $BASH_COMP"
fi

ZSH_COMP="$HOME/.zsh/completions/_ops_assistant"
if [ -f "$ZSH_COMP" ]; then
    rm -f "$ZSH_COMP"
    log_success "Removed Zsh autocompletion: $ZSH_COMP"
fi

if [ -f "/etc/bash_completion.d/ops-assistant" ]; then
    $SUDO rm -f "/etc/bash_completion.d/ops-assistant" 2>/dev/null || true
fi

# 4. Remove Global Symlink
if [ -L "/usr/local/bin/ops-assistant" ]; then
    if [ -w "/usr/local/bin" ]; then
        rm -f "/usr/local/bin/ops-assistant"
        log_success "Removed global symlink: /usr/local/bin/ops-assistant"
    elif [ -n "$SUDO" ]; then
        $SUDO rm -f "/usr/local/bin/ops-assistant" 2>/dev/null || true
        log_success "Removed global symlink: /usr/local/bin/ops-assistant (via sudo)"
    fi
fi

# 5. Remove CLI Wrapper
WRAPPER="$HOME/.local/bin/ops-assistant"
if [ -f "$WRAPPER" ]; then
    rm -f "$WRAPPER"
    log_success "Removed executable wrapper: $WRAPPER"
fi

# 6. Remove Installed Package & Venv in ~/.local/share/ops-assistant
DEFAULT_INSTALL_DIR="$HOME/.local/share/ops-assistant"
if [ -d "$DEFAULT_INSTALL_DIR" ]; then
    log_info "Removing install directory: $DEFAULT_INSTALL_DIR..."
    rm -rf "$DEFAULT_INSTALL_DIR"
    log_success "Removed $DEFAULT_INSTALL_DIR"
fi

# 7. Clean up ~/.ops_assistant config & cache if purge requested
CONFIG_DIR="$HOME/.ops_assistant"
if [ "$PURGE" = true ]; then
    if [ -d "$CONFIG_DIR" ]; then
        rm -rf "$CONFIG_DIR"
        log_success "Purged configuration, models, and data directory: $CONFIG_DIR"
    fi
else
    if [ -d "$CONFIG_DIR" ]; then
        log_info "Preserved data and configuration directory at $CONFIG_DIR."
        echo -e "  ${DIM}(To remove completely, re-run with: ./uninstall.sh --purge)${RESET}"
    fi
fi

echo ""
echo -e "${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${GREEN}               ops-assistant uninstalled successfully!                        ${RESET}"
echo -e "${CYAN}==============================================================================${RESET}"
echo ""
