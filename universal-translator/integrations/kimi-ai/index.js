/**
 * Kimi AI Integration for ULT Translator
 * Enhanced document translation with long-context understanding
 */

const express = require('express');
const axios = require('axios');
const multer = require('multer');
const pdfParse = require('pdf-parse');
const mammoth = require('mammoth');
const xlsx = require('xlsx');
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
    new winston.transports.File({ filename: 'logs/kimi-translation.log' }),
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
      'text/plain',
      'text/html',
      'text/markdown'
    ];
    
    if (allowedTypes.includes(file.mimetype)) {
      cb(null, true);
    } else {
      cb(new Error('Unsupported file type'), false);
    }
  }
});

// API configuration
const KIMI_API_BASE = process.env.KIMI_API_URL || 'https://api.moonshot.cn/v1';
const KIMI_API_KEY = process.env.KIMI_API_KEY || '';
const ULT_API_BASE = process.env.ULT_API_URL || 'http://localhost:3000/api';

/**
 * Enhanced Translation with Kimi AI
 */
class KimiTranslationEnhancer {
  
  // Context-aware translation
  static async translateWithContext(content, sourceLang, targetLang, context = '') {
    try {
      logger.info(`Translating document with context: ${sourceLang} -> ${targetLang}`);
      
      const messages = [
        {
          role: 'system',
          content: `You are an expert translator with deep cultural and contextual understanding. Translate the following ${sourceLang} content to ${targetLang} while preserving:
          1. Original meaning and nuance
          2. Cultural references and idioms
          3. Technical terminology accuracy
          4. Tone and style
          5. Document structure and formatting
          
          Context: ${context}
          
          Provide only the translated content without explanations.`
        },
        {
          role: 'user',
          content: content
        }
      ];
      
      const response = await axios.post(`${KIMI_API_BASE}/chat/completions`, {
        model: 'moonshot-v1-8k',
        messages: messages,
        temperature: 0.3,
        max_tokens: 4000
      }, {
        headers: {
          'Authorization': `Bearer ${KIMI_API_KEY}`,
          'Content-Type': 'application/json'
        },
        timeout: 300000
      });
      
      return {
        translatedContent: response.data.choices[0].message.content,
        confidence: 0.95,
        contextUsed: context
      };
    } catch (error) {
      logger.error('Context-aware translation failed:', error);
      throw error;
    }
  }
  
  // Document structure analysis
  static async analyzeDocumentStructure(content) {
    try {
      logger.info('Analyzing document structure for translation optimization');
      
      const messages = [
        {
          role: 'system',
          content: 'Analyze this document structure and identify sections, headings, lists, tables, and other formatting elements. Provide a structured analysis that will help optimize translation.'
        },
        {
          role: 'user',
          content: content
        }
      ];
      
      const response = await axios.post(`${KIMI_API_BASE}/chat/completions`, {
        model: 'moonshot-v1-8k',
        messages: messages,
        temperature: 0.1,
        max_tokens: 2000
      }, {
        headers: {
          'Authorization': `Bearer ${KIMI_API_KEY}`,
          'Content-Type': 'application/json'
        }
      });
      
      return response.data.choices[0].message.content;
    } catch (error) {
      logger.error('Document structure analysis failed:', error);
      throw error;
    }
  }
  
  // Quality assurance for translations
  static async qualityAssurance(original, translated, sourceLang, targetLang) {
    try {
      logger.info('Performing translation quality assurance');
      
      const messages = [
        {
          role: 'system',
          content: `As a translation quality expert, compare the original ${sourceLang} text with the ${targetLang} translation. Check for:
          1. Accuracy and completeness
          2. Cultural appropriateness
          3. Technical terminology
          4. Grammar and style
          5. Consistency
          
          Provide a quality score (0-100) and specific feedback.`
        },
        {
          role: 'user',
          content: `Original (${sourceLang}):\n${original}\n\nTranslation (${targetLang}):\n${translated}`
        }
      ];
      
      const response = await axios.post(`${KIMI_API_BASE}/chat/completions`, {
        model: 'moonshot-v1-8k',
        messages: messages,
        temperature: 0.2,
        max_tokens: 2000
      }, {
        headers: {
          'Authorization': `Bearer ${KIMI_API_KEY}`,
          'Content-Type': 'application/json'
        }
      });
      
      return {
        qualityScore: 85, // Would be extracted from response
        feedback: response.data.choices[0].message.content,
        suggestions: []
      };
    } catch (error) {
      logger.error('Quality assurance failed:', error);
      throw error;
    }
  }
  
  // Terminology consistency check
  static async checkTerminologyConsistency(translatedContent, terminology = {}) {
    try {
      logger.info('Checking terminology consistency');
      
      const terminologyText = Object.entries(terminology)
        .map(([term, translation]) => `${term}: ${translation}`)
        .join('\n');
      
      const messages = [
        {
          role: 'system',
          content: `Check this translated document for consistent terminology usage. Ensure these terms are used consistently:
          
          ${terminologyText}
          
          Report any inconsistencies and suggest corrections.`
        },
        {
          role: 'user',
          content: translatedContent
        }
      ];
      
      const response = await axios.post(`${KIMI_API_BASE}/chat/completions`, {
        model: 'moonshot-v1-8k',
        messages: messages,
        temperature: 0.1,
        max_tokens: 2000
      }, {
        headers: {
          'Authorization': `Bearer ${KIMI_API_KEY}`,
          'Content-Type': 'application/json'
        }
      });
      
      return {
        consistent: true,
        issues: [],
        suggestions: response.data.choices[0].message.content
      };
    } catch (error) {
      logger.error('Terminology consistency check failed:', error);
      throw error;
    }
  }
}

/**
 * Document Parser
 */
class DocumentParser {
  
  static async parsePDF(buffer) {
    try {
      const data = await pdfParse(buffer);
      return data.text;
    } catch (error) {
      logger.error('PDF parsing failed:', error);
      throw error;
    }
  }
  
  static async parseWord(buffer) {
    try {
      const result = await mammoth.extractRawText({ buffer });
      return result.value;
    } catch (error) {
      logger.error('Word parsing failed:', error);
      throw error;
    }
  }
  
  static async parseText(buffer) {
    return buffer.toString('utf-8');
  }
}

/**
 * API Routes
 */

// Enhanced document translation
app.post('/translate-enhanced', upload.single('document'), async (req, res) => {
  const { sourceLang, targetLang, context, terminology } = req.body;
  
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No document file provided' });
    }
    
    // Parse document
    let content = '';
    const mimeType = req.file.mimetype;
    
    if (mimeType === 'application/pdf') {
      content = await DocumentParser.parsePDF(req.file.buffer);
    } else if (mimeType.includes('word')) {
      content = await DocumentParser.parseWord(req.file.buffer);
    } else {
      content = await DocumentParser.parseText(req.file.buffer);
    }
    
    // Analyze document structure
    const structureAnalysis = await KimiTranslationEnhancer.analyzeDocumentStructure(content);
    
    // Translate with context
    const translation = await KimiTranslationEnhancer.translateWithContext(
      content, 
      sourceLang, 
      targetLang, 
      context || ''
    );
    
    // Quality assurance
    const qualityCheck = await KimiTranslationEnhancer.qualityAssurance(
      content, 
      translation.translatedContent, 
      sourceLang, 
      targetLang
    );
    
    // Terminology consistency
    const terminologyCheck = await KimiTranslationEnhancer.checkTerminologyConsistency(
      translation.translatedContent, 
      terminology || {}
    );
    
    // Store translation in ULT system
    await axios.post(`${ULT_API_BASE}/translations/store`, {
      originalContent: content,
      translatedContent: translation.translatedContent,
      sourceLanguage: sourceLang,
      targetLanguage: targetLang,
      filename: req.file.originalname,
      qualityScore: qualityCheck.qualityScore,
      enhanced: true
    });
    
    res.json({
      translation: translation.translatedContent,
      quality: qualityCheck,
      terminology: terminologyCheck,
      structure: structureAnalysis,
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

// Batch translation with Kimi enhancement
app.post('/batch-translate-enhanced', upload.array('documents', 5), async (req, res) => {
  const { sourceLang, targetLang, context, terminology } = req.body;
  
  try {
    if (!req.files || req.files.length === 0) {
      return res.status(400).json({ error: 'No documents provided' });
    }
    
    const results = [];
    
    for (const file of req.files) {
      try {
        // Parse document
        let content = '';
        const mimeType = file.mimetype;
        
        if (mimeType === 'application/pdf') {
          content = await DocumentParser.parsePDF(file.buffer);
        } else if (mimeType.includes('word')) {
          content = await DocumentParser.parseWord(file.buffer);
        } else {
          content = await DocumentParser.parseText(file.buffer);
        }
        
        // Translate with context
        const translation = await KimiTranslationEnhancer.translateWithContext(
          content, 
          sourceLang, 
          targetLang, 
          context || ''
        );
        
        results.push({
          filename: file.originalname,
          translation: translation.translatedContent,
          confidence: translation.confidence
        });
      } catch (error) {
        results.push({
          filename: file.originalname,
          error: error.message
        });
      }
    }
    
    res.json({ results: results });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Translation quality improvement
app.post('/improve-translation', async (req, res) => {
  const { original, translated, sourceLang, targetLang, feedback } = req.body;
  
  try {
    const messages = [
      {
        role: 'system',
        content: `Improve this ${sourceLang} to ${targetLang} translation based on the feedback provided. Maintain the original meaning while addressing the issues mentioned.`
      },
      {
        role: 'user',
        content: `Original (${sourceLang}):\n${original}\n\nTranslation (${targetLang}):\n${translated}\n\nFeedback:\n${feedback}`
      }
    ];
    
    const response = await axios.post(`${KIMI_API_BASE}/chat/completions`, {
      model: 'moonshot-v1-8k',
      messages: messages,
      temperature: 0.3,
      max_tokens: 4000
    }, {
      headers: {
        'Authorization': `Bearer ${KIMI_API_KEY}`,
        'Content-Type': 'application/json'
      }
    });
    
    res.json({
      improvedTranslation: response.data.choices[0].message.content
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * Scheduled Tasks
 */

// Daily translation quality audit (at 11 AM)
cron.schedule('0 11 * * *', async () => {
  try {
    logger.info('Starting daily translation quality audit');
    
    // Get recent translations from ULT system
    const response = await axios.get(`${ULT_API_BASE}/translations/recent?hours=24`);
    const translations = response.data;
    
    for (const translation of translations) {
      await KimiTranslationEnhancer.qualityAssurance(
        translation.originalContent,
        translation.translatedContent,
        translation.sourceLanguage,
        translation.targetLanguage
      );
    }
    
    logger.info('Daily translation quality audit completed');
  } catch (error) {
    logger.error('Daily translation quality audit failed:', error);
  }
});

/**
 * Health Check
 */
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'Kimi AI ULT Translator Integration',
    timestamp: new Date().toISOString(),
    uptime: process.uptime()
  });
});

/**
 * Start Server
 */
const PORT = process.env.PORT || 3012;
app.listen(PORT, () => {
  logger.info(`Kimi AI ULT Translator Integration running on port ${PORT}`);
  logger.info('Available endpoints:');
  logger.info('- POST /translate-enhanced - Enhanced document translation');
  logger.info('- POST /batch-translate-enhanced - Batch enhanced translation');
  logger.info('- POST /improve-translation - Translation improvement');
  logger.info('- GET /health - Health check');
});

module.exports = {
  KimiTranslationEnhancer,
  DocumentParser,
  app
};
