/** @type {import('tailwindcss').Config} */
module.exports = {
	darkMode: ['class'],
	content: [
		'./pages/**/*.{ts,tsx}',
		'./components/**/*.{ts,tsx}',
		'./app/**/*.{ts,tsx}',
		'./src/**/*.{ts,tsx}',
	],
	theme: {
		container: {
			center: true,
			padding: '2rem',
			screens: {
				'2xl': '1400px',
			},
		},
		extend: {
			colors: {
				// Deep Indigo Theme for Krita AI
				primary: {
					900: '#1e1b4b',
					800: '#312e81', 
					700: '#4338ca',
					600: '#4f46e5',
					500: '#6366f1',
					DEFAULT: '#312e81',
					foreground: '#f1f5f9',
				},
				neutral: {
					900: '#0f172a',
					800: '#1e293b',
					700: '#334155', 
					400: '#94a3b8',
					200: '#e2e8f0',
					100: '#f1f5f9',
					DEFAULT: '#0f172a',
				},
				accent: {
					500: '#06b6d4',
					400: '#22d3ee',
					DEFAULT: '#06b6d4',
					glow: 'rgba(6, 182, 212, 0.5)',
					foreground: '#0f172a',
				},
				semantic: {
					success: '#10b981',
					warning: '#f59e0b', 
					error: '#ef4444',
					info: '#3b82f6',
				},
				// Shadcn/ui compatibility
				border: 'hsl(var(--border))',
				input: 'hsl(var(--input))',
				ring: 'hsl(var(--ring))',
				background: 'hsl(var(--background))',
				foreground: 'hsl(var(--foreground))',
				secondary: {
					DEFAULT: 'hsl(var(--secondary))',
					foreground: 'hsl(var(--secondary-foreground))',
				},
				destructive: {
					DEFAULT: 'hsl(var(--destructive))',
					foreground: 'hsl(var(--destructive-foreground))',
				},
				muted: {
					DEFAULT: 'hsl(var(--muted))',
					foreground: 'hsl(var(--muted-foreground))',
				},
				popover: {
					DEFAULT: 'hsl(var(--popover))',
					foreground: 'hsl(var(--popover-foreground))',
				},
				card: {
					DEFAULT: 'hsl(var(--card))',
					foreground: 'hsl(var(--card-foreground))',
				},
			},
			fontFamily: {
				sans: ['Inter', 'system-ui', 'sans-serif'],
				mono: ['JetBrains Mono', 'monospace'],
			},
			fontSize: {
				'xs': '10px',
				'sm': '12px', 
				'base': '13px',
				'md': '14px',
				'lg': '16px',
				'xl': '18px',
				'2xl': '24px',
			},
			spacing: {
				'sidebar-width': '64px',
				'sidebar-expanded': '240px', 
				'panel-width': '340px',
			},
			borderRadius: {
				'sm': '4px',
				'md': '6px', 
				'lg': '8px',
				'full': '9999px',
			},
			boxShadow: {
				'panel': '0 4px 6px -1px rgba(0, 0, 0, 0.3)',
				'floating': '0 10px 15px -3px rgba(0, 0, 0, 0.5)',
				'glow': '0 0 10px rgba(6, 182, 212, 0.3)',
			},
			animation: {
				'fast': '150ms ease-out',
				'normal': '250ms ease-in-out', 
				'slow': '400ms ease-in-out',
			},
			keyframes: {
				'accordion-down': {
					from: { height: 0 },
					to: { height: 'var(--radix-accordion-content-height)' },
				},
				'accordion-up': {
					from: { height: 'var(--radix-accordion-content-height)' },
					to: { height: 0 },
				},
			},
			animation: {
				'accordion-down': 'accordion-down 0.2s ease-out',
				'accordion-up': 'accordion-up 0.2s ease-out',
			},
		},
	},
	plugins: [require('tailwindcss-animate')],
}
