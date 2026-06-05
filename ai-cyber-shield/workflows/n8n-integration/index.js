/**
 * Balu Cyber Shield n8n Workflow Automation Integration
 * Automated security monitoring and alert workflows
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
    new winston.transports.File({ filename: 'logs/security-workflows.log' }),
    new winston.transports.Console()
  ]
});

const app = express();
app.use(express.json());

// Security API endpoints
const SECURITY_API_BASE = process.env.SECURITY_API_URL || 'http://localhost:3002/api';
const N8N_WEBHOOK_URL = process.env.N8N_WEBHOOK_URL || 'http://localhost:5678/webhook';

/**
 * Security Workflow Triggers
 */
class SecurityWorkflows {
  
  // Automated threat detection
  static async threatDetection(securityEvent) {
    try {
      logger.info(`Processing security event: ${securityEvent.type}`);
      
      // Trigger n8n threat analysis workflow
      const response = await axios.post(`${N8N_WEBHOOK_URL}/threat-detection`, {
        event: securityEvent,
        severity: this.calculateSeverity(securityEvent),
        timestamp: new Date().toISOString()
      });
      
      logger.info('Threat detection workflow triggered:', response.data);
      return response.data;
    } catch (error) {
      logger.error('Threat detection workflow failed:', error);
      throw error;
    }
  }
  
  // Security alert automation
  static async securityAlert(alert) {
    try {
      logger.warn(`Security alert: ${alert.type}`, alert);
      
      // Trigger alert handling workflow
      const response = await axios.post(`${N8N_WEBHOOK_URL}/security-alert`, {
        alert: alert,
        autoResponse: this.shouldAutoRespond(alert),
        escalationLevel: this.calculateEscalation(alert),
        timestamp: new Date().toISOString()
      });
      
      logger.info('Security alert workflow triggered:', response.data);
      return response.data;
    } catch (error) {
      logger.error('Security alert workflow failed:', error);
      throw error;
    }
  }
  
  // Automated incident response
  static async incidentResponse(incident) {
    try {
      logger.error(`Security incident: ${incident.type}`, incident);
      
      // Trigger incident response workflow
      const response = await axios.post(`${N8N_WEBHOOK_URL}/incident-response`, {
        incident: incident,
        responseActions: this.getResponseActions(incident),
        priority: this.calculatePriority(incident),
        timestamp: new Date().toISOString()
      });
      
      logger.info('Incident response workflow triggered:', response.data);
      return response.data;
    } catch (error) {
      logger.error('Incident response workflow failed:', error);
      throw error;
    }
  }
  
  // Periodic security scanning
  static async securityScan() {
    try {
      logger.info('Starting automated security scan');
      
      // Trigger security scan workflow
      const response = await axios.post(`${N8N_WEBHOOK_URL}/security-scan`, {
        scanType: 'comprehensive',
        targets: ['network', 'system', 'applications', 'logs'],
        timestamp: new Date().toISOString()
      });
      
      logger.info('Security scan workflow triggered:', response.data);
      return response.data;
    } catch (error) {
      logger.error('Security scan workflow failed:', error);
      throw error;
    }
  }
  
  // Log analysis automation
  static async analyzeLogs(logSource) {
    try {
      logger.info(`Analyzing logs from: ${logSource}`);
      
      // Trigger log analysis workflow
      const response = await axios.post(`${N8N_WEBHOOK_URL}/log-analysis`, {
        logSource: logSource,
        timeRange: 'last-24-hours',
        analysisType: 'security-events',
        timestamp: new Date().toISOString()
      });
      
      logger.info('Log analysis workflow triggered:', response.data);
      return response.data;
    } catch (error) {
      logger.error('Log analysis workflow failed:', error);
      throw error;
    }
  }
  
  // Helper methods
  static calculateSeverity(event) {
    const severityMap = {
      'malware': 'critical',
      'unauthorized_access': 'high',
      'suspicious_activity': 'medium',
      'policy_violation': 'low'
    };
    return severityMap[event.type] || 'medium';
  }
  
