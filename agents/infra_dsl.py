#!/usr/bin/env python3

import os
import sys
import json
import logging
import argparse
import requests
import re

# Setup logging
LOG_DIR = os.path.expanduser("~/.nativeos/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "infra-dsl.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class InfraDSL:
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
    
    def _get_system_prompt(self):
        """Get the standard system prompt for infra DSL parsing."""
        return """You are an expert infrastructure engineer that analyzes natural language requests and converts them into structured task objects.

Your task is to extract precise infrastructure information from natural language requests and create a JSON object with the relevant details.

For each request, identify:
1. Cloud provider (aws, azure, gcp, etc)
2. Resource type (ec2, vm, container, kubernetes, etc)
3. Region/location
4. Size/specs (memory, CPU, disk)
5. Any software to be installed
6. Network configuration
7. Security settings
8. Scaling requirements
9. Additional parameters specific to the request

Use the following schema:
{
  "provider": "cloud provider name",
  "resource": "resource type",
  "region": "region name",
  "size": {
    "cpu": "cpu count",
    "memory": "memory in GB",
    "disk": "disk size in GB"
  },
  "count": number of instances,
  "post_setup": ["software to install", "configuration to apply"],
  "network": {
    "public_ip": true/false,
    "vpc": "vpc name if specified",
    "subnet": "subnet details if specified"
  },
  "security": {
    "ssh_access": true/false,
    "open_ports": [list of ports to open]
  },
  "scaling": {
    "min": minimum count,
    "max": maximum count,
    "desired": desired count
  },
  "additional_params": {}
}

Only include fields for which you have information. Use null for unknown values that are expected in the schema. Omit optional fields if no information is provided.

Respond with a valid JSON object only, no additional explanation."""
    
    def _get_openai_response(self, prompt):
        """Get response from OpenAI API for DSL conversion."""
        try:
            headers = {
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2  # Low temperature for more deterministic outputs
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
                return None
        except Exception as e:
            logging.exception("Error connecting to OpenAI")
            return None
    
    def _get_claude_response(self, prompt):
        """Get response from Claude API for DSL conversion."""
        try:
            headers = {
                "x-api-key": f"{self.anthropic_api_key}",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
            
            # Create the system prompt and user message
            system_prompt = self._get_system_prompt()
            
            data = {
                "model": "claude-3-haiku-20240307",
                "max_tokens": 1000,
                "temperature": 0.2,
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
            else:
                logging.error(f"Claude error: {response.text}")
                return None
        except Exception as e:
            logging.exception("Error connecting to Claude API")
            return None
    
    def _get_ollama_response(self, prompt):
        """Get response from local Ollama model for DSL conversion."""
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "codellama",
                    "prompt": f"{self._get_system_prompt()}\n\nUser request: {prompt}\n\nJSON output:",
                    "stream": False
                }
            )
            
            if response.status_code == 200:
                return response.json().get("response", "")
            else:
                logging.error(f"Ollama error: {response.text}")
                return None
        except Exception as e:
            logging.exception("Error connecting to Ollama")
            return None
    
    def _clean_json_response(self, response):
        """Clean and extract valid JSON from a response."""
        if not response:
            return None
        
        # Try to find JSON object in the response
        json_match = re.search(r'({[\s\S]*})', response)
        if json_match:
            json_str = json_match.group(1)
            
            try:
                # Parse the JSON to validate it
                parsed_json = json.loads(json_str)
                return parsed_json
            except json.JSONDecodeError:
                logging.error(f"Invalid JSON: {json_str}")
                return None
        else:
            logging.error("No JSON found in response")
            return None
    
    def parse_request(self, prompt):
        """Parse a natural language infrastructure request into a structured object."""
        logging.info(f"Parsing infrastructure request: {prompt}")
        
        # Get response from the appropriate model
        response = None
        if self.use_local_model:
            logging.info("Using local Ollama model")
            response = self._get_ollama_response(prompt)
        else:
            # Choose AI provider based on default_provider setting and available API keys
            provider = self.default_provider
            
            if provider == "openai" and self.openai_api_key:
                logging.info("Using OpenAI API")
                response = self._get_openai_response(prompt)
            elif provider == "claude" and self.anthropic_api_key:
                logging.info("Using Claude API")
                response = self._get_claude_response(prompt)
            else:
                # Fallback to any available provider
                if self.openai_api_key:
                    logging.info("Falling back to OpenAI API")
                    response = self._get_openai_response(prompt)
                elif self.anthropic_api_key:
                    logging.info("Falling back to Claude API")
                    response = self._get_claude_response(prompt)
                else:
                    logging.error("No AI provider available")
                    return None
        
        # Clean and extract JSON from the response
        task_object = self._clean_json_response(response)
        
        return task_object
    
    def run(self, prompt):
        """Run the DSL parsing process and display the result."""
        task_object = self.parse_request(prompt)
        
        if task_object:
            print("\n✅ Successfully parsed infrastructure request")
            print("\nStructured Task Object:")
            print(json.dumps(task_object, indent=2))
            return task_object
        else:
            print("\n❌ Failed to parse infrastructure request")
            return None

def main():
    parser = argparse.ArgumentParser(description="Native OS Infrastructure DSL Parser")
    parser.add_argument("prompt", nargs="?", help="The infrastructure request prompt")
    args = parser.parse_args()
    
    if args.prompt:
        dsl = InfraDSL()
        dsl.run(args.prompt)
    else:
        print("Please provide a prompt.")
        print("Example: python3 infra_dsl.py 'Spin up a dev EC2 with 8GB RAM and Docker installed'")

if __name__ == "__main__":
    main()