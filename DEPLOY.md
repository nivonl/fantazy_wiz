# Deploying PitchMetric

Two pieces, two hosts: the React frontend on Netlify, the existing FastAPI backend on a
Python-friendly host (Railway used below — Render or Fly.io work the same way).

## 0. Push this repo

This `fantasy_app/` folder needs to be its own git repo (not the parent `fantazy_wiz/`, which
also has the unrelated `prev_project/`). If it isn't already:

```bash
cd fantasy_app
git init
git add .
git commit -m "Initial commit"
```

Push it to GitHub (or GitLab) — both Netlify and Railway deploy from a connected repo.

## 1. Backend — Railway

1. Sign up at railway.app, "New Project" -> "Deploy from GitHub repo" -> pick this repo.
2. Railway auto-detects Python via Nixpacks and uses the `Procfile` here (`web: uvicorn ...`).
   `nixpacks.toml` installs `libgomp1`, which PuLP's bundled solver needs at runtime.
3. In the service's **Variables** tab, add:
   - `FOOTBALL_DATA_TOKEN` = your token from football-data.org
   - `ALLOWED_ORIGINS` = your Netlify URL once you have it (e.g. `https://pitchmetric.netlify.app`) —
     optional; the backend defaults to allowing all origins, which is fine here (no auth, no
     secrets ever sent to the client), but you can lock it down once you know the real domain.
4. Railway assigns a public URL (Settings -> Networking -> "Generate Domain"). Copy it — you'll
   need it for the frontend's env var next.
5. Sanity check: open `<your-railway-url>/health` in a browser — should return `{"status":"ok"}`.

## 2. Frontend — Netlify

1. Sign up at netlify.com, "Add new site" -> "Import an existing project" -> connect the same
   repo.
2. Netlify reads `netlify.toml` at the repo root automatically (base dir `frontend/`, build
   command `npm run build`, publish dir `dist`) — no manual build config needed.
3. Before the first deploy, add an environment variable: Site settings -> Environment variables
   -> `VITE_API_BASE_URL` = the Railway URL from step 1 (no trailing slash).
4. Deploy. Netlify gives you a `*.netlify.app` URL, reachable from any browser — phone included.
5. If you set `ALLOWED_ORIGINS` on the backend, go back and set it to this exact Netlify URL,
   then redeploy the backend.

## Known gotchas

- **CBC solver errors on squad-building endpoints only** (`/recommend/fpl/build`,
  `/team-builder`, `/full`) but predictions work fine: missing `libgomp1` on the backend host —
  `nixpacks.toml` handles this for Railway; on Render, add a build command
  `apt-get update && apt-get install -y libgomp1 && pip install -r requirements.txt`.
- **First request after a while is slow**: free tiers on Railway/Render spin down idle
  services; the first request wakes it back up (10-30s), then it's normal speed.
- **`.env` never gets deployed** (it's gitignored, on purpose — it has your token in it).
  Environment variables must be set in each platform's dashboard instead, per the steps above.
