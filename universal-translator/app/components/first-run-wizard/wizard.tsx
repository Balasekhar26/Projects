"use client";

import { useEffect, useState } from "react";

interface WizardStep {
  id: string;
  title: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  logs: string[];
  result?: unknown;
}

interface WizardState {
  currentStep: number;
  totalSteps: number;
  isRunning: boolean;
  isComplete: boolean;
  steps: WizardStep[];
  error?: string;
}

export function FirstRunWizardComponent({ onComplete }: { onComplete?: () => void }) {
  const [wizardState, setWizardState] = useState<WizardState>({
    currentStep: 0,
    totalSteps: 8,
    isRunning: false,
    isComplete: false,
    steps: [
      {
        id: "welcome",
        title: "Welcome to Universal Language Translator",
        description: "Setting up your real-time audio translation engine",
        status: 'pending',
        logs: []
      },
      {
        id: "check-dependencies",
        title: "Checking System Dependencies",
        description: "Verifying required components are installed",
        status: 'pending',
        logs: []
      },
      {
        id: "audio-devices",
        title: "Configuring Audio Devices",
        description: "Setting up microphone and speaker routing",
        status: 'pending',
        logs: []
      },
      {
        id: "download-models",
        title: "Downloading AI Models",
        description: "Fetching speech-to-text and translation models",
        status: 'pending',
        logs: []
      },
      {
        id: "language-selection",
        title: "Selecting Languages",
        description: "Choose source and target languages",
        status: 'pending',
        logs: []
      },
      {
        id: "voice-profile",
        title: "Voice Profile Setup",
        description: "Configure voice preservation settings (optional)",
        status: 'pending',
        logs: []
      },
      {
        id: "diagnostics",
        title: "Running System Diagnostics",
        description: "Testing audio pipeline and performance",
        status: 'pending',
        logs: []
      },
      {
        id: "completion",
        title: "Setup Complete",
        description: "Ready to translate in real-time",
        status: 'pending',
        logs: []
      }
    ]
  });

  const [selectedLanguages, setSelectedLanguages] = useState({
    source: 'en',
    target: 'te'
  });

  const [voiceProfileChoice, setVoiceProfileChoice] = useState<'skip' | 'system' | 'openai' | 'xtts' | 'elevenlabs'>('skip');

  const supportedLanguages = [
    { code: "en", name: "English" },
    { code: "te", name: "Telugu" },
    { code: "hi", name: "Hindi" },
    { code: "es", name: "Spanish" },
    { code: "fr", name: "French" },
    { code: "de", name: "German" },
    { code: "zh", name: "Mandarin Chinese" },
    { code: "ja", name: "Japanese" }
  ];

  useEffect(() => {
    const pollWizardState = () => {
      fetch('/api/wizard')
        .then(res => res.json())
        .then(data => {
          setWizardState(prev => ({
            ...prev,
            ...data,
            steps: data.steps || prev.steps
          }));

          if (data.isComplete && onComplete) {
            onComplete();
          }
        })
        .catch(error => {
          console.error('Failed to poll wizard state:', error);
        });
    };

    if (wizardState.isRunning) {
      const interval = setInterval(pollWizardState, 1000);
      return () => clearInterval(interval);
    }
  }, [wizardState.isRunning, onComplete]);

  const startWizard = async () => {
    try {
      const response = await fetch('/api/wizard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'start' })
      });

      if (response.ok) {
        setWizardState(prev => ({ ...prev, isRunning: true, error: undefined }));
      } else {
        const error = await response.json();
        setWizardState(prev => ({ ...prev, error: error.error }));
      }
    } catch (error) {
      console.error('Failed to start wizard:', error);
      setWizardState(prev => ({ ...prev, error: 'Failed to start setup wizard' }));
    }
  };

  const stopWizard = async () => {
    try {
      await fetch('/api/wizard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'stop' })
      });
      setWizardState(prev => ({ ...prev, isRunning: false }));
    } catch (error) {
      console.error('Failed to stop wizard:', error);
    }
  };

  const updateStepLogs = (stepId: string, newLogs: string[]) => {
    setWizardState(prev => ({
      ...prev,
      steps: prev.steps.map(step =>
        step.id === stepId
          ? { ...step, logs: [...step.logs, ...newLogs] }
          : step
      )
    }));
  };

  const updateStepStatus = (stepId: string, status: WizardStep['status']) => {
    setWizardState(prev => ({
      ...prev,
      steps: prev.steps.map(step =>
        step.id === stepId
          ? { ...step, status }
          : step
      )
    }));
  };

  const handleLanguageChange = (type: 'source' | 'target', value: string) => {
    setSelectedLanguages(prev => ({ ...prev, [type]: value }));
  };

  const handleVoiceProfileChange = (choice: typeof voiceProfileChoice) => {
    setVoiceProfileChoice(choice);
  };

  const renderStepContent = (step: WizardStep) => {
    switch (step.id) {
      case 'language-selection':
        return (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Source Language
                </label>
                <select
                  value={selectedLanguages.source}
                  onChange={(e) => handleLanguageChange('source', e.target.value)}
                  className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  {supportedLanguages.map(lang => (
                    <option key={lang.code} value={lang.code}>
                      {lang.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Target Language
                </label>
                <select
                  value={selectedLanguages.target}
                  onChange={(e) => handleLanguageChange('target', e.target.value)}
                  className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  {supportedLanguages.map(lang => (
                    <option key={lang.code} value={lang.code}>
                      {lang.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <p className="text-sm text-gray-600">
              Selected: {supportedLanguages.find(l => l.code === selectedLanguages.source)?.name} → {supportedLanguages.find(l => l.code === selectedLanguages.target)?.name}
            </p>
          </div>
        );

      case 'voice-profile':
        return (
          <div className="space-y-4">
            <div className="space-y-3">
              <label className="flex items-center space-x-3">
                <input
                  type="radio"
                  name="voice-profile"
                  value="skip"
                  checked={voiceProfileChoice === 'skip'}
                  onChange={() => handleVoiceProfileChange('skip')}
                  className="text-blue-600 focus:ring-blue-500"
                />
                <div>
                  <div className="font-medium">Skip for now</div>
                  <div className="text-sm text-gray-600">Configure voice settings later</div>
                </div>
              </label>

              <label className="flex items-center space-x-3">
                <input
                  type="radio"
                  name="voice-profile"
                  value="system"
                  checked={voiceProfileChoice === 'system'}
                  onChange={() => handleVoiceProfileChange('system')}
                  className="text-blue-600 focus:ring-blue-500"
                />
                <div>
                  <div className="font-medium">System Voices</div>
                  <div className="text-sm text-gray-600">Basic quality, always available offline</div>
                </div>
              </label>

              <label className="flex items-center space-x-3">
                <input
                  type="radio"
                  name="voice-profile"
                  value="openai"
                  checked={voiceProfileChoice === 'openai'}
                  onChange={() => handleVoiceProfileChange('openai')}
                  className="text-blue-600 focus:ring-blue-500"
                />
                <div>
                  <div className="font-medium">OpenAI TTS</div>
                  <div className="text-sm text-gray-600">High quality, requires internet connection</div>
                </div>
              </label>

              <label className="flex items-center space-x-3">
                <input
                  type="radio"
                  name="voice-profile"
                  value="elevenlabs"
                  checked={voiceProfileChoice === 'elevenlabs'}
                  onChange={() => handleVoiceProfileChange('elevenlabs')}
                  className="text-blue-600 focus:ring-blue-500"
                />
                <div>
                  <div className="font-medium">ElevenLabs Voice Clone</div>
                  <div className="text-sm text-gray-600">Premium voice cloning, highest quality (requires API key)</div>
                </div>
              </label>

              <label className="flex items-center space-x-3">
                <input
                  type="radio"
                  name="voice-profile"
                  value="xtts"
                  checked={voiceProfileChoice === 'xtts'}
                  onChange={() => handleVoiceProfileChange('xtts')}
                  className="text-blue-600 focus:ring-blue-500"
                />
                <div>
                  <div className="font-medium">XTTS Voice Clone</div>
                  <div className="text-sm text-gray-600">Custom voice preservation, works offline</div>
                </div>
              </label>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Universal Language Translator Setup
          </h1>
          <p className="text-lg text-gray-600">
            Let&apos;s get your real-time translation system ready
          </p>
        </div>

        {/* Progress Bar */}
        <div className="mb-8">
          <div className="flex justify-between items-center mb-2">
            <span className="text-sm font-medium text-gray-700">
              Step {wizardState.currentStep + 1} of {wizardState.totalSteps}
            </span>
            <span className="text-sm text-gray-500">
              {Math.round(((wizardState.currentStep + 1) / wizardState.totalSteps) * 100)}% Complete
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${((wizardState.currentStep + 1) / wizardState.totalSteps) * 100}%` }}
            ></div>
          </div>
        </div>

        {/* Error Display */}
        {wizardState.error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-md">
            <div className="flex">
              <div className="text-red-400">⚠</div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-red-800">Setup Error</h3>
                <p className="text-sm text-red-700 mt-1">{wizardState.error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Steps */}
        <div className="space-y-4 mb-8">
          {wizardState.steps.map((step, index) => (
            <div
              key={step.id}
              className={`p-4 rounded-lg border transition-all ${
                index === wizardState.currentStep && wizardState.isRunning
                  ? 'border-blue-300 bg-blue-50 shadow-md'
                  : step.status === 'completed'
                  ? 'border-green-300 bg-green-50'
                  : step.status === 'error'
                  ? 'border-red-300 bg-red-50'
                  : 'border-gray-200 bg-white'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center space-x-3">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                    step.status === 'completed'
                      ? 'bg-green-100 text-green-800'
                      : step.status === 'error'
                      ? 'bg-red-100 text-red-800'
                      : index === wizardState.currentStep && wizardState.isRunning
                      ? 'bg-blue-100 text-blue-800'
                      : 'bg-gray-100 text-gray-600'
                  }`}>
                    {step.status === 'completed' ? '✓' :
                     step.status === 'error' ? '✗' :
                     index + 1}
                  </div>
                  <div>
                    <h3 className="font-medium text-gray-900">{step.title}</h3>
                    <p className="text-sm text-gray-600">{step.description}</p>
                  </div>
                </div>
                <div className="text-sm font-medium">
                  {step.status === 'completed' && <span className="text-green-600">Complete</span>}
                  {step.status === 'error' && <span className="text-red-600">Error</span>}
                  {step.status === 'running' && <span className="text-blue-600">Running...</span>}
                  {step.status === 'pending' && <span className="text-gray-500">Pending</span>}
                </div>
              </div>

              {/* Interactive Content for Current Step */}
              {index === wizardState.currentStep && wizardState.isRunning && renderStepContent(step)}

              {/* Logs */}
              {step.logs.length > 0 && (
                <div className="mt-3 p-3 bg-gray-50 rounded-md">
                  <div className="text-xs font-mono text-gray-700 space-y-1 max-h-32 overflow-y-auto">
                    {step.logs.map((log, logIndex) => (
                      <div key={logIndex}>{log}</div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Controls */}
        <div className="flex justify-center space-x-4">
          {!wizardState.isRunning && !wizardState.isComplete && (
            <button
              onClick={startWizard}
              className="px-8 py-3 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
            >
              Start Setup
            </button>
          )}

          {wizardState.isComplete && (
            <button
              onClick={() => window.location.reload()}
              className="px-8 py-3 bg-green-600 text-white font-medium rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 transition-colors"
            >
              Continue to Translator
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
