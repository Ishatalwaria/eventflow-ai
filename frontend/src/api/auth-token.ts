let apiToken: string | null = null;

export function getApiToken() { return apiToken; }
export function setApiToken(token: string | null) { apiToken = token?.trim() || null; }
export function clearApiToken() { apiToken = null; }
