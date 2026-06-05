import React, { useState, useEffect } from 'react';

interface AITool {
  id: string;
  name: string;
  description: string;
  category: 'file' | 'system' | 'ai' | 'network' | 'development';
  enabled: boolean;
  permissions: {
    read: boolean;
    write: boolean;
    execute: boolean;
    network: boolean;
  };
  security: 'safe' | 'restricted' | 'dangerous';
  lastUsed?: string;
  usageCount: number;
}

interface ToolExecution {
  id: string;
  toolId: string;
  command: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: string;
  error?: string;
  timestamp: string;
  duration?: number;
}

export function AIToolSystem() {
  const [tools, setTools] = useState<AITool[]>([
    {
      id: 'bash-tool',
      name: 'Bash Tool',
      description: 'Execute system commands and scripts with security validation',
      category: 'system',
      enabled: true,
      permissions: { read: true, write: true, execute: true, network: false },
      security: 'restricted',
      lastUsed: '2 minutes ago',
      usageCount: 15
    },
    {
      id: 'file-read',
      name: 'File Reader',
      description: 'Read and analyze file contents with encoding detection',
      category: 'file',
      enabled: true,
      permissions: { read: true, write: false, execute: false, network: false },
      security: 'safe',
      lastUsed: '5 minutes ago',
      usageCount: 32
    },
    {
      id: 'file-edit',
      name: 'File Editor',
      description: 'Edit and modify files with backup and history tracking',
      category: 'file',
      enabled: true,
      permissions: { read: true, write: true, execute: false, network: false },
      security: 'restricted',
      lastUsed: '10 minutes ago',
      usageCount: 8
    },
    {
      id: 'web-search',
      name: 'Web Search',
      description: 'Search the web for information and resources',
      category: 'network',
      enabled: true,
      permissions: { read: true, write: false, execute: false, network: true },
      security: 'safe',
      lastUsed: '1 hour ago',
      usageCount: 5
    },
    {
      id: 'code-analyzer',
      name: 'Code Analyzer',
      description: 'Analyze code structure, dependencies, and patterns',
      category: 'development',
      enabled: true,
      permissions: { read: true, write: false, execute: false, network: false },
      security: 'safe',
      lastUsed: '30 minutes ago',
      usageCount: 12
    },
    {
      id: 'git-operations',
      name: 'Git Operations',
      description: 'Perform Git operations with safety checks',
      category: 'development',
      enabled: false,
      permissions: { read: true, write: true, execute: true, network: true },
      security: 'restricted',
      lastUsed: '2 days ago',
      usageCount: 3
    }
  ]);

  const [executions, setExecutions] = useState<ToolExecution[]>([
    {
      id: 'exec-1',
      toolId: 'bash-tool',
      command: 'ls -la',
      status: 'completed',
      result: 'total 42\ndrwxr-xr-x  12 user  staff   384 Dec 10 10:30 .',
      timestamp: '2024-12-10T10:30:00Z',
      duration: 150
    },
    {
      id: 'exec-2',
      toolId: 'file-read',
      command: 'read package.json',
      status: 'completed',
      result: '{"name": "ai-assistant", "version": "0.1.0"}',
      timestamp: '2024-12-10T10:25:00Z',
      duration: 80
    }
  ]);

  const [selectedTool, setSelectedTool] = useState<AITool | null>(null);
  const [commandInput, setCommandInput] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);

  const getSecurityColor = (security: AITool['security']) => {
    switch (security) {
      case 'safe': return 'bg-green-500';
      case 'restricted': return 'bg-yellow-500';
      case 'dangerous': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  const getCategoryIcon = (category: AITool['category']) => {
    switch (category) {
      case 'file': return '📄';
      case 'system': return '⚙️';
      case 'ai': return '🤖';
      case 'network': return '🌐';
      case 'development': return '💻';
      default: return '🔧';
    }
  };

  const toggleTool = (toolId: string) => {
    setTools(prev => prev.map(tool =>
      tool.id === toolId ? { ...tool, enabled: !tool.enabled } : tool
    ));
  };

  const executeTool = async (tool: AITool, command: string) => {
    if (!tool.enabled) return;

    setIsExecuting(true);
    const execution: ToolExecution = {
      id: `exec-${Date.now()}`,
      toolId: tool.id,
      command,
      status: 'running',
      timestamp: new Date().toISOString()
    };

    setExecutions(prev => [execution, ...prev]);

    // Simulate tool execution
    setTimeout(() => {
      setExecutions(prev => prev.map(exec =>
        exec.id === execution.id
          ? {
              ...exec,
              status: 'completed',
              result: `Executed: ${command}`,
              duration: Math.floor(Math.random() * 1000) + 100
            }
          : exec
      ));

      setTools(prev => prev.map(t =>
        t.id === tool.id
          ? { ...t, lastUsed: 'Just now', usageCount: t.usageCount + 1 }
          : t
      ));

      setIsExecuting(false);
    }, 2000);
  };

  const getExecutionStatusColor = (status: ToolExecution['status']) => {
    switch (status) {
      case 'completed': return 'text-green-600';
      case 'running': return 'text-blue-600';
      case 'failed': return 'text-red-600';
      case 'pending': return 'text-yellow-600';
      default: return 'text-gray-600';
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">AI Tool System</h2>
          <p className="text-muted-foreground">Advanced tool management and execution system</p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Tools Panel */}
        <div className="lg:col-span-2 space-y-4">
          <div className="rounded-lg border bg-card p-6">
            <h3 className="text-lg font-semibold mb-4">Available Tools</h3>
            <div className="grid gap-4 md:grid-cols-2">
              {tools.map((tool) => (
                <div
                  key={tool.id}
                  className={`rounded-lg border p-4 cursor-pointer transition-all ${
                    selectedTool?.id === tool.id ? 'ring-2 ring-primary' : ''
                  } ${!tool.enabled ? 'opacity-50' : ''}`}
                  onClick={() => setSelectedTool(tool)}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">{getCategoryIcon(tool.category)}</span>
                      <h4 className="font-medium">{tool.name}</h4>
                    </div>
                    <div className={`w-2 h-2 rounded-full ${getSecurityColor(tool.security)}`} />
                  </div>
                  <p className="text-sm text-muted-foreground mb-3">{tool.description}</p>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">
                      Used {tool.usageCount} times
                    </span>
                    <span className="text-muted-foreground">
                      {tool.lastUsed}
                    </span>
                  </div>
                  <div className="flex gap-2 mt-3">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleTool(tool.id);
                      }}
                      className={`px-2 py-1 text-xs rounded ${
                        tool.enabled
                          ? 'bg-green-100 text-green-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {tool.enabled ? 'Enabled' : 'Disabled'}
                    </button>
                    <span className={`px-2 py-1 text-xs rounded ${
                      tool.security === 'safe' ? 'bg-green-100 text-green-800' :
                      tool.security === 'restricted' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-red-100 text-red-800'
                    }`}>
                      {tool.security}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Tool Execution */}
          {selectedTool && (
            <div className="rounded-lg border bg-card p-6">
              <h3 className="text-lg font-semibold mb-4">
                Execute: {selectedTool.name}
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium mb-2 block">Command</label>
                  <textarea
                    value={commandInput}
                    onChange={(e) => setCommandInput(e.target.value)}
                    placeholder={`Enter command for ${selectedTool.name}...`}
                    className="w-full p-3 border rounded-md resize-none h-24"
                    disabled={!selectedTool.enabled}
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => executeTool(selectedTool, commandInput)}
                    disabled={!selectedTool.enabled || !commandInput.trim() || isExecuting}
                    className="px-4 py-2 bg-primary text-primary-foreground rounded-md disabled:opacity-50"
                  >
                    {isExecuting ? 'Executing...' : 'Execute'}
                  </button>
                  <button
                    onClick={() => setCommandInput('')}
                    className="px-4 py-2 border rounded-md"
                  >
                    Clear
                  </button>
                </div>

                {/* Permissions Display */}
                <div className="border-t pt-4">
                  <h4 className="font-medium mb-2">Permissions</h4>
                  <div className="flex gap-2">
                    {Object.entries(selectedTool.permissions).map(([key, value]) => (
                      <span
                        key={key}
                        className={`px-2 py-1 text-xs rounded ${
                          value ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        {key}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Execution History */}
        <div className="space-y-4">
          <div className="rounded-lg border bg-card p-6">
            <h3 className="text-lg font-semibold mb-4">Execution History</h3>
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {executions.map((execution) => {
                const tool = tools.find(t => t.id === execution.toolId);
                return (
                  <div key={execution.id} className="border rounded p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-sm">{tool?.name}</span>
                      <span className={`text-xs ${getExecutionStatusColor(execution.status)}`}>
                        {execution.status}
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground mb-1">
                      {execution.command}
                    </div>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>{new Date(execution.timestamp).toLocaleTimeString()}</span>
                      {execution.duration && (
                        <span>{execution.duration}ms</span>
                      )}
                    </div>
                    {execution.result && (
                      <div className="mt-2 p-2 bg-muted rounded text-xs font-mono">
                        {execution.result.substring(0, 100)}...
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* System Stats */}
          <div className="rounded-lg border bg-card p-6">
            <h3 className="text-lg font-semibold mb-4">System Statistics</h3>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-sm">Total Tools</span>
                <span className="font-medium">{tools.length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm">Enabled Tools</span>
                <span className="font-medium">{tools.filter(t => t.enabled).length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm">Total Executions</span>
                <span className="font-medium">{executions.length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm">Success Rate</span>
                <span className="font-medium">
                  {Math.round((executions.filter(e => e.status === 'completed').length / executions.length) * 100)}%
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
