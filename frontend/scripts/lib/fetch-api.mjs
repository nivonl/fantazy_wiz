// Reuses the same env var the frontend build already uses (VITE_API_BASE_URL) so no new
// Netlify env var needs configuring for this to work in CI.
export const API_BASE = process.env.VITE_API_BASE_URL || "https://fantazywiz.up.railway.app";

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Railway's free tier cold-starts after idling (documented: first request can take 10-30s) --
 * hammering it with hundreds of requests immediately would be unreliable without this. */
export async function warmUpBackend(maxAttempts = 10, delayMs = 3000) {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(15000) });
      if (res.ok) {
        console.log(`Backend warm after ${attempt} attempt(s).`);
        return;
      }
    } catch {
      // fall through to retry
    }
    console.log(`Backend not ready yet (attempt ${attempt}/${maxAttempts}), retrying...`);
    await sleep(delayMs);
  }
  throw new Error(`Backend at ${API_BASE} never responded to /health after ${maxAttempts} attempts.`);
}

export async function fetchJson(path, { retries = 3, timeoutMs = 30000 } = {}) {
  let lastError;
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(timeoutMs) });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
      return await res.json();
    } catch (err) {
      lastError = err;
      if (attempt < retries) await sleep(1000 * attempt);
    }
  }
  throw lastError;
}

/** Runs `fn` over `items` with at most `concurrency` in flight at once. Never throws for an
 * individual item's failure -- callers get { item, result, error } per item and decide how to
 * degrade (e.g. render a page without one optional section rather than failing the whole
 * build), matching this project's existing "a hiccup degrades, doesn't crash" philosophy. */
export async function mapWithConcurrency(items, concurrency, fn) {
  const results = new Array(items.length);
  let nextIndex = 0;

  async function worker() {
    while (true) {
      const i = nextIndex++;
      if (i >= items.length) return;
      try {
        results[i] = { item: items[i], result: await fn(items[i]), error: null };
      } catch (error) {
        results[i] = { item: items[i], result: null, error };
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, worker));
  return results;
}
