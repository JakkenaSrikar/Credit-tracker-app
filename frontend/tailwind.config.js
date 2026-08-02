/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ledger: {
          bg: '#FAF9F6',       // Warm off-white/cream paper color
          card: '#FFFFFF',     // Clean white cards
          primary: '#4F46E5',  // Deep Indigo
          text: '#1F2937',     // Slate/grey dark text
          muted: '#6B7280',    // Slate/grey muted text
          credit: '#E53E3E',   // Crimson Red for Credit (debt)
          payment: '#38A169',  // Emerald Green for Payments
          hover: '#F3F4F6',    // Soft grey hover
        }
      },
      fontFamily: {
        sans: ['Outfit', 'Inter', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
