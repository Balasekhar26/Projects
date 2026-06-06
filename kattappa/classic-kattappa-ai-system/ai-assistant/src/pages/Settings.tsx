export default function Settings() {
  return (
    <div className="p-8 space-y-6">
      <div className="rounded-3xl border border-slate-700 bg-card p-8 shadow-lg shadow-black/10">
        <h1 className="text-3xl font-semibold text-white">Settings</h1>
        <p className="mt-4 text-slate-300">
          Configure your chat environment, AI provider defaults, and local workspace settings.
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-3xl border border-slate-700 bg-card p-6">
          <h2 className="text-xl font-semibold text-white">Backend</h2>
          <p className="mt-4 text-slate-300">Choose the local AI backend and verify the Python/AI runtime integration.</p>
        </div>
        <div className="rounded-3xl border border-slate-700 bg-card p-6">
          <h2 className="text-xl font-semibold text-white">Interface</h2>
          <p className="mt-4 text-slate-300">Adjust chat, session, and agent coordination preferences.</p>
        </div>
      </div>
    </div>
  )
}
