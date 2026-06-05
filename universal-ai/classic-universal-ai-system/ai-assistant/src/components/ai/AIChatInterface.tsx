import React, { useState, useEffect, useRef } from 'react';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  agent?: string;
  tools?: string[];
  status?: 'sending' | 'delivered' | 'processing' | 'completed' | 'failed';
}

interface Agent {
  id: string;
  name: string;
  type: 'general' | 'specialist' | 'coordinator';
  status: 'online' | 'offline' | 'busy';
  capabilities: string[];
}

interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  agents: Agent[];
  createdAt: string;
  lastActivity: string;
}

export function AIChatInterface() {
  const [sessions, setSessions] = useState<ChatSession[]>([
    {
      id: 'session-1',
      title: 'General Conversation',
      messages: [
        {
          id: 'msg-1',
          role: 'user',
          content: 'Hello, can you help me with a coding problem?',
          timestamp: '2024-12-10T10:00:00Z',
          status: 'delivered'
        },
        {
          id: 'msg-2',
          role: 'assistant',
          content: 'I\'d be happy to help you with your coding problem! What specific issue are you facing?',
          timestamp: '2024-12-10T10:00:30Z',
          agent: 'General Assistant',
          status: 'delivered'
        }
      ],
      agents: [
        {
          id: 'agent-1',
          name: 'General Assistant',
          type: 'general',
          status: 'online',
          capabilities: ['coding', 'analysis', 'troubleshooting']
        }
      ],
      createdAt: '2024-12-10T10:00:00Z',
      lastActivity: '2024-12-10T10:00:30Z'
    }
  ]);

  const [currentSession, setCurrentSession] = useState<string>('session-1');
  const [inputMessage, setInputMessage] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string>('agent-1');
  const [showAgentPanel, setShowAgentPanel] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const currentSessionData = sessions.find(s => s.id === currentSession);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [currentSessionData?.messages]);

  const sendMessage = async () => {
    if (!inputMessage.trim() || !currentSessionData) return;

    const messageText = inputMessage.trim();
    const agent = currentSessionData.agents.find(a => a.id === selectedAgent);

    const newMessage: Message = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: messageText,
      timestamp: new Date().toISOString(),
      status: 'sending'
    };

    setSessions(prev => prev.map(session =>
      session.id === currentSession
        ? {
            ...session,
            messages: [...session.messages, newMessage],
            lastActivity: new Date().toISOString()
          }
        : session
    ));

    setInputMessage('');
    setIsTyping(true);

    const ensureDelivered = () => {
      setSessions(prev => prev.map(session =>
        session.id === currentSession
          ? {
              ...session,
              messages: session.messages.map(msg =>
                msg.id === newMessage.id
                  ? { ...msg, status: 'delivered' as const }
                  : msg
              )
            }
          : session
      ));
    };

    ensureDelivered();

    try {
      let content = ''
      let status: Message['status'] = 'delivered'
      let tools: string[] = []

      if (window.electronAPI?.sendAIMessage) {
        const result = await window.electronAPI.sendAIMessage(messageText)
        content = result.success
          ? result.message
          : result.message || `Unable to reach local backend: ${result.error || 'unknown error'}`
        status = result.success ? 'delivered' : 'failed'
        tools = result.success ? ['universal-ai'] : ['error-handler']
      } else {
        content = `This desktop interface is ready. Run the Electron app to connect to the local AI backend, or open chat in demo mode.`
        tools = ['demo-mode']
      }

      const aiResponse: Message = {
        id: `msg-${Date.now() + 1}`,
        role: 'assistant',
        content,
        timestamp: new Date().toISOString(),
        agent: agent?.name || 'AI Assistant',
        tools,
        status
      }

      setSessions(prev => prev.map(session =>
        session.id === currentSession
          ? {
              ...session,
              messages: [...session.messages, aiResponse],
              lastActivity: new Date().toISOString()
            }
          : session
      ));
    } catch (error) {
      const aiResponse: Message = {
        id: `msg-${Date.now() + 1}`,
        role: 'assistant',
        content: `There was an error calling the local AI backend: ${error instanceof Error ? error.message : String(error)}`,
        timestamp: new Date().toISOString(),
        agent: agent?.name || 'AI Assistant',
        status: 'failed'
      }

      setSessions(prev => prev.map(session =>
        session.id === currentSession
          ? {
              ...session,
              messages: [...session.messages, aiResponse],
              lastActivity: new Date().toISOString()
            }
          : session
      ));
    } finally {
      setIsTyping(false)
    }
  };

  const createNewSession = () => {
    const newSession: ChatSession = {
      id: `session-${Date.now()}`,
      title: `New Chat ${sessions.length + 1}`,
      messages: [],
      agents: [
        {
          id: 'agent-1',
          name: 'General Assistant',
          type: 'general',
          status: 'online',
          capabilities: ['coding', 'analysis', 'troubleshooting']
        }
      ],
      createdAt: new Date().toISOString(),
      lastActivity: new Date().toISOString()
    };

    setSessions(prev => [newSession, ...prev]);
    setCurrentSession(newSession.id);
  };

  const addAgentToSession = (agentId: string) => {
    if (!currentSessionData) return;

    const newAgent: Agent = {
      id: agentId,
      name: `Specialist Agent ${agentId}`,
      type: 'specialist',
      status: 'online',
      capabilities: ['advanced-analysis', 'domain-expertise']
    };

    setSessions(prev => prev.map(session =>
      session.id === currentSession
        ? { ...session, agents: [...session.agents, newAgent] }
        : session
    ));
  };

  const getMessageStyle = (role: Message['role']) => {
    switch (role) {
      case 'user':
        return 'bg-primary text-primary-foreground ml-auto max-w-[70%]';
      case 'assistant':
        return 'bg-muted max-w-[70%]';
      case 'system':
        return 'bg-yellow-100 text-yellow-800 max-w-[70%]';
      default:
        return 'bg-muted max-w-[70%]';
    }
  };

  const getStatusIcon = (status: Message['status']) => {
    switch (status) {
      case 'sending': return '⏳';
      case 'delivered': return '✓';
      case 'processing': return '🔄';
      case 'completed': return '✅';
      case 'failed': return '❌';
      default: return '';
    }
  };

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <div className="w-80 border-r bg-card">
        <div className="p-4 border-b">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Chat Sessions</h2>
            <button
              onClick={createNewSession}
              className="px-3 py-1 bg-primary text-primary-foreground rounded-md text-sm"
            >
              New Chat
            </button>
          </div>

          {/* Agent Selection */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Active Agent:</label>
            <select
              value={selectedAgent}
              onChange={(e) => setSelectedAgent(e.target.value)}
              aria-label="Active assistant selection"
              className="w-full p-2 border rounded-md text-sm"
            >
              {currentSessionData?.agents.map(agent => (
                <option key={agent.id} value={agent.id}>
                  {agent.name} ({agent.type})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Session List */}
        <div className="overflow-y-auto h-[calc(100vh-200px)]">
          {sessions.map(session => (
            <div
              key={session.id}
              onClick={() => setCurrentSession(session.id)}
              className={`p-4 border-b cursor-pointer transition-colors ${
                currentSession === session.id ? 'bg-accent' : 'hover:bg-muted'
              }`}
            >
              <div className="font-medium text-sm">{session.title}</div>
              <div className="text-xs text-muted-foreground mt-1">
                {session.messages.length} messages
              </div>
              <div className="text-xs text-muted-foreground">
                {new Date(session.lastActivity).toLocaleTimeString()}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="p-4 border-b bg-card">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-semibold">{currentSessionData?.title}</h1>
              <div className="text-sm text-muted-foreground">
                {currentSessionData?.agents.length} agents active
              </div>
            </div>
            <button
              onClick={() => setShowAgentPanel(!showAgentPanel)}
              className="px-3 py-1 border rounded-md text-sm"
            >
              {showAgentPanel ? 'Hide' : 'Show'} Agents
            </button>
          </div>

          {/* Agent Panel */}
          {showAgentPanel && (
            <div className="mt-4 p-3 border rounded-md bg-muted">
              <h3 className="font-medium text-sm mb-2">Active Agents</h3>
              <div className="space-y-2">
                {currentSessionData?.agents.map(agent => (
                  <div key={agent.id} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${
                        agent.status === 'online' ? 'bg-green-500' :
                        agent.status === 'busy' ? 'bg-yellow-500' : 'bg-gray-500'
                      }`} />
                      <span>{agent.name}</span>
                      <span className="text-xs text-muted-foreground">({agent.type})</span>
                    </div>
                    <div className="flex gap-1">
                      {agent.capabilities.slice(0, 2).map(cap => (
                        <span key={cap} className="px-1 py-0.5 bg-background rounded text-xs">
                          {cap}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              <button
                onClick={() => addAgentToSession(`agent-${Date.now()}`)}
                className="mt-2 px-2 py-1 bg-primary text-primary-foreground rounded text-xs"
              >
                Add Specialist Agent
              </button>
            </div>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {currentSessionData?.messages.map(message => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`rounded-lg p-3 ${getMessageStyle(message.role)}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-sm">
                    {message.role === 'user' ? 'You' : message.agent || 'AI Assistant'}
                  </span>
                  {message.status && (
                    <span className="text-xs">{getStatusIcon(message.status)}</span>
                  )}
                </div>
                <div className="text-sm">{message.content}</div>
                {message.tools && message.tools.length > 0 && (
                  <div className="flex gap-1 mt-2">
                    {message.tools.map(tool => (
                      <span key={tool} className="px-1 py-0.5 bg-background rounded text-xs">
                        🔧 {tool}
                      </span>
                    ))}
                  </div>
                )}
                <div className="text-xs text-muted-foreground mt-1">
                  {new Date(message.timestamp).toLocaleTimeString()}
                </div>
              </div>
            </div>
          ))}

          {isTyping && (
            <div className="flex justify-start">
              <div className="bg-muted rounded-lg p-3 max-w-[70%]">
                <div className="flex items-center gap-2">
                  <div className="flex gap-1">
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce typing-dot" />
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce typing-dot delay-1" />
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce typing-dot delay-2" />
                  </div>
                  <span className="text-sm text-muted-foreground">AI is thinking...</span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="p-4 border-t bg-card">
          <div className="flex gap-2">
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
              placeholder="Type your message..."
              className="flex-1 p-2 border rounded-md"
              disabled={isTyping}
            />
            <button
              onClick={sendMessage}
              disabled={!inputMessage.trim() || isTyping}
              className="px-4 py-2 bg-primary text-primary-foreground rounded-md disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
