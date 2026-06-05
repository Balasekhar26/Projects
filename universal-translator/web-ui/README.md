# ULT Translator Web UI

A modern React-based web interface for the Universal Language Translator system.

## Features

- Real-time audio translation dashboard
- Device management and configuration
- Language settings and preferences
- Session history and analytics
- Modern UI with TailwindCSS and Radix components

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
web-ui/
├── src/
│   ├── components/     # Reusable UI components
│   ├── pages/         # Page components
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

The web UI is designed to work independently as a standalone application. It communicates with the ULT Translator backend through REST APIs.

### Key Pages

- **Dashboard** - Overview and quick actions
- **Translate** - Real-time translation interface
- **Sessions** - Translation history and analytics
- **Devices** - Audio device configuration
- **Languages** - Language settings
- **Settings** - Application preferences

## Building and Deployment

```bash
# Build for production
npm run build

# The build output will be in the `dist/` directory
# This can be deployed to any static hosting service
```

## License

This project is part of the ULT Translator system.
