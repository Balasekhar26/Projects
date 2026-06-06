/**
 * Kimi AI Assistant Integration for Kattappa AI System
 * Long-context reasoning, document analysis, and research capabilities
 */

const express = require('express');
const axios = require('axios');
const multer = require('multer');
const pdfParse = require('pdf-parse');
const mammoth = require('mammoth');
const xlsx = require('xlsx');
const cheerio = require('cheerio');
const { marked } = require('marked');
const winston = require('winston');
const cron = require('node-cron');
require('dotenv').config();

// Configure logging
const logger = winston.createLogger({
  level: 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [
    new winston.transports.File({ filename: 'logs/kimi-integration.log' }),
    new winston.transports.Console()
  ]
});

const app = express();
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Configure multer for file uploads
const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 50 * 1024 * 1024, // 50MB limit for large documents
  },
  fileFilter: (req, file, cb) => {
    const allowedTypes = [
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/msword',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'text/plain',
      'text/html',
      'text/markdown',
      'application/json'
    ];

    if (allowedTypes.includes(file.mimetype)) {
      cb(null, true);
    } else {
      cb(new Error('Unsupported file type'), false);
    }
  }
});

// Kimi AI API configuration
const KIMI_API_BASE = process.env.KIMI_API_URL || 'https://api.moonshot.cn/v1';
const KIMI_API_KEY = process.env.KIMI_API_KEY || '';
const AI_API_BASE = process.env.AI_API_URL || 'http://localhost:3004/api';

/**
 * Kimi AI Assistant Class
 */
class KimiAssistant {

  // Chat with long context support
  static async chat(messages, options = {}) {
    try {
      logger.info(`Kimi chat with ${messages.length} messages`);

      const requestBody = {
        model: options.model || 'moonshot-v1-8k',
        messages: messages,
        temperature: options.temperature || 0.7,
        max_tokens: options.maxTokens || 4000,
        stream: options.stream || false,
        tools: options.tools || []
      };

      const response = await axios.post(`${KIMI_API_BASE}/chat/completions`, requestBody, {
        headers: {
          'Authorization': `Bearer ${KIMI_API_KEY}`,
          'Content-Type': 'application/json'
        },
        timeout: 300000 // 5 minutes timeout for long context
      });

      return response.data;
    } catch (error) {
      logger.error('Kimi chat failed:', error);
      throw error;
    }
  }

  // Long document analysis
  static async analyzeDocument(content, analysisType = 'summary') {
    try {
      logger.info(`Analyzing document: ${analysisType}`);

      const analysisPrompts = {
        summary: 'Please provide a comprehensive summary of this document, including key points, main arguments, and conclusions.',
        key_insights: 'Extract the most important insights, patterns, and actionable information from this document.',
        research_analysis: 'Analyze this document as a researcher would, identifying methodology, findings, limitations, and implications.',
        code_review: 'Review this code/document for best practices, potential issues, and improvement suggestions.',
        legal_analysis: 'Analyze this document from a legal perspective, identifying key clauses, obligations, and potential risks.',
        business_analysis: 'Provide a business analysis of this document, including opportunities, risks, and strategic implications.'
      };

      const messages = [
        {
          role: 'system',
          content: `You are Kimi, an AI assistant specialized in long-context document analysis. ${analysisPrompts[analysisType] || analysisPrompts.summary}`
        },
        {
          role: 'user',
          content: content
        }
      ];

      const response = await this.chat(messages, {
        maxTokens: 4000,
        temperature: 0.3
      });

      return response;
    } catch (error) {
      logger.error('Document analysis failed:', error);
      throw error;
    }
  }

  // Research and reasoning
  static async research(query, context = []) {
    try {
      logger.info(`Research query: ${query.substring(0, 100)}...`);

      const messages = [
        {
          role: 'system',
          content: 'You are Kimi, a research assistant with strong reasoning capabilities. Provide comprehensive, well-structured research responses with citations, counterarguments, and future directions.'
        },
        ...context,
        {
          role: 'user',
          content: query
        }
      ];

      const response = await this.chat(messages, {
        maxTokens: 4000,
        temperature: 0.5
      });

      return response;
    } catch (error) {
      logger.error('Research failed:', error);
      throw error;
    }
  }

  // Code assistance
  static async codeAssistant(code, task = 'review') {
    try {
      logger.info(`Code assistance: ${task}`);

      const taskPrompts = {
        review: 'Review this code for quality, best practices, potential bugs, and performance improvements.',
        explain: 'Explain this code in detail, including its purpose, how it works, and any important concepts.',
        optimize: 'Optimize this code for better performance, readability, and maintainability.',
        debug: 'Help debug this code by identifying issues and suggesting fixes.',
        refactor: 'Refactor this code to improve structure and maintainability.',
        test: 'Write comprehensive tests for this code.'
      };

      const messages = [
        {
          role: 'system',
          content: `You are Kimi, a coding assistant. ${taskPrompts[task] || taskPrompts.review}`
        },
        {
          role: 'user',
          content: code
        }
      ];

      const response = await this.chat(messages, {
        maxTokens: 4000,
        temperature: 0.3
      });

      return response;
    } catch (error) {
      logger.error('Code assistance failed:', error);
      throw error;
    }
  }
}

