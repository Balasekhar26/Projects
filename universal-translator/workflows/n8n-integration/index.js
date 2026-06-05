/**
 * ULT Translator n8n Workflow Automation Integration
 * Connects ULT Translator with n8n for automated translation workflows
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
    new winston.transports.File({ filename: 'logs/workflow.log' }),
    new winston.transports.Console()
  ]
});

const app = express();
app.use(express.json());

// ULT Translator API endpoints
const ULT_API_BASE = process.env.ULT_API_URL || 'http://localhost:3000/api';
const N8N_WEBHOOK_URL = process.env.N8N_WEBHOOK_URL || 'http://localhost:5678/webhook';

/**
 * Translation Workflow Triggers
 */
class TranslationWorkflows {
  
  // Auto-translate incoming files
  static async autoTranslateFiles(sourceDir, targetLanguages) {
    try {
      logger.info(`Starting auto-translation for directory: ${sourceDir}`);
      
      // Trigger n8n workflow
      const response = await axios.post(`${N8N_WEBHOOK_URL}/auto-translate`, {
        sourceDirectory: sourceDir,
        targetLanguages: targetLanguages,
        timestamp: new Date().toISOString()
      });
      
      logger.info('Auto-translate workflow triggered:', response.data);
      return response.data;
    } catch (error) {
      logger.error('Auto-translate workflow failed:', error);
      throw error;
    }
  }
  
  // Batch translation queue
  static async batchTranslationQueue(translations) {
    try {
      logger.info(`Processing batch translation queue: ${translations.length} items`);
      
      const response = await axios.post(`${N8N_WEBHOOK_URL}/batch-translate`, {
        translations: translations,
        timestamp: new Date().toISOString()
      });
      
      logger.info('Batch translation workflow triggered:', response.data);
      return response.data;
    } catch (error) {
      logger.error('Batch translation workflow failed:', error);
      throw error;
    }
  }
  
  // Real-time translation monitoring
  static async monitorTranslations() {
    try {
      const response = await axios.get(`${ULT_API_BASE}/translations/recent`);
      const recentTranslations = response.data;
      
      // Trigger workflow for new translations
      for (const translation of recentTranslations) {
        if (translation.status === 'completed') {
          await axios.post(`${N8N_WEBHOOK_URL}/translation-completed`, {
            translation: translation,
            timestamp: new Date().toISOString()
          });
        }
      }
      
      return recentTranslations;
    } catch (error) {
      logger.error('Translation monitoring failed:', error);
      throw error;
    }
  }
  
  // Translation quality assurance
  static async qualityCheck(translationId) {
    try {
      const response = await axios.get(`${ULT_API_BASE}/translations/${translationId}`);
      const translation = response.data;
      
      // Trigger QA workflow
      const qaResponse = await axios.post(`${N8N_WEBHOOK_URL}/quality-check`, {
        translation: translation,
        checks: ['grammar', 'accuracy', 'consistency'],
        timestamp: new Date().toISOString()
      });
      
      logger.info('Quality check workflow triggered:', qaResponse.data);
      return qaResponse.data;
    } catch (error) {
      logger.error('Quality check workflow failed:', error);
      throw error;
    }
  }
}

/**
 * API Routes for n8n Integration
 */

// Webhook endpoint for n8n workflows
app.post('/webhook/:workflow', async (req, res) => {
  const { workflow } = req.params;
  const data = req.body;
  
  try {
    logger.info(`Received webhook for workflow: ${workflow}`, data);
    
    switch (workflow) {
      case 'translation-completed':
        // Handle translation completion
        await handleTranslationCompleted(data);
        break;
        
      case 'quality-alert':
        // Handle quality issues
        await handleQualityAlert(data);
        break;
        
      case 'batch-ready':
        // Handle batch translation completion
        await handleBatchReady(data);
        break;
        
      default:
        logger.warn(`Unknown workflow: ${workflow}`);
    }
    
    res.json({ success: true, message: 'Webhook processed' });
  } catch (error) {
    logger.error(`Webhook processing failed for ${workflow}:`, error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Trigger auto-translation
app.post('/auto-translate', async (req, res) => {
  const { sourceDir, targetLanguages } = req.body;
  
  try {
    const result = await TranslationWorkflows.autoTranslateFiles(sourceDir, targetLanguages);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Batch translation
app.post('/batch-translate', async (req, res) => {
  const { translations } = req.body;
  
  try {
    const result = await TranslationWorkflows.batchTranslationQueue(translations);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Quality check
app.post('/quality-check/:translationId', async (req, res) => {
  const { translationId } = req.params;
  
  try {
    const result = await TranslationWorkflows.qualityCheck(translationId);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * Workflow Handlers
 */
async function handleTranslationCompleted(data) {
  logger.info('Translation completed:', data.translation);
  
  // Send notification
  if (data.translation.notify) {
    await sendNotification({
      type: 'translation_completed',
      translation: data.translation,
      timestamp: new Date().toISOString()
    });
  }
  
  // Update statistics
  await updateTranslationStats(data.translation);
}

async function handleQualityAlert(data) {
  logger.warn('Quality alert:', data);
  
  // Create quality improvement task
  await axios.post(`${N8N_WEBHOOK_URL}/improve-quality`, {
    alert: data,
    priority: 'high',
    timestamp: new Date().toISOString()
  });
}

async function handleBatchReady(data) {
  logger.info('Batch translation ready:', data);
  
  // Notify user
  await sendNotification({
    type: 'batch_completed',
    batchId: data.batchId,
    summary: data.summary,
    timestamp: new Date().toISOString()
  });
}

async function sendNotification(notification) {
  // Integration with notification systems
  logger.info('Sending notification:', notification);
  
  // Could integrate with:
  // - Email
  // - Slack
  // - Discord
  // - Push notifications
}

async function updateTranslationStats(translation) {
  // Update translation statistics
  logger.info('Updating stats for translation:', translation.id);
}

/**
 * Scheduled Tasks
 */

// Monitor translations every 5 minutes
cron.schedule('*/5 * * * *', async () => {
  try {
    await TranslationWorkflows.monitorTranslations();
  } catch (error) {
    logger.error('Scheduled translation monitoring failed:', error);
  }
});

// Daily quality check at 2 AM
cron.schedule('0 2 * * *', async () => {
  try {
    logger.info('Starting daily quality check');
    
    // Get all translations from last 24 hours
    const response = await axios.get(`${ULT_API_BASE}/translations/recent?hours=24`);
    const translations = response.data;
    
    // Run quality checks
    for (const translation of translations) {
      await TranslationWorkflows.qualityCheck(translation.id);
    }
    
    logger.info('Daily quality check completed');
  } catch (error) {
    logger.error('Daily quality check failed:', error);
  }
});

/**
 * Health Check
 */
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    uptime: process.uptime()
  });
});

/**
 * Start Server
 */
const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  logger.info(`ULT Translator n8n Integration running on port ${PORT}`);
  logger.info('Available endpoints:');
  logger.info('- POST /webhook/:workflow - n8n webhook receiver');
  logger.info('- POST /auto-translate - trigger auto-translation');
  logger.info('- POST /batch-translate - batch translation');
  logger.info('- POST /quality-check/:id - quality assurance');
  logger.info('- GET /health - health check');
});

module.exports = {
  TranslationWorkflows,
  app
};
