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
LOG_FILE = os.path.join(LOG_DIR, "agent-infra.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class InfraAgent:
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
        self.output_dir = os.path.join(os.getcwd(), "output", "infra")
        os.makedirs(self.output_dir, exist_ok=True)
    
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
        """Get the standard system prompt for infrastructure generation."""
        return """You are an expert infrastructure and deployment engineer created by hxcode ai. Generate infrastructure as code, deployment configurations, and provide comprehensive cloud architecture guidance.

Your capabilities:
1. Write robust, production-ready infrastructure code and deployment scripts
2. Design cloud architecture patterns that follow best practices
3. Implement secure, scalable, and cost-effective solutions
4. Provide detailed explanations of infrastructure components and their interactions
5. Generate complete deployment pipelines and workflows

Areas of expertise:
- AWS, Azure, GCP, and other cloud providers
- Kubernetes, Docker, and containerization
- Terraform, CloudFormation, Ansible, and other IaC tools
- CI/CD pipelines and DevOps workflows
- Networking, security, and compliance
- Database and storage solutions
- Monitoring, logging, and observability

Infrastructure design principles:
- Defense in depth: Implement multiple security controls at different layers
- Zero-trust security: Verify everything, trust nothing
- Infrastructure as Code: Use declarative definitions for all resources
- Least privilege: Grant only the permissions necessary for each component
- Auto-scaling: Design for elasticity based on demand
- High availability: Eliminate single points of failure
- Immutable infrastructure: Replace rather than modify components
- Modular architecture: Create reusable, decoupled components

Output format:
- Use '## file: filename.ext' format for each infrastructure file
- Include clear code blocks with language-specific syntax highlighting
- Provide architecture diagrams described in text format where helpful
- Include deployment instructions and prerequisites
- Add validation and testing procedures for the infrastructure

Specialized implementations:
- Micro-services architecture with service mesh patterns
- Serverless deployment models for cost optimization
- Multi-region disaster recovery configurations
- GitOps workflows for continuous deployment
- Infrastructure monitoring and alerting systems
- Compliance frameworks implementation (SOC2, HIPAA, etc.)
- Advanced networking with VPC peering, TransitGateway, etc.

Guidelines:
- Include detailed documentation and comments in your code
- Prioritize security, reliability, and maintainability
- Suggest cost-optimized solutions when possible
- Structure responses with clear file paths and code blocks
- Add thorough error handling and validation
- Implement proper security controls and access management

Avoid:
- Overly complex solutions when simpler ones will suffice
- Deprecated or outdated services/practices
- Insecure configurations or setups that expose vulnerabilities"""
    
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
    
    def generate_infra(self, prompt):
        """Generate infrastructure code/guidance based on the given prompt."""
        logging.info(f"Generating infrastructure for prompt: {prompt}")
        
        # Enhance the prompt for better infrastructure generation
        enhanced_prompt = f"""
        Generate infrastructure as code, deployment scripts, or cloud configuration for the following request:
        
        {prompt}
        
        Please provide:
        1. Complete configuration files and scripts
        2. Step-by-step deployment instructions
        3. Explanation of the infrastructure components
        4. Security considerations and best practices
        
        Format your response with file paths and code blocks like:
        
        ## file: deploy.sh
        ```bash
        # Code here
        ```
        
        ## file: terraform/main.tf
        ```hcl
        # Code here
        ```
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
        
        return response
    
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
            
            # Check for code block markers
            elif line.strip().startswith("```"):
                if in_code_block:
                    # End of code block
                    in_code_block = False
                    if current_file:
                        files.append({
                            "filename": current_file,
                            "content": "\n".join(current_content)
                        })
                        current_file = None
                        current_content = []
                else:
                    # Start of code block
                    in_code_block = True
                    # If no file name was specified before the code block,
                    # use a default name based on the language
                    if not current_file:
                        lang = line.strip()[3:].strip()
                        if lang:
                            extensions = {
                                "bash": "sh", "sh": "sh",
                                "yaml": "yaml", "yml": "yml",
                                "terraform": "tf", "tf": "tf", "hcl": "tf",
                                "dockerfile": "Dockerfile", "docker": "Dockerfile",
                                "json": "json", "python": "py", "py": "py"
                            }
                            ext = extensions.get(lang.lower(), "txt")
                            current_file = f"infra.{ext}"
            
            # If we're in a code block, add the line to the current content
            elif in_code_block and current_file:
                current_content.append(line)
        
        # Add the last file if there is one
        if current_file and current_content:
            files.append({
                "filename": current_file,
                "content": "\n".join(current_content)
            })
        
        # If no code blocks were found, save the entire response as a README
        if not files:
            files.append({
                "filename": "README.md",
                "content": response
            })
        
        return files
    
    def save_files(self, files, base_dir=None):
        """Save the extracted files to disk."""
        if not base_dir:
            # Create a timestamped output directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_dir = os.path.join(self.output_dir, f"infra_{timestamp}")
        
        os.makedirs(base_dir, exist_ok=True)
        
        saved_files = []
        for file_info in files:
            filename = file_info["filename"]
            content = file_info["content"]
            
            # Create full path
            full_path = os.path.join(base_dir, filename)
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # Save the file
            with open(full_path, "w") as f:
                f.write(content)
            
            # Make shell scripts executable
            if filename.endswith(".sh"):
                os.chmod(full_path, 0o755)
            
            saved_files.append(full_path)
            logging.info(f"Saved file: {full_path}")
        
        return saved_files
    
    def check_command_safety(self, command):
        """Check if a command is safe to execute."""
        dangerous_keywords = [
            "rm -rf", "rmdir", "mkfs", "dd if=", "dd of=", 
            "> /dev", "format", "fdisk", "mkfs", "wget", "curl -o",
            "sudo", "su -", "chmod 777", "> /etc/passwd"
        ]
        
        for keyword in dangerous_keywords:
            if keyword in command:
                return False, f"Command contains potentially dangerous operation: {keyword}"
        
        return True, "Command appears safe"
    
    def execute_command(self, command):
        """Execute a shell command with safety checks."""
        # Check command safety
        is_safe, reason = self.check_command_safety(command)
        
        if not is_safe:
            logging.warning(f"Unsafe command rejected: {command}. Reason: {reason}")
            return {
                "success": False,
                "output": f"Command rejected for safety reasons: {reason}",
                "command": command
            }
        
        # Ask for confirmation
        print(f"\n⚠️ About to execute command: {command}")
        confirm = input("Proceed? (y/n): ").lower()
        
        if not confirm.startswith('y'):
            return {
                "success": False,
                "output": "Command execution cancelled by user",
                "command": command
            }
        
        # Execute the command
        try:
            logging.info(f"Executing command: {command}")
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True
            )
            
            output = {
                "success": result.returncode == 0,
                "output": result.stdout if result.returncode == 0 else f"{result.stdout}\n{result.stderr}",
                "command": command,
                "returncode": result.returncode
            }
            
            logging.info(f"Command execution result: {output['success']}")
            return output
        except Exception as e:
            logging.exception(f"Error executing command: {command}")
            return {
                "success": False,
                "output": f"Error: {str(e)}",
                "command": command
            }
    
    def run(self, prompt):
        """Run the infrastructure agent process."""
        # Generate infrastructure code
        response = self.generate_infra(prompt)
        
        # Extract files from the response
        files = self.extract_files(response)
        
        # Preview the files
        print("\n=== Generated Infrastructure Files Preview ===\n")
        for i, file_info in enumerate(files):
            print(f"{i+1}. {file_info['filename']}")
            # Print first few lines as preview
            preview_lines = file_info['content'].split('\n')[:5]
            for line in preview_lines:
                print(f"   {line}")
            print("   ...")
            print()
        
        # Ask for confirmation
        confirm = input("Save these files to disk? (y/n): ").lower()
        if not confirm.startswith('y'):
            print("Files not saved.")
            return json.dumps({
                "success": False,
                "message": "Infrastructure generation completed, but files were not saved (user canceled)"
            })
        
        # Get target directory
        target_dir = input(f"Enter target directory (default: {self.output_dir}): ").strip()
        if not target_dir:
            target_dir = self.output_dir
        
        # Save the files
        saved_files = self.save_files(files, target_dir)
        
        print(f"\nSaved {len(saved_files)} files to {target_dir}")
        for file_path in saved_files:
            print(f"- {file_path}")
        
        # Check if there are executable scripts
        executable_scripts = [f for f in saved_files if f.endswith(".sh")]
        if executable_scripts:
            print("\n=== Executable Scripts ===")
            for i, script in enumerate(executable_scripts):
                print(f"{i+1}. {os.path.basename(script)}")
            
            # Ask if user wants to execute any script
            execute = input("\nWould you like to execute any of these scripts? (y/n): ").lower()
            if execute.startswith('y'):
                script_num = input(f"Enter script number (1-{len(executable_scripts)}): ")
                try:
                    script_index = int(script_num) - 1
                    if 0 <= script_index < len(executable_scripts):
                        script_path = executable_scripts[script_index]
                        result = self.execute_command(script_path)
                        
                        print("\n=== Execution Result ===")
                        print(f"Success: {result['success']}")
                        print(f"Output: {result['output']}")
                    else:
                        print("Invalid script number.")
                except ValueError:
                    print("Invalid input. Please enter a number.")
        
        # Return result as JSON
        return json.dumps({
            "success": True,
            "message": f"Generated and saved {len(saved_files)} infrastructure files to {target_dir}",
            "files": saved_files
        })
    
    def test(self):
        """Run a test to check if the agent is working."""
        print("Testing Infrastructure Agent...")
        test_prompt = "Create a simple Docker deployment for a web application"
        
        try:
            response = self.generate_infra(test_prompt)
            files = self.extract_files(response)
            
            if files:
                print("✅ Test successful - infrastructure generation works!")
                for file_info in files:
                    print(f"- Would have generated: {file_info['filename']}")
                return True
            else:
                print("⚠️ Test completed, but no files were extracted from the response")
                return False
        except Exception as e:
            print(f"❌ Test failed: {str(e)}")
            logging.exception("Test failed")
            return False

def main():
    parser = argparse.ArgumentParser(description="Native OS Infrastructure Agent")
    parser.add_argument("prompt", nargs="?", help="The infrastructure generation prompt")
    parser.add_argument("--test", action="store_true", help="Run a test to check if the agent is working")
    args = parser.parse_args()
    
    agent = InfraAgent()
    
    if args.test:
        agent.test()
    elif args.prompt:
        result = agent.run(args.prompt)
        print(result)
    else:
        # If no prompt is provided and not testing, read from stdin
        prompt = sys.stdin.read().strip()
        if prompt:
            result = agent.run(prompt)
            print(result)
        else:
            parser.print_help()

if __name__ == "__main__":
    main()
