import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: '#0b1220',
        card: '#111827',
        muted: '#1f2937',
        'muted-foreground': '#94a3b8',
        primary: '#7c3aed',
        'primary-foreground': '#ffffff',
        accent: '#475569',
        'accent-foreground': '#f8fafc',
      },
    },
  },
  plugins: [],
} satisfies Config
