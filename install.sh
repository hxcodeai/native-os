#!/bin/bash

# Native OS - Installation Script
# This script will install Native OS on a Debian-based system
# Copyright (c) 2025 hxcode ai
# Released under MIT License

# Log file setup
LOG_DIR="$HOME/.nativeos/logs"
LOG_FILE="$LOG_DIR/install.log"

# Function to log messages
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

# Function to check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log "Error: This script must be run as root (with sudo)"
        exit 1
    fi
}

# Function to create necessary directories
create_directories() {
    log "Creating necessary directories..."
    mkdir -p "$LOG_DIR"
    touch "$LOG_FILE"
    log "Log file created at $LOG_FILE"
}

# Function to install Layer 1 (Core)
install_layer1() {
    log "Installing Layer 1 (Core)..."
    
    # Install core packages
    log "Installing core dependencies..."
    apt-get update
    apt-get install -y zsh python3 python3-pip docker.io nodejs npm curl git sqlite3
    apt-get install -y bspwm sxhkd polybar rofi picom
    
    # Copy config files
    log "Copying configuration files..."
    mkdir -p "$HOME/.config/bspwm"
    mkdir -p "$HOME/.config/sxhkd"
    mkdir -p "$HOME/.config/polybar"
    
    cp .config/bspwm/bspwmrc "$HOME/.config/bspwm/"
    cp .config/sxhkd/sxhkdrc "$HOME/.config/sxhkd/"
    cp .config/polybar/config "$HOME/.config/polybar/"
    
    chmod +x "$HOME/.config/bspwm/bspwmrc"
    chmod +x "$HOME/.config/sxhkd/sxhkdrc"
    
    # Setup CLI tool
    log "Setting up CLI tool..."
    chmod +x cli/devctl
    ln -sf "$(pwd)/cli/devctl" /usr/local/bin/devctl
    
    # Install Ollama
    log "Installing Ollama..."
    curl -fsSL https://ollama.ai/install.sh | sh
    
    log "Layer 1 installation complete!"
}

# Function to install Layer 2 (Automation)
install_layer2() {
    log "Installing Layer 2 (Automation)..."
    
    # Install system dependencies for infrastructure tools
    log "Installing infrastructure dependencies..."
    apt-get update
    apt-get install -y terraform ansible docker.io kubectl awscli

    # Install Python packages
    log "Installing Python packages..."
    pip3 install openai langchain chromadb requests rich langchain_text_splitters langchain_community langchain_openai deepseek-ai anthropic
    
    # Setup all agent scripts
    log "Setting up agent scripts..."
    chmod +x agents/code-agent.py
    chmod +x agents/infra-agent.py
    chmod +x agents/doc-agent.py
    chmod +x agents/terraform-agent.py
    chmod +x agents/ansible-agent.py
    chmod +x agents/docker-agent.py
    chmod +x agents/k8s-agent.py
    
    # Create infrastructure directories
    log "Creating infrastructure directories..."
    mkdir -p infra/terraform
    mkdir -p infra/playbooks
    mkdir -p infra/docker
    mkdir -p infra/k8s
    
    log "Testing code-agent..."
    python3 agents/code-agent.py --test
    
    log "Layer 2 installation complete!"
}

# Function to install Layer 3 (Self-Evolving)
install_layer3() {
    log "Installing Layer 3 (Self-Evolving)..."
    
    # Setup evolver and memory
    log "Setting up self-evolution system..."
    chmod +x evolver/self_optimize.py
    chmod +x memory/init_memory.py
    
    # Create alias for self-optimization
    log "Creating nativectl alias..."
    echo "alias nativectl='devctl'" >> "$HOME/.bashrc"
    echo "alias nativectl='devctl'" >> "$HOME/.zshrc"
    
    log "Initializing memory system..."
    python3 memory/init_memory.py
    
    log "Layer 3 installation complete!"
}

# Main installation function
run_installation() {
    echo "===== Native OS Installation ====="
    echo "Select installation layer:"
    echo "1) Layer 1 - Core (Window manager, CLI, basic utilities)"
    echo "2) Layer 2 - Automation (AI agents, Infrastructure tools, Python packages)"
    echo "3) Layer 3 - Self-Evolving (Evolver, Memory system)"
    echo "4) All Layers (Complete installation)"
    echo "5) Quit"
    
    read -p "Enter your choice [1-5]: " choice
    
    case $choice in
        1)
            install_layer1
            ;;
        2)
            install_layer2
            ;;
        3)
            install_layer3
            ;;
        4)
            install_layer1
            install_layer2
            install_layer3
            ;;
        5)
            log "Installation cancelled by user"
            exit 0
            ;;
        *)
            log "Invalid option selected"
            run_installation
            ;;
    esac
    
    log "Installation completed successfully!"
    echo "Native OS has been installed. Please restart your system to apply all changes."
}

# Main execution
check_root
create_directories
run_installation
