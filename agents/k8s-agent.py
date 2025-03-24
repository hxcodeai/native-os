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
LOG_FILE = os.path.join(LOG_DIR, "k8s.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class K8sAgent:
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
        self.k8s_dir = os.path.join(os.getcwd(), "infra", "k8s")
        os.makedirs(self.k8s_dir, exist_ok=True)
    
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
        """Get the standard system prompt for Kubernetes configuration generation."""
        return """You are an expert Kubernetes specialist created by hxcode ai. Generate production-ready Kubernetes manifests, Helm charts, and Kustomize configurations.

Your capabilities:
1. Create complete, well-structured Kubernetes manifests for deployments, services, and other resources
2. Design Helm charts with appropriate templates and values
3. Implement Kustomize overlays and bases for environment-specific configurations
4. Generate scripts and utilities for Kubernetes management and automation
5. Provide comprehensive deployment and scaling strategies

Areas of expertise:
- Pod scheduling and orchestration
- Service networking and exposure
- Ingress controllers and traffic routing
- StatefulSets and persistent storage
- ConfigMaps and Secrets management
- Resource requests and limits
- Horizontal and Vertical Pod Autoscaling
- Custom Resource Definitions
- Operators and custom controllers

Best practices to follow:
- Implement proper liveness and readiness probes
- Set appropriate resource requests and limits
- Use namespaces for isolation
- Apply secure context and RBAC configurations
- Configure horizontal pod autoscaling for scalability
- Implement proper labels and selectors
- Use init containers for setup operations
- Handle persistent volume claims appropriately

Output format:
- YAML manifests with clear structure and comments
- Helm chart directory structures with templates and values
- Kustomize overlays and bases if requested
- Shell scripts for deployment and management

Your response should include:
1. Complete YAML manifests for all required Kubernetes resources
2. Documentation on deployment procedures and prerequisites
3. Explanation of key configuration choices and options
4. Instructions for scaling and management

Format your response with file paths and code blocks:

## file: deployment.yaml
```yaml
# YAML manifest here
```

## file: service.yaml
```yaml
# YAML manifest here
```

Include ONLY valid Kubernetes YAML syntax and ensure all resources are properly configured for production use."""
    
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
    
    def generate_k8s_manifests(self, prompt, project_name=None):
        """Generate Kubernetes manifests based on a given prompt."""
        logging.info(f"Generating Kubernetes manifests for prompt: {prompt}")
        
        # If no project name is provided, generate one based on the prompt
        if not project_name:
            # Generate a sanitized project name from the first few words of the prompt
            words = prompt.lower().replace(":", "").replace(",", "").replace(".", "").split()
            project_name = "-".join(words[:3])
            # Add timestamp to ensure uniqueness
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            project_name = f"{project_name}-{timestamp}"
        
        # Create project directory
        project_dir = os.path.join(self.k8s_dir, project_name)
        os.makedirs(project_dir, exist_ok=True)
        
        # Detect current Kubernetes context to provide more contextual information
        current_context = self.get_current_k8s_context()
        context_info = ""
        if current_context:
            context_info = f"\nThe current Kubernetes context is: {current_context}\n"
        
        # Enhance the prompt for better Kubernetes manifest generation
        enhanced_prompt = f"""
        Generate Kubernetes manifests for the following request:
        
        {prompt}
        {context_info}
        
        Please provide:
        1. Complete YAML manifests for all necessary Kubernetes resources
        2. Clear comments and documentation
        3. Proper resource limits and requests
        4. Security best practices (RBAC, securityContext, etc.)
        
        The Kubernetes configuration is for a project named '{project_name}'.
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
    
    def get_current_k8s_context(self):
        """Get the current Kubernetes context."""
        try:
            result = subprocess.run(
                "kubectl config current-context",
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logging.warning("Failed to get current Kubernetes context")
                return None
        except Exception as e:
            logging.exception("Error getting Kubernetes context")
            return None
    
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
        
        # Validate that we're only running kubectl or helm commands
        allowed_commands = ["kubectl", "helm", "kustomize"]
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
        """Run the Kubernetes agent process."""
        try:
            # If no project name is provided, generate one based on the prompt
            if not project_name:
                # Generate a sanitized project name from the first few words of the prompt
                words = prompt.lower().replace(":", "").replace(",", "").replace(".", "").split()
                project_name = "-".join(words[:3])
                # Add timestamp to ensure uniqueness
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                project_name = f"{project_name}-{timestamp}"
            
            logging.info(f"Starting Kubernetes agent for project: {project_name}")
            
            # Log the user request
            logging.info(f"User prompt: {prompt}")
            
            # Check if kubectl is available
            kubectl_check = self.execute_command("kubectl version --client")
            if not kubectl_check["success"]:
                print("\n❌ kubectl is not available. Please install kubectl to use this agent.")
                return
            
            # Check if we're connected to a Kubernetes cluster
            cluster_check = self.execute_command("kubectl cluster-info")
            cluster_connected = cluster_check["success"]
            
            if not cluster_connected:
                print("\n⚠️ Not connected to a Kubernetes cluster. Manifests will be generated but not applied.")
            else:
                print("\n✅ Connected to Kubernetes cluster")
                print(cluster_check["output"])
            
            # Generate Kubernetes manifests
            print(f"\nGenerating Kubernetes manifests for project '{project_name}'...")
            result = self.generate_k8s_manifests(prompt, project_name)
            
            if isinstance(result, str) and result.startswith("Error:"):
                print(f"\n❌ {result}")
                return
            
            project_dir = result["project_dir"]
            files = result["files"]
            
            print(f"\n✅ Generated {len(files)} Kubernetes files in {project_dir}")
            print("\nGenerated files:")
            for file in files:
                print(f"  - {file}")
            
            # If connected to a cluster, ask if user wants to apply the manifests
            if cluster_connected:
                apply_confirmation = input("\nDo you want to apply these manifests to the current Kubernetes cluster? (yes/no): ")
                
                if apply_confirmation.lower() in ["yes", "y"]:
                    # Check if we should use kubectl apply or helm
                    is_helm_chart = False
                    for file in files:
                        if "Chart.yaml" in file or "values.yaml" in file:
                            is_helm_chart = True
                            break
                    
                    if is_helm_chart:
                        # Use Helm to deploy
                        print("\nDetected Helm chart configuration, using Helm for deployment...")
                        
                        # Check if Helm is installed
                        helm_check = self.execute_command("helm version")
                        if not helm_check["success"]:
                            print("\n❌ Helm is not available. Please install Helm to deploy this chart.")
                            return
                        
                        chart_name = project_name.replace("_", "-").lower()
                        release_name = input(f"\nEnter the Helm release name (default: {chart_name}): ") or chart_name
                        namespace = input("\nEnter the Kubernetes namespace (default: default): ") or "default"
                        
                        # Check if namespace exists, create if not
                        ns_check = self.execute_command(f"kubectl get namespace {namespace}")
                        if not ns_check["success"]:
                            create_ns = input(f"\nNamespace '{namespace}' does not exist. Create it? (yes/no): ")
                            if create_ns.lower() in ["yes", "y"]:
                                ns_create = self.execute_command(f"kubectl create namespace {namespace}")
                                if not ns_create["success"]:
                                    print(f"\n❌ Failed to create namespace: {ns_create['output']}")
                                    return
                                print(f"\n✅ Created namespace '{namespace}'")
                            else:
                                print("\nDeployment cancelled")
                                return
                        
                        # Install the Helm chart
                        print(f"\nInstalling Helm chart '{release_name}' in namespace '{namespace}'...")
                        helm_command = f"helm install {release_name} {project_dir} --namespace {namespace}"
                        
                        # Execute the Helm install command
                        install_result = self.execute_command(helm_command)
                        
                        if install_result["success"]:
                            print("\n✅ Helm chart installed successfully")
                            print(install_result["output"])
                            
                            # Get the deployment status
                            status_command = f"helm status {release_name} --namespace {namespace}"
                            status_result = self.execute_command(status_command)
                            
                            if status_result["success"]:
                                print("\nHelm release status:")
                                print(status_result["output"])
                        else:
                            print(f"\n❌ Helm chart installation failed:")
                            print(install_result["output"])
                    else:
                        # Use kubectl apply
                        print("\nApplying Kubernetes manifests with kubectl...")
                        
                        # Find all YAML files
                        yaml_files = []
                        for file in files:
                            if file.endswith((".yaml", ".yml")):
                                yaml_files.append(os.path.join(project_dir, file))
                        
                        if not yaml_files:
                            print("\n❌ No YAML files found in the generated manifests")
                            return
                        
                        # Ask for namespace
                        namespace = input("\nEnter the Kubernetes namespace (default: default): ") or "default"
                        
                        # Check if namespace exists, create if not
                        ns_check = self.execute_command(f"kubectl get namespace {namespace}")
                        if not ns_check["success"]:
                            create_ns = input(f"\nNamespace '{namespace}' does not exist. Create it? (yes/no): ")
                            if create_ns.lower() in ["yes", "y"]:
                                ns_create = self.execute_command(f"kubectl create namespace {namespace}")
                                if not ns_create["success"]:
                                    print(f"\n❌ Failed to create namespace: {ns_create['output']}")
                                    return
                                print(f"\n✅ Created namespace '{namespace}'")
                            else:
                                print("\nDeployment cancelled")
                                return
                        
                        # Apply each YAML file
                        success_count = 0
                        for yaml_file in yaml_files:
                            print(f"\nApplying {os.path.basename(yaml_file)}...")
                            apply_command = f"kubectl apply -f {yaml_file} --namespace {namespace}"
                            apply_result = self.execute_command(apply_command)
                            
                            if apply_result["success"]:
                                print(f"✅ Applied {os.path.basename(yaml_file)}")
                                print(apply_result["output"])
                                success_count += 1
                            else:
                                print(f"❌ Failed to apply {os.path.basename(yaml_file)}")
                                print(apply_result["output"])
                        
                        print(f"\nApplied {success_count} out of {len(yaml_files)} manifest files")
                        
                        # Get the deployment status
                        print("\nChecking deployment status...")
                        
                        # Try to find deployment resources to check status
                        status_commands = [
                            f"kubectl get pods --namespace {namespace} -l app={project_name}",
                            f"kubectl get deployment --namespace {namespace}"
                        ]
                        
                        for cmd in status_commands:
                            status_result = self.execute_command(cmd)
                            if status_result["success"] and status_result["output"].strip():
                                print(f"\nResource status:")
                                print(status_result["output"])
                                break
                        
                        print(f"\n✅ Deployment completed to namespace '{namespace}'")
                else:
                    print("\nManifest application cancelled")
            
            # Return the project directory and files
            return {
                "project_dir": project_dir,
                "files": files,
                "applied": cluster_connected and apply_confirmation.lower() in ["yes", "y"] if "apply_confirmation" in locals() else False
            }
            
        except Exception as e:
            logging.exception("Error running Kubernetes agent")
            print(f"\n❌ Error: {str(e)}")
    
    def test(self):
        """Run a test to check if the agent is working."""
        test_prompt = "Create a Kubernetes deployment for a simple Node.js application with 3 replicas"
        test_project = "test-k8s-agent"
        
        print(f"Running test with prompt: '{test_prompt}'")
        result = self.generate_k8s_manifests(test_prompt, test_project)
        
        if isinstance(result, dict) and "files" in result:
            print(f"✅ Test successful! Generated {len(result['files'])} files in {result['project_dir']}")
            return True
        else:
            print(f"❌ Test failed: {result}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Native OS Kubernetes Agent")
    parser.add_argument("prompt", nargs="?", help="The Kubernetes task prompt")
    parser.add_argument("--project", "-p", help="Project name for the Kubernetes manifests")
    parser.add_argument("--test", action="store_true", help="Run a test to check if the agent is working")
    args = parser.parse_args()
    
    agent = K8sAgent()
    
    if args.test:
        agent.test()
    elif args.prompt:
        agent.run(args.prompt, args.project)
    else:
        print("Please provide a prompt or use --test to run a test")
        print("Example: python3 k8s-agent.py 'Deploy a Node.js application with 3 replicas'")
        print("Example with project name: python3 k8s-agent.py --project my-app 'Scale the frontend service to 5 replicas'")

if __name__ == "__main__":
    main()