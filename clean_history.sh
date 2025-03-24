#!/bin/bash

# This script cleans Replit references from Git commit history
# Run this in your local clone of the native-os repository

# Install git-filter-repo if not already installed
# Uncomment the appropriate line for your system

# For Ubuntu/Debian:
# sudo apt-get install git-filter-repo

# For macOS with Homebrew:
# brew install git-filter-repo

# For pip installation:
# pip install git-filter-repo

# Clean the commit messages
git filter-repo --commit-callback '
message = commit.message.decode("utf-8")
if "Replit" in message or "replit" in message:
    if "Remove Replit files and traces" in message:
        commit.message = b"Remove platform-specific files and traces"
    elif "Remove Replit-specific files and references" in message:
        commit.message = b"Remove platform-specific files and references"
    elif "Update Native OS Replit workflow" in message:
        commit.message = b"Update Native OS workflow and add agent testing"
    else:
        commit.message = commit.message.replace(b"Replit", b"platform").replace(b"replit", b"platform")
'

# Force push to GitHub
echo "Commit history has been cleaned. Run the following command to push:"
echo "git push -f origin main"