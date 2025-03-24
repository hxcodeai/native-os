// main.ts - Tauri application entry point for Native OS
// Copyright (c) 2025 hxcode ai
// Released under MIT License

import { invoke } from '@tauri-apps/api/tauri';
import { appWindow } from '@tauri-apps/api/window';
import { exit } from '@tauri-apps/api/process';
import { open } from '@tauri-apps/api/dialog';
import { readTextFile } from '@tauri-apps/api/fs';

// Configure window behavior
appWindow.onCloseRequested(async (event) => {
  // Prevent default close behavior
  event.preventDefault();
  
  // Ask for confirmation before closing
  const shouldClose = await invoke('confirm_close');
  if (shouldClose) {
    await exit(0);
  }
});

// Native OS communication functions
async function runDevCTLCommand(command: string) {
  try {
    // Use invoke to call Rust backend
    const result = await invoke('run_devctl_command', { command });
    return result;
  } catch (error) {
    console.error('Error executing command:', error);
    return {
      success: false,
      error: String(error)
    };
  }
}

// System info functions
async function getSystemInfo() {
  try {
    const sysInfo = await invoke('get_system_info');
    return sysInfo;
  } catch (error) {
    console.error('Error getting system info:', error);
    return {
      cpu: 'Unknown',
      memory: 'Unknown',
      os: 'Unknown'
    };
  }
}

// File explorer functions
async function openFileExplorer() {
  try {
    const selected = await open({
      multiple: false,
      directory: false,
      filters: [{
        name: 'All Files',
        extensions: ['*']
      }]
    });
    
    if (selected && !Array.isArray(selected)) {
      const content = await readTextFile(selected);
      return {
        path: selected,
        content
      };
    }
    return null;
  } catch (error) {
    console.error('Error opening file explorer:', error);
    return null;
  }
}

// Export functions for React frontend
window.nativeOS = {
  runDevCTLCommand,
  getSystemInfo,
  openFileExplorer
};

// Handle initialization
document.addEventListener('DOMContentLoaded', () => {
  console.log('Native OS UI initialized');
});
