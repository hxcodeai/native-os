/*
 * Native OS - Tauri UI Application
 * Copyright (c) 2025 hxcode ai
 * Released under MIT License
 */

import React, { useState, useEffect, useRef } from 'react';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { 
  faCode, faCog, faServer, 
  faBook, faMemory, faRobot 
} from '@fortawesome/free-solid-svg-icons';

// Main Application
function App() {
  const [activePanel, setActivePanel] = useState('terminal');
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [systemInfo, setSystemInfo] = useState({ cpu: 'Loading...', memory: 'Loading...' });
  const [files, setFiles] = useState([]);
  
  const terminalRef = useRef(null);
  const terminalInstanceRef = useRef(null);
  
  // Initialize terminal
  useEffect(() => {
    if (terminalRef.current && !terminalInstanceRef.current) {
      const term = new Terminal({
        cursorBlink: true,
        theme: {
          background: '#1e1e1e',
          foreground: '#f0f0f0'
        }
      });
      
      const fitAddon = new FitAddon();
      term.loadAddon(fitAddon);
      term.open(terminalRef.current);
      fitAddon.fit();
      
      term.writeln('Native OS Terminal');
      term.writeln('Type commands to interact with the system');
      term.writeln('');
      
      // Store terminal instance
      terminalInstanceRef.current = term;
      
      // Handle window resize
      const handleResize = () => fitAddon.fit();
      window.addEventListener('resize', handleResize);
      
      return () => {
        window.removeEventListener('resize', handleResize);
        term.dispose();
      };
    }
  }, []);
  
  // Load system info periodically
  useEffect(() => {
    const loadSystemInfo = async () => {
      if (window.nativeOS) {
        try {
          const info = await window.nativeOS.getSystemInfo();
          setSystemInfo(info);
        } catch (error) {
          console.error('Failed to load system info:', error);
        }
      }
    };
    
    loadSystemInfo();
    const interval = setInterval(loadSystemInfo, 5000);
    
    return () => clearInterval(interval);
  }, []);
  
  // Handle chat submission
  const handleChatSubmit = async (e) => {
    e.preventDefault();
    
    if (!inputMessage.trim()) return;
    
    // Add user message
    const userMessage = {
      id: Date.now(),
      sender: 'user',
      content: inputMessage,
      timestamp: new Date().toISOString()
    };
    
    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    
    // Send to devctl
    if (window.nativeOS) {
      try {
        const response = await window.nativeOS.runDevCTLCommand(inputMessage);
        
        // Add response message
        const botMessage = {
          id: Date.now() + 1,
          sender: 'assistant',
          content: response.message || JSON.stringify(response),
          timestamp: new Date().toISOString()
        };
        
        setMessages(prev => [...prev, botMessage]);
        
        // Also output to terminal
        if (terminalInstanceRef.current) {
          terminalInstanceRef.current.writeln('\r\n> ' + inputMessage);
          terminalInstanceRef.current.writeln(botMessage.content);
        }
      } catch (error) {
        console.error('Error sending command:', error);
        
        // Add error message
        setMessages(prev => [...prev, {
          id: Date.now() + 1,
          sender: 'system',
          content: `Error: ${error.message || 'Unknown error'}`,
          timestamp: new Date().toISOString()
        }]);
      }
    }
  };
  
  // Render sidebar
  const renderSidebar = () => (
    <div className="sidebar">
      <div className="logo">
        <h2>Native OS</h2>
      </div>
      <nav>
        <button 
          className={activePanel === 'terminal' ? 'active' : ''} 
          onClick={() => setActivePanel('terminal')}
        >
          <FontAwesomeIcon icon={faCode} /> Terminal
        </button>
        <button 
          className={activePanel === 'chat' ? 'active' : ''} 
          onClick={() => setActivePanel('chat')}
        >
          <FontAwesomeIcon icon={faRobot} /> AI Chat
        </button>
        <button 
          className={activePanel === 'files' ? 'active' : ''} 
          onClick={() => setActivePanel('files')}
        >
          <FontAwesomeIcon icon={faMemory} /> Files
        </button>
        <button 
          className={activePanel === 'settings' ? 'active' : ''} 
          onClick={() => setActivePanel('settings')}
        >
          <FontAwesomeIcon icon={faCog} /> Settings
        </button>
      </nav>
      <div className="system-info">
        <div className="info-item">
          <label>CPU:</label>
          <span>{systemInfo.cpu}</span>
        </div>
        <div className="info-item">
          <label>Memory:</label>
          <span>{systemInfo.memory}</span>
        </div>
      </div>
    </div>
  );
  
  // Render active panel
  const renderPanel = () => {
    switch (activePanel) {
      case 'terminal':
        return <div className="terminal-container" ref={terminalRef} />;
      
      case 'chat':
        return (
          <div className="chat-container">
            <div className="messages">
              {messages.map(msg => (
                <div key={msg.id} className={`message ${msg.sender}`}>
                  <div className="content">{msg.content}</div>
                  <div className="timestamp">{new Date(msg.timestamp).toLocaleTimeString()}</div>
                </div>
              ))}
            </div>
            <form className="chat-input" onSubmit={handleChatSubmit}>
              <input
                type="text"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                placeholder="Ask Native OS..."
              />
              <button type="submit">Send</button>
            </form>
          </div>
        );
      
      case 'files':
        return (
          <div className="files-container">
            <div className="files-header">
              <h2>File Explorer</h2>
              <button onClick={async () => {
                if (window.nativeOS) {
                  const file = await window.nativeOS.openFileExplorer();
                  if (file) {
                    setFiles(prev => [...prev, file]);
                  }
                }
              }}>
                Open File
              </button>
            </div>
            <div className="files-list">
              {files.length === 0 ? (
                <div className="empty-state">No files opened yet</div>
              ) : (
                files.map((file, index) => (
                  <div key={index} className="file-item">
                    <div className="file-name">{file.path.split('/').pop()}</div>
                    <div className="file-path">{file.path}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        );
      
      case 'settings':
        return (
          <div className="settings-container">
            <h2>Settings</h2>
            <div className="settings-group">
              <h3>API Configuration</h3>
              <div className="setting-item">
                <label>OpenAI API Key:</label>
                <input type="password" placeholder="sk-..." />
                <button>Save</button>
              </div>
            </div>
            <div className="settings-group">
              <h3>UI Theme</h3>
              <div className="theme-options">
                <button className="theme-option active">Dark</button>
                <button className="theme-option">Light</button>
                <button className="theme-option">System</button>
              </div>
            </div>
          </div>
        );
      
      default:
        return <div>Unknown panel</div>;
    }
  };
  
  return (
    <div className="app">
      {renderSidebar()}
      <main className="main-content">
        {renderPanel()}
      </main>
    </div>
  );
}

export default App;
