import { ReactNode } from 'react'
import { Link, useLocation } from 'wouter'

const navigation = [
  { href: '/', label: 'Dashboard' },
  { href: '/chat', label: 'Chat' },
  { href: '/models', label: 'Models' },
  { href: '/tasks', label: 'Tasks' },
  { href: '/settings', label: 'Settings' },
]

interface SidebarProps {
  children: ReactNode
}

export function Sidebar({ children }: SidebarProps) {
  const [location] = useLocation()

  return (
    <div className="flex h-screen overflow-hidden bg-background text-slate-100">
      <aside className="w-72 border-r border-slate-800 bg-card p-5">
        <div className="mb-8">
          <div className="text-2xl font-semibold text-white">Kattappa</div>
          <p className="mt-2 text-sm text-slate-400">Local multi-agent assistant</p>
        </div>
        <nav className="space-y-2">
          {navigation.map((item) => {
            const isActive = location === item.href
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`block rounded-2xl px-4 py-3 text-sm font-medium transition ${
                  isActive
                    ? 'bg-primary text-white shadow-lg shadow-primary/20'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`}
              >
                {item.label}
              </Link>
            )
          })}
        </nav>
        <div className="mt-10 rounded-3xl border border-slate-700 bg-slate-950 p-4 text-sm text-slate-300">
          <p className="font-medium text-white">Fast access</p>
          <p className="mt-3 leading-6">Your AI assistant is ready. Open chat and start a new conversation immediately.</p>
        </div>
      </aside>
      <main className="flex-1 overflow-auto bg-background">{children}</main>
    </div>
  )
}
