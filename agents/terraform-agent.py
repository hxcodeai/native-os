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
LOG_FILE = os.path.join(LOG_DIR, "terraform.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class TerraformAgent:
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
        
        # Configure infrastructure directory
        self.infra_dir = os.path.join(os.getcwd(), "infra")
        os.makedirs(self.infra_dir, exist_ok=True)
    
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
        """Get the standard system prompt for Terraform generation."""
        return """You are an expert Terraform and infrastructure as code specialist created by hxcode ai. Generate production-ready Terraform files for cloud infrastructure deployments.

Your capabilities:
1. Create complete Terraform configurations for all major cloud providers
2. Implement infrastructure best practices for security, scalability, and reliability
3. Structure code with modules, variables, and outputs for maximum reusability
4. Design state management and remote backend configurations
5. Generate clear documentation and usage instructions

Areas of expertise:
- AWS, Azure, GCP, and other cloud provider resources
- Network architecture and security groups
- Container orchestration with EKS, AKS, GKE
- Database and storage configurations
- Load balancing and auto-scaling
- IAM and security best practices
- Monitoring and observability setups

Best practices to follow:
- Use resource naming conventions consistently
- Implement least privilege IAM policies
- Organize resources into logical modules
- Use variables with descriptive names and defaults
- Include helpful comments and documentation
- Follow security best practices for each provider
- Structure remote state for collaboration

Output format:
- Create separate files for main.tf, variables.tf, outputs.tf
- Include provider.tf for provider configuration
- Add a README.md with usage instructions
- Structure directory for module reuse
- Add appropriate .gitignore for Terraform

Your response should include multiple files:
1. main.tf - Primary resource definitions
2. variables.tf - Input variable declarations
3. outputs.tf - Output definitions
4. provider.tf - Provider configuration
5. README.md - Documentation and usage

Format your response with file paths and code blocks:

## file: main.tf
```hcl
# Terraform code here
```

## file: variables.tf
```hcl
# Variables here
```

Include ONLY valid Terraform syntax and ensure all resources are properly configured with required attributes."""
    
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
                    "model": "deepseek-chat",  # Use DeepSeek chat model for infrastructure
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
    
    def generate_terraform(self, prompt, project_name):
        """Generate Terraform files based on a given prompt."""
        logging.info(f"Generating Terraform files for prompt: {prompt}")
        
        # Create project directory if it doesn't exist
        project_dir = os.path.join(self.infra_dir, project_name)
        os.makedirs(project_dir, exist_ok=True)
        
        # Enhance the prompt for better Terraform generation
        enhanced_prompt = f"""
        Generate Terraform files for the following infrastructure request:
        
        {prompt}
        
        Please provide:
        1. Complete Terraform configuration files (main.tf, variables.tf, outputs.tf, provider.tf)
        2. README.md with usage instructions and explanations
        3. Ensure all resources are properly configured with required attributes
        4. Use best practices for security, scalability, and maintainability
        
        The files will be deployed in a project named '{project_name}'.
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
        self.save_files(files, project_dir)
        
        return {
            "project_dir": project_dir,
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
        
        # Validate that we're only running terraform commands
        allowed_commands = ["terraform"]
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
    
    def run(self, prompt, project_name=None):
        """Run the Terraform agent process."""
        try:
            # If no project name is provided, generate one based on the prompt
            if not project_name:
                # Generate a sanitized project name from the first few words of the prompt
                words = prompt.lower().replace(":", "").replace(",", "").replace(".", "").split()
                project_name = "-".join(words[:3])
                # Add timestamp to ensure uniqueness
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                project_name = f"{project_name}-{timestamp}"
            
            logging.info(f"Starting Terraform agent for project: {project_name}")
            
            # Log the user request
            logging.info(f"User prompt: {prompt}")
            
            # Generate Terraform files
            print(f"\nGenerating Terraform files for project '{project_name}'...")
            result = self.generate_terraform(prompt, project_name)
            
            if "Error:" in result:
                print(f"\n❌ {result}")
                return
            
            project_dir = result["project_dir"]
            files = result["files"]
            
            print(f"\n✅ Generated {len(files)} Terraform files in {project_dir}")
            print("\nGenerated files:")
            for file in files:
                print(f"  - {file}")
            
            # Initialize Terraform
            print("\nInitializing Terraform...")
            init_result = self.execute_command("terraform init", cwd=project_dir)
            
            if not init_result["success"]:
                print(f"\n❌ Terraform initialization failed:")
                print(init_result["output"])
                return
            
            print("\n✅ Terraform initialized successfully")
            
            # Run terraform plan
            print("\nRunning terraform plan...")
            plan_result = self.execute_command("terraform plan", cwd=project_dir)
            
            if not plan_result["success"]:
                print(f"\n❌ Terraform plan failed:")
                print(plan_result["output"])
                return
            
            print("\n✅ Terraform plan created successfully")
            print("\nPlan output:")
            print(plan_result["output"])
            
            # Ask for confirmation before applying
            confirmation = input("\nDo you want to apply this Terraform plan? (yes/no): ")
            
            if confirmation.lower() in ["yes", "y"]:
                print("\nApplying Terraform plan...")
                apply_result = self.execute_command("terraform apply -auto-approve", cwd=project_dir)
                
                if not apply_result["success"]:
                    print(f"\n❌ Terraform apply failed:")
                    print(apply_result["output"])
                    return
                
                print("\n✅ Terraform apply completed successfully")
                print("\nApply output:")
                print(apply_result["output"])
            else:
                print("\nTerraform apply cancelled")
            
            # Return the project directory and files
            return {
                "project_dir": project_dir,
                "files": files,
                "applied": confirmation.lower() in ["yes", "y"]
            }
            
        except Exception as e:
            logging.exception("Error running Terraform agent")
            print(f"\n❌ Error: {str(e)}")
    
    def test(self):
        """Run a test to check if the agent is working."""
        test_prompt = "Create a simple AWS EC2 instance with a security group"
        test_project = "test-terraform-agent"
        
        print(f"Running test with prompt: '{test_prompt}'")
        result = self.generate_terraform(test_prompt, test_project)
        
        if isinstance(result, dict) and "files" in result:
            print(f"✅ Test successful! Generated {len(result['files'])} files in {result['project_dir']}")
            return True
        else:
            print(f"❌ Test failed: {result}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Native OS Terraform Agent")
    parser.add_argument("prompt", nargs="?", help="The infrastructure request prompt")
    parser.add_argument("--project", "-p", help="Project name for the Terraform files")
    parser.add_argument("--test", action="store_true", help="Run a test to check if the agent is working")
    args = parser.parse_args()
    
    agent = TerraformAgent()
    
    if args.test:
        agent.test()
    elif args.prompt:
        agent.run(args.prompt, args.project)
    else:
        print("Please provide a prompt or use --test to run a test")
        print("Example: python3 terraform-agent.py 'Create an EC2 instance with 16GB RAM in us-east-1'")
        print("Example with project name: python3 terraform-agent.py --project my-aws-infra 'Create an EC2 instance with 16GB RAM'")

if __name__ == "__main__":
    main()