# Deployment

NEXUS ships as a single Docker image containing both the Cortex API and the
compiled Second Brain UI. Two hosting shapes are supported:

| Shape | Backend | Frontend | When |
|---|---|---|---|
| **Single origin** | Railway (Docker) | served by the same container at `/` | simplest, no CORS |
| **Split origin** | Railway (Docker) | Vercel (static `frontend/dist`) | CDN for the UI, API separate |

The single-origin shape is the default and needs no extra config: the image
already copies the built UI into `frontend/dist/`, and the API serves it at `/`.
Use the split shape only when you want the UI on a CDN.

## Railway (backend)

`railway.json` at the repo root drives Railway's config-as-code:

- **builder**: `DOCKERFILE` - Railway builds the multi-stage `Dockerfile`
  (stage 1 `npm ci && npm run build` for the UI, stage 2 the Python runtime).
- **startCommand**: binds Uvicorn to `$PORT`, which Railway injects. The
  `Dockerfile` CMD hardcodes 8000, so the override keeps the container reachable
  on the port Railway routes to it.
- **healthcheckPath**: `/healthz` - Railway gates the rollout on the liveness
  probe.
- **restartPolicyType**: `ON_FAILURE` with up to 10 retries.

### Deploy

```bash
railway login
railway init                       # or: railway link <existing-project>
railway up                         # builds the Dockerfile and deploys
```

### Environment

Set these on the service (Railway dashboard -> Variables, or `railway variables`):

| Variable | Purpose |
|---|---|
| `NEXUS_API_KEYS` | JSON map `{key: {user_id, tenant_id, role}}`; **required** (fail-closed auth) |
| `NEXUS_LLM_BASE_URL` | OpenAI-compatible endpoint (e.g. your hosted model) |
| `NEXUS_INFRA_BACKEND` | `memory` for a stateless demo, `external` for Redis/Qdrant/Neo4j |
| `NEXUS_SECRET_BACKEND` | `env` (platform vars) or `json:<path>` for a mounted secrets file |
| `NEXUS_SANDBOX_BACKEND` | `docker` needs the Docker socket; use `subprocess` if unavailable |
| `NEXUS_OTEL_ENABLED` | `true` to export traces/metrics to a collector |
| `NEXUS_CORS_ORIGINS` | comma-separated origins when the UI is on another host |
| `NEXUS_JSON_LOGS` | `true` for structured logs (Railway log search) |

With `NEXUS_INFRA_BACKEND=external`, attach managed Redis, Qdrant, and Neo4j
(their `NEXUS_*` connection vars are documented in
[Architecture Map](architecture-map.md)) or run the bundled services from
`docker-compose.prod.yml` on a VM instead.

## Vercel (frontend, split origin)

`vercel.json` builds the Vite app in `web/` and serves the compiled assets:

- **installCommand**: `npm --prefix web ci` (uses `web/package-lock.json`).
- **buildCommand**: `npm --prefix web run build`.
- **outputDirectory**: `frontend/dist` (the Vite config's `outDir`).
- **rewrites**: single-page-app fallback so client routes resolve to `index.html`.

```bash
npm i -g vercel
vercel --prod
```

### Pointing the SPA at the API

The UI issues **relative** requests (`/v1/*`, `/api/*`). Two ways to reach the
backend:

1. **Same origin (recommended)**: skip Vercel and serve the UI from the Railway
   container at `/`. No proxy, no CORS.
2. **Split origin**: add proxy rewrites to `vercel.json` so `/v1/*` and `/api/*`
   forward to the Railway host, e.g.

   ```json
   {
     "rewrites": [
       { "source": "/v1/:path*", "destination": "https://YOUR-APP.up.railway.app/v1/:path*" },
       { "source": "/api/:path*", "destination": "https://YOUR-APP.up.railway.app/api/:path*" },
       { "source": "/(.*)", "destination": "/index.html" }
     ]
   }
   ```

   The API key is read from `VITE_NEXUS_API_KEY` at build time or from browser
   local storage at runtime; keep the bearer tokens on the server side and proxy
   rather than baking real keys into the bundle.

## Verify

```bash
python scripts/preflight.py                 # local readiness
curl -f https://YOUR-APP.up.railway.app/healthz   # Railway liveness
curl -f https://YOUR-APP.up.railway.app/readyz    # dependency readiness
```

`/readyz` returns non-200 until Redis/Qdrant/Neo4j are reachable (in `external`
mode), which is the signal Railway uses to hold traffic during a rollout.

## Rollback

Railway keeps prior deployments: pick the last green one in the dashboard
(Deployments -> Redeploy), or `railway rollback`. On Vercel, `vercel rollback`
promotes the previous production deployment. Because every patch in the repo
flows through the consensus gate (see [Swarm](swarm.md)), a bad change is
usually caught before it reaches `main`.
