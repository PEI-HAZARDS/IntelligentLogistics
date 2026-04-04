# Keycloak Authentication Integration

## Overview

The system uses **Keycloak** as the identity provider for all authentication. Login UIs remain unchanged — the API Gateway exchanges credentials with Keycloak behind the scenes using the **Resource Owner Password Credentials (ROPC)** flow (Direct Access Grants).

**Identity strategy**: Keycloak handles authentication (token issuance, validation, refresh, revocation). PostgreSQL remains the source of truth for user profiles, relationships, and business data.

---

## Architecture

```
                         +-----------+
                         | Keycloak  |
                         | (port 8443)|
                         +-----+-----+
                               |
              token exchange /  \ JWKS (public keys)
                           /    \
    +----------+     +----+------+----+     +-------------+
    | Frontend |---->| API Gateway    |---->| Data Module  |
    | (Web/    |     | (port 8000)    |     | (port 8080)  |
    |  Mobile) |<----| Token Validate |<----| Profile Data |
    +----------+     +----------------+     +-------------+
```

### Login Flow

1. User submits credentials (email+password or license+password) to the frontend login form
2. Frontend calls `POST /api/auth/workers/login` or `POST /api/auth/drivers/login`
3. API Gateway receives credentials and forwards them to Keycloak's token endpoint (ROPC grant)
4. Keycloak validates credentials and returns `access_token` + `refresh_token`
5. API Gateway fetches the user profile from the Data Module (`GET /workers/by-email/{email}` or `GET /drivers/{license}`)
6. API Gateway returns `{ access_token, refresh_token, expires_in, user_info }` to the frontend
7. Frontend stores both tokens and uses `access_token` in the `Authorization: Bearer` header for all subsequent requests

### Token Validation

- The API Gateway validates every request's Bearer token against Keycloak's **JWKS** (JSON Web Key Set) endpoint
- Tokens are RS256-signed by Keycloak — no shared secret needed
- Token claims include `realm_access.roles` (driver, operator, manager) and `resource_access.api-gateway.roles` (access_level_admin, access_level_basic)

### Token Refresh

- Access tokens expire after **15 minutes**
- Refresh tokens expire after **8 hours** (one work shift)
- When a 401 is received, the frontend automatically calls `POST /api/auth/refresh` with the stored refresh token
- If refresh fails, the user is redirected to the login page

### Logout

- Frontend calls `POST /api/auth/logout` with the refresh token
- API Gateway revokes the refresh token in Keycloak (server-side session end)
- Local storage is cleared

---

## Roles & Permissions

| Role | Realm Role | Client Roles | Access |
|------|-----------|-------------|--------|
| **Driver** | `driver` | — | `/drivers/me/*`, `/drivers/claim`, driver WebSocket |
| **Operator** | `operator` | — | Arrivals, manual review, alerts, stream, shifts, gate WebSocket |
| **Manager** | `manager` | `access_level_admin` or `access_level_basic` | All operator access + statistics, driver listing, manager endpoints |

### Route Protection Summary

| Endpoint Group | Required Role | Auth Method |
|---------------|--------------|-------------|
| `POST /api/auth/*` | Public | — |
| `GET /health` | Public | — |
| `GET /api/arrivals/*` | operator, manager | Bearer token |
| `POST /api/manual-review/` | operator, manager | Bearer token |
| `GET /api/alerts/*` | operator, manager | Bearer token |
| `GET /api/stream/*` | operator, manager | Bearer token |
| `GET /api/workers/*` | operator, manager | Bearer token |
| `GET /api/statistics/*` | manager | Bearer token |
| `GET /api/drivers/me/*` | driver | Bearer token (identity from JWT `sub`) |
| `GET /api/drivers` | manager | Bearer token |
| `WS /api/ws/gate/{id}` | operator, manager | `?token=` query param |
| `WS /api/ws/driver/{license}` | driver | `?token=` query param |

---

## Infrastructure

### Docker Services

Added to `V_APP/docker-compose.yml`:

- **`keycloak-db`** — PostgreSQL 15 dedicated to Keycloak (separate from app DB). Volume: `kc_pgdata`
- **`keycloak`** — Keycloak 26.0, `start-dev --import-realm`. Port: `8443:8080`. Auto-imports realm config on first start

### Environment Variables

Added to `.env`:

```env
KC_DB_USER=keycloak
KC_DB_PASSWORD=keycloak_secret
KC_ADMIN_USER=admin
KC_ADMIN_PASSWORD=admin
KEYCLOAK_URL=http://keycloak:8080
KEYCLOAK_REALM=intelligent-logistics
KEYCLOAK_CLIENT_ID=api-gateway
KEYCLOAK_CLIENT_SECRET=api-gateway-secret
```

### Realm Configuration

File: `keycloak/realm-export.json` — auto-imported on first Keycloak start.

- Realm: `intelligent-logistics`
- Client: `api-gateway` (confidential, ROPC enabled, service account enabled)
- Realm roles: `driver`, `operator`, `manager`
- Client roles: `access_level_admin`, `access_level_basic`
- Access token TTL: 15 minutes
- Refresh token TTL: 8 hours

---

## Files Changed

### New Files

| File | Purpose |
|------|---------|
| `V_APP/keycloak/realm-export.json` | Keycloak realm configuration |
| `V_APP/keycloak/sync_users.py` | Migration script: PostgreSQL users to Keycloak |
| `V_APP/api_gateway/src/auth/__init__.py` | Auth package |
| `V_APP/api_gateway/src/auth/keycloak_client.py` | Keycloak REST API wrapper |
| `V_APP/api_gateway/src/auth/token_validator.py` | JWT validation + FastAPI dependencies |
| `frontend/src/services/auth.ts` | Web frontend auth service |
| `frontend/src/components/auth/ProtectedRoute.tsx` | Route guard component |

### Modified Files

| File | Changes |
|------|---------|
| `V_APP/docker-compose.yml` | Added keycloak + keycloak-db services, kc_pgdata volume |
| `V_APP/.env` | Added Keycloak env vars |
| `V_APP/api_gateway/requirements.txt` | Added `PyJWT[crypto]` |
| `V_APP/api_gateway/src/api_gateway.py` | Keycloak config, init client + validator, register auth router |
| `V_APP/api_gateway/src/dependencies.py` | Added `get_keycloak_client` dependency |
| `V_APP/api_gateway/src/routers/auth.py` | Implemented login, refresh, logout endpoints |
| `V_APP/api_gateway/src/routers/arrivals.py` | Added `require_role("operator", "manager")` |
| `V_APP/api_gateway/src/routers/manual_review.py` | Added `require_role("operator", "manager")` |
| `V_APP/api_gateway/src/routers/alerts.py` | Added `require_role("operator", "manager")` |
| `V_APP/api_gateway/src/routers/stream.py` | Added `require_role("operator", "manager")` |
| `V_APP/api_gateway/src/routers/statistics.py` | Added `require_role("manager")` |
| `V_APP/api_gateway/src/routers/workers.py` | Per-endpoint role protection |
| `V_APP/api_gateway/src/routers/drivers.py` | JWT-based identity for `/me/*`, role protection |
| `V_APP/api_gateway/src/routers/realtime.py` | WebSocket token validation via `?token=` |
| `V_APP/Data_Module/config.py` | Deprecated `jwt_secret` |
| `V_APP/Data_Module/routes/worker.py` | Added `GET /workers/by-email/{email}` |
| `frontend/src/lib/api.ts` | Token refresh interceptor with request queue |
| `frontend/src/pages/Login/Login.tsx` | Uses new auth service |
| `frontend/src/router.tsx` | Protected routes with `ProtectedRoute` wrapper |
| `frontend/src/components/.../OperatorHeader.tsx` | Server-side logout |
| `frontend/src/components/.../ManagerHeader.tsx` | Server-side logout |
| `mobile/src/services/api.ts` | Token refresh interceptor, dual token storage |
| `mobile/src/services/drivers.ts` | New auth endpoint, removed `drivers_license` query params |
| `mobile/src/stores/authStore.ts` | Dual tokens, server-side logout |
| `mobile/src/screens/LoginScreen.tsx` | New response shape |
| `mobile/src/screens/HomeScreen.tsx` | Updated API calls (no `driversLicense` param) |
| `mobile/src/screens/ArrivalsScreen.tsx` | Updated API calls |
| `mobile/src/screens/ActiveArrivalScreen.tsx` | Updated API calls |

---

## User Migration

Run `sync_users.py` after Keycloak starts and the realm is imported:

```bash
cd src/V_APP
python keycloak/sync_users.py
```

The script:
1. Reads all active workers and drivers from PostgreSQL
2. Creates each user in Keycloak with their **existing bcrypt password hash** (no password reset needed)
3. Assigns realm roles (driver, operator, manager) and client roles (access_level_admin/basic)
4. Is idempotent — safely re-run without duplicates

---

## Verification Checklist

1. `docker-compose up` — Keycloak starts, admin console at `:8443`
2. Run `sync_users.py` — users appear in Keycloak admin
3. `curl -X POST /api/auth/workers/login` — returns tokens
4. Call protected endpoint without token — returns 401
5. Call protected endpoint with valid token — returns 200
6. Call operator endpoint with driver token — returns 403
7. `POST /api/auth/refresh` — returns new token pair
8. Web login + dashboard loads + logout works
9. Mobile login + appointments work + logout works
10. WebSocket connections authenticate via `?token=`
