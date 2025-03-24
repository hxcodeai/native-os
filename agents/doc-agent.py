#!/usr/bin/env python3

import os
import sys
import json
import time
import logging
import argparse
import requests
import glob
from datetime import datetime
from pathlib import Path

# Setup logging
LOG_DIR = os.path.expanduser("~/.nativeos/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "agent-doc.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class DocAgent:
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
        self.output_dir = os.path.join(os.getcwd(), "output", "docs")
        os.makedirs(self.output_dir, exist_ok=True)
    
    def _get_ollama_response(self, prompt):
        """Get response from local Ollama model."""
        try:
            # Check if Ollama is running
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3", # or another model good for documentation
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
                    print(f"Request headers: {headers}")
                    print(f"Response: {error_details}")
                    return f"Error: Failed to get response from OpenAI. Status code: {response.status_code}. Details: {error_details}"
            except Exception as e:
                logging.exception("Error connecting to OpenAI")
                return f"Error: {str(e)}"
        
        return "Error: Maximum retries exceeded when contacting OpenAI API."
    
    def read_project_files(self, directory=None):
        """Read source code files from a directory to provide context."""
        if not directory:
            directory = os.getcwd()
        
        logging.info(f"Reading project files from {directory}")
        
        # File types to include
        file_extensions = [
            ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".sh",
            ".md", ".json", ".yaml", ".yml", ".toml", ".rs", ".go"
        ]
        
        # Directories to exclude
        exclude_dirs = ["node_modules", "venv", ".git", "__pycache__", "build", "dist"]
        
        # Collect files
        files_content = {}
        for ext in file_extensions:
            pattern = os.path.join(directory, f"**/*{ext}")
            for file_path in glob.glob(pattern, recursive=True):
                # Check if file is in excluded directory
                if any(exclude_dir in file_path for exclude_dir in exclude_dirs):
                    continue
                
                try:
                    # Only read files smaller than 100KB to avoid memory issues
                    if os.path.getsize(file_path) < 100 * 1024:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            rel_path = os.path.relpath(file_path, directory)
                            files_content[rel_path] = f.read()
                except Exception as e:
                    logging.warning(f"Error reading file {file_path}: {str(e)}")
        
        return files_content
    
    def _get_system_prompt(self):
        """Get the standard system prompt for documentation generation."""
        return """You are an expert technical writer and documentation specialist created by hxcode ai. Generate clear, comprehensive, and professional documentation for software projects, APIs, and technical systems.

Your capabilities:
1. Create detailed yet accessible technical documentation for various audiences
2. Structure information logically with proper hierarchy and organization
3. Explain complex concepts in clear, precise language
4. Produce documentation in various formats (tutorials, API references, guides, etc.)
5. Balance technical accuracy with readability and user experience

Documentation style guidelines:
- Use clear, concise language with consistent terminology
- Structure content with logical headings, lists, and tables
- Include relevant code examples with explanations
- Add visual elements where appropriate (diagrams, flowcharts described in text)
- Maintain a professional, neutral tone
- Anticipate user questions and address them proactively
- Follow industry best practices for technical documentation

Specialized strengths:
- API documentation with request/response examples
- Setup and installation guides with step-by-step instructions
- Project READMEs with clear organization and essential information
- System architecture documentation with component relationships
- User guides with appropriate screenshots and usage examples
- Troubleshooting sections with common issues and solutions

Always format documentation in clean Markdown with proper syntax highlighting for code blocks and consistent heading levels."""
    
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
                    "model": "deepseek-chat",  # Use DeepSeek chat model for documentation
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
    
    def generate_documentation(self, prompt, project_dir=None):
        """Generate documentation based on the given prompt and project context."""
        logging.info(f"Generating documentation for prompt: {prompt}")
        
        # Get project context if directory is provided
        context = ""
        if project_dir:
            files_content = self.read_project_files(project_dir)
            if files_content:
                context = "Project files:\n\n"
                for file_path, content in files_content.items():
                    # Add first 100 lines or less of each file
                    lines = content.split('\n')[:100]
                    context += f"## File: {file_path}\n```\n" + "\n".join(lines) + "\n```\n\n"
        
        # Enhance the prompt for better documentation generation
        enhanced_prompt = f"""
        Generate documentation for the following request:
        
        {prompt}
        
        {context}
        
        Please provide:
        1. Clear and comprehensive documentation
        2. Well-structured with headers, lists, and code examples
        3. Include installation/usage instructions if applicable
        4. Follow best practices for technical documentation
        
        Format the documentation in Markdown.
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
    
    def save_documentation(self, content, filename=None):
        """Save the generated documentation to a file."""
        if not filename:
            # Generate a default filename if none provided
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"documentation_{timestamp}.md"
        
        # Ensure the filename has .md extension
        if not filename.endswith(".md"):
            filename += ".md"
        
        # Create full path
        full_path = os.path.join(self.output_dir, filename)
        
        # Save the file
        with open(full_path, "w") as f:
            f.write(content)
        
        logging.info(f"Saved documentation to: {full_path}")
        return full_path
    
    def run(self, prompt, interactive=True):
        """Run the documentation generation process."""
        project_dir = None
        
        # Interactive mode is used when the script is called directly
        if interactive:
            try:
                # Ask for project context
                print("\nDo you want to include project files as context? (y/n): ", end="")
                include_context = input().lower().startswith('y')
                
                if include_context:
                    print("\nEnter project directory path (leave empty for current directory): ", end="")
                    project_dir = input().strip()
                    if not project_dir:
                        project_dir = os.getcwd()
            except EOFError:
                # If we can't get input (like when called from CLI), use non-interactive mode
                interactive = False
                logging.info("Input not available, switching to non-interactive mode")
        
        # Non-interactive mode automatically includes project context from current directory
        if not interactive:
            project_dir = os.getcwd()
        
        # Generate documentation
        documentation = self.generate_documentation(prompt, project_dir)
        
        # Interactive mode shows preview and asks for confirmation
        if interactive:
            # Preview the documentation
            print("\n=== Documentation Preview ===\n")
            preview_lines = documentation.split('\n')[:20]
            for line in preview_lines:
                print(line)
            if len(documentation.split('\n')) > 20:
                print("...(content truncated for preview)...")
            
            # Ask for confirmation
            print("\nSave this documentation? (y/n): ", end="")
            confirm = input().lower()
            if not confirm.startswith('y'):
                print("Documentation not saved.")
                return json.dumps({
                    "success": False,
                    "message": "Documentation generated but not saved (user canceled)"
                })
            
            # Get filename
            print("\nEnter filename (leave empty for auto-generated name): ", end="")
            filename = input().strip()
        else:
            # Non-interactive mode automatically saves with a generated filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Create a filename based on the first few words of the prompt
            prompt_words = prompt.split()[:3]
            prompt_part = "_".join(word.lower() for word in prompt_words if word.isalnum())
            filename = f"{prompt_part}_{timestamp}.md"
        
        # Save the documentation
        saved_path = self.save_documentation(documentation, filename)
        
        if interactive:
            print(f"\nSaved documentation to: {saved_path}")
        
        # Return result as JSON
        content_preview = documentation[:500] + "..." if len(documentation) > 500 else documentation
        return json.dumps({
            "success": True,
            "message": f"Generated and saved documentation to {saved_path}",
            "file": saved_path,
            "content": content_preview
        })
    
    def test(self):
        """Run a test to check if the agent is working."""
        print("Testing Documentation Agent...")
        test_prompt = "Create a simple README for a Python web application"
        
        try:
            response = self.generate_documentation(test_prompt)
            if response and len(response) > 100:  # Simple check for reasonable content
                print("✅ Test successful - documentation generation works!")
                print(f"- Generated {len(response)} characters of documentation")
                return True
            else:
                print("⚠️ Test completed, but documentation seems too short or empty")
                return False
        except Exception as e:
            print(f"❌ Test failed: {str(e)}")
            logging.exception("Test failed")
            return False

def main():
    parser = argparse.ArgumentParser(description="Native OS Documentation Agent")
    parser.add_argument("prompt", nargs="?", help="The documentation generation prompt")
    parser.add_argument("--test", action="store_true", help="Run a test to check if the agent is working")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode with user prompts")
    args = parser.parse_args()
    
    agent = DocAgent()
    
    # Detect if we're being run from CLI pipe (non-interactive)
    is_pipe = not sys.stdin.isatty() if hasattr(sys.stdin, 'isatty') else True
    # Default to non-interactive mode when called from CLI unless explicitly requested
    interactive_mode = args.interactive and not is_pipe
    
    if args.test:
        agent.test()
    elif args.prompt:
        result = agent.run(args.prompt, interactive=interactive_mode)
        print(result)
    else:
        # If no prompt is provided and not testing, read from stdin
        prompt = sys.stdin.read().strip()
        if prompt:
            result = agent.run(prompt, interactive=interactive_mode)
            print(result)
        else:
            parser.print_help()

if __name__ == "__main__":
    main()
