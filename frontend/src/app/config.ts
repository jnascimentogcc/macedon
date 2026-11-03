/** Deployment settings. Defaults match the dev stack in docker-compose.yml. */
export const APP_CONFIG = {
  apiUrl: 'http://127.0.0.1:8000',
  oidcAuthority: 'http://localhost:8080/realms/macedon',
  oidcClientId: 'macedon-web',
} as const;
