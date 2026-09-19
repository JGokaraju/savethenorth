/** @type {import('tailwindcss').Config} */
// Government-service style: square corners, no shadows, restrained palette (USWDS-like tokens).
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    borderRadius: { none: "0", sm: "2px", DEFAULT: "2px", md: "2px", lg: "2px", xl: "2px", "2xl": "2px", "3xl": "2px", full: "9999px" },
    boxShadow: { none: "none", sm: "none", DEFAULT: "none", md: "none", lg: "none", xl: "none", "2xl": "none" },
    extend: {
      fontFamily: { sans: ['"Public Sans"', '"Source Sans 3"', '"Segoe UI"', "Arial", "sans-serif"] },
      colors: {
        ink: "#1b1b1b", muted: "#565c65", rule: "#dfe1e2", paper: "#f0f0f0",
        primary: { DEFAULT: "#005ea2", dark: "#1a4480", darker: "#162e51" },
        alert: { red: "#b50909", green: "#00a91c", amber: "#ffbe2e", info: "#00bde3" },
      },
    },
  },
  plugins: [],
};
