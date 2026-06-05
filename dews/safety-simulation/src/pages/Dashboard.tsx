import React from "react";

export default function Dashboard() {
  return (
    <div className="flex-1 space-y-4 p-8 pt-6">
      <div className="flex items-center justify-between space-y-2">
        <h2 className="text-3xl font-bold tracking-tight">DEWS Safety Simulation</h2>
      </div>
      
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border bg-card p-6">
          <h3 className="text-sm font-medium">Energy Status</h3>
          <div className="text-2xl font-bold">Normal</div>
          <p className="text-xs text-muted-foreground">All systems operational</p>
        </div>
        
        <div className="rounded-lg border bg-card p-6">
          <h3 className="text-sm font-medium">Environment</h3>
          <div className="text-2xl font-bold">Safe</div>
          <p className="text-xs text-muted-foreground">No anomalies detected</p>
        </div>
        
        <div className="rounded-lg border bg-card p-6">
          <h3 className="text-sm font-medium">Safety Level</h3>
          <div className="text-2xl font-bold">Green</div>
          <p className="text-xs text-muted-foreground">All safety systems active</p>
        </div>
        
        <div className="rounded-lg border bg-card p-6">
          <h3 className="text-sm font-medium">Simulation</h3>
          <div className="text-2xl font-bold">Active</div>
          <p className="text-xs text-muted-foreground">Running normally</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border bg-card p-6">
          <h3 className="text-lg font-semibold">Safety Monitoring</h3>
          <p className="text-muted-foreground">Real-time safety monitoring and protection systems</p>
        </div>
        
        <div className="rounded-lg border bg-card p-6">
          <h3 className="text-lg font-semibold">Energy Simulation</h3>
          <p className="text-muted-foreground">Energy environment modeling and simulation</p>
        </div>
      </div>
    </div>
  )
}
