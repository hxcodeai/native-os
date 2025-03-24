#!/usr/bin/env python3

import os
import sys
import json
import logging
import argparse
import glob
from datetime import datetime
from pathlib import Path

# Check if running in a venv or normal environment
try:
    import chromadb
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain.vectorstores import Chroma
    from langchain.embeddings import OpenAIEmbeddings
    from langchain.document_loaders import TextLoader
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

# Setup logging
LOG_DIR = os.path.expanduser("~/.nativeos/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "memory.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class MemoryInitializer:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        
        # Project root directory
        self.project_root = self._find_project_root()
        
        # Memory directory
        self.memory_dir = os.path.join(os.path.expanduser("~/.nativeos"), "memory")
        os.makedirs(self.memory_dir, exist_ok=True)
        
        # Check dependencies
        if not HAS_DEPS:
            logging.error("Required dependencies not found. Please install langchain, chromadb, etc.")
            print("Error: Required dependencies not found. Please run:")
            print("pip install langchain chromadb openai")
            return
    
    def _find_project_root(self):
        """Find the root directory of the Native OS project."""
        # Start from the current directory and traverse upward
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # If we're in the memory directory, go up one level
        if os.path.basename(current_dir) == "memory":
            return os.path.dirname(current_dir)
        
        return current_dir
    
    def scan_project_files(self):
        """Scan all project files for embedding."""
        project_files = []
        
        # File types to include
        file_extensions = [
            ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".sh",
            ".md", ".txt", ".json", ".yaml", ".yml", ".toml"
        ]
        
        # Directories to exclude
        exclude_dirs = [
            "node_modules", "venv", ".git", "__pycache__", "build", "dist",
            ".nativeos", "evolver/backups"
        ]
        
        logging.info(f"Scanning project files in {self.project_root}")
        
        # Collect files
        for ext in file_extensions:
            pattern = os.path.join(self.project_root, f"**/*{ext}")
            for file_path in glob.glob(pattern, recursive=True):
                # Check if file is in excluded directory
                if any(exclude_dir in file_path for exclude_dir in exclude_dirs):
                    continue
                
                # Ensure file is not too large (max 1MB)
                if os.path.getsize(file_path) > 1024 * 1024:
                    logging.info(f"Skipping large file: {file_path}")
                    continue
                
                project_files.append(file_path)
        
        logging.info(f"Found {len(project_files)} files to embed")
        return project_files
    
    def create_embeddings(self, files):
        """Create embeddings for the given files."""
        if not HAS_DEPS:
            return False
        
        logging.info("Creating embeddings...")
        
        try:
            if self.api_key:
                # Use OpenAI embeddings
                embeddings = OpenAIEmbeddings(openai_api_key=self.api_key)
            else:
                logging.error("No OpenAI API key found. Cannot create embeddings.")
                print("Error: OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")
                return False
            
            # Document loader and text splitter
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200
            )
            
            # Process each file
            documents = []
            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    # Create metadata
                    rel_path = os.path.relpath(file_path, self.project_root)
                    file_type = os.path.splitext(file_path)[1][1:]
                    
                    # Split text into chunks
                    chunks = text_splitter.split_text(content)
                    
                    # Add chunks to documents
                    for i, chunk in enumerate(chunks):
                        documents.append({
                            "content": chunk,
                            "metadata": {
                                "source": rel_path,
                                "file_type": file_type,
                                "chunk": i
                            }
                        })
                    
                    logging.info(f"Processed file: {rel_path}")
                except Exception as e:
                    logging.error(f"Error processing file {file_path}: {str(e)}")
            
            # Create vector store
            vectorstore = Chroma.from_documents(
                documents=[{"page_content": doc["content"], "metadata": doc["metadata"]} for doc in documents],
                embedding=embeddings,
                persist_directory=os.path.join(self.memory_dir, "chroma")
            )
            
            # Persist the database
            vectorstore.persist()
            
            logging.info(f"Created embeddings for {len(documents)} documents")
            return True
        
        except Exception as e:
            logging.exception("Error creating embeddings")
            print(f"Error creating embeddings: {str(e)}")
            return False
    
    def query_memory(self, query):
        """Query the memory system."""
        if not HAS_DEPS:
            return "Error: Required dependencies not found."
        
        try:
            if self.api_key:
                # Use OpenAI embeddings
                embeddings = OpenAIEmbeddings(openai_api_key=self.api_key)
            else:
                return "Error: OpenAI API key not found."
            
            # Load the persisted vector store
            vectorstore = Chroma(
                persist_directory=os.path.join(self.memory_dir, "chroma"),
                embedding_function=embeddings
            )
            
            # Query the database
            results = vectorstore.similarity_search(query, k=5)
            
            # Format results
            response = []
            for doc in results:
                response.append({
                    "content": doc.page_content,
                    "source": doc.metadata.get("source", "Unknown"),
                    "similarity": doc.metadata.get("score", 0)
                })
            
            return response
        
        except Exception as e:
            logging.exception(f"Error querying memory: {query}")
            return f"Error querying memory: {str(e)}"
    
    def run(self):
        """Run the memory initialization process."""
        print("=== Native OS Memory Initialization ===")
        
        if not HAS_DEPS:
            print("Error: Required dependencies not found.")
            print("Please install required packages:")
            print("pip install langchain chromadb openai")
            return False
        
        # Scan project files
        print("Scanning project files...")
        files = self.scan_project_files()
        
        if not files:
            print("No files found to embed.")
            return False
        
        print(f"Found {len(files)} files to process.")
        
        # Confirm before proceeding
        confirm = input("\nProceed with embedding creation? (y/n): ").lower()
        if not confirm.startswith('y'):
            print("Memory initialization cancelled.")
            return False
        
        # Create embeddings
        print("\nCreating embeddings... This may take a while.")
        success = self.create_embeddings(files)
        
        if success:
            print("\n✅ Memory initialization completed successfully!")
            print(f"Embeddings stored in: {self.memory_dir}")
            
            # Offer to test the memory system
            test = input("\nTest the memory system with a query? (y/n): ").lower()
            if test.startswith('y'):
                query = input("\nEnter your query: ")
                results = self.query_memory(query)
                
                print("\n=== Query Results ===")
                if isinstance(results, list):
                    for i, result in enumerate(results):
                        print(f"\n{i+1}. Source: {result['source']}")
                        print(f"Content: {result['content'][:200]}...")
                else:
                    print(results)
            
            return True
        else:
            print("\n❌ Memory initialization failed. Check the logs for details.")
            return False

def main():
    parser = argparse.ArgumentParser(description="Native OS Memory Initialization")
    parser.add_argument("--query", help="Query the memory system")
    args = parser.parse_args()
    
    memory = MemoryInitializer()
    
    if args.query:
        results = memory.query_memory(args.query)
        
        print("\n=== Query Results ===")
        if isinstance(results, list):
            for i, result in enumerate(results):
                print(f"\n{i+1}. Source: {result['source']}")
                print(f"Content: {result['content'][:200]}...")
        else:
            print(results)
    else:
        memory.run()

if __name__ == "__main__":
    main()
