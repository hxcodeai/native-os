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
LOG_FILE = os.path.join(LOG_DIR, "docker.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class DockerAgent:
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
        self.docker_dir = os.path.join(os.getcwd(), "infra", "docker")
        os.makedirs(self.docker_dir, exist_ok=True)
    
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
        """Get the standard system prompt for Docker configuration generation."""
        return """You are an expert Docker container specialist created by hxcode ai. Generate production-ready Dockerfiles, docker-compose files, and container configurations.

Your capabilities:
1. Create optimized Dockerfiles for various applications and languages
2. Design multi-container systems with docker-compose
3. Implement container security best practices
4. Generate build and deployment scripts for containers
5. Provide complete configuration for container orchestration

Areas of expertise:
- Containerizing applications (Node.js, Python, Java, Go, etc.)
- Multi-stage builds for optimization
- Docker networking and volumes
- Docker Compose for complex services
- Container security hardening
- CI/CD patterns for container workflows
- Registry configuration and management
- Container monitoring and logging setups

Best practices to follow:
- Use specific version tags instead of 'latest'
- Minimize layer count for smaller images
- Implement proper user permissions (avoid running as root)
- Cache dependencies effectively
- Remove unnecessary files and build tools from final images
- Include health checks for robustness
- Set appropriate environment variables
- Follow the principle of least privilege

Output format:
- Dockerfiles with clear comments and organization
- docker-compose.yml files with proper service definitions
- Shell scripts for build/deployment automation
- README files with usage instructions

Your response should include:
1. Dockerfile with optimized layers and security considerations
2. docker-compose.yml if multiple services are needed
3. Build and deployment scripts if requested
4. Documentation on usage and configuration options

Format your response with file paths and code blocks:

## file: Dockerfile
```dockerfile
# Dockerfile content here
```

## file: docker-compose.yml
```yaml
# docker-compose content here
```

Include ONLY valid Docker syntax and ensure all configurations follow current best practices."""
    
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
    
    def generate_docker_config(self, prompt, project_name=None, context_path=None):
        """Generate Docker configuration files based on a given prompt."""
        logging.info(f"Generating Docker configuration for prompt: {prompt}")
        
        # If no project name is provided, generate one based on the prompt
        if not project_name:
            # Generate a sanitized project name from the first few words of the prompt
            words = prompt.lower().replace(":", "").replace(",", "").replace(".", "").split()
            project_name = "-".join(words[:3])
            # Add timestamp to ensure uniqueness
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            project_name = f"{project_name}-{timestamp}"
        
        # Create project directory
        project_dir = os.path.join(self.docker_dir, project_name)
        os.makedirs(project_dir, exist_ok=True)
        
        # Determine the application context path
        context_info = ""
        if context_path:
            context_info = f"\nThe application source code is located at: {context_path}\n"
            
            # Try to determine language and framework
            detected_info = self.detect_app_info(context_path)
            if detected_info:
                context_info += f"\nDetected application information:\n{detected_info}\n"
        
        # Enhance the prompt for better Docker configuration generation
        enhanced_prompt = f"""
        Generate Docker configuration for the following request:
        
        {prompt}
        {context_info}
        
        Please provide:
        1. An optimized Dockerfile following best practices
        2. A docker-compose.yml file if multiple services are needed
        3. Build and deployment scripts if appropriate
        4. Clear comments and documentation
        
        The Docker configuration is for a project named '{project_name}'.
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
    
    def detect_app_info(self, context_path):
        """Detect application language, framework, and dependencies."""
        info = []
        
        try:
            # Check if context path exists
            if not os.path.exists(context_path):
                return None
            
            # Check for package.json (Node.js)
            package_json_path = os.path.join(context_path, "package.json")
            if os.path.exists(package_json_path):
                info.append("Language: Node.js")
                try:
                    with open(package_json_path, "r") as f:
                        package_data = json.load(f)
                        
                    if "dependencies" in package_data:
                        deps = list(package_data["dependencies"].keys())
                        if "express" in deps:
                            info.append("Framework: Express.js")
                        elif "react" in deps:
                            info.append("Framework: React")
                        elif "next" in deps:
                            info.append("Framework: Next.js")
                        elif "vue" in deps:
                            info.append("Framework: Vue.js")
                        
                        info.append(f"Dependencies: {', '.join(deps[:5])}" + (", ..." if len(deps) > 5 else ""))
                except Exception as e:
                    logging.warning(f"Error parsing package.json: {str(e)}")
            
            # Check for requirements.txt (Python)
            requirements_path = os.path.join(context_path, "requirements.txt")
            if os.path.exists(requirements_path):
                info.append("Language: Python")
                try:
                    with open(requirements_path, "r") as f:
                        deps = [line.strip().split("==")[0] for line in f.readlines() if line.strip() and not line.startswith("#")]
                    
                    if "flask" in [d.lower() for d in deps]:
                        info.append("Framework: Flask")
                    elif "django" in [d.lower() for d in deps]:
                        info.append("Framework: Django")
                    elif "fastapi" in [d.lower() for d in deps]:
                        info.append("Framework: FastAPI")
                    
                    info.append(f"Dependencies: {', '.join(deps[:5])}" + (", ..." if len(deps) > 5 else ""))
                except Exception as e:
                    logging.warning(f"Error parsing requirements.txt: {str(e)}")
            
            # Check for pom.xml (Java/Maven)
            pom_path = os.path.join(context_path, "pom.xml")
            if os.path.exists(pom_path):
                info.append("Language: Java (Maven)")
            
            # Check for build.gradle (Java/Gradle)
            gradle_path = os.path.join(context_path, "build.gradle")
            if os.path.exists(gradle_path):
                info.append("Language: Java (Gradle)")
            
            # Check for go.mod (Go)
            go_mod_path = os.path.join(context_path, "go.mod")
            if os.path.exists(go_mod_path):
                info.append("Language: Go")
            
            # Check for Cargo.toml (Rust)
            cargo_path = os.path.join(context_path, "Cargo.toml")
            if os.path.exists(cargo_path):
                info.append("Language: Rust")
            
            # Check for Gemfile (Ruby)
            gemfile_path = os.path.join(context_path, "Gemfile")
            if os.path.exists(gemfile_path):
                info.append("Language: Ruby")
                
                try:
                    with open(gemfile_path, "r") as f:
                        content = f.read()
                    
                    if "rails" in content.lower():
                        info.append("Framework: Ruby on Rails")
                except Exception as e:
                    logging.warning(f"Error parsing Gemfile: {str(e)}")
        
        except Exception as e:
            logging.exception(f"Error detecting application info: {str(e)}")
            return None
        
        return "\n".join(info) if info else None
    
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
        
        # Validate that we're only running docker commands
        allowed_commands = ["docker", "docker-compose"]
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
    
    def parse_registry_info(self, prompt):
        """Parse registry information from the prompt."""
        registry = {
            "username": None,
            "password": None,
            "url": None,
            "image_name": None,
            "tag": "latest"
        }
        
        # Look for Docker Hub references
        if "docker hub" in prompt.lower() or "dockerhub" in prompt.lower():
            registry["url"] = "docker.io"
        
        # Look for AWS ECR references
        if "ecr" in prompt.lower() or "elastic container registry" in prompt.lower():
            registry["url"] = "aws_ecr"
        
        # Look for GitHub Container Registry references
        if "ghcr" in prompt.lower() or "github container registry" in prompt.lower():
            registry["url"] = "ghcr.io"
        
        # Check for username/password in environment variables
        registry["username"] = os.getenv("DOCKER_USERNAME")
        registry["password"] = os.getenv("DOCKER_PASSWORD")
        
        # Analyze the prompt for image name and tag information
        words = prompt.lower().split()
        for i, word in enumerate(words):
            if word in ["tag", "tags", "tagged", "tagging"]:
                if i + 1 < len(words):
                    potential_tag = words[i + 1].strip(",.;:")
                    if potential_tag.isalnum() or "-" in potential_tag or "." in potential_tag:
                        registry["tag"] = potential_tag
            
            if word in ["call", "name", "called", "named"]:
                if i + 1 < len(words):
                    potential_name = words[i + 1].strip(",.;:")
                    if "/" not in potential_name and ":" not in potential_name:
                        registry["image_name"] = potential_name
        
        return registry
    
    def run(self, prompt, project_name=None, context_path=None):
        """Run the Docker agent process."""
        try:
            # Generate project name if not provided
            if not project_name:
                # Generate a sanitized project name from the first few words of the prompt
                words = prompt.lower().replace(":", "").replace(",", "").replace(".", "").split()
                project_name = "-".join(words[:3])
                # Add timestamp to ensure uniqueness
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                project_name = f"{project_name}-{timestamp}"
            
            # Set context path to current directory if not provided
            if not context_path:
                # Check if prompt specifies a context path
                lower_prompt = prompt.lower()
                path_indicators = ["in ", "from ", "at ", "context ", "directory ", "folder "]
                for indicator in path_indicators:
                    if indicator in lower_prompt:
                        index = lower_prompt.find(indicator) + len(indicator)
                        # Extract the path from the prompt
                        potential_path = prompt[index:].split()[0].strip(",.;:'\"")
                        if os.path.exists(potential_path):
                            context_path = potential_path
                            break
                
                # Default to current directory if still no context path
                if not context_path:
                    context_path = os.getcwd()
            
            logging.info(f"Starting Docker agent for project: {project_name}")
            logging.info(f"Context path: {context_path}")
            
            # Log the user request
            logging.info(f"User prompt: {prompt}")
            
            # Check if we need to generate a Dockerfile
            dockerfile_path = os.path.join(context_path, "Dockerfile")
            generate_dockerfile = not os.path.exists(dockerfile_path)
            
            # Parse registry information from prompt
            registry_info = self.parse_registry_info(prompt)
            
            # Set image name from project name if not specified
            if not registry_info["image_name"]:
                registry_info["image_name"] = project_name
            
            if generate_dockerfile:
                # Generate Docker configuration files
                print(f"\nGenerating Docker configuration for project '{project_name}'...")
                result = self.generate_docker_config(prompt, project_name, context_path)
                
                if isinstance(result, str) and result.startswith("Error:"):
                    print(f"\n❌ {result}")
                    return
                
                project_dir = result["project_dir"]
                files = result["files"]
                
                print(f"\n✅ Generated {len(files)} Docker files in {project_dir}")
                print("\nGenerated files:")
                for file in files:
                    print(f"  - {file}")
                
                # Find the Dockerfile
                dockerfile = None
                for file in files:
                    if file.lower() == "dockerfile":
                        dockerfile = os.path.join(project_dir, file)
                        break
                
                if not dockerfile:
                    print("\n❌ No Dockerfile found in the generated files")
                    return
                
                # Copy the Dockerfile to the context directory if they're different
                if project_dir != context_path:
                    import shutil
                    shutil.copy2(dockerfile, os.path.join(context_path, "Dockerfile"))
                    print(f"\nCopied Dockerfile to context directory: {context_path}")
                
                # Find docker-compose.yml if it exists
                compose_file = None
                for file in files:
                    if file.lower() == "docker-compose.yml" or file.lower() == "docker-compose.yaml":
                        compose_file = os.path.join(project_dir, file)
                        break
                
                if compose_file and project_dir != context_path:
                    import shutil
                    shutil.copy2(compose_file, os.path.join(context_path, os.path.basename(compose_file)))
                    print(f"\nCopied {os.path.basename(compose_file)} to context directory: {context_path}")
            else:
                print(f"\nUsing existing Dockerfile in {context_path}")
            
            # Ask for confirmation to build the Docker image
            confirmation = input(f"\nDo you want to build the Docker image for {project_name}? (yes/no): ")
            
            if confirmation.lower() in ["yes", "y"]:
                # Build the Docker image
                print(f"\nBuilding Docker image '{registry_info['image_name']}:{registry_info['tag']}'...")
                
                build_command = f"docker build -t {registry_info['image_name']}:{registry_info['tag']} {context_path}"
                build_result = self.execute_command(build_command)
                
                if not build_result["success"]:
                    print(f"\n❌ Docker build failed:")
                    print(build_result["output"])
                    return
                
                print("\n✅ Docker image built successfully")
                
                # Ask for confirmation to push the Docker image
                push_confirmation = input(f"\nDo you want to push the Docker image to a registry? (yes/no): ")
                
                if push_confirmation.lower() in ["yes", "y"]:
                    # Check for registry credentials
                    if not registry_info["username"] or not registry_info["password"]:
                        registry_info["username"] = input("\nEnter registry username: ")
                        registry_info["password"] = input("Enter registry password: ")
                    
                    # If still no URL, ask for one
                    if not registry_info["url"]:
                        registry_info["url"] = input("\nEnter registry URL (default: docker.io): ") or "docker.io"
                    
                    # If registry is AWS ECR, handle special case
                    if registry_info["url"] == "aws_ecr":
                        # Get AWS region
                        aws_region = input("\nEnter AWS region (default: us-east-1): ") or "us-east-1"
                        
                        # Get AWS account ID
                        aws_account_id = input("\nEnter AWS account ID: ")
                        
                        # Construct ECR URL
                        ecr_url = f"{aws_account_id}.dkr.ecr.{aws_region}.amazonaws.com"
                        
                        # Login to ECR
                        print(f"\nLogging in to AWS ECR ({ecr_url})...")
                        login_command = f"aws ecr get-login-password --region {aws_region} | docker login --username AWS --password-stdin {ecr_url}"
                        login_result = self.execute_command(login_command)
                        
                        if not login_result["success"]:
                            print(f"\n❌ ECR login failed:")
                            print(login_result["output"])
                            return
                        
                        # Tag image for ECR
                        tag_command = f"docker tag {registry_info['image_name']}:{registry_info['tag']} {ecr_url}/{registry_info['image_name']}:{registry_info['tag']}"
                        tag_result = self.execute_command(tag_command)
                        
                        if not tag_result["success"]:
                            print(f"\n❌ Image tagging failed:")
                            print(tag_result["output"])
                            return
                        
                        # Push to ECR
                        print(f"\nPushing image to AWS ECR...")
                        push_command = f"docker push {ecr_url}/{registry_info['image_name']}:{registry_info['tag']}"
                        push_result = self.execute_command(push_command)
                        
                        if not push_result["success"]:
                            print(f"\n❌ Image push failed:")
                            print(push_result["output"])
                            return
                        
                        print(f"\n✅ Image pushed successfully to ECR: {ecr_url}/{registry_info['image_name']}:{registry_info['tag']}")
                    else:
                        # For other registries, use standard docker login and push
                        full_image_name = f"{registry_info['url']}/{registry_info['username']}/{registry_info['image_name']}"
                        
                        # Login to registry
                        print(f"\nLogging in to registry {registry_info['url']}...")
                        login_command = f"echo {registry_info['password']} | docker login {registry_info['url']} --username {registry_info['username']} --password-stdin"
                        login_result = self.execute_command(login_command)
                        
                        if not login_result["success"]:
                            print(f"\n❌ Registry login failed:")
                            print(login_result["output"])
                            return
                        
                        # Tag image for registry
                        tag_command = f"docker tag {registry_info['image_name']}:{registry_info['tag']} {full_image_name}:{registry_info['tag']}"
                        tag_result = self.execute_command(tag_command)
                        
                        if not tag_result["success"]:
                            print(f"\n❌ Image tagging failed:")
                            print(tag_result["output"])
                            return
                        
                        # Push to registry
                        print(f"\nPushing image to registry...")
                        push_command = f"docker push {full_image_name}:{registry_info['tag']}"
                        push_result = self.execute_command(push_command)
                        
                        if not push_result["success"]:
                            print(f"\n❌ Image push failed:")
                            print(push_result["output"])
                            return
                        
                        print(f"\n✅ Image pushed successfully: {full_image_name}:{registry_info['tag']}")
                
                # Check for docker-compose.yml in the context directory
                compose_path = os.path.join(context_path, "docker-compose.yml")
                if not os.path.exists(compose_path):
                    compose_path = os.path.join(context_path, "docker-compose.yaml")
                
                if os.path.exists(compose_path):
                    # Ask for confirmation to start containers with docker-compose
                    compose_confirmation = input(f"\nDo you want to start containers with docker-compose? (yes/no): ")
                    
                    if compose_confirmation.lower() in ["yes", "y"]:
                        print(f"\nStarting containers with docker-compose...")
                        
                        compose_command = f"docker-compose -f {compose_path} up -d"
                        compose_result = self.execute_command(compose_command, cwd=context_path)
                        
                        if not compose_result["success"]:
                            print(f"\n❌ docker-compose up failed:")
                            print(compose_result["output"])
                            return
                        
                        print("\n✅ Containers started successfully")
                        
                        # Show running containers
                        ps_command = "docker-compose ps"
                        ps_result = self.execute_command(ps_command, cwd=context_path)
                        
                        if ps_result["success"]:
                            print("\nRunning containers:")
                            print(ps_result["output"])
            else:
                print("\nDocker build cancelled")
            
            return {
                "context_path": context_path,
                "image_name": registry_info["image_name"],
                "tag": registry_info["tag"],
                "built": confirmation.lower() in ["yes", "y"]
            }
            
        except Exception as e:
            logging.exception("Error running Docker agent")
            print(f"\n❌ Error: {str(e)}")
    
    def test(self):
        """Run a test to check if the agent is working."""
        test_prompt = "Create a Dockerfile for a simple Node.js application"
        test_project = "test-docker-agent"
        
        print(f"Running test with prompt: '{test_prompt}'")
        result = self.generate_docker_config(test_prompt, test_project)
        
        if isinstance(result, dict) and "files" in result:
            print(f"✅ Test successful! Generated {len(result['files'])} files in {result['project_dir']}")
            return True
        else:
            print(f"❌ Test failed: {result}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Native OS Docker Agent")
    parser.add_argument("prompt", nargs="?", help="The Docker task prompt")
    parser.add_argument("--project", "-p", help="Project name for the Docker configuration")
    parser.add_argument("--context", "-c", help="Context path for Docker build (default: current directory)")
    parser.add_argument("--test", action="store_true", help="Run a test to check if the agent is working")
    args = parser.parse_args()
    
    agent = DockerAgent()
    
    if args.test:
        agent.test()
    elif args.prompt:
        agent.run(args.prompt, args.project, args.context)
    else:
        print("Please provide a prompt or use --test to run a test")
        print("Example: python3 docker-agent.py 'Build a Docker image for a Node.js app in ./src'")
        print("Example with options: python3 docker-agent.py --project my-app --context ./src 'Build and push to Docker Hub'")

if __name__ == "__main__":
    main()