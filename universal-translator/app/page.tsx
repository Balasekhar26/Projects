"use client";

import { useEffect, useState } from "react";
import EnhancedDashboard from "./components/enhanced-dashboard";
import { FirstRunWizardComponent } from "./components/first-run-wizard/wizard";

export default function Page() {
  const [isFirstRun, setIsFirstRun] = useState<boolean | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    checkFirstRun();
    initializeDatabase();
  }, []);

  const initializeDatabase = async () => {
    try {
      await fetch("/api/db/init");
    } catch (error) {
      console.warn("Database initialization failed:", error);
    }
  };

  const checkFirstRun = async () => {
    try {
      // Check if setup is complete by looking for a completion marker
      const response = await fetch("/api/setup-status");
      const data = await response.json();
      setIsFirstRun(!data.isSetupComplete);
    } catch (error) {
      console.warn("Could not check setup status, assuming first run:", error);
      setIsFirstRun(true);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSetupComplete = () => {
    setIsFirstRun(false);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading Universal Language Translator...</p>
        </div>
      </div>
    );
  }

  if (isFirstRun) {
    return <FirstRunWizardComponent onComplete={handleSetupComplete} />;
  }

  return <EnhancedDashboard />;
}
