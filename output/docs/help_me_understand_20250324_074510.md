# Native OS Documentation

## Overview

Native OS is an AI-native Debian-based operating system that integrates AI automation, intelligent CLI tools, and self-evolving capabilities to enhance developer productivity. This documentation provides an overview of the key features and components of Native OS.

### Project Files

- **Layer 1: Core**
  - **File**: `agents/infra-agent.py`
    - **Description**: Implements the infrastructure agent functionality.
  - **File**: `agents/doc-agent.py`
    - **Description**: Implements the documentation agent functionality.
  - **File**: `agents/code-agent.py`
    - **Description**: Implements the code generation agent functionality.
  - **File**: `evolver/self_optimize.py`
    - **Description**: Implements the self-optimization functionality.
  - **File**: `memory/init_memory.py`
    - **Description**: Initializes the memory system.
  - **File**: `memory/memory_query.py`
    - **Description**: Implements memory querying functionality.

- **User Interface**
  - **File**: `ui/tauri-app/src/App.jsx`
    - **Description**: Main application UI component.
  - **File**: `ui/tauri-app/main.ts`
    - **Description**: Entry point for the Tauri application.

- **Setup and Installation**
  - **File**: `install.sh`
    - **Description**: Installation script for Debian-based systems.
  - **File**: `bootstrap.sh`
    - **Description**: Bootstrap script for setting up Native OS in a Replit environment.

- **Additional Configurations**
  - **File**: `pyproject.toml`
    - **Description**: Python project metadata and dependencies.

### Features

#### Layer 1: Core

- **Window Management**: Utilizes `bspwm`, `sxhkd`, and `polybar` for an efficient desktop environment.
- **AI-Powered CLI**: `devctl` provides a natural language command-line interface.
- **Ollama Integration**: Supports local LLM for offline AI features.
- **Essential Utilities**: Includes `zsh`, `git`, `docker`, `nodejs`, `python`, and more.

#### Layer 2: Automation

- **Code Agent**: Generates code from natural language descriptions.
- **Infrastructure Agent**: Manages cloud infrastructure deployment.
- **Documentation Agent**: Automatically creates project documentation.

#### Layer 3: Self-Evolving

- **Self-Optimization**: Components that improve over time.
- **Memory System**: Long-term context storage for project understanding.
- **AI-Powered Evolution**: Analyzes code and suggests improvements.

## Installation

### Quick Install (Debian/Ubuntu)

1. Clone the repository:
   ```bash
   git clone https://github.com/hxcodeai/native-os.git
   cd native-os
   ```

2. Run the installation script:
   ```bash
   sudo ./install.sh
   ```

## Usage

- **CLI Tool Setup**: Make `devctl` executable and symlink to `/usr/local/bin` for global access.
- **System Initialization**: Execute the bootstrap script for setting up Native OS in a Replit environment.
- **Explore Features**: Utilize the provided agents and tools for code generation, infrastructure management, and documentation generation.

---

This documentation provides an overview of the Native OS features and components, including installation instructions and key functionalities across different layers.