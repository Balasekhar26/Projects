/**
 * Computer Vision AI Integration for PCB Doctor
 * Automated visual PCB diagnostics using OpenCV and OCR
 */

const express = require('express');
const axios = require('axios');
const multer = require('multer');
const sharp = require('sharp');
const cv = require('opencv4nodejs');
const Tesseract = require('tesseract.js');
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
    new winston.transports.File({ filename: 'logs/pcb-vision.log' }),
    new winston.transports.Console()
  ]
});

const app = express();
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Configure multer for image uploads
const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 20 * 1024 * 1024, // 20MB limit
  },
  fileFilter: (req, file, cb) => {
    if (file.mimetype.startsWith('image/')) {
      cb(null, true);
    } else {
      cb(new Error('Only image files are allowed'), false);
    }
  }
});

// PCB Doctor API configuration
const PCB_API_BASE = process.env.PCB_API_URL || 'http://localhost:3006/api';

/**
 * Computer Vision PCB Diagnostics Class
 */
class PCBVisionDiagnostics {
  
  // Analyze PCB image for defects
  static async analyzePCBImage(imageBuffer, analysisType = 'comprehensive') {
    try {
      logger.info(`Analyzing PCB image: ${analysisType}`);
      
      // Convert image buffer to OpenCV format
      const image = await cv.imdecodeAsync(imageBuffer);
      
      const results = {
        originalImage: image,
        defects: [],
        components: [],
        traces: [],
        quality: 0
      };
      
      // Preprocess image
      const processedImage = await this.preprocessImage(image);
      
      // Detect defects
      if (analysisType === 'comprehensive' || analysisType === 'defects') {
        results.defects = await this.detectDefects(processedImage);
      }
      
      // Identify components
      if (analysisType === 'comprehensive' || analysisType === 'components') {
        results.components = await this.identifyComponents(processedImage);
      }
      
      // Analyze traces
      if (analysisType === 'comprehensive' || analysisType === 'traces') {
        results.traces = await this.analyzeTraces(processedImage);
      }
      
      // Calculate overall quality score
      results.quality = this.calculateQualityScore(results);
      
      return results;
    } catch (error) {
      logger.error('PCB image analysis failed:', error);
      throw error;
    }
  }
  
  // Preprocess image for analysis
  static async preprocessImage(image) {
    try {
      // Convert to grayscale
      const gray = image.cvtColor(cv.COLOR_BGR2GRAY);
      
      // Apply Gaussian blur to reduce noise
      const blurred = gray.gaussianBlur(new cv.Size(5, 5), 0);
      
      // Apply adaptive thresholding
      const thresholded = blurred.adaptiveThreshold(
        255, 
        cv.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv.THRESH_BINARY, 
        11, 
        2
      );
      
      // Morphological operations
      const kernel = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(3, 3));
      const opened = thresholded.morphologyEx(cv.MORPH_OPEN, kernel);
      
      return opened;
    } catch (error) {
      logger.error('Image preprocessing failed:', error);
      throw error;
    }
  }
  
  // Detect PCB defects
  static async detectDefects(processedImage) {
    try {
      const defects = [];
      
      // Detect solder bridges
      const solderBridges = await this.detectSolderBridges(processedImage);
      defects.push(...solderBridges);
      
      // Detect missing components
      const missingComponents = await this.detectMissingComponents(processedImage);
      defects.push(...missingComponents);
      
      // Detect physical damage
      const physicalDamage = await this.detectPhysicalDamage(processedImage);
      defects.push(...physicalDamage);
      
      // Detect corrosion
      const corrosion = await this.detectCorrosion(processedImage);
      defects.push(...corrosion);
      
      return defects;
    } catch (error) {
      logger.error('Defect detection failed:', error);
      throw error;
    }
  }
  
  // Detect solder bridges
  static async detectSolderBridges(image) {
    try {
      const defects = [];
      
      // Use contour detection to find potential solder bridges
      const contours = image.findContours(cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE);
      
      for (let i = 0; i < contours.length; i++) {
        const contour = contours[i];
        const area = contour.contourArea;
        
        // Filter for bridge-like structures
        if (area > 50 && area < 500) {
          const rect = contour.boundingRect();
          const aspectRatio = rect.width / rect.height;
          
          // Bridges typically have high aspect ratio
          if (aspectRatio > 2 && aspectRatio < 10) {
            defects.push({
              type: 'solder_bridge',
              location: { x: rect.x, y: rect.y },
              size: { width: rect.width, height: rect.height },
              severity: this.calculateSeverity('solder_bridge', area),
              confidence: 0.85
            });
          }
        }
      }
      
      return defects;
    } catch (error) {
      logger.error('Solder bridge detection failed:', error);
      return [];
    }
  }
  
  // Detect missing components
  static async detectMissingComponents(image) {
    try {
      const defects = [];
      
      // Look for empty component pads
      const circles = image.houghCircles(
        cv.HOUGH_GRADIENT,
        1,
        20,
        50,
        30,
        1,
        30
      );
      
      if (circles) {
        for (let i = 0; i < circles.length; i++) {
          const circle = circles[i];
          const center = new cv.Point(circle.x, circle.y);
          const radius = circle.radius;
          
          // Check if circle area is empty (missing component)
          const roi = image.getRegion(new cv.Rect(
            center.x - radius,
            center.y - radius,
            radius * 2,
            radius * 2
          ));
          
          const meanIntensity = roi.mean().mean()[0];
          
          // Empty pads typically have different intensity
          if (meanIntensity > 200) {
            defects.push({
              type: 'missing_component',
              location: { x: center.x, y: center.y },
              size: { radius: radius },
              severity: 'medium',
              confidence: 0.75
            });
          }
        }
      }
      
      return defects;
    } catch (error) {
      logger.error('Missing component detection failed:', error);
      return [];
    }
  }
  
  // Detect physical damage
  static async detectPhysicalDamage(image) {
    try {
      const defects = [];
      
      // Use edge detection to find cracks and damage
      const edges = image.canny(50, 150);
      
      // Find long edges that might be cracks
      const lines = edges.houghLinesP(1, Math.PI / 180, 50, 50, 10);
      
      if (lines) {
        for (let i = 0; i < lines.length; i++) {
          const line = lines[i];
          const length = Math.sqrt(
            Math.pow(line.x2 - line.x1, 2) + Math.pow(line.y2 - line.y1, 2)
          );
          
          // Long, straight edges might indicate cracks
          if (length > 100) {
            defects.push({
              type: 'physical_damage',
              subtype: 'crack',
              location: {
                start: { x: line.x1, y: line.y1 },
                end: { x: line.x2, y: line.y2 }
              },
              length: length,
              severity: this.calculateSeverity('crack', length),
              confidence: 0.80
            });
          }
        }
      }
      
      return defects;
    } catch (error) {
      logger.error('Physical damage detection failed:', error);
      return [];
    }
  }
  
  // Detect corrosion
  static async detectCorrosion(image) {
    try {
      const defects = [];
      
      // Convert back to color for corrosion detection
      const colorImage = image.cvtColor(cv.COLOR_GRAY2BGR);
      
      // Use color analysis to detect corrosion (typically green/blue/white spots)
      const hsv = colorImage.cvtColor(cv.COLOR_BGR2HSV);
      
      // Define range for corrosion colors
      const lowerGreen = new cv.Mat(1, 3, cv.CV_8UC1, [40, 40, 40]);
      const upperGreen = new cv.Mat(1, 3, cv.CV_8UC1, [80, 255, 255]);
      
      const mask = hsv.inRange(lowerGreen, upperGreen);
      const corrosionAreas = mask.findContours(cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE);
      
      for (let i = 0; i < corrosionAreas.length; i++) {
        const area = corrosionAreas[i].contourArea;
        
        if (area > 20 && area < 1000) {
          const rect = corrosionAreas[i].boundingRect();
          defects.push({
            type: 'corrosion',
            location: { x: rect.x, y: rect.y },
            size: { width: rect.width, height: rect.height },
            area: area,
            severity: this.calculateSeverity('corrosion', area),
            confidence: 0.70
          });
        }
      }
      
      return defects;
    } catch (error) {
      logger.error('Corrosion detection failed:', error);
      return [];
    }
  }
  
  // Identify components on PCB
  static async identifyComponents(image) {
    try {
      const components = [];
      
      // Detect rectangular components (chips, resistors, etc.)
      const contours = image.findContours(cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE);
      
      for (let i = 0; i < contours.length; i++) {
        const contour = contours[i];
        const area = contour.contourArea;
        
        if (area > 100) {
          const rect = contour.boundingRect();
          const aspectRatio = rect.width / rect.height;
          
          // Classify component based on size and shape
          let componentType = 'unknown';
          
          if (aspectRatio > 0.8 && aspectRatio < 1.2) {
            componentType = 'chip'; // Square components
          } else if (aspectRatio > 2 && aspectRatio < 5) {
            componentType = 'resistor'; // Long components
          } else if (area > 1000) {
            componentType = 'large_component'; // Large components
          }
          
          components.push({
            type: componentType,
            location: { x: rect.x, y: rect.y },
            size: { width: rect.width, height: rect.height },
            area: area,
            confidence: 0.75
          });
        }
      }
      
      return components;
    } catch (error) {
      logger.error('Component identification failed:', error);
      return [];
    }
  }
  
  // Analyze PCB traces
  static async analyzeTraces(image) {
    try {
      const traces = [];
      
      // Use morphological operations to enhance traces
      const kernel = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(10, 1));
      const enhanced = image.morphologyEx(cv.MORPH_CLOSE, kernel);
      
      // Find trace-like structures
      const contours = enhanced.findContours(cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE);
      
      for (let i = 0; i < contours.length; i++) {
        const contour = contours[i];
        const area = contour.contourArea;
        
        if (area > 50 && area < 5000) {
          const rect = contour.boundingRect();
          const aspectRatio = rect.width / rect.height;
          
          // Traces typically have high aspect ratio
          if (aspectRatio > 3) {
            traces.push({
              type: 'trace',
              location: { x: rect.x, y: rect.y },
              size: { width: rect.width, height: rect.height },
              length: Math.max(rect.width, rect.height),
              width: Math.min(rect.width, rect.height),
              continuity: this.checkTraceContinuity(contour),
              confidence: 0.80
            });
          }
        }
      }
      
      return traces;
    } catch (error) {
      logger.error('Trace analysis failed:', error);
      return [];
    }
  }
  
  // Check trace continuity
  static checkTraceContinuity(contour) {
    try {
      // Simple continuity check based on contour properties
      const perimeter = contour.arcLength(true);
      const area = contour.contourArea;
      const circularity = 4 * Math.PI * area / (perimeter * perimeter);
      
      // Good traces should have appropriate circularity
      return circularity > 0.1 && circularity < 0.8;
    } catch (error) {
      return false;
    }
  }
  
  // Calculate quality score
  static calculateQualityScore(results) {
    try {
      let score = 100;
      
      // Deduct points for defects
      results.defects.forEach(defect => {
        switch (defect.severity) {
          case 'critical':
            score -= 20;
            break;
          case 'high':
            score -= 15;
            break;
          case 'medium':
            score -= 10;
            break;
          case 'low':
            score -= 5;
            break;
        }
      });
      
      // Bonus points for good trace continuity
      const goodTraces = results.traces.filter(trace => trace.continuity).length;
      score += Math.min(goodTraces * 2, 10);
      
      return Math.max(0, Math.min(100, score));
    } catch (error) {
      return 50; // Default score if calculation fails
    }
  }
  
  // Calculate defect severity
  static calculateSeverity(defectType, measurement) {
    try {
      switch (defectType) {
        case 'solder_bridge':
          return measurement > 100 ? 'critical' : measurement > 50 ? 'high' : 'medium';
        case 'crack':
          return measurement > 200 ? 'critical' : measurement > 100 ? 'high' : 'medium';
        case 'corrosion':
          return measurement > 500 ? 'high' : measurement > 200 ? 'medium' : 'low';
        default:
          return 'medium';
      }
    } catch (error) {
      return 'medium';
    }
  }
  
  // OCR text recognition for component labels
  static async performOCR(imageBuffer) {
    try {
      logger.info('Performing OCR on PCB image');
      
      // Use Tesseract for text recognition
      const result = await Tesseract.recognize(imageBuffer, 'eng', {
        logger: m => console.log(m)
      });
      
      return {
        text: result.data.text,
        confidence: result.data.confidence,
        words: result.data.words
      };
    } catch (error) {
      logger.error('OCR failed:', error);
      return { text: '', confidence: 0, words: [] };
    }
  }
}

/**
 * API Routes
 */

// Upload and analyze PCB image
app.post('/analyze-pcb', upload.single('image'), async (req, res) => {
  const { analysisType, boardId } = req.body;
  
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No image file provided' });
    }
    
    // Analyze PCB image
    const results = await PCBVisionDiagnostics.analyzePCBImage(
      req.file.buffer, 
      analysisType || 'comprehensive'
    );
    
    // Perform OCR for text recognition
    const ocrResults = await PCBVisionDiagnostics.performOCR(req.file.buffer);
    
    // Store results in PCB Doctor system
    await axios.post(`${PCB_API_BASE}/diagnostics/store-vision-results`, {
      boardId: boardId || 'unknown',
      visionResults: results,
      ocrResults: ocrResults,
      filename: req.file.originalname,
      timestamp: new Date().toISOString()
    });
    
    res.json({
      analysis: results,
      ocr: ocrResults,
      imageInfo: {
        name: req.file.originalname,
        size: req.file.size,
        type: req.file.mimetype
      }
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Batch PCB analysis
app.post('/batch-analyze', upload.array('images', 10), async (req, res) => {
  const { analysisType } = req.body;
  
  try {
    if (!req.files || req.files.length === 0) {
      return res.status(400).json({ error: 'No image files provided' });
    }
    
    const results = [];
    
    for (const file of req.files) {
      try {
        const analysis = await PCBVisionDiagnostics.analyzePCBImage(
          file.buffer, 
          analysisType || 'comprehensive'
        );
        
        const ocr = await PCBVisionDiagnostics.performOCR(file.buffer);
        
        results.push({
          filename: file.originalname,
          analysis: analysis,
          ocr: ocr
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

// Get analysis status
app.get('/analysis-status/:analysisId', async (req, res) => {
  const { analysisId } = req.params;
  
  try {
    const response = await axios.get(`${PCB_API_BASE}/diagnostics/vision-status/${analysisId}`);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * Scheduled Tasks
 */

// Daily PCB quality audit (at 8 AM)
cron.schedule('0 8 * * *', async () => {
  try {
    logger.info('Starting daily PCB quality audit');
    
    // Get pending PCB images for analysis
    const response = await axios.get(`${PCB_API_BASE}/boards/pending-vision-analysis`);
    const boards = response.data;
    
    for (const board of boards) {
      // Analyze each board
      await PCBVisionDiagnostics.analyzePCBImage(board.imageBuffer, 'comprehensive');
    }
    
    logger.info('Daily PCB quality audit completed');
  } catch (error) {
    logger.error('Daily PCB quality audit failed:', error);
  }
});

/**
 * Health Check
 */
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'PCB Doctor Computer Vision Integration',
    timestamp: new Date().toISOString(),
    uptime: process.uptime()
  });
});

/**
 * Start Server
 */
const PORT = process.env.PORT || 3013;
app.listen(PORT, () => {
  logger.info(`PCB Doctor Computer Vision Integration running on port ${PORT}`);
  logger.info('Available endpoints:');
  logger.info('- POST /analyze-pcb - Analyze single PCB image');
  logger.info('- POST /batch-analyze - Batch PCB analysis');
  logger.info('- GET /analysis-status/:id - Get analysis status');
  logger.info('- GET /health - Health check');
});

module.exports = {
  PCBVisionDiagnostics,
  app
};
