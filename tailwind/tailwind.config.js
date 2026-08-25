/**
 * Tailwind config for Nebulae.
 *
 * Replaces the cdn.tailwindcss.com <script> that used to run in every
 * visitor's browser. That script was the Tailwind "Play CDN": it shipped a
 * ~400KB compiler to every device and rebuilt the stylesheet on every page
 * load, and it meant a node with no internet access rendered unstyled.
 *
 * This produces a plain static CSS file containing only the classes the
 * templates actually use.
 */
module.exports = {
  // Templates use dark: variants (e.g. dark:bg-gray-700), and the theme is
  // toggled by adding .dark to <html>. This MUST stay 'class' - the default
  // ('media') would follow the OS setting and ignore the user's choice.
  darkMode: 'class',

  content: [
    './templates/**/*.html',
    './static/js/**/*.js',
  ],

  // Anything built at runtime in JS (e.g. 'bg-' + colour) is invisible to the
  // scanner above and would be stripped. Add those class names here.
  // Check app.js for className assignments before your first build.
  safelist: [
    // 'bg-green-100', 'text-green-800',
  ],

  theme: {
    extend: {
      // style.css sets body { font-family: 'Inter', sans-serif } already;
      // this keeps Tailwind's own font-sans utility consistent with it.
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },

  plugins: [],
}
