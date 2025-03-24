# Native OS

Native OS is an AI-native Debian operating system with integrated AI automation, intelligent CLI tools, and self-evolving capabilities. It's designed to enhance developer productivity and provide a seamless interface between natural language intent and system operations.

**© 2025 hxcode ai. Released under MIT License.**

## Features

### Layer 1: Core
- **Window Management**: bspwm, sxhkd, polybar for a clean, efficient desktop environment
- **AI-Powered CLI**: Natural language command-line interface (`devctl`)
- **Ollama Integration**: Local LLM support for offline AI features
- **Essential Utilities**: zsh, git, docker, nodejs, python, and more

### Layer 2: Automation
- **Code Agent**: Automatically generate code from natural language descriptions
- **Infrastructure Agent**: Deploy and manage cloud infrastructure with simple prompts
- **Documentation Agent**: Create documentation for your projects automatically

### Layer 3: Self-Evolving
- **Self-Optimization**: System components that improve over time
- **Memory System**: Long-term context storage for project understanding
- **AI-Powered Evolution**: Code analysis and automated improvements

## Installation

### Quick Install (Debian/Ubuntu)

```bash
git clone https://github.com/hxcodeai/native-os.git
cd native-os && sudo ./install.sh
```

### Repository Maintenance

To clean platform-specific references from the Git history:

```bash
# Clone the repository
git clone https://github.com/hxcodeai/native-os.git
cd native-os

# Run the cleaning script
./clean_history.sh

# Force push the cleaned history
git push -f origin main
```
