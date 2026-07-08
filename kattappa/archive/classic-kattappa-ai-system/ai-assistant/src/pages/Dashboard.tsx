import { Link } from 'wouter'

export default function Dashboard() {
  return (
    <div className="p-8 space-y-6">
      <div className="rounded-3xl border border-slate-700 bg-card p-8 shadow-lg shadow-black/10">
        <h1 className="text-3xl font-semibold text-white">Kattappa AI System</h1>
        <p className="mt-4 max-w-2xl text-slate-300">
          Your local multi-agent AI platform is ready. Use the chat interface to ask questions,
          coordinate tasks, and run code with the smart assistant.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/chat" className="rounded-lg bg-primary px-4 py-2 text-white shadow-lg shadow-primary/30 transition hover:bg-primary/90">
            Open Chat Interface
          </Link>
          <Link href="/models" className="rounded-lg border border-slate-600 px-4 py-2 text-slate-100 transition hover:border-slate-400">
            Manage Models
          </Link>
          <Link href="/settings" className="rounded-lg border border-slate-600 px-4 py-2 text-slate-100 transition hover:border-slate-400">
            Settings
          </Link>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="rounded-3xl border border-slate-700 bg-card p-6">
          <h2 className="text-xl font-semibold text-white">Quick Actions</h2>
          <ul className="mt-4 space-y-3 text-slate-300">
            <li>• Ask the AI anything in Chat.</li>
            <li>• Switch models and providers in Models.</li>
            <li>• Review automation Tasks and preferences.</li>
          </ul>
        </div>
        <div className="rounded-3xl border border-slate-700 bg-card p-6">
          <h2 className="text-xl font-semibold text-white">Status</h2>
          <p className="mt-4 text-slate-300">Local Python backend available via Electron bridge.</p>
        </div>
        <div className="rounded-3xl border border-slate-700 bg-card p-6">
          <h2 className="text-xl font-semibold text-white">Note</h2>
          <p className="mt-4 text-slate-300">If the local backend is not available, the chat interface will still work in demo mode.</p>
        </div>
      </div>
    </div>
  )
}
