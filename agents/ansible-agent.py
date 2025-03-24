#!/usr/bin/env python3

import os
import sys
import json
import time
import logging
import argparse
import requests
import subprocess
from datetime import datetime
from pathlib import Path

# Setup logging
LOG_DIR = os.path.expanduser("~/.nativeos/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "ansible.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class AnsibleAgent:
    def __init__(self):
        # API keys for different providers
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        
        # Default to OpenAI if available
        self.default_provider = os.getenv("NATIVE_OS_DEFAULT_PROVIDER", "openai").lower()
        
        # Check if we should use local model
        self.use_local_model = os.getenv("NATIVE_OS_LOCAL_MODEL", "0") == "1" or (
            self.openai_api_key is None and 
            self.anthropic_api_key is None and 
            self.deepseek_api_key is None
        )
        
        # Configure output directory
        self.playbooks_dir = os.path.join(os.getcwd(), "infra", "playbooks")
        os.makedirs(self.playbooks_dir, exist_ok=True)
    
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
    
    def _get_system_prompt(self):
        """Get the standard system prompt for Ansible playbook generation."""
        return """You are an expert Ansible automation specialist created by hxcode ai. Generate production-ready Ansible playbooks, roles, and automation configurations.

Your capabilities:
1. Create complete, idempotent Ansible playbooks for server configuration
2. Design role-based Ansible structures for reusable automation
3. Implement best practices for security, scalability, and maintainability
4. Generate inventory files and configuration for various environments
5. Provide comprehensive deployment and execution instructions

Areas of expertise:
- Server provisioning and configuration management
- Application deployment and orchestration
- Security hardening and compliance automation
- Database installation and configuration
- Container setup (Docker, containerd)
- Monitoring agent installation and configuration
- CI/CD pipelines with Ansible
- Multi-environment deployment strategies

Best practices to follow:
- Write idempotent tasks that can be run multiple times safely
- Use handlers for service restarts and other triggered actions
- Implement proper error handling and reporting
- Leverage Ansible built-in modules over shell/command when possible
- Include well-structured variable files and templates
- Follow YAML best practices with proper indentation
- Use meaningful names for tasks, roles, and variables

Output format:
- Main playbook YAML file with complete task definitions
- Related inventory files if needed
- Variable files with default values
- Template files for configuration generation
- README with execution instructions and requirements

Your response should include:
1. Detailed playbook.yml with properly formatted YAML
2. Any additional files needed (templates, variables, inventory)
3. Clear documentation on how to run the playbook
4. Prerequisites for execution

Format your response with file paths and code blocks:

## file: playbook.yml
```yaml
# Ansible playbook code here
```

## file: inventory.ini
```ini
# Inventory file here
```

Include ONLY valid Ansible syntax and ensure all tasks are properly defined for idempotent execution."""
    
    def _get_openai_response(self, prompt):
        """Get response from OpenAI API with retry logic for rate limits."""
        max_retries = 3
        retry_delay = 2  # Initial delay in seconds
        
        for attempt in range(max_retries):
            try:
                headers = {
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "model": "gpt-3.5-turbo",  # Using gpt-3.5-turbo instead of gpt-4 for higher rate limits
                    "messages": [
                        {"role": "system", "content": self._get_system_prompt()},
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
                elif response.status_code == 429:
                    # Rate limit hit - implement exponential backoff
                    if attempt < max_retries - 1:  # Don't sleep on the last attempt
                        sleep_time = retry_delay * (2 ** attempt)
                        logging.warning(f"Rate limit hit. Retrying in {sleep_time} seconds...")
                        time.sleep(sleep_time)
                        continue
                    else:
                        logging.error(f"OpenAI rate limit exceeded after {max_retries} attempts: {response.text}")
                        return f"Error: OpenAI rate limit exceeded. Please try again later."
                else:
                    error_details = response.text
                    logging.error(f"OpenAI error: {error_details}")
                    # Print detailed error message for debugging
                    print(f"\nOpenAI API Error (Status {response.status_code}):")
                    print(f"Response: {error_details}")
                    return f"Error: Failed to get response from OpenAI. Status code: {response.status_code}. Details: {error_details}"
            except Exception as e:
                logging.exception("Error connecting to OpenAI")
                return f"Error: {str(e)}"
        
        return "Error: Maximum retries exceeded when contacting OpenAI API."
        
    def _get_claude_response(self, prompt):
        """Get response from Claude (Anthropic) API with retry logic."""
        max_retries = 3
        retry_delay = 2  # Initial delay in seconds
        
        for attempt in range(max_retries):
            try:
                headers = {
                    "x-api-key": f"{self.anthropic_api_key}",
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                }
                
                # Create the system prompt and user message
                system_prompt = self._get_system_prompt()
                
                data = {
                    "model": "claude-3-haiku-20240307",  # Use the latest Claude model
                    "max_tokens": 4000,
                    "temperature": 0.7,
                    "system": system_prompt,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }
                
                response = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=data
                )
                
                if response.status_code == 200:
                    return response.json()["content"][0]["text"]
                elif response.status_code == 429:
                    # Rate limit hit - implement exponential backoff
                    if attempt < max_retries - 1:  # Don't sleep on the last attempt
                        sleep_time = retry_delay * (2 ** attempt)
                        logging.warning(f"Claude rate limit hit. Retrying in {sleep_time} seconds...")
                        time.sleep(sleep_time)
                        continue
                    else:
                        logging.error(f"Claude rate limit exceeded after {max_retries} attempts: {response.text}")
                        return f"Error: Claude rate limit exceeded. Please try again later."
                else:
                    logging.error(f"Claude error: {response.text}")
                    return f"Error: Failed to get response from Claude. Status code: {response.status_code}"
            except Exception as e:
                logging.exception("Error connecting to Claude API")
                return f"Error: {str(e)}"
        
        return "Error: Maximum retries exceeded when contacting Claude API."
        
    def _get_deepseek_response(self, prompt):
        """Get response from DeepSeek API with retry logic."""
        max_retries = 3
        retry_delay = 2  # Initial delay in seconds
        
        for attempt in range(max_retries):
            try:
                headers = {
                    "Authorization": f"Bearer {self.deepseek_api_key}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "model": "deepseek-chat",  # Use DeepSeek chat model
                    "messages": [
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 4000
                }
                
                response = requests.post(
                    "https://api.deepseek.com/v1/chat/completions",  
                    headers=headers,
                    json=data
                )
                
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"]
                elif response.status_code == 429:
                    # Rate limit hit - implement exponential backoff
                    if attempt < max_retries - 1:  # Don't sleep on the last attempt
                        sleep_time = retry_delay * (2 ** attempt)
                        logging.warning(f"DeepSeek rate limit hit. Retrying in {sleep_time} seconds...")
                        time.sleep(sleep_time)
                        continue
                    else:
                        logging.error(f"DeepSeek rate limit exceeded after {max_retries} attempts: {response.text}")
                        return f"Error: DeepSeek rate limit exceeded. Please try again later."
                else:
                    logging.error(f"DeepSeek error: {response.text}")
                    return f"Error: Failed to get response from DeepSeek. Status code: {response.status_code}"
            except Exception as e:
                logging.exception("Error connecting to DeepSeek API")
                return f"Error: {str(e)}"
        
        return "Error: Maximum retries exceeded when contacting DeepSeek API."
    
    def generate_playbook(self, prompt, task_name=None):
        """Generate an Ansible playbook based on a given prompt."""
        logging.info(f"Generating Ansible playbook for prompt: {prompt}")
        
        # Generate a task name if not provided
        if not task_name:
            # Simple sanitization of the prompt for use in filename
            words = prompt.lower().replace(":", "").replace(",", "").replace(".", "").split()
            task_name = "-".join(words[:3])
            # Add timestamp to ensure uniqueness
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            task_name = f"{task_name}-{timestamp}"
        
        # Create task directory if it doesn't exist
        task_dir = os.path.join(self.playbooks_dir, task_name)
        os.makedirs(task_dir, exist_ok=True)
        
        # Enhance the prompt for better Ansible playbook generation
        enhanced_prompt = f"""
        Generate an Ansible playbook for the following task:
        
        {prompt}
        
        Please provide:
        1. A complete Ansible playbook with all necessary tasks
        2. Any required inventory files or templates
        3. Ensure tasks are idempotent and follow best practices
        4. Include clear comments and documentation
        
        The playbook will be used for task '{task_name}'.
        """
        
        # Get response from the appropriate model
        if self.use_local_model:
            logging.info("Using local Ollama model")
            response = self._get_ollama_response(enhanced_prompt)
        else:
            # Choose AI provider based on default_provider setting and available API keys
            provider = self.default_provider
            
            if provider == "openai" and self.openai_api_key:
                logging.info("Using OpenAI API")
                response = self._get_openai_response(enhanced_prompt)
            elif provider == "claude" and self.anthropic_api_key:
                logging.info("Using Claude API")
                response = self._get_claude_response(enhanced_prompt)
            elif provider == "deepseek" and self.deepseek_api_key:
                logging.info("Using DeepSeek API")
                response = self._get_deepseek_response(enhanced_prompt)
            else:
                # Fallback to any available provider
                if self.openai_api_key:
                    logging.info("Falling back to OpenAI API")
                    response = self._get_openai_response(enhanced_prompt)
                elif self.anthropic_api_key:
                    logging.info("Falling back to Claude API")
                    response = self._get_claude_response(enhanced_prompt)
                elif self.deepseek_api_key:
                    logging.info("Falling back to DeepSeek API")
                    response = self._get_deepseek_response(enhanced_prompt)
                else:
                    return "Error: No AI provider available. Please set at least one API key for OpenAI, Claude, or DeepSeek."
        
        # Extract files from the response
        files = self.extract_files(response)
        
        # Save the files
        self.save_files(files, task_dir)
        
        return {
            "task_dir": task_dir,
            "files": [f["filename"] for f in files],
            "response": response
        }
    
    def extract_files(self, response):
        """Extract files from the generated response."""
        files = []
        
        # Look for file markers like "## file: filename.ext" or "```language\n"
        lines = response.split("\n")
        current_file = None
        current_content = []
        in_code_block = False
        
        for line in lines:
            # Check for file markers
            if line.startswith("## file:") or line.startswith("## File:"):
                # If we were processing a file, save it
                if current_file:
                    files.append({
                        "filename": current_file,
                        "content": "\n".join(current_content)
                    })
                    current_content = []
                
                # Extract new filename
                current_file = line.split(":", 1)[1].strip()
                in_code_block = False
            elif line.strip().startswith("```") and not in_code_block:
                # Beginning of a code block
                in_code_block = True
                # Skip this line as it's just the code block marker
                continue
            elif line.strip() == "```" and in_code_block:
                # End of a code block
                in_code_block = False
                # Skip this line as it's just the code block marker
                continue
            elif current_file:  # Only append content if we're inside a file section
                current_content.append(line)
        
        # Don't forget to save the last file if there is one
        if current_file:
            files.append({
                "filename": current_file,
                "content": "\n".join(current_content)
            })
        
        return files
    
    def save_files(self, files, base_dir):
        """Save the extracted files to disk."""
        logging.info(f"Saving {len(files)} files to {base_dir}")
        
        saved_files = []
        
        for file_info in files:
            filename = file_info["filename"]
            content = file_info["content"]
            
            # Handle potential path traversal attempts
            safe_filename = os.path.normpath(filename)
            if safe_filename.startswith(os.path.sep) or ".." in safe_filename:
                logging.warning(f"Potential path traversal attempt: {filename}. Skipping.")
                continue
            
            # Create the full path
            file_path = os.path.join(base_dir, safe_filename)
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            
            # Write the file
            with open(file_path, "w") as f:
                f.write(content)
            
            saved_files.append(file_path)
            logging.info(f"Saved file: {file_path}")
        
        return saved_files
    
    def check_command_safety(self, command):
        """Check if a command is safe to execute."""
        # List of potentially dangerous commands
        dangerous_patterns = [
            "rm -rf", "rmdir", "mkfs", 
            "> /dev", "dd if", 
            ":(){:|:&};:", "wget", "curl -o",
            "sudo", "su"
        ]
        
        # Check if the command contains any dangerous patterns
        for pattern in dangerous_patterns:
            if pattern in command:
                return False, f"Command contains potentially dangerous pattern: {pattern}"
        
        # Validate that we're only running ansible commands
        allowed_commands = ["ansible-playbook", "ansible"]
        command_parts = command.strip().split()
        
        if not command_parts:
            return False, "Empty command"
        
        if command_parts[0] not in allowed_commands:
            return False, f"Only the following commands are allowed: {', '.join(allowed_commands)}"
        
        return True, "Command appears safe"
    
    def execute_command(self, command, cwd=None):
        """Execute a shell command after checking for safety."""
        # Check command safety first
        is_safe, message = self.check_command_safety(command)
        
        if not is_safe:
            logging.error(f"Unsafe command rejected: {command}. Reason: {message}")
            return {
                "success": False,
                "output": f"Error: Command rejected for safety reasons: {message}",
                "command": command
            }
        
        logging.info(f"Executing command: {command} in directory: {cwd or 'current'}")
        
        try:
            # Execute the command
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True
            )
            
            output = result.stdout
            error = result.stderr
            
            if result.returncode == 0:
                logging.info(f"Command executed successfully: {command}")
                if error:
                    logging.warning(f"Command had warnings: {error}")
                
                return {
                    "success": True,
                    "output": output,
                    "warnings": error if error else None,
                    "command": command
                }
            else:
                logging.error(f"Command failed: {command}")
                logging.error(f"Error: {error}")
                
                return {
                    "success": False,
                    "output": f"Error: {error}",
                    "command": command
                }
        except Exception as e:
            logging.exception(f"Exception while executing command: {command}")
            return {
                "success": False,
                "output": f"Error: {str(e)}",
                "command": command
            }
    
    def run(self, prompt, task_name=None):
        """Run the Ansible agent process."""
        try:
            # Generate a task name if not provided
            if not task_name:
                # Generate a sanitized task name from the first few words of the prompt
                words = prompt.lower().replace(":", "").replace(",", "").replace(".", "").split()
                task_name = "-".join(words[:3])
                # Add timestamp to ensure uniqueness
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                task_name = f"{task_name}-{timestamp}"
            
            logging.info(f"Starting Ansible agent for task: {task_name}")
            
            # Log the user request
            logging.info(f"User prompt: {prompt}")
            
            # Generate Ansible playbook
            print(f"\nGenerating Ansible playbook for task '{task_name}'...")
            result = self.generate_playbook(prompt, task_name)
            
            if isinstance(result, str) and result.startswith("Error:"):
                print(f"\n❌ {result}")
                return
            
            task_dir = result["task_dir"]
            files = result["files"]
            
            print(f"\n✅ Generated {len(files)} Ansible files in {task_dir}")
            print("\nGenerated files:")
            for file in files:
                print(f"  - {file}")
            
            # Look for the main playbook file
            playbook_file = None
            for file in files:
                if file.endswith(".yml") or file.endswith(".yaml"):
                    if "playbook" in file.lower() or "main" in file.lower() or "site" in file.lower():
                        playbook_file = file
                        break
            
            # If no obvious main playbook found, use the first .yml file
            if not playbook_file:
                for file in files:
                    if file.endswith(".yml") or file.endswith(".yaml"):
                        playbook_file = file
                        break
            
            if not playbook_file:
                print("\n❌ No playbook file found in the generated files")
                return
            
            playbook_path = os.path.join(task_dir, playbook_file)
            
            # Ask for confirmation before running
            confirmation = input(f"\nDo you want to run the Ansible playbook {playbook_file}? (yes/no): ")
            
            if confirmation.lower() in ["yes", "y"]:
                print(f"\nRunning Ansible playbook: {playbook_file}...")
                
                # Check if inventory file exists
                inventory_file = None
                for file in files:
                    if "inventory" in file.lower() or "hosts" in file.lower():
                        inventory_file = os.path.join(task_dir, file)
                        break
                
                # Build the command
                command = f"ansible-playbook {playbook_path}"
                if inventory_file:
                    command += f" -i {inventory_file}"
                
                # Execute the playbook
                result = self.execute_command(command)
                
                if result["success"]:
                    print("\n✅ Ansible playbook executed successfully")
                    print("\nExecution output:")
                    print(result["output"])
                    
                    # Parse the output for success/fail counts if available
                    success_count = 0
                    fail_count = 0
                    changed_count = 0
                    
                    for line in result["output"].split("\n"):
                        if "ok=" in line:
                            parts = line.split()
                            for part in parts:
                                if part.startswith("ok="):
                                    success_count = int(part.split("=")[1])
                                elif part.startswith("failed="):
                                    fail_count = int(part.split("=")[1])
                                elif part.startswith("changed="):
                                    changed_count = int(part.split("=")[1])
                    
                    if success_count > 0 or fail_count > 0 or changed_count > 0:
                        print(f"\nPlaybook summary: {success_count} successful, {changed_count} changed, {fail_count} failed")
                else:
                    print(f"\n❌ Ansible playbook execution failed:")
                    print(result["output"])
            else:
                print("\nAnsible playbook execution cancelled")
            
            # Return the task directory and files
            return {
                "task_dir": task_dir,
                "files": files,
                "executed": confirmation.lower() in ["yes", "y"]
            }
            
        except Exception as e:
            logging.exception("Error running Ansible agent")
            print(f"\n❌ Error: {str(e)}")
    
    def test(self):
        """Run a test to check if the agent is working."""
        test_prompt = "Install Docker on a Linux server and configure it to start on boot"
        test_task = "test-ansible-agent"
        
        print(f"Running test with prompt: '{test_prompt}'")
        result = self.generate_playbook(test_prompt, test_task)
        
        if isinstance(result, dict) and "files" in result:
            print(f"✅ Test successful! Generated {len(result['files'])} files in {result['task_dir']}")
            return True
        else:
            print(f"❌ Test failed: {result}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Native OS Ansible Agent")
    parser.add_argument("prompt", nargs="?", help="The Ansible task prompt")
    parser.add_argument("--task", "-t", help="Task name for the Ansible playbook")
    parser.add_argument("--test", action="store_true", help="Run a test to check if the agent is working")
    args = parser.parse_args()
    
    agent = AnsibleAgent()
    
    if args.test:
        agent.test()
    elif args.prompt:
        agent.run(args.prompt, args.task)
    else:
        print("Please provide a prompt or use --test to run a test")
        print("Example: python3 ansible-agent.py 'Install Docker, NGINX, and deploy our container'")
        print("Example with task name: python3 ansible-agent.py --task deploy-nginx 'Install and configure NGINX as a reverse proxy'")

if __name__ == "__main__":
    main()