import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Bot,
  Users,
  MessageSquare,
  Settings,
  Play,
  Pause,
  Square,
  Zap,
  Brain,
  Network
} from 'lucide-react';

interface Agent {
  id: string;
  name: string;
  type: 'coordinator' | 'worker' | 'specialist';
  status: 'active' | 'idle' | 'busy' | 'offline';
  capabilities: string[];
  tasks: number;
  lastActivity: string;
}

interface Tool {
  id: string;
  name: string;
  description: string;
  category: 'file' | 'system' | 'ai' | 'network';
  enabled: boolean;
  agent?: string;
}

export function AgentCoordinator() {
  const [agents, setAgents] = useState<Agent[]>([
    {
      id: 'coordinator-1',
      name: 'Main Coordinator',
      type: 'coordinator',
      status: 'active',
      capabilities: ['orchestration', 'task-distribution', 'monitoring'],
      tasks: 3,
      lastActivity: '2 minutes ago'
    },
    {
      id: 'worker-1',
      name: 'Code Assistant',
      type: 'worker',
      status: 'busy',
      capabilities: ['code-generation', 'debugging', 'analysis'],
      tasks: 2,
      lastActivity: '1 minute ago'
    },
    {
      id: 'specialist-1',
      name: 'Data Analyst',
      type: 'specialist',
      status: 'idle',
      capabilities: ['data-processing', 'analysis', 'visualization'],
      tasks: 0,
      lastActivity: '5 minutes ago'
    }
  ]);

  const [tools, setTools] = useState<Tool[]>([
    {
      id: 'bash-tool',
      name: 'Bash Tool',
      description: 'Execute system commands and scripts',
      category: 'system',
      enabled: true,
      agent: 'worker-1'
    },
    {
      id: 'file-read',
      name: 'File Reader',
      description: 'Read and analyze file contents',
      category: 'file',
      enabled: true,
      agent: 'coordinator-1'
    },
    {
      id: 'file-edit',
      name: 'File Editor',
      description: 'Edit and modify files',
      category: 'file',
      enabled: true
    },
    {
      id: 'web-search',
      name: 'Web Search',
      description: 'Search the web for information',
      category: 'network',
      enabled: true,
      agent: 'specialist-1'
    },
    {
      id: 'ai-chat',
      name: 'AI Chat',
      description: 'Interactive AI conversation',
      category: 'ai',
      enabled: true
    }
  ]);

  const [coordinatorMode, setCoordinatorMode] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  const getStatusColor = (status: Agent['status']) => {
    switch (status) {
      case 'active': return 'bg-green-500';
      case 'busy': return 'bg-yellow-500';
      case 'idle': return 'bg-blue-500';
      case 'offline': return 'bg-gray-500';
      default: return 'bg-gray-500';
    }
  };

  const getCategoryIcon = (category: Tool['category']) => {
    switch (category) {
      case 'file': return <Settings className="h-4 w-4" />;
      case 'system': return <Zap className="h-4 w-4" />;
      case 'ai': return <Brain className="h-4 w-4" />;
      case 'network': return <Network className="h-4 w-4" />;
      default: return <Settings className="h-4 w-4" />;
    }
  };

  const toggleCoordinatorMode = () => {
    setCoordinatorMode(!coordinatorMode);
  };

  const assignToolToAgent = (toolId: string, agentId: string) => {
    setTools(prev => prev.map(tool =>
      tool.id === toolId ? { ...tool, agent: agentId } : tool
    ));
  };

  const removeToolFromAgent = (toolId: string) => {
    setTools(prev => prev.map(tool =>
      tool.id === toolId ? { ...tool, agent: undefined } : tool
    ));
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Agent Coordinator</h2>
          <p className="text-muted-foreground">Manage and orchestrate AI agents and tools</p>
        </div>
        <Button
          onClick={toggleCoordinatorMode}
          variant={coordinatorMode ? "default" : "outline"}
          className="flex items-center gap-2"
        >
          <Users className="h-4 w-4" />
          {coordinatorMode ? "Coordinator Mode Active" : "Enable Coordinator"}
        </Button>
      </div>

      {coordinatorMode && (
        <Card className="border-green-200 bg-green-50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-green-800">
              <Users className="h-5 w-5" />
              Coordinator Mode Active
            </CardTitle>
            <CardDescription>
              Multi-agent orchestration is enabled. Agents can collaborate and share tools.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      <Tabs defaultValue="agents" className="space-y-4">
        <TabsList>
          <TabsTrigger value="agents">Agents</TabsTrigger>
          <TabsTrigger value="tools">Tools</TabsTrigger>
          <TabsTrigger value="orchestration">Orchestration</TabsTrigger>
        </TabsList>

        <TabsContent value="agents" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {agents.map((agent) => (
              <Card
                key={agent.id}
                className={`cursor-pointer transition-all ${
                  selectedAgent === agent.id ? 'ring-2 ring-primary' : ''
                }`}
                onClick={() => setSelectedAgent(agent.id)}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Bot className="h-5 w-5" />
                      <CardTitle className="text-sm">{agent.name}</CardTitle>
                    </div>
                    <div className={`w-2 h-2 rounded-full ${getStatusColor(agent.status)}`} />
                  </div>
                  <CardDescription className="text-xs">
                    {agent.type} • {agent.tasks} active tasks
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex flex-wrap gap-1">
                    {agent.capabilities.slice(0, 2).map((capability) => (
                      <Badge key={capability} variant="secondary" className="text-xs">
                        {capability}
                      </Badge>
                    ))}
                    {agent.capabilities.length > 2 && (
                      <Badge variant="outline" className="text-xs">
                        +{agent.capabilities.length - 2}
                      </Badge>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Last activity: {agent.lastActivity}
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" className="flex-1">
                      <Play className="h-3 w-3 mr-1" />
                      Start
                    </Button>
                    <Button size="sm" variant="outline" className="flex-1">
                      <Pause className="h-3 w-3 mr-1" />
                      Pause
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="tools" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {tools.map((tool) => (
              <Card key={tool.id} className="transition-all">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {getCategoryIcon(tool.category)}
                      <CardTitle className="text-sm">{tool.name}</CardTitle>
                    </div>
                    <div className={`w-2 h-2 rounded-full ${
                      tool.enabled ? 'bg-green-500' : 'bg-gray-400'
                    }`} />
                  </div>
                  <CardDescription className="text-xs">
                    {tool.description}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Badge variant="outline" className="text-xs">
                    {tool.category}
                  </Badge>
                  {tool.agent && (
                    <div className="text-xs text-muted-foreground">
                      Assigned to: {agents.find(a => a.id === tool.agent)?.name}
                    </div>
                  )}
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1"
                      onClick={() => tool.agent ? removeToolFromAgent(tool.id) :
                        selectedAgent && assignToolToAgent(tool.id, selectedAgent)}
                    >
                      {tool.agent ? 'Unassign' : 'Assign'}
                    </Button>
                    <Button
                      size="sm"
                      variant={tool.enabled ? "default" : "outline"}
                      className="flex-1"
                    >
                      {tool.enabled ? 'Enabled' : 'Disabled'}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="orchestration" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5" />
                Orchestration Settings
              </CardTitle>
              <CardDescription>
                Configure how agents collaborate and share resources
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <h4 className="font-medium">Task Distribution</h4>
                  <p className="text-sm text-muted-foreground">
                    Automatic task assignment based on agent capabilities
                  </p>
                  <Button variant="outline" size="sm">Configure</Button>
                </div>
                <div className="space-y-2">
                  <h4 className="font-medium">Resource Sharing</h4>
                  <p className="text-sm text-muted-foreground">
                    Allow agents to share tools and data
                  </p>
                  <Button variant="outline" size="sm">Configure</Button>
                </div>
                <div className="space-y-2">
                  <h4 className="font-medium">Communication</h4>
                  <p className="text-sm text-muted-foreground">
                    Inter-agent communication protocols
                  </p>
                  <Button variant="outline" size="sm">Configure</Button>
                </div>
                <div className="space-y-2">
                  <h4 className="font-medium">Monitoring</h4>
                  <p className="text-sm text-muted-foreground">
                    Track agent performance and coordination
                  </p>
                  <Button variant="outline" size="sm">Configure</Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
