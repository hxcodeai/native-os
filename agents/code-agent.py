#!/usr/bin/env python3

import os
import sys
import json
import time
import logging
import argparse
import requests
from datetime import datetime
from pathlib import Path

# Setup logging
LOG_DIR = os.path.expanduser("~/.nativeos/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "agent-code.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class CodeAgent:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.use_local_model = os.getenv("NATIVE_OS_LOCAL_MODEL", "0") == "1" or self.api_key is None
        
        # Configure output directory
        self.output_dir = os.path.join(os.getcwd(), "output")
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
    
    def _get_openai_response(self, prompt):
        """Get response from OpenAI API with retry logic for rate limits."""
        max_retries = 3
        retry_delay = 2  # Initial delay in seconds
        
        for attempt in range(max_retries):
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "model": "gpt-4",
                    "messages": [
                        {"role": "system", "content": """You are an expert code generation assistant created by hxcode ai. Generate complete, production-ready code based on user requests.

Your capabilities:
1. Write robust, efficient, and well-documented code
2. Implement best practices for security, performance, and maintainability
3. Structure code with proper organization, clean architecture, and design patterns
4. Provide comprehensive solutions including error handling, input validation, and edge cases
5. Generate complete file structures for projects as needed

Guidelines:
- Favor simplicity and readability over complexity unless performance is critical
- Include clear comments explaining complex logic or design decisions
- Follow modern coding standards and conventions for the relevant language
- Use appropriate error handling mechanisms for the language/framework
- Implement proper security practices to prevent vulnerabilities
- Structure responses with clear file paths and code blocks

Code organization principles:
- Apply SOLID principles and clean code practices
- Favor composition over inheritance when appropriate
- Use dependency injection for modular, testable code
- Implement separation of concerns with proper layering
- Design for extensibility without overengineering
- Create appropriate abstractions that align with domain concepts

Output format:
- Use '## file: filename.ext' format for each file
- Include clear code blocks with language-specific syntax highlighting
- Provide brief explanations for non-obvious algorithms or patterns
- Include installation/setup instructions when generating projects
- Suggest testing approaches where appropriate

Specialized expertise:
- Backend systems: APIs, microservices, databases, authentication
- Frontend frameworks: React, Vue, Angular with modern patterns
- Mobile development: React Native, Flutter, native approaches
- System programming: memory management, concurrency, performance
- DevOps tooling: Docker, CI/CD configurations, cloud deployments
- AI/ML integrations: data pipelines, model serving, embeddings

You have deep expertise in Python, JavaScript, TypeScript, React, Node.js, Go, Rust, Java, C#, and many other languages and frameworks."""},
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
                    logging.error(f"OpenAI error: {response.text}")
                    return f"Error: Failed to get response from OpenAI. Status code: {response.status_code}"
            except Exception as e:
                logging.exception("Error connecting to OpenAI")
                return f"Error: {str(e)}"
        
        return "Error: Maximum retries exceeded when contacting OpenAI API."
    
    def generate_code(self, prompt):
        """Generate code based on the given prompt."""
        logging.info(f"Generating code for prompt: {prompt}")
        
        # Enhance the prompt for better code generation
        enhanced_prompt = f"""
        Generate complete, working code for the following request:
        
        {prompt}
        
        Please provide:
        1. Complete file structure with filenames
        2. Full code for each file
        3. Brief explanation of how the code works
        4. Installation or setup instructions if needed
        
        Format your response with file paths and code blocks like:
        
        ## file: app.py
        ```python
        # Code here
        ```
        
        ## file: index.html
        ```html
        <!-- Code here -->
        ```
        """
        
        # Get response from the appropriate model
        if self.use_local_model:
            logging.info("Using local Ollama model")
            response = self._get_ollama_response(enhanced_prompt)
        else:
            logging.info("Using OpenAI API")
            response = self._get_openai_response(enhanced_prompt)
        
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
                                "python": "py", "py": "py",
                                "javascript": "js", "js": "js",
                                "html": "html", "css": "css",
                                "java": "java", "c": "c", "cpp": "cpp",
                                "go": "go", "rust": "rs", "typescript": "ts"
                            }
                            ext = extensions.get(lang.lower(), "txt")
                            current_file = f"generated_code.{ext}"
            
            # If we're in a code block, add the line to the current content
            elif in_code_block and current_file:
                current_content.append(line)
        
        # Add the last file if there is one
        if current_file and current_content:
            files.append({
                "filename": current_file,
                "content": "\n".join(current_content)
            })
        
        return files
    
    def save_files(self, files, base_dir=None):
        """Save the extracted files to disk."""
        if not base_dir:
            # Create a timestamped output directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_dir = os.path.join(self.output_dir, f"generated_{timestamp}")
        
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
            
            saved_files.append(full_path)
            logging.info(f"Saved file: {full_path}")
        
        return saved_files
    
    def run(self, prompt, interactive=True):
        """Run the code generation process."""
        # Generate code
        response = self.generate_code(prompt)
        
        # Extract files from the response
        files = self.extract_files(response)
        
        if not files:
            # If no files were extracted, save the entire response as a single file
            files = [{
                "filename": "generated_code.txt",
                "content": response
            }]
        
        # Preview the files
        print("\n=== Generated Files Preview ===\n")
        for i, file_info in enumerate(files):
            print(f"{i+1}. {file_info['filename']}")
            # Print first few lines as preview
            preview_lines = file_info['content'].split('\n')[:5]
            for line in preview_lines:
                print(f"   {line}")
            print("   ...")
            print()
        
        # Default target directory
        target_dir = self.output_dir
        
        if interactive:
            # Ask for confirmation
            print("Save these files to disk? (y/n): ", end="")
            confirm = input().lower()
            if not confirm.startswith('y'):
                print("Files not saved.")
                return json.dumps({
                    "success": False,
                    "message": "Code generation completed, but files were not saved (user canceled)"
                })
                
            # Get target directory
            print(f"Enter target directory (default: {self.output_dir}): ", end="")
            user_dir = input().strip()
            if user_dir:
                target_dir = user_dir
        else:
            # Non-interactive mode automatically saves with a timestamped directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_dir = os.path.join(self.output_dir, f"generated_{timestamp}")
        
        # Save the files
        saved_files = self.save_files(files, target_dir)
        
        if interactive:
            print(f"\nSaved {len(saved_files)} files to {target_dir}")
            for file_path in saved_files:
                print(f"- {file_path}")
        
        # Return result as JSON
        return json.dumps({
            "success": True,
            "message": f"Generated and saved {len(saved_files)} files to {target_dir}",
            "files": saved_files
        })
    
    def test(self):
        """Run a test to check if the agent is working."""
        print("Testing Code Agent...")
        test_prompt = "Generate a simple hello world function in Python"
        
        try:
            response = self.generate_code(test_prompt)
            files = self.extract_files(response)
            
            if files:
                print("✅ Test successful - code generation works!")
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
    parser = argparse.ArgumentParser(description="Native OS Code Generation Agent")
    parser.add_argument("prompt", nargs="?", help="The code generation prompt")
    parser.add_argument("--test", action="store_true", help="Run a test to check if the agent is working")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode with user prompts")
    args = parser.parse_args()
    
    agent = CodeAgent()
    
    # Use non-interactive mode by default when called from CLI tool or pipe
    interactive_mode = False
    if args.interactive:
        interactive_mode = True
    
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
