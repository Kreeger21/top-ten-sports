# UI design toolkit

This toolkit is development-only. Installing it does not alter the Flask app or its production requirements.

## What is available

- Tailwind CSS and Open Props for utilities, design tokens, colors, shadows, spacing, and motion
- Sass, PostCSS, and Autoprefixer for advanced CSS authoring and browser compatibility
- Font Awesome, Lucide, and Tabler for broad icon coverage
- Inter and Oswald as locally packaged UI and sports-display fonts
- Prettier and its Jinja plugin for formatting templates and stylesheets
- Stylelint for CSS quality checks
- Axe Core for accessibility testing
- Color.js for color conversion, contrast work, and palette generation

## Commands

Run these commands directly from PowerShell in the project directory:

```powershell
.\node_modules\.bin\stylelint.cmd "static/**/*.css"
.\node_modules\.bin\prettier.cmd --check "templates/**/*.html" "static/**/*.css"
.\node_modules\.bin\tailwindcss.cmd --help
```

Codex can also run the shorter `pnpm ui:lint` and `pnpm ui:format:check` package scripts through its bundled pnpm runtime.

Package lifecycle scripts are disabled in `.npmrc` for a safer design environment. The app does not import any of these packages yet. Add assets deliberately as individual UI changes are designed and tested.
