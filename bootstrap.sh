#!/bin/bash

# Native OS - Bootstrap Script for Replit
# This script sets up Native OS in a Replit environment
# Copyright (c) 2025 hxcode ai
# Released under MIT License

# Log file setup
LOG_DIR="$HOME/.nativeos/logs"
LOG_FILE="$LOG_DIR/bootstrap.log"

# Function to log messages
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

# Function to create necessary directories
create_directories() {
    log "Creating necessary directories..."
    mkdir -p "$LOG_DIR"
    touch "$LOG_FILE"
    log "Log file created at $LOG_FILE"
}

# Function to check and clone repository if needed
check_repo() {
    log "Checking for existing repository..."
    if [ ! -d "native-os" ] && [ ! -f "install.sh" ]; then
        log "Repository not found, cloning from GitHub..."
        git clone https://github.com/hxcodeai/native-os.git
        cd native-os
    else
        log "Repository already exists"
    fi
}

# Function to install dependencies
install_dependencies() {
    log "Installing dependencies for Replit environment..."
    
    # Update package lists
    log "Updating package lists..."
    # Using pip to install Python dependencies since apt-get might not work in Replit
    python3 -m pip install --upgrade pip
    python3 -m pip install chromadb langchain-community langchain-openai openai requests rich
    
    # Install optional dependencies if possible
    if command -v npm &> /dev/null; then
        npm install -g typescript @tauri-apps/cli
    fi
    
    # Create necessary config directories
    mkdir -p "$HOME/.config/bspwm"
    mkdir -p "$HOME/.config/sxhkd"
    mkdir -p "$HOME/.config/polybar"
    
    # Copy config files if they exist
    if [ -d ".config" ]; then
        cp -r ".config/"* "$HOME/.config/"
        chmod +x "$HOME/.config/polybar/launch.sh" 2>/dev/null || true
        chmod +x "$HOME/.config/bspwm/bspwmrc" 2>/dev/null || true
    fi
    
    log "Dependencies installed successfully"
}

# Function to set up CLI tool
setup_cli() {
    log "Setting up CLI tool..."
    
    # Make devctl executable
    chmod +x cli/devctl
    
    # Symlink to /usr/local/bin for global access
    ln -sf "$(pwd)/cli/devctl" /usr/local/bin/devctl
    
    log "CLI tool setup complete"
}

# Function to print onboarding message
print_welcome() {
    echo "
    =============================================
    🚀 Native OS is ready to use in Replit! 🚀
    =============================================
    
    Example commands:
    
    1. Generate code:
       devctl \"create a simple flask app\"
    
    2. Deploy to cloud:
       devctl \"deploy to aws\"
    
    3. Generate documentation:
       devctl \"create readme for my project\"
    
    4. Self-optimize the system:
       devctl self-optimize
    
    Enjoy using Native OS!
    "
    
    log "Welcome message displayed"
}

# Main execution
create_directories
check_repo
install_dependencies
setup_cli
print_welcome

log "Bootstrap process completed successfully"
