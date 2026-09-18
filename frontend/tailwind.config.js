/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          50: '#f1f5f9',
          600: '#1e293b',
          700: '#172033',
          800: '#111827',
          900: '#0b1220',
        },
        brand: {
          50: '#eef4ff',
          100: '#d9e5ff',
          200: '#b8ceff',
          400: '#5b8cf7',
          500: '#3b6fe0',
          600: '#2456c4',
          700: '#1c449b',
        },
      },
      boxShadow: {
        card: '0 1px 2px rgba(15, 23, 42, 0.06), 0 8px 24px -12px rgba(15, 23, 42, 0.18)',
      },
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', 'sans-serif'],
        mono: ['Consolas', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
