/**
 * Kattappa AI System n8n Workflow Automation Integration
 * Multi-agent AI workflow automation and orchestration
 */

const express = require('express');
const axios = require('axios');
const cron = require('node-cron');
const winston = require('winston');
require('dotenv').config();

// Configure logging
const logger = winston.createLogger({
  level: 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [
    new winston.transports.File({ filename: 'logs/ai-workflows.log' }),
    new winston.transports.Console()
  ]
});

const app = express();
app.use(express.json());

// AI System API endpoints
const AI_API_BASE = process.env.AI_API_URL || 'http://localhost:3004/api';
const N8N_WEBHOOK_URL = process.env.N8N_WEBHOOK_URL || 'http://localhost:5678/webhook';

/**
 * AI Workflow Triggers
 */
class AIWorkflows {

  // Multi-agent task orchestration
  static async orchestrateAgents(task, agents) {
    try {
      logger.info(`Orchestrating agents for task: ${task.type}`, { agents, task });

      // Trigger n8n multi-agent workflow
      const response = await axios.post(`${N8N_WEBHOOK_URL}/agent-orchestration`, {
        task: task,
        agents: agents,
        workflow: 'collaborative_problem_solving',
        timestamp: new Date().toISOString()
      });

      logger.info('Agent orchestration workflow triggered:', response.data);
      return response.data;
    } catch (error) {
      logger.error('Agent orchestration workflow failed:', error);
      throw error;
    }
  }

  // Automated AI tool selection
  static async selectTools(requirements) {
    try {
      logger.info(`Selecting AI tools for requirements:`, requirements);

      // Trigger tool selection workflow
      const response = await axios.post(`${N8N_WEBHOOK_URL}/tool-selection`, {
        requirements: requirements,
        availableTools: await this.getAvailableTools(),
        optimization: 'efficiency',
        timestamp: new Date().toISOString()
      });

      logger.info('Tool selection workflow triggered:', response.data);
      return response.data;
    } catch (error) {
      logger.error('Tool selection workflow failed:', error);
      throw error;
    }
  }

  // AI conversation automation
  static async automateConversation(conversationConfig) {
    try {
      logger.info(`Starting automated conversation:`, conversationConfig);

      // Trigger conversation workflow
      const response = await axios.post(`${N8N_WEBHOOK_URL}/conversation-automation`, {
        config: conversationConfig,
        agents: conversationConfig.agents,
        topic: conversationConfig.topic,
        duration: conversationConfig.duration,
        timestamp: new Date().toISOString()
      });

      logger.info('Conversation automation workflow triggered:', response.data);
      return response.data;
    } catch (error) {
      logger.error('Conversation automation workflow failed:', error);
      throw error;
    }
  }

  // AI learning and adaptation
  static async triggerLearning(learningData) {
    try {
      logger.info(`Triggering AI learning for:`, learningData.type);

      // Trigger learning workflow
      const response = await axios.post(`${N8N_WEBHOOK_URL}/ai-learning`, {
        data: learningData,
        learningType: learningData.type,
        agents: learningData.agents,
        timestamp: new Date().toISOString()
      });

      logger.info('AI learning workflow triggered:', response.data);
      return response.data;
    } catch (error) {
      logger.error('AI learning workflow failed:', error);
      throw error;
    }
  }

  // Performance monitoring
  static async monitorPerformance() {
    try {
      logger.info('Starting AI performance monitoring');

      // Get performance metrics
      const response = await axios.get(`${AI_API_BASE}/agents/performance`);
      const metrics = response.data;

      // Trigger performance analysis workflow
      const analysisResponse = await axios.post(`${N8N_WEBHOOK_URL}/performance-analysis`, {
        metrics: metrics,
        analysisType: 'comprehensive',
        recommendations: true,
        timestamp: new Date().toISOString()
      });

      logger.info('Performance monitoring workflow triggered:', analysisResponse.data);
      return analysisResponse.data;
    } catch (error) {
      logger.error('Performance monitoring workflow failed:', error);
      throw error;
    }
  }

