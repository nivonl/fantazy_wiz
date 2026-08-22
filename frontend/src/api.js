// Talks to the PitchMetric FastAPI backend. In dev this is localhost:8000 (CORS is enabled
// there for exactly this reason); in production, Netlify build-time env var VITE_API_BASE_URL
// points at wherever the backend is actually hosted (Railway/Render/Fly.io/etc).
const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, { method = "GET", body } = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data && data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return data;
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body }),
};

export { API_BASE };
