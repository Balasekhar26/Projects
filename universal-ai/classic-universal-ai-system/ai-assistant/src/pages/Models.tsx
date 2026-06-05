export default function Models() {
  return (
    <div className="p-8 space-y-6">
      <div className="rounded-3xl border border-slate-700 bg-card p-8 shadow-lg shadow-black/10">
        <h1 className="text-3xl font-semibold text-white">Model Management</h1>
        <p className="mt-4 text-slate-300">
          Select and configure your local AI providers. The interface is designed to support Ollama,
          NVIDIA NIM, and other local execution backends in the future.
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-3xl border border-slate-700 bg-card p-6">
          <h2 className="text-xl font-semibold text-white">Active Providers</h2>
          <div className="mt-4 space-y-3 text-slate-300">
            <div className="rounded-xl border border-slate-600 bg-slate-950 p-4">
              <p className="font-medium text-white">Ollama</p>
              <p className="text-sm text-slate-400">Local model provider for Mistral, Phi-3, and custom models.</p>
            </div>
            <div className="rounded-xl border border-slate-600 bg-slate-950 p-4">
              <p className="font-medium text-white">NVIDIA NIM</p>
              <p className="text-sm text-slate-400">Hardware-accelerated provider if configured.</p>
            </div>
          </div>
        </div>
        <div className="rounded-3xl border border-slate-700 bg-card p-6">
          <h2 className="text-xl font-semibold text-white">Available Models</h2>
          <div className="mt-4 space-y-3 text-slate-300">
            <div className="rounded-xl border border-slate-600 bg-slate-950 p-4">mistral</div>
            <div className="rounded-xl border border-slate-600 bg-slate-950 p-4">phi3</div>
            <div className="rounded-xl border border-slate-600 bg-slate-950 p-4">custom local models</div>
          </div>
        </div>
      </div>
    </div>
  )
}