  // Helper methods
  static async getAvailableTools() {
    try {
      const response = await axios.get(`${AI_API_BASE}/tools/available`);
      return response.data;
    } catch (error) {
      logger.error('Failed to get available tools:', error);
      return [];
    }
  }

  static async getAgentStatus(agentId) {
    try {
      const response = await axios.get(`${AI_API_BASE}/agents/${agentId}/status`);
      return response.data;
    } catch (error) {
      logger.error(`Failed to get agent status for ${agentId}:`, error);
      return null;
    }
  }
}

/**
 * API Routes for AI Workflows
 */

// Webhook endpoint for n8n AI workflows
app.post('/webhook/:workflow', async (req, res) => {
  const { workflow } = req.params;
  const data = req.body;

  try {
    logger.info(`Received AI workflow webhook: ${workflow}`, data);

    switch (workflow) {
      case 'task-completed':
        await handleTaskCompleted(data);
        break;

      case 'agent-failure':
        await handleAgentFailure(data);
        break;

      case 'learning-complete':
        await handleLearningComplete(data);
        break;

      case 'performance-alert':
        await handlePerformanceAlert(data);
        break;

      default:
        logger.warn(`Unknown AI workflow: ${workflow}`);
    }

    res.json({ success: true, message: 'AI webhook processed' });
  } catch (error) {
    logger.error(`AI webhook processing failed for ${workflow}:`, error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Agent orchestration
app.post('/orchestrate-agents', async (req, res) => {
  const { task, agents } = req.body;

  try {
    const result = await AIWorkflows.orchestrateAgents(task, agents);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Tool selection
app.post('/select-tools', async (req, res) => {
  const { requirements } = req.body;

  try {
    const result = await AIWorkflows.selectTools(requirements);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Conversation automation
app.post('/automate-conversation', async (req, res) => {
  const { conversationConfig } = req.body;

  try {
    const result = await AIWorkflows.automateConversation(conversationConfig);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Trigger learning
app.post('/trigger-learning', async (req, res) => {
  const { learningData } = req.body;

  try {
    const result = await AIWorkflows.triggerLearning(learningData);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Performance monitoring
app.post('/monitor-performance', async (req, res) => {
  try {
    const result = await AIWorkflows.monitorPerformance();
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * AI Workflow Handlers
 */
async function handleTaskCompleted(data) {
  logger.info('Task completed:', data.task);

  // Update task tracking
  await updateTaskStatus(data.task.id, 'completed');

  // Trigger next steps if needed
  if (data.nextTask) {
    await AIWorkflows.orchestrateAgents(data.nextTask, data.agents);
  }

  // Notify stakeholders
  await notifyTaskCompletion(data.task);
}

async function handleAgentFailure(data) {
  logger.error('Agent failure:', data.agent);

  // Attempt agent recovery
  await attemptAgentRecovery(data.agent);

  // Reassign tasks if necessary
  if (data.reassignTasks) {
    await reassignAgentTasks(data.agent.id, data.agents);
  }

  // Log failure for learning
  await AIWorkflows.triggerLearning({
    type: 'failure_analysis',
    agent: data.agent,
    context: data.context,
    timestamp: new Date().toISOString()
  });
}

async function handleLearningComplete(data) {
  logger.info('Learning completed:', data.learning);

  // Apply learned improvements
  await applyLearnedImprovements(data.learning);

  // Update agent configurations
  await updateAgentConfigurations(data.learning.agentUpdates);

  // Validate improvements
  await validateAgentImprovements(data.learning);
}

async function handlePerformanceAlert(data) {
  logger.warn('Performance alert:', data.alert);

  // Trigger performance optimization
  await optimizeAgentPerformance(data.alert.agentId);

  // Scale resources if needed
  if (data.alert.action === 'scale') {
    await scaleAgentResources(data.alert.agentId, data.alert.direction);
  }

  // Notify system administrator
  await notifyPerformanceIssue(data.alert);
}

async function updateTaskStatus(taskId, status) {
  logger.info(`Updating task ${taskId} to ${status}`);
}

async function notifyTaskCompletion(task) {
  logger.info(`Notifying task completion: ${task.id}`);

  // Integration options:
  // - Email notifications
  // - Slack messages
  // - Dashboard updates
  // - Mobile push notifications
}

async function attemptAgentRecovery(agent) {
  logger.info(`Attempting recovery for agent: ${agent.id}`);

  // Recovery strategies:
  // - Restart agent
  // - Clear cache
  // - Reset configuration
  // - Load backup state
}

async function reassignAgentTasks(failedAgentId, availableAgents) {
  logger.info(`Reassigning tasks from agent ${failedAgentId}`);
}

async function applyLearnedImprovements(learning) {
  logger.info('Applying learned improvements:', learning.type);
}

async function updateAgentConfigurations(agentUpdates) {
  logger.info('Updating agent configurations:', Object.keys(agentUpdates));
}

async function validateAgentImprovements(learning) {
  logger.info('Validating agent improvements for:', learning.type);
}

async function optimizeAgentPerformance(agentId) {
  logger.info(`Optimizing performance for agent: ${agentId}`);
}

async function scaleAgentResources(agentId, direction) {
  logger.info(`Scaling ${direction} resources for agent: ${agentId}`);
}

async function notifyPerformanceIssue(alert) {
  logger.warn('Notifying performance issue:', alert);
}

/**
 * Scheduled AI Tasks
 */

// Agent health monitoring (every 2 minutes)
cron.schedule('*/2 * * * *', async () => {
  try {
    const response = await axios.get(`${AI_API_BASE}/agents/status`);
    const agents = response.data;

    for (const agent of agents) {
      if (agent.status !== 'healthy') {
        await AIWorkflows.triggerLearning({
          type: 'health_issue',
          agent: agent,
          timestamp: new Date().toISOString()
        });
      }
    }
  } catch (error) {
    logger.error('Agent health monitoring failed:', error);
  }
});

// Performance optimization (every 30 minutes)
cron.schedule('*/30 * * * *', async () => {
  try {
    await AIWorkflows.monitorPerformance();
  } catch (error) {
    logger.error('Scheduled performance monitoring failed:', error);
  }
});

// Learning and adaptation (every 4 hours)
cron.schedule('0 */4 * * *', async () => {
  try {
    logger.info('Starting scheduled AI learning cycle');

    // Collect learning data
    const response = await axios.get(`${AI_API_BASE}/learning/data`);
    const learningData = response.data;

    // Trigger learning workflows
    for (const data of learningData) {
      await AIWorkflows.triggerLearning(data);
    }

    logger.info('Scheduled AI learning cycle completed');
  } catch (error) {
    logger.error('Scheduled AI learning failed:', error);
  }
});

// Daily agent optimization (at 2 AM)
cron.schedule('0 2 * * *', async () => {
  try {
    logger.info('Starting daily agent optimization');

    const response = await axios.post(`${N8N_WEBHOOK_URL}/daily-optimization`, {
      optimizationType: 'comprehensive',
      agents: 'all',
      timestamp: new Date().toISOString()
    });

    logger.info('Daily optimization workflow triggered:', response.data);
  } catch (error) {
    logger.error('Daily agent optimization failed:', error);
  }
});

/**
 * Health Check
 */
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'Kattappa AI System n8n Integration',
    timestamp: new Date().toISOString(),
    uptime: process.uptime()
  });
});

/**
 * Start Server
 */
const PORT = process.env.PORT || 3005;
app.listen(PORT, () => {
  logger.info(`Kattappa AI System n8n Integration running on port ${PORT}`);
  logger.info('Available endpoints:');
  logger.info('- POST /webhook/:workflow - n8n webhook receiver');
  logger.info('- POST /orchestrate-agents - multi-agent orchestration');
  logger.info('- POST /select-tools - AI tool selection');
  logger.info('- POST /automate-conversation - conversation automation');
  logger.info('- POST /trigger-learning - AI learning trigger');
  logger.info('- POST /monitor-performance - performance monitoring');
  logger.info('- GET /health - health check');
});

module.exports = {
  AIWorkflows,
  app
};
