# Macedon web

Angular 22 + Tailwind CSS 4 + SpartanNG client for the Macedon API. It holds no business or access
rules: it signs in through Keycloak (Authorization Code + PKCE) and calls the API with the access
token. The design system is `../docs/ui-spec.md`; the screens are described in
`../docs/features/documents-ui.md`.

```bash
npm ci
npm start          # http://localhost:4200, needs the dev stack and the API on :8000
npm test           # unit tests (Vitest)
npm run build
```

Deployment settings (API URL, OIDC authority and client) live in `src/app/config.ts`. Spartan
primitives are generated into `src/app/ui` (`npx ng g @spartan-ng/cli:ui <name>`); the theme tokens
in `src/styles.css` come from the UI spec.
