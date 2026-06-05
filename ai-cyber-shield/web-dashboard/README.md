# Balu Cyber Shield Web Dashboard

A comprehensive security monitoring and management dashboard for the Balu Cyber Shield system.

## Features

- Real-time security monitoring
- Threat detection and analysis
- Process and network monitoring
- Security event logging
- Interactive dashboard with alerts

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
web-dashboard/
├── src/
│   ├── components/     # Reusable UI components
│   ├── pages/         # Security monitoring pages
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
- **Radix UI** - Component primitives
- **Wouter** - Routing
- **React Query** - State management

## Development

The web dashboard is designed to work independently as a standalone application. It communicates with the Balu Cyber Shield backend through REST APIs.

### Key Pages

- **Dashboard** - Security overview and status
- **Threats** - Threat detection and analysis
- **Processes** - Process monitoring
- **Network** - Network activity monitoring
- **Reports** - Security reports and logs
- **Settings** - Security configuration

## Security Features

- Real-time threat monitoring
- Process inventory and analysis
- Network connection tracking
- Security event logging
- Alert system for suspicious activities

## Building and Deployment

```bash
# Build for production
npm run build

# The build output will be in the `dist/` directory
# This can be deployed to any static hosting service
```

## License

This project is part of the Balu Cyber Shield system.
