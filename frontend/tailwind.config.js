/** @type {import('tailwindcss').Config} */
// Dark editorial theme: deep teal-black surfaces, cream text, gold accents, serif display type.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    borderRadius: { none: "0", sm: "2px", DEFAULT: "2px", md: "2px", lg: "2px", xl: "2px", "2xl": "2px", "3xl": "2px", full: "9999px" },
    boxShadow: { none: "none", sm: "none", DEFAULT: "none", md: "none", lg: "none", xl: "none", "2xl": "none" },
    extend: {
      fontFamily: {
        sans: ['"Public Sans"', '"Segoe UI"', "Arial", "sans-serif"],
        display: ['"Playfair Display"', "Georgia", "serif"],
      },
      colors: {
        ink: "#f3f1ea",           // primary text on dark
        muted: "#9bacab",         // secondary text
        page: "#0b1719",          // page background
        panel: "#102124",         // raised surface
        panel2: "#16292c",        // hover / header rows
        rule: "#24393c",          // hairlines
        gold: { DEFAULT: "#c9a24a", light: "#e3c27c" },
        primary: { DEFAULT: "#3987e5", dark: "#2a78d6", darker: "#0b1719" },
        alert: { red: "#e05c4b", green: "#2fa96b", amber: "#e0a83c", info: "#4aa8c7" },
      },
    },
  },
  plugins: [],
};
