import { Link } from 'wouter'

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-8">
      <div className="max-w-xl rounded-3xl border border-slate-700 bg-card p-10 text-center shadow-xl shadow-black/20">
        <h1 className="text-4xl font-semibold text-white">Page Not Found</h1>
        <p className="mt-4 text-slate-300">The page you are looking for doesn’t exist or has moved.</p>
        <Link href="/" className="mt-8 inline-flex rounded-lg bg-primary px-5 py-3 text-white transition hover:bg-primary/90">
          Back to Dashboard
        </Link>
      </div>
    </div>
  )
}
