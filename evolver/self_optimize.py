#!/usr/bin/env python3

import os
import sys
import json
import time
import logging
import argparse
import difflib
import shutil
import requests
from datetime import datetime
from pathlib import Path

# Setup logging
LOG_DIR = os.path.expanduser("~/.nativeos/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "evolver.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class Evolver:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.use_local_model = os.getenv("NATIVE_OS_LOCAL_MODEL", "0") == "1" or self.api_key is None
        
        # Project root directory
        self.project_root = self._find_project_root()
        
        # Backup directory
        self.backup_dir = os.path.join(self.project_root, "evolver", "backups")
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def _find_project_root(self):
        """Find the root directory of the Native OS project."""
        # Start from the current directory and traverse upward
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # If we're in the evolver directory, go up one level
        if os.path.basename(current_dir) == "evolver":
            return os.path.dirname(current_dir)
        
        return current_dir
    
    def _get_ollama_response(self, prompt):
        """Get response from local Ollama model."""
        try:
            # Check if Ollama is running
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "codellama",
                    "prompt": prompt,
                    "stream": False
                }
            )
            
            if response.status_code == 200:
                return response.json().get("response", "")
            else:
                logging.error(f"Ollama error: {response.text}")
                return f"Error: Failed to get response from local model. Status code: {response.status_code}"
        except Exception as e:
            logging.exception("Error connecting to Ollama")
            return f"Error: Could not connect to Ollama. Is it running? Error: {str(e)}"
    
    def _get_openai_response(self, prompt):
        """Get response from OpenAI API."""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "gpt-4",
                "messages": [
                    {"role": "system", "content": """You are an expert code evolution and optimization specialist created by hxcode ai. Analyze existing code to identify improvements, optimizations, and enhancements while maintaining core functionality.

Your capabilities:
1. Identify performance bottlenecks and optimize for speed and efficiency
2. Improve code readability and maintainability without compromising functionality
3. Enhance error handling and edge case management
4. Apply best practices and design patterns appropriate for the language
5. Identify and fix potential security vulnerabilities
6. Suggest architectural improvements for better scalability

Optimization approach:
- Start with high-impact, low-risk improvements
- Maintain backward compatibility where possible
- Prioritize security fixes over performance gains
- Look for opportunities to reduce complexity and improve clarity
- Suggest appropriate test coverage for critical sections
- Consider memory usage and resource efficiency
- Provide clear explanations for why each change is beneficial

Areas of expertise:
- Python performance optimization and best practices
- JavaScript/TypeScript modernization and patterns
- Refactoring techniques across multiple languages
- AI-specific optimization for ML/NLP code
- API design and interface improvements
- Multi-threading and concurrency optimizations
- Memory management and resource efficiency

Output format:
1. Provide a concise summary of identified issues
2. Present suggested improvements with clear before/after code examples
3. Explain the reasoning and benefits behind each improvement
4. Rate changes by risk level (low/medium/high) and impact (low/medium/high)
5. Include validation steps to verify improvements work as expected"""},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7
            }
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                logging.error(f"OpenAI error: {response.text}")
                return f"Error: Failed to get response from OpenAI. Status code: {response.status_code}"
        except Exception as e:
            logging.exception("Error connecting to OpenAI")
            return f"Error: {str(e)}"
    
    def scan_agent_scripts(self):
        """Scan all agent scripts in the project."""
        agent_scripts = []
        
        # Scan agents directory
        agents_dir = os.path.join(self.project_root, "agents")
        if os.path.exists(agents_dir) and os.path.isdir(agents_dir):
            for file in os.listdir(agents_dir):
                if file.endswith(".py"):
                    agent_scripts.append(os.path.join(agents_dir, file))
        
        # Scan CLI directory
        cli_dir = os.path.join(self.project_root, "cli")
        if os.path.exists(cli_dir) and os.path.isdir(cli_dir):
            devctl_path = os.path.join(cli_dir, "devctl")
            if os.path.exists(devctl_path):
                agent_scripts.append(devctl_path)
        
        # Scan memory directory
        memory_dir = os.path.join(self.project_root, "memory")
        if os.path.exists(memory_dir) and os.path.isdir(memory_dir):
            for file in os.listdir(memory_dir):
                if file.endswith(".py"):
                    agent_scripts.append(os.path.join(memory_dir, file))
        
        return agent_scripts
    
    def create_backup(self, file_path):
        """Create a backup of the file before modification."""
        if os.path.exists(file_path):
            # Create timestamped backup filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.basename(file_path)
            backup_filename = f"{filename}.{timestamp}.bak"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # Copy file to backup location
            shutil.copy2(file_path, backup_path)
            logging.info(f"Created backup of {file_path} at {backup_path}")
            
            return backup_path
        
        return None
    
    def analyze_script(self, script_path):
        """Analyze a script and suggest optimizations."""
        logging.info(f"Analyzing script: {script_path}")
        
        try:
            # Read script content
            with open(script_path, 'r') as f:
                script_content = f.read()
            
            # Create prompt for optimization suggestions
            prompt = (
                f"Analyze the following Python script and suggest improvements for:\n"
                f"1. Performance optimization\n"
                f"2. Code readability\n"
                f"3. Error handling\n"
                f"4. Security considerations\n"
                f"5. Maintainability\n\n"
                f"Provide specific code changes with explanations.\n\n"
                f"File: {os.path.basename(script_path)}\n\n"
                f"```python\n{script_content}\n```"
            )
            
            # Get response from the appropriate model
            if self.use_local_model:
                logging.info("Using local Ollama model")
                response = self._get_ollama_response(prompt)
            else:
                logging.info("Using OpenAI API")
                response = self._get_openai_response(prompt)
            
            return response
        except Exception as e:
            logging.exception(f"Error analyzing script: {script_path}")
            return f"Error analyzing script: {str(e)}"
    
    def apply_optimization(self, script_path, suggested_changes):
        """Apply suggested optimizations to a script.
        
        Args:
            script_path: Path to the script file
            suggested_changes: Dictionary with keys 'old_code' and 'new_code' for replacements
        
        Returns:
            Tuple of (success, message)
        """
        logging.info(f"Applying optimizations to {script_path}")
        
        try:
            # Create backup first
            backup_path = self.create_backup(script_path)
            if not backup_path:
                return False, "Failed to create backup"
            
            # Read current content
            with open(script_path, 'r') as f:
                content = f.read()
            
            # Apply each change
            updated_content = content
            for change in suggested_changes:
                if 'old_code' in change and 'new_code' in change:
                    updated_content = updated_content.replace(change['old_code'], change['new_code'])
            
            # Write back to file
            with open(script_path, 'w') as f:
                f.write(updated_content)
            
            logging.info(f"Successfully applied optimizations to {script_path}")
            return True, f"Optimizations applied. Backup saved at {backup_path}"
            
        except Exception as e:
            logging.exception(f"Error applying optimizations to {script_path}")
            return False, f"Error: {str(e)}"
    
    def run(self, args=None):
        """Run the self-optimization process."""
        print("\n=== Native OS Self-Optimization ===\n")
        
        # Scan for agent scripts
        print("Scanning for scripts to optimize...")
        scripts = self.scan_agent_scripts()
        
        if not scripts:
            print("No scripts found to optimize.")
            return
        
        print(f"Found {len(scripts)} scripts:")
        for i, script in enumerate(scripts):
            print(f"{i+1}. {os.path.basename(script)}")
        
        # Ask which script to optimize
        try:
            selection = input("\nEnter script number to optimize (or 'all' for all scripts): ")
            
            if selection.lower() == 'all':
                selected_scripts = scripts
            else:
                index = int(selection) - 1
                if 0 <= index < len(scripts):
                    selected_scripts = [scripts[index]]
                else:
                    print("Invalid selection.")
                    return
        except ValueError:
            print("Invalid input. Please enter a number.")
            return
        
        # Analyze and optimize each selected script
        for script in selected_scripts:
            print(f"\nAnalyzing {os.path.basename(script)}...")
            suggestions = self.analyze_script(script)
            
            print("\n=== Optimization Suggestions ===\n")
            print(suggestions)
            
            # Ask if user wants to apply changes
            print("\nWould you like to apply these optimizations?")
            print("This will create a backup of the original file first.")
            apply = input("Apply optimizations? (y/n): ").lower()
            
            if apply.startswith('y'):
                # In a real implementation, we would parse the AI response to get structured changes
                # Here we simply demonstrate the flow
                print("\nExtracting suggested code changes...")
                print("This is a limited demo that would identify specific code blocks to change.")
                print("No actual changes will be made in this demo to avoid unexpected modifications.")
                
                backup_path = self.create_backup(script)
                print(f"Created backup at: {backup_path}")
                print("In a full implementation, changes would be applied here.")
            else:
                print("Optimizations not applied.")
        
        print("\nSelf-optimization process completed.")
        return json.dumps({
            "success": True,
            "message": "Self-optimization analysis completed. See the logs for details."
        })
    
    def test(self):
        """Run a test to check if the agent is working."""
        print("Testing Self-Optimization Agent...")
        
        try:
            # Check if scanning works
            scripts = self.scan_agent_scripts()
            
            if scripts:
                print(f"✅ Test successful - found {len(scripts)} scripts that could be optimized.")
                sample_script = scripts[0]
                print(f"- Example script: {os.path.basename(sample_script)}")
                
                # Test backup creation
                backup_path = self.create_backup(sample_script)
                if backup_path:
                    print(f"- Successfully created backup at: {os.path.basename(backup_path)}")
                    return True
                else:
                    print("⚠️ Test partially completed, but backup creation failed")
                    return False
            else:
                print("⚠️ Test completed, but no scripts were found")
                return False
        except Exception as e:
            print(f"❌ Test failed: {str(e)}")
            logging.exception("Test failed")
            return False


def main():
    parser = argparse.ArgumentParser(description="Native OS Self-Optimization Agent")
    parser.add_argument("--test", action="store_true", help="Run a test to check if the agent is working")
    parser.add_argument("--scan", action="store_true", help="Scan for eligible scripts without analysis")
    parser.add_argument("--analyze", metavar="SCRIPT_PATH", help="Analyze a specific script path")
    args = parser.parse_args()
    
    agent = Evolver()
    
    if args.test:
        agent.test()
    elif args.scan:
        scripts = agent.scan_agent_scripts()
        if scripts:
            print(f"Found {len(scripts)} scripts that can be optimized:")
            for script in scripts:
                print(f"- {script}")
        else:
            print("No eligible scripts found.")
    elif args.analyze:
        # Analyze a specific script
        if os.path.exists(args.analyze):
            result = agent.analyze_script(args.analyze)
            print(result)
        else:
            print(f"Error: File not found: {args.analyze}")
    else:
        # Interactive mode
        result = agent.run()
        if isinstance(result, str):
            print(result)


if __name__ == "__main__":
    main()