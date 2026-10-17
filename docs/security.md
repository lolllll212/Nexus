# Security & Secrets

How NEXUS is hardened for production: what is enforced in code, what is a
deployment responsibility, and the safe defaults to keep.

## Authentication (fail-closed)

Every `/v1/*` route requires a Bearer token validated against
`NEXUS_API_KEYS`, a JSON map of `{key: {user_id, tenant_id, role}}`.

- **Fail-closed.** `NEXUS_API_KEYS={}` means zero keys are configured, so every
  request is rejected with `401`. There is no "auth disabled" mode and no
  wildcard key. Configure at least one key before exposing the service.
- **Roles.** `admin` and `user`. Admin-only routes additionally check the role;
  a valid `user` token is still rejected on admin surfaces.
- **Identity → tenant.** The token's `tenant_id` scopes memory, graph, quotas,
  and goals. Two tenants never share a Qdrant collection or a Neo4j subgraph —
  see [Backup & DR](backup-dr.md) for the tenant-naming rule.

## Secrets

Secrets are resolved through the `SecretStore` port, not read ad hoc from the
process environment in business code. The composition root
(`infrastructure/di/container.py`) selects the backend from
`NEXUS_SECRET_BACKEND`:

| Backend | Meaning |
|---|---|
| `env` (default) | Read from the process environment |
| `json:<path>` | Read from the JSON file at `<path>` (e.g. `json:./.secrets.json`), falling back to env |

Rules of thumb:

- **Never commit `.env`.** It is gitignored; `.env.example` is the template and
  holds no real values.
- **Never bake `.env` into an image.** The root `.dockerignore` excludes
  `.env` and `.env.*` (while keeping `.env.example`) so the file never reaches
  the Docker daemon or a layer.
- **Prefer the platform secret store in production.** On Railway/Vercel, inject
  secrets as environment variables from the platform, not from a shipped file.
  See the [Deployment](deploy.md) runbook.

## SSRF protection

Outbound fetches (`web_fetch`, `http_request`, and research tooling) go through
`infrastructure/adapters/security/ssrf.py`:

- Only `http`/`https` schemes are allowed.
- Loopback, private, link-local, reserved, multicast, and unspecified IPs are
  rejected, along with the cloud metadata endpoints (AWS/GCP/Azure
  `169.254.169.254`, Alibaba `100.100.100.200`).
- DNS is resolved once and the IP is **pinned** to the connection, closing the
  DNS-rebinding (TOCTOU) window.
- Every redirect hop is re-validated; the chain is bounded.
- Resolution failures **fail closed** — an ambiguous host is blocked, not
  allowed.

## Sandboxed execution

Generated and user code runs in a sandbox selected by `NEXUS_SANDBOX_BACKEND`:

- `docker` — the production default; `DockerSandbox` runs code in a locked-down
  container.
- `subprocess` — development fallback only. It runs on the host and must not be
  used for untrusted input.

`run_shell` and other privileged actions also pass through the autonomy policy
and fail closed when no policy is set (they return `approval_required`).

## Path confinement

File tools resolve paths through `resolve_confined_path`, which rejects
traversal and a denylist of sensitive names: `.env`, `.env.local`,
`.env.production`, private keys (`id_rsa`, `*.pem`, `*.key`), `secrets.json`,
and `.git/config`.

## Rate limiting

Per-identity sliding-window limits:

| Env var | Applies to |
|---|---|
| `NEXUS_CHAT_RATE_LIMIT` | chat / ReAct turns |
| `NEXUS_TOOL_GEN_RATE_LIMIT` | tool generation |
| `NEXUS_RATE_LIMIT_WINDOW_SECONDS` | window size |
| `NEXUS_RATE_LIMIT_FAIL_CLOSED` | deny (true) vs. skip (false) when Redis is down |

Set `NEXUS_RATE_LIMIT_FAIL_CLOSED=true` in production so an unreachable Redis
degrades to "reject", not "unlimited".

## Dependency & static scanning

CI runs an advisory security job (`.github/workflows/ci.yml`):

- **pip-audit** over `requirements.txt` — known CVEs in the runtime lock.
- **bandit** over `src/nexus` — common insecure patterns.

Both are `continue-on-error` while existing findings are triaged. Remove that
flag to make them hard gates once the backlog is clear. Locally:

```bash
pip install pip-audit bandit
pip-audit -r requirements.txt
bandit -q -ll -r src/nexus
```

The consensus protocol's `bandit` reviewer reuses the same pattern set on every
proposed patch, so security checks apply to autonomous changes too.

## Container hardening checklist

- `.dockerignore` excludes `.git`, `.env*`, caches, tests, docs, and local
  runtime state from the build context.
- The image installs only `requirements.txt` (runtime), not the dev extras.
- Health probes (`/healthz`, `/readyz`) and metrics (`/metrics`) are exposed for
  orchestrators.
- Run the container as a non-root user and mount the Docker socket only where
  the sandbox genuinely needs it.
