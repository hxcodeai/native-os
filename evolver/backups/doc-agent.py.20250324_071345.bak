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
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.use_local_model = os.getenv("NATIVE_OS_LOCAL_MODEL", "0") == "1" or self.api_key is None
        
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
        """Get response from OpenAI API."""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "gpt-4",
                "messages": [
                    {"role": "system", "content": """You are an expert technical writer and documentation specialist created by hxcode ai. Generate clear, comprehensive, and professional documentation for software projects, APIs, and technical systems.

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

Always format documentation in clean Markdown with proper syntax highlighting for code blocks and consistent heading levels."""},
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
                    context += f"## File: {file_path}\n```\n{'\n'.join(lines)}\n```\n\n"
        
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
            logging.info("Using OpenAI API")
            response = self._get_openai_response(enhanced_prompt)
        
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
    
    def run(self, prompt):
        """Run the documentation generation process."""
        # Ask for project context
        print("\nDo you want to include project files as context? (y/n): ", end="")
        include_context = input().lower().startswith('y')
        
        project_dir = None
        if include_context:
            print("\nEnter project directory path (leave empty for current directory): ", end="")
            project_dir = input().strip()
            if not project_dir:
                project_dir = os.getcwd()
        
        # Generate documentation
        documentation = self.generate_documentation(prompt, project_dir)
        
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
        
        # Save the documentation
        saved_path = self.save_documentation(documentation, filename)
        
        print(f"\nSaved documentation to: {saved_path}")
        
        # Return result as JSON
        return json.dumps({
            "success": True,
            "message": f"Generated and saved documentation to {saved_path}",
            "file": saved_path
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
    args = parser.parse_args()
    
    agent = DocAgent()
    
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
