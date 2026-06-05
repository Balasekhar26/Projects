export default function Tasks() {
  return (
    <div className="p-8 space-y-6">
      <div className="rounded-3xl border border-slate-700 bg-card p-8 shadow-lg shadow-black/10">
        <h1 className="text-3xl font-semibold text-white">Task Automation</h1>
        <p className="mt-4 text-slate-300">
          Create, review, and execute automation workflows. This area helps you manage scheduled
          jobs, prompts, and multi-agent simulations.
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-3xl border border-slate-700 bg-card p-6">
          <h2 className="text-xl font-semibold text-white">Active Tasks</h2>
          <p className="mt-4 text-slate-300">No active tasks yet. Open the chat and begin a new simulation.</p>
        </div>
        <div className="rounded-3xl border border-slate-700 bg-card p-6">
          <h2 className="text-xl font-semibold text-white">Workflow Builder</h2>
          <p className="mt-4 text-slate-300">Define AI workflows, tool chains, and multi-agent coordination from the chat interface.</p>
        </div>
      </div>
    </div>
  )
}
