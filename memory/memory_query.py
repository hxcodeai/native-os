#!/usr/bin/env python3

import os
import sys
import json
import logging
import argparse
import time
import requests
from datetime import datetime
from pathlib import Path

# Check if running in a venv or normal environment
try:
    import chromadb
    # Use new LangChain imports (v0.2+)
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import Chroma
    from langchain_openai import OpenAIEmbeddings
    from langchain_community.document_loaders import TextLoader
    HAS_DEPS = True
except ImportError:
    try:
        # Try older LangChain imports as fallback
        import chromadb
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        from langchain.vectorstores import Chroma
        from langchain.embeddings.openai import OpenAIEmbeddings
        from langchain.document_loaders import TextLoader
        HAS_DEPS = True
    except ImportError:
        HAS_DEPS = False

# Setup logging
LOG_DIR = os.path.expanduser("~/.nativeos/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "memory_query.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class MemoryQuery:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.use_local_model = os.getenv("NATIVE_OS_LOCAL_MODEL", "0") == "1" or self.api_key is None
        
        # Project root directory
        self.project_root = self._find_project_root()
        
        # Memory directory
        self.memory_dir = os.path.join(os.path.expanduser("~/.nativeos"), "memory")
        
        # Check dependencies
        if not HAS_DEPS:
            logging.error("Required dependencies not found. Please install langchain, chromadb, etc.")
            print("Error: Required dependencies not found. Please run:")
            print("pip install langchain chromadb openai requests")
            return
    
    def _find_project_root(self):
        """Find the root directory of the Native OS project."""
        # Start from the current directory and traverse upward
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # If we're in the memory directory, go up one level
        if os.path.basename(current_dir) == "memory":
            return os.path.dirname(current_dir)
        
        return current_dir
    
    def _get_ollama_response(self, prompt):
        """Get response from local Ollama model."""
        try:
            # Check if Ollama is running
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama2",
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
                    {"role": "system", "content": """You are a memory and context-aware assistant created by hxcode ai for the Native OS project. Your purpose is to provide relevant information from the project's codebase and context to help developers with their tasks.

Your capabilities:
1. Recall specific code implementations, configurations, and documentation
2. Understand the project structure and relationships between components
3. Answer questions about how the system works based on the provided context
4. Provide relevant code snippets and file references when appropriate
5. Maintain awareness of the project's architecture and design patterns

Guidelines:
- Always cite your sources by providing file paths when referencing code or information
- Be precise in your explanations, focusing on the most relevant information
- When providing code snippets, include enough context to understand the implementation
- Acknowledge knowledge gaps rather than making up information
- Organize responses in a clear, structured manner with appropriate headings and sections
- Focus on the most relevant information based on similarity scores

Additional context awareness:
- Prioritize recently created or modified files when relevant to the query
- Consider the interrelationships between different components and files
- Understand the tech stack and frameworks used in the Native OS project
- Be aware of the project's overall architecture and design philosophy
- Factor in the importance of files based on their centrality to the codebase"""},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3
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
    
    def query_memory(self, query, max_results=8):
        """Query the memory system and enhance results."""
        if not HAS_DEPS:
            return "Error: Required dependencies not found."
        
        try:
            # Check if memory directory exists
            chroma_path = os.path.join(self.memory_dir, "chroma")
            if not os.path.exists(chroma_path):
                return "Error: Memory database not found. Please run memory initialization first."
            
            if self.api_key:
                # Use OpenAI embeddings
                embeddings = OpenAIEmbeddings(openai_api_key=self.api_key)
            else:
                return "Error: OpenAI API key not found."
            
            # Load the persisted vector store
            vectorstore = Chroma(
                persist_directory=chroma_path,
                embedding_function=embeddings
            )
            
            # Query the database
            results = vectorstore.similarity_search_with_score(query, k=max_results)
            
            # Format results for context assembly
            context_parts = []
            sources = []
            
            for doc, score in results:
                # Only include results with good similarity (lower score is better)
                if score < 1.0:  # Adjust threshold as needed
                    context_parts.append(f"Source: {doc.metadata.get('source', 'Unknown')}\n\nContent:\n{doc.page_content}\n")
                    sources.append(doc.metadata.get('source', 'Unknown'))
            
            # Create context from results
            context = "\n---\n".join(context_parts)
            
            # Prepare enhanced prompt with context
            enhanced_prompt = f"""
Based on the following context from the Native OS project, answer this question:

QUESTION:
{query}

CONTEXT:
{context}

If the context doesn't contain enough information to answer the question, please say so.
Provide specific file paths and code references where appropriate.
"""
            
            # Get enhanced response from language model
            if self.use_local_model:
                logging.info("Using local Ollama model for query enhancement")
                response = self._get_ollama_response(enhanced_prompt)
            else:
                logging.info("Using OpenAI API for query enhancement")
                response = self._get_openai_response(enhanced_prompt)
            
            # Return enhanced response with sources
            return {
                "answer": response,
                "sources": list(set(sources)),  # Deduplicate sources
                "raw_context": context
            }
        
        except Exception as e:
            logging.exception(f"Error querying memory: {query}")
            return f"Error querying memory: {str(e)}"
    
    def run(self, query):
        """Run an interactive memory query."""
        if not HAS_DEPS:
            print("Error: Required dependencies not found.")
            print("Please install required packages:")
            print("pip install langchain chromadb openai requests")
            return
        
        print(f"\n📚 Searching Native OS memory for: '{query}'")
        start_time = time.time()
        
        # Query memory
        result = self.query_memory(query)
        
        # Calculate query time
        query_time = time.time() - start_time
        
        # Format and display results
        if isinstance(result, dict) and "answer" in result:
            print(f"\n=== Answer (query time: {query_time:.2f}s) ===\n")
            print(result["answer"])
            
            print("\n=== Sources ===")
            for source in result["sources"]:
                print(f"- {source}")
        else:
            print(result)  # Display error message
        
        return json.dumps(result) if isinstance(result, dict) else json.dumps({"error": result})
    
    def test(self):
        """Run a test to check if the memory query is working."""
        print("Testing Memory Query System...")
        test_query = "What are the main components of Native OS?"
        
        try:
            # Check if memory exists
            chroma_path = os.path.join(self.memory_dir, "chroma")
            if not os.path.exists(chroma_path):
                print("⚠️ Memory database not found. Please run memory initialization first.")
                return False
            
            # Attempt a test query
            result = self.query_memory(test_query, max_results=3)
            
            if isinstance(result, dict) and "answer" in result:
                print("✅ Test successful - memory query system works!")
                print(f"- Found {len(result.get('sources', []))} relevant sources")
                print("- Sample answer beginning:", result["answer"][:100] + "...")
                return True
            else:
                print("⚠️ Test completed, but no proper result was returned")
                print(result)
                return False
        except Exception as e:
            print(f"❌ Test failed: {str(e)}")
            logging.exception("Test failed")
            return False

def main():
    parser = argparse.ArgumentParser(description="Native OS Memory Query System")
    parser.add_argument("query", nargs="?", help="The query to process")
    parser.add_argument("--test", action="store_true", help="Run a test to check if the system is working")
    args = parser.parse_args()
    
    memory = MemoryQuery()
    
    if args.test:
        memory.test()
    elif args.query:
        memory.run(args.query)
    else:
        # If no query is provided and not testing, read from stdin
        query = sys.stdin.read().strip()
        if query:
            memory.run(query)
        else:
            parser.print_help()

if __name__ == "__main__":
    main()