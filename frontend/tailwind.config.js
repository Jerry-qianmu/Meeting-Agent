/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
        },
        secondary: {
          400: '#a78bfa',
          500: '#8b5cf6',
        },
        'soft-bg': '#f0f9ff',
        'soft-blue': '#dbeafe',
      },
    },
  },
  plugins: [],
}