/**
 * Document Processing Utilities
 */
class DocumentProcessor {

  // Parse PDF files
  static async parsePDF(buffer) {
    try {
      const data = await pdfParse(buffer);
      return {
        text: data.text,
        metadata: data.metadata,
        pages: data.numpages
      };
    } catch (error) {
      logger.error('PDF parsing failed:', error);
      throw error;
    }
  }

  // Parse Word documents
  static async parseWord(buffer) {
    try {
      const result = await mammoth.extractRawText({ buffer });
      return {
        text: result.value,
        messages: result.messages
      };
    } catch (error) {
      logger.error('Word parsing failed:', error);
      throw error;
    }
  }

  // Parse Excel files
  static async parseExcel(buffer) {
    try {
      const workbook = xlsx.read(buffer, { type: 'buffer' });
      const sheets = {};

      workbook.SheetNames.forEach(sheetName => {
        const worksheet = workbook.Sheets[sheetName];
        sheets[sheetName] = xlsx.utils.sheet_to_json(worksheet, { header: 1 });
      });

      return {
        sheets: sheets,
        sheetNames: workbook.SheetNames
      };
    } catch (error) {
      logger.error('Excel parsing failed:', error);
      throw error;
    }
  }

  // Parse HTML files
  static parseHTML(buffer) {
    try {
      const html = buffer.toString('utf-8');
      const $ = cheerio.load(html);

      // Remove script and style elements
      $('script, style').remove();

      return {
        text: $.text(),
        title: $('title').text(),
        metadata: {
          description: $('meta[name="description"]').attr('content'),
          keywords: $('meta[name="keywords"]').attr('content')
        }
      };
    } catch (error) {
      logger.error('HTML parsing failed:', error);
      throw error;
    }
  }

  // Parse Markdown files
  static parseMarkdown(buffer) {
    try {
      const markdown = buffer.toString('utf-8');
      const html = marked(markdown);
      const $ = cheerio.load(html);

      return {
        text: $.text(),
        html: html,
        markdown: markdown
      };
    } catch (error) {
      logger.error('Markdown parsing failed:', error);
      throw error;
    }
  }
}

/**
 * API Routes
 */

// Chat endpoint
app.post('/chat', async (req, res) => {
  const { messages, options, agentConfig } = req.body;

  try {
    const response = await KimiAssistant.chat(messages, options);

    // Log AI agent usage
    if (agentConfig) {
      await axios.post(`${AI_API_BASE}/agents/log-activity`, {
        agent: agentConfig.agent,
        action: 'kimi_chat',
        messageCount: messages.length,
        responseId: response.id,
        timestamp: new Date().toISOString()
      });
    }

    res.json(response);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Document analysis endpoint
app.post('/analyze-document', upload.single('document'), async (req, res) => {
  const { analysisType, agentConfig } = req.body;

  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No document file provided' });
    }

    // Parse document based on type
    let content = '';
    const mimeType = req.file.mimetype;

    if (mimeType === 'application/pdf') {
      const parsed = await DocumentProcessor.parsePDF(req.file.buffer);
      content = parsed.text;
    } else if (mimeType.includes('word')) {
      const parsed = await DocumentProcessor.parseWord(req.file.buffer);
      content = parsed.text;
    } else if (mimeType.includes('excel')) {
      const parsed = await DocumentProcessor.parseExcel(req.file.buffer);
      content = JSON.stringify(parsed.sheets, null, 2);
    } else if (mimeType === 'text/html') {
      const parsed = await DocumentProcessor.parseHTML(req.file.buffer);
      content = parsed.text;
    } else if (mimeType === 'text/markdown') {
      const parsed = await DocumentProcessor.parseMarkdown(req.file.buffer);
      content = parsed.text;
    } else {
      content = req.file.buffer.toString('utf-8');
    }

    // Analyze with Kimi
    const analysis = await KimiAssistant.analyzeDocument(content, analysisType);

    // Log AI agent usage
    if (agentConfig) {
      await axios.post(`${AI_API_BASE}/agents/log-activity`, {
        agent: agentConfig.agent,
        action: 'document_analysis',
        documentType: mimeType,
        analysisType: analysisType,
        timestamp: new Date().toISOString()
      });
    }

    res.json({
      analysis: analysis,
      documentInfo: {
        name: req.file.originalname,
        type: mimeType,
        size: req.file.size
      }
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Research endpoint
app.post('/research', async (req, res) => {
  const { query, context, agentConfig } = req.body;

  try {
    const response = await KimiAssistant.research(query, context || []);

    // Log AI agent usage
    if (agentConfig) {
      await axios.post(`${AI_API_BASE}/agents/log-activity`, {
        agent: agentConfig.agent,
        action: 'research',
        query: query,
        responseId: response.id,
        timestamp: new Date().toISOString()
      });
    }

    res.json(response);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Code assistance endpoint
app.post('/code-assistant', async (req, res) => {
  const { code, task, agentConfig } = req.body;

  try {
    const response = await KimiAssistant.codeAssistant(code, task);

    // Log AI agent usage
    if (agentConfig) {
      await axios.post(`${AI_API_BASE}/agents/log-activity`, {
        agent: agentConfig.agent,
        action: 'code_assistance',
        task: task,
        responseId: response.id,
        timestamp: new Date().toISOString()
      });
    }

    res.json(response);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Long context conversation endpoint
app.post('/long-context', async (req, res) => {
  const { conversation, options, agentConfig } = req.body;

  try {
    // Kimi excels at long context - handle up to 8k tokens
    const response = await KimiAssistant.chat(conversation, {
      ...options,
      maxTokens: 4000,
      model: 'moonshot-v1-8k'
    });

    // Log AI agent usage
    if (agentConfig) {
      await axios.post(`${AI_API_BASE}/agents/log-activity`, {
        agent: agentConfig.agent,
        action: 'long_context_conversation',
        conversationLength: conversation.length,
        responseId: response.id,
        timestamp: new Date().toISOString()
      });
    }

    res.json(response);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Batch document processing
app.post('/batch-process', upload.array('documents', 10), async (req, res) => {
  const { analysisType, agentConfig } = req.body;

  try {
    if (!req.files || req.files.length === 0) {
      return res.status(400).json({ error: 'No documents provided' });
    }

    const results = [];

    for (const file of req.files) {
      try {
        let content = '';
        const mimeType = file.mimetype;

        // Parse document
        if (mimeType === 'application/pdf') {
          const parsed = await DocumentProcessor.parsePDF(file.buffer);
          content = parsed.text;
        } else if (mimeType.includes('word')) {
          const parsed = await DocumentProcessor.parseWord(file.buffer);
          content = parsed.text;
        } else {
          content = file.buffer.toString('utf-8');
        }

        // Analyze with Kimi
        const analysis = await KimiAssistant.analyzeDocument(content, analysisType);

        results.push({
          filename: file.originalname,
          type: mimeType,
          analysis: analysis
        });
      } catch (error) {
        results.push({
          filename: file.originalname,
          error: error.message
        });
      }
    }

    // Log AI agent usage
    if (agentConfig) {
      await axios.post(`${AI_API_BASE}/agents/log-activity`, {
        agent: agentConfig.agent,
        action: 'batch_document_processing',
        documentCount: req.files.length,
        analysisType: analysisType,
        timestamp: new Date().toISOString()
      });
    }

    res.json({ results: results });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * Scheduled Tasks
 */

// Daily research digest (at 9 AM)
cron.schedule('0 9 * * *', async () => {
  try {
    logger.info('Starting daily research digest');

    // Get trending topics from AI system
    const response = await axios.get(`${AI_API_BASE}/topics/trending`);
    const topics = response.data;

    // Generate research digest
    for (const topic of topics) {
      await KimiAssistant.research(
        `Provide a comprehensive research digest on ${topic.name}, including latest developments, key findings, and future implications.`,
        topic.context || []
      );
    }

    logger.info('Daily research digest completed');
  } catch (error) {
    logger.error('Daily research digest failed:', error);
  }
});

// Document analysis optimization (every 6 hours)
cron.schedule('0 */6 * * *', async () => {
  try {
    // Check for pending document analyses
    const response = await axios.get(`${AI_API_BASE}/documents/pending-analysis`);
    const documents = response.data;

    for (const doc of documents) {
      await KimiAssistant.analyzeDocument(doc.content, doc.analysisType);
    }

    logger.info('Document analysis optimization completed');
  } catch (error) {
    logger.error('Scheduled document analysis failed:', error);
  }
});

/**
 * Health Check
 */
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'Kimi AI Integration',
    timestamp: new Date().toISOString(),
    uptime: process.uptime()
  });
});

/**
 * Start Server
 */
const PORT = process.env.PORT || 3011;
app.listen(PORT, () => {
  logger.info(`Kimi AI Integration running on port ${PORT}`);
  logger.info('Available endpoints:');
  logger.info('- POST /chat - Long context chat');
  logger.info('- POST /analyze-document - Document analysis');
  logger.info('- POST /research - Research and reasoning');
  logger.info('- POST /code-assistant - Code assistance');
  logger.info('- POST /long-context - Extended conversation');
  logger.info('- POST /batch-process - Batch document processing');
  logger.info('- GET /health - Health check');
});

module.exports = {
  KimiAssistant,
  DocumentProcessor,
  app
};
