# Project Setup and Running Guide

This guide provides instructions for running each project independently.

## Prerequisites

- Node.js 18+ installed
- npm or yarn package manager
- Git (for some projects)

## 1. ULT Translator Web UI

**Location**: `projects/universal-translator/web-ui/`

### Setup and Run:
```bash
# Navigate to project directory
cd projects/universal-translator/web-ui

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run serve
```

**Access**: http://localhost:5173

---

## 2. Balu Cyber Shield Web Dashboard

**Location**: `projects/balu-cyber-shield/web-dashboard/`

### Setup and Run:
```bash
# Navigate to project directory
cd projects/balu-cyber-shield/web-dashboard

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run serve
```

**Access**: http://localhost:5174 (or next available port)

---

## 3. Universal AI System Assistant

**Location**: `projects/universal-ai-system/ai-assistant/`

### Setup and Run:
```bash
# Navigate to project directory
cd projects/universal-ai-system/ai-assistant

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run serve
```

**Access**: http://localhost:5175 (or next available port)

---

## 4. PCB Doctor Diagnostic System

**Location**: `projects/future/pcb-doctor/pcb-diagnostic/`

### Setup and Run:
```bash
# Navigate to project directory
cd projects/future/pcb-doctor/pcb-diagnostic

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run serve
```

**Access**: http://localhost:5176 (or next available port)

---

## 5. DEWS Safe-Domain Simulation

**Location**: `projects/future/dews-safe-sim/safety-simulation/`

### Setup and Run:
```bash
# Navigate to project directory
cd projects/future/dews-safe-sim/safety-simulation

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run serve
```

**Access**: http://localhost:5177 (or next available port)

---

## Quick Start Commands

### Run All Projects (Multiple Terminals)

Open separate terminal windows for each project:

**Terminal 1 - ULT Translator:**
```bash
cd projects/universal-translator/web-ui && npm run dev
```

**Terminal 2 - Balu Cyber Shield:**
```bash
cd projects/balu-cyber-shield/web-dashboard && npm run dev
```

**Terminal 3 - Universal AI System:**
```bash
cd projects/universal-ai-system/ai-assistant && npm run dev
```

**Terminal 4 - PCB Doctor:**
```bash
cd projects/future/pcb-doctor/pcb-diagnostic && npm run dev
```

**Terminal 5 - DEWS Safe Simulation:**
```bash
cd projects/future/dews-safe-sim/safety-simulation && npm run dev
```

---

## Troubleshooting

### Common Issues:

1. **Port Already in Use**
   - Solution: Vite will automatically use next available port
   - Or specify port: `npm run dev -- --port 3000`

2. **Dependencies Not Found**
   - Solution: Run `npm install` in the project directory
   - Clear cache: `rm -rf node_modules package-lock.json && npm install`

3. **TypeScript Errors**
   - Solution: Run `npm run typecheck` to see specific errors
   - Most projects will work despite some TypeScript warnings

4. **Build Failures**
   - Solution: Check if all dependencies are installed
   - Update dependencies: `npm update`

---

## Project Features

### ULT Translator Web UI
- Real-time translation dashboard
- Device management
- Language settings
- Session history

### Balu Cyber Shield Dashboard
- Security monitoring
- Threat detection
- Process tracking
- Security reports

### Universal AI System
- Multi-agent coordination
- Advanced tool system
- AI chat interface
- Agent orchestration

### PCB Doctor Diagnostic
- Circuit analysis
- Measurement tracking
- Fault detection
- Repair guidance

### DEWS Safe Simulation
- Energy monitoring
- Safety simulation
- Environment tracking
- Protective recommendations

---

## Development Notes

- Each project is completely independent
- No cross-project dependencies
- All use Vite as build tool
- React 18 + TypeScript
- Modern UI with TailwindCSS

For production deployment, use `npm run build` and deploy the `dist/` folder to any static hosting service.
