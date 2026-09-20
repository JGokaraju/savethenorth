/** @type {import('tailwindcss').Config} */
// Light government theme: white surfaces, grey rules, USWDS-style blue, Public Sans throughout.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    borderRadius: { none: "0", sm: "0", DEFAULT: "0", md: "0", lg: "0", xl: "0", "2xl": "0", "3xl": "0", full: "9999px" },
    boxShadow: { none: "none", sm: "none", DEFAULT: "none", md: "none", lg: "none", xl: "none", "2xl": "none" },
    extend: {
      fontFamily: {
        sans: ['"Public Sans"', '"Segoe UI"', "Helvetica", "Arial", "sans-serif"],
        display: ['"Public Sans"', '"Segoe UI"', "Helvetica", "Arial", "sans-serif"],
      },
      colors: {
        ink: "#1b1b1b",           // body text
        muted: "#565c65",         // secondary text
        page: "#ffffff",          // page background
        panel: "#f5f6f7",         // raised surface / table header
        panel2: "#edeff0",        // hover, secondary fill
        rule: "#dfe1e2",          // hairlines
        accent: { DEFAULT: "#005ea2", light: "#0071bc" },   // links, labels, primary action
        primary: { DEFAULT: "#005ea2", dark: "#1a4480", darker: "#162e51" },
        alert: { red: "#b50909", green: "#008817", amber: "#936f38", info: "#005ea2" },
      },
    },
  },
  plugins: [],
};
