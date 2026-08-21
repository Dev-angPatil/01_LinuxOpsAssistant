# Bash completion script for AI-Powered Linux Operations Assistant (ops-assistant)

_ops_assistant_completions() {
    local cur prev opts models distros providers
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    opts="--distro -d --provider -p --model-path --list-models --download-model \
          --inspect-health --diagnose-failed --profile-hardware --test-hardware \
          --auto-tune --setup --proactive-audit --docker-status --security-audit \
          --safety-check -s --demo --benchmark --interactive -i --export-json \
          --export-md --gui --port --no-browser --help -h"

    models="smollm2-360m qwen2.5-coder-0.5b qwen2.5-coder-1.5b llama-3.2-3b qwen2.5-coder-7b mistral-7b-instruct deepseek-r1-distill-qwen-7b"
    distros="ubuntu debian rhel rocky fedora arch alpine opensuse suse generic"
    providers="auto deterministic gguf ollama"

    case "$prev" in
        --distro|-d)
            COMPREPLY=( $(compgen -W "${distros}" -- "$cur") )
            return 0
            ;;
        --provider|-p)
            COMPREPLY=( $(compgen -W "${providers}" -- "$cur") )
            return 0
            ;;
        --download-model)
            COMPREPLY=( $(compgen -W "${models}" -- "$cur") )
            return 0
            ;;
        --model-path|--export-json|--export-md)
            COMPREPLY=( $(compgen -f -- "$cur") )
            return 0
            ;;
        --port)
            COMPREPLY=( $(compgen -W "8888 8080 3000 5000" -- "$cur") )
            return 0
            ;;
        --safety-check|-s)
            return 0
            ;;
    esac

    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "${opts}" -- "$cur") )
        return 0
    fi
}

complete -F _ops_assistant_completions ops-assistant
