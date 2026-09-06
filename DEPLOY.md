# Deploying PitchMetric

Both pieces live in one Railway project as two services from the same repo: the FastAPI backend
(root directory `.`) and the React frontend (root directory `frontend`). One dashboard, one
billing plan, no Netlify build-minute ceiling.

## 0. Push this repo

This `fantasy_app/` folder needs to be its own git repo (not the parent `fantazy_wiz/`, which
also has the unrelated `prev_project/`). If it isn't already:

```bash
cd fantasy_app
git init
git add .
git commit -m "Initial commit"
```

Push it to GitHub (or GitLab) — Railway deploys from a connected repo.

## 1. Backend service

1. Sign up at railway.app, "New Project" -> "Deploy from GitHub repo" -> pick this repo.
2. Railway auto-detects Python via Nixpacks and uses the `Procfile` here (`web: uvicorn ...`).
   `nixpacks.toml` installs `libgomp1`, which PuLP's bundled solver needs at runtime.
3. In the service's **Variables** tab, add:
   - `FOOTBALL_DATA_TOKEN` = your token from football-data.org
   - `ALLOWED_ORIGINS` = the frontend's Railway domain from step 2 below, once you have it —
     optional; the backend defaults to allowing all origins, which is fine here (no auth, no
     secrets ever sent to the client), but you can lock it down once you know the real domain.
4. Railway assigns a public URL (Settings -> Networking -> "Generate Domain"). Copy it — you'll
   need it for the frontend's env var next.
5. Sanity check: open `<your-railway-url>/health` in a browser — should return `{"status":"ok"}`.

## 2. Frontend service (same Railway project)

1. In the same project, "New" -> "GitHub Repo" -> the same repo again, as a second service.
2. Service **Settings -> Root Directory** -> set to `frontend`. Railway's Nixpacks builder
   detects the Node project, runs `npm install` then `npm run build` (which runs `vite build`
   and the static-page prerender step, producing 650+ real static pages — one per player, one
   per blog post, plus the core pages), and starts it with `frontend/Procfile`
   (`web: serve dist -l $PORT`).
   - Deliberately **not** `serve -s` (single-page-app mode): tested locally, `-s` serves the
     bare SPA shell for `/blog` and every static page instead of the real prerendered HTML —
     it doesn't do directory-index resolution, only literal-file-or-fallback. `frontend/public/
     serve.json` (copied into `dist/` by the Vite build) fixes this the explicit way: plain
     `serve` already resolves `/blog` -> `dist/blog/index.html` correctly, and `serve.json`'s
     `rewrites` list adds `index.html` fallback for only the handful of real client-only SPA
     routes (`/fpl-team-analyzer`, `/methodology`, etc. — see `frontend/src/nav-items.js` for
     the full list). A path matching neither still 404s, instead of Netlify's old blanket
     catch-all silently serving the wrong content for typos too.
3. Before the first deploy, add a **Variable** on this service: `VITE_API_BASE_URL` = the
   backend's Railway URL from step 1 (no trailing slash). Vite bakes this in at build time, so
   changing it later means triggering a redeploy, not just restarting.
4. Deploy. Railway assigns this service its own `*.up.railway.app` URL too — confirm the site
   loads and talks to the backend before moving the real domain over.
5. If you set `ALLOWED_ORIGINS` on the backend, go back and set it to this frontend's real
   domain (`https://pitchmetricai.com`, once step 3 below is done), then redeploy the backend.

## 3. Point pitchmetricai.com at the new frontend service

The domain itself doesn't move between registrars or hosts — only its DNS record changes what
it points to.

1. On the frontend service: **Settings -> Networking -> Custom Domain** -> enter
   `pitchmetricai.com` (and `www.pitchmetricai.com` if you use both). Railway shows the exact
   DNS record (type + value) it needs — usually a `CNAME` pointing at a Railway-provided target.
2. Log into wherever the domain's DNS is managed (your registrar, or Cloudflare/etc. if you use
   a separate DNS host — not necessarily where you bought the domain) and replace the existing
   record that points at Netlify with the one Railway just gave you.
   - Apex/root domains (`pitchmetricai.com` with no `www`) can't take a plain CNAME per the DNS
     spec. If your DNS provider offers CNAME flattening / ALIAS / ANAME records (Cloudflare,
     Namecheap, and most modern providers do), use that at the apex and a normal CNAME for
     `www`. If it doesn't, point the apex at whatever A/ALIAS record Railway's custom-domain
     screen provides for that case, or redirect the apex to `www` and put the CNAME there.
3. DNS propagation is usually minutes, occasionally a few hours. Once `pitchmetricai.com`
   resolves to Railway, remove the site from Netlify (or just let it sit idle — no rush).
4. Pick **one** canonical host name and make sure the other actually redirects to it, rather
   than both serving identical content — `www.pitchmetricai.com` and `pitchmetricai.com` are,
   as far as Google's concerned, two different pages unless one visibly 301s to the other.
   Railway's custom-domain screen redirects http -> https automatically; a `www` -> apex (or
   apex -> `www`) redirect is usually a checkbox on the same screen, or a rule at your DNS/CDN
   provider if you're using one in front of Railway (e.g. Cloudflare).

## 4. Google Search Console, after the domain is live

1. If `pitchmetricai.com` is already a verified property (it should be, given the indexing
   report that prompted this), no re-verification is needed — GSC verifies the domain, not the
   host behind it, so moving from Netlify to Railway doesn't affect it.
2. **Search Console -> Sitemaps** -> submit `https://pitchmetricai.com/sitemap.xml` again (or
   resubmit the existing one) so Google picks up this build's URLs — every static page's
   canonical URL now matches its sitemap entry and its own internal links exactly (see below),
   which it didn't before.
3. **Search Console -> URL Inspection** -> paste a couple of the specific URLs GSC listed under
   "Page with redirect" or "Crawled - currently not indexed" and hit "Request indexing" once
   they're live on the new domain. Re-indexing is on Google's own schedule (days, sometimes a
   couple of weeks) — requesting it doesn't force an immediate recrawl, just queues it sooner
   than waiting for the next natural crawl pass.

## Known gotchas

- **CBC solver errors on squad-building endpoints only** (`/recommend/fpl/build`,
  `/team-builder`, `/full`) but predictions work fine: missing `libgomp1` on the backend host —
  `nixpacks.toml` handles this for Railway; on Render, add a build command
  `apt-get update && apt-get install -y libgomp1 && pip install -r requirements.txt`.
- **First request after a while is slow**: free tiers on Railway/Render spin down idle
  services; the first request wakes it back up (10-30s), then it's normal speed.
- **`.env` never gets deployed** (it's gitignored, on purpose — it has your token in it).
  Environment variables must be set in each platform's dashboard instead, per the steps above.
