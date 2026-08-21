#compdef ops-assistant
# Zsh completion script for AI-Powered Linux Operations Assistant (ops-assistant)

_ops_assistant() {
    local -a models distros providers

    models=(
        'smollm2-360m:SmolLM2-360M-Instruct (218 MB)'
        'qwen2.5-coder-0.5b:Qwen2.5-Coder-0.5B-Instruct (379 MB)'
        'qwen2.5-coder-1.5b:Qwen2.5-Coder-1.5B-Instruct (986 MB)'
        'llama-3.2-3b:Llama-3.2-3B-Instruct (1.92 GB)'
        'qwen2.5-coder-7b:Qwen2.5-Coder-7B-Instruct (4.36 GB)'
        'mistral-7b-instruct:Mistral-7B-Instruct-v0.3 (4.07 GB)'
        'deepseek-r1-distill-qwen-7b:DeepSeek-R1-Distill-Qwen-7B (4.58 GB)'
    )

    distros=(
        'ubuntu:Ubuntu / Debian Linux'
        'debian:Debian GNU/Linux'
        'rhel:RHEL / Rocky / CentOS / Fedora'
        'arch:Arch Linux'
        'alpine:Alpine Linux (OpenRC / musl)'
        'opensuse:openSUSE / SLES'
        'generic:Generic Linux Distribution'
    )

    providers=(
        'auto:Automatic inference backend selection'
        'deterministic:Rule-based sub-50ms deterministic engine'
        'gguf:In-process edge GGUF LLM inference'
        'ollama:Local Ollama server connection'
    )

    _arguments -s \
        '(-d --distro)'{-d,--distro}'[Target Linux distribution family]:distro:->distros' \
        '(-p --provider)'{-p,--provider}'[Reasoning engine backend]:provider:->providers' \
        '--model-path[Path to custom GGUF model file]:file:_files' \
        '--list-models[List registered and downloaded edge GGUF models]' \
        '--download-model[Download registered GGUF model]:model:->models' \
        '--inspect-health[Display system health snapshot & PSI metrics]' \
        '--diagnose-failed[Scan and diagnose failed systemd services]' \
        '--profile-hardware[Profile CPU, RAM, GPU, and Storage capabilities]' \
        '--test-hardware[Run automated hardware benchmarking tests]' \
        '--auto-tune[Profile hardware, select optimal model, and tune system]' \
        '--setup[Launch interactive Setup & Model Configuration Wizard]' \
        '--proactive-audit[Run proactive autonomous health audit]' \
        '--docker-status[List Docker containers and port conflicts]' \
        '--security-audit[Run consolidated security and hardening audit]' \
        '(-s --safety-check)'{-s,--safety-check}'[AST safety analysis on a command]:command:_values' \
        '--demo[Run interactive demo across representative scenarios]' \
        '--benchmark[Run empirical performance benchmark]' \
        '(-i --interactive)'{-i,--interactive}'[Enable interactive command execution prompt]' \
        '--export-json[Export diagnostic report to JSON file]:file:_files -g "*.json"' \
        '--export-md[Export diagnostic report to Markdown file]:file:_files -g "*.md"' \
        '--gui[Launch interactive Web GUI Dashboard]' \
        '--port[Port for Web GUI Dashboard]:port:(8888 8080 3000)' \
        '--no-browser[Do not open web browser automatically]' \
        '(-h --help)'{-h,--help}'[Show help and exit]' \
        '*:query: '

    case "$state" in
        models)
            _describe -t models 'Available Models' models
            ;;
        distros)
            _describe -t distros 'Linux Distributions' distros
            ;;
        providers)
            _describe -t providers 'Inference Providers' providers
            ;;
    esac
}

_ops_assistant "$@"