  static shouldAutoRespond(alert) {
    const autoRespondTypes = ['known_malware', 'failed_login_threshold', 'port_scan'];
    return autoRespondTypes.includes(alert.type);
  }
  
  static calculateEscalation(alert) {
    const escalationLevels = {
      'critical': 'immediate',
      'high': 'within_1_hour',
      'medium': 'within_4_hours',
      'low': 'daily_report'
    };
    return escalationLevels[this.calculateSeverity(alert)] || 'daily_report';
  }
  
  static getResponseActions(incident) {
    const actionMap = {
      'malware_detected': ['quarantine_system', 'scan_network', 'notify_admin'],
      'data_breach': ['isolate_system', 'preserve_evidence', 'notify_compliance'],
      'ddos_attack': ['enable_protection', 'notify_isp', 'scale_resources'],
      'insider_threat': ['monitor_user', 'restrict_access', 'investigate']
    };
    return actionMap[incident.type] || ['log_event', 'notify_admin'];
  }
  
  static calculatePriority(incident) {
    const priorityMap = {
      'critical': 1,
      'high': 2,
      'medium': 3,
      'low': 4
    };
    return priorityMap[this.calculateSeverity(incident)] || 3;
  }
}

/**
 * API Routes for Security Workflows
 */

// Webhook endpoint for n8n security workflows
app.post('/webhook/:workflow', async (req, res) => {
  const { workflow } = req.params;
  const data = req.body;
  
  try {
    logger.info(`Received security webhook: ${workflow}`, data);
    
    switch (workflow) {
      case 'threat-confirmed':
        await handleThreatConfirmed(data);
        break;
        
      case 'incident-resolved':
        await handleIncidentResolved(data);
        break;
        
      case 'vulnerability-found':
        await handleVulnerabilityFound(data);
        break;
        
      case 'compliance-alert':
        await handleComplianceAlert(data);
        break;
        
      default:
        logger.warn(`Unknown security workflow: ${workflow}`);
    }
    
    res.json({ success: true, message: 'Security webhook processed' });
  } catch (error) {
    logger.error(`Security webhook processing failed for ${workflow}:`, error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Trigger threat detection
app.post('/threat-detection', async (req, res) => {
  const { securityEvent } = req.body;
  
  try {
    const result = await SecurityWorkflows.threatDetection(securityEvent);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Security alert
app.post('/security-alert', async (req, res) => {
  const { alert } = req.body;
  
  try {
    const result = await SecurityWorkflows.securityAlert(alert);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Incident response
app.post('/incident-response', async (req, res) => {
  const { incident } = req.body;
  
  try {
    const result = await SecurityWorkflows.incidentResponse(incident);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Security scan
app.post('/security-scan', async (req, res) => {
  try {
    const result = await SecurityWorkflows.securityScan();
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Log analysis
app.post('/analyze-logs', async (req, res) => {
  const { logSource } = req.body;
  
  try {
    const result = await SecurityWorkflows.analyzeLogs(logSource);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * Security Workflow Handlers
 */
async function handleThreatConfirmed(data) {
  logger.error('Threat confirmed:', data.threat);
  
  // Execute automated response
  if (data.autoResponse) {
    await executeSecurityResponse(data.threat);
  }
  
  // Notify security team
  await notifySecurityTeam({
    type: 'threat_confirmed',
    threat: data.threat,
    actions: data.actions || [],
    timestamp: new Date().toISOString()
  });
}

async function handleIncidentResolved(data) {
  logger.info('Incident resolved:', data.incident);
  
  // Update incident tracking
  await updateIncidentStatus(data.incident.id, 'resolved');
  
  // Generate post-incident report
  await generateIncidentReport(data.incident);
}

async function handleVulnerabilityFound(data) {
  logger.warn('Vulnerability found:', data.vulnerability);
  
  // Schedule patch management
  await schedulePatchManagement(data.vulnerability);
  
  // Assess risk impact
  await assessRiskImpact(data.vulnerability);
}

async function handleComplianceAlert(data) {
  logger.warn('Compliance alert:', data.alert);
  
  // Create compliance task
  await createComplianceTask(data.alert);
  
  // Update compliance dashboard
  await updateComplianceDashboard(data.alert);
}

async function executeSecurityResponse(threat) {
  logger.info('Executing security response for:', threat.type);
  
  // Could integrate with:
  // - Firewall rules
  // - System isolation
  // - Process termination
  // - Network blocking
}

async function notifySecurityTeam(notification) {
  logger.info('Notifying security team:', notification);
  
  // Integration options:
  // - Email alerts
  // - Slack notifications
  // - PagerDuty escalation
  // - SMS alerts
}

async function updateIncidentStatus(incidentId, status) {
  logger.info(`Updating incident ${incidentId} to ${status}`);
}

async function generateIncidentReport(incident) {
  logger.info('Generating incident report for:', incident.id);
}

async function schedulePatchManagement(vulnerability) {
  logger.info('Scheduling patch management for:', vulnerability.id);
}

async function assessRiskImpact(vulnerability) {
  logger.info('Assessing risk impact for:', vulnerability.id);
}

async function createComplianceTask(alert) {
  logger.info('Creating compliance task for:', alert.type);
}

async function updateComplianceDashboard(alert) {
  logger.info('Updating compliance dashboard with:', alert.type);
}

/**
 * Scheduled Security Tasks
 */

// Real-time threat monitoring (every 1 minute)
cron.schedule('* * * * *', async () => {
  try {
    // Monitor for new security events
    const response = await axios.get(`${SECURITY_API_BASE}/events/recent`);
    const events = response.data;
    
    for (const event of events) {
      if (!event.processed) {
        await SecurityWorkflows.threatDetection(event);
      }
    }
  } catch (error) {
    logger.error('Real-time threat monitoring failed:', error);
  }
});

// Daily security scan at 3 AM
cron.schedule('0 3 * * *', async () => {
  try {
    logger.info('Starting daily comprehensive security scan');
    await SecurityWorkflows.securityScan();
  } catch (error) {
    logger.error('Daily security scan failed:', error);
  }
});

// Log analysis every 6 hours
cron.schedule('0 */6 * * *', async () => {
  try {
    logger.info('Starting scheduled log analysis');
    await SecurityWorkflows.analyzeLogs('system');
    await SecurityWorkflows.analyzeLogs('security');
    await SecurityWorkflows.analyzeLogs('application');
  } catch (error) {
    logger.error('Scheduled log analysis failed:', error);
  }
});

// Weekly vulnerability assessment (Sundays at 4 AM)
cron.schedule('0 4 * * 0', async () => {
  try {
    logger.info('Starting weekly vulnerability assessment');
    
    const response = await axios.post(`${N8N_WEBHOOK_URL}/vulnerability-assessment`, {
      assessmentType: 'comprehensive',
      include: ['system', 'network', 'applications'],
      timestamp: new Date().toISOString()
    });
    
    logger.info('Vulnerability assessment workflow triggered:', response.data);
  } catch (error) {
    logger.error('Weekly vulnerability assessment failed:', error);
  }
});

/**
 * Health Check
 */
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'Balu Cyber Shield n8n Integration',
    timestamp: new Date().toISOString(),
    uptime: process.uptime()
  });
});

/**
 * Start Server
 */
const PORT = process.env.PORT || 3003;
app.listen(PORT, () => {
  logger.info(`Balu Cyber Shield n8n Integration running on port ${PORT}`);
  logger.info('Available endpoints:');
  logger.info('- POST /webhook/:workflow - n8n webhook receiver');
  logger.info('- POST /threat-detection - trigger threat analysis');
  logger.info('- POST /security-alert - security alert handling');
  logger.info('- POST /incident-response - incident response automation');
  logger.info('- POST /security-scan - automated security scanning');
  logger.info('- POST /analyze-logs - log analysis automation');
  logger.info('- GET /health - health check');
});

module.exports = {
  SecurityWorkflows,
  app
};
