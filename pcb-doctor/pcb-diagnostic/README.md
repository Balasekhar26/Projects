# PCB Doctor Diagnostic System

A comprehensive PCB diagnostic and troubleshooting system for circuit board analysis and repair.

## Features

- Interactive diagnostic interface
- Measurement tracking and analysis
- Fault pattern recognition
- Repair guidance and recommendations
- Component database management

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn

### Installation

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run serve
```

## Project Structure

```
pcb-diagnostic/
├── src/
│   ├── components/     # Reusable UI components
│   ├── pages/         # Diagnostic pages
│   ├── lib/           # Utility functions
│   └── App.tsx        # Main application component
├── public/            # Static assets
├── package.json       # Dependencies and scripts
├── vite.config.ts     # Vite configuration
└── tsconfig.json      # TypeScript configuration
```

## Technology Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool
- **TailwindCSS** - Styling
- **Wouter** - Routing
- **React Query** - State management

## Development

The PCB diagnostic system is designed to work independently as a standalone application. It provides tools for PCB analysis and troubleshooting.

### Key Pages

- **Dashboard** - Diagnostic overview
- **Diagnosis** - Interactive diagnostic tools
- **Measurements** - Measurement tracking
- **Database** - Fault pattern database
- **Settings** - Diagnostic preferences

## Diagnostic Capabilities

- Component testing
- Voltage analysis
- Circuit tracing
- Fault identification
- Repair recommendations

## Building and Deployment

```bash
# Build for production
npm run build

# The build output will be in the `dist/` directory
# This can be deployed to any static hosting service
```

## License

This project is part of the PCB Doctor system.
