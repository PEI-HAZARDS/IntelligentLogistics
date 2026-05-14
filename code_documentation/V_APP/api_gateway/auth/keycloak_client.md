# `keycloak_client.py`

> Keycloak REST API client for the API Gateway handling credential exchange, token refresh, and user management.

---

## Overview

`KeycloakClient` is a wrapper around Keycloak's OpenID Connect and Admin REST endpoints. It facilitates Resource Owner Password Credentials (ROPC) flow for direct login exchanges, token refreshing, and logouts. Additionally, it implements methods to create new users directly in Keycloak (optionally porting existing bcrypt hashes) and assigns Realm/Client roles, making it essential for onboarding new workers/drivers seamlessly into the IAM system from the V_APP backend.

---

## Location
```
src/V_APP/api_gateway/src/auth/keycloak_client.py
```

## Dependencies

### Internal
> N/A

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `httpx` | — | Async HTTP client for Keycloak APIs |
| `fastapi` | — | `HTTPException`, `status` for structured error raising |

---

## Architecture & Flow

```
[API Gateway Auth Routers]
             │
             ├─ exchange_credentials(user, pass) → [Keycloak /token endpoint]
             ├─ fetch_jwks()                     → [Keycloak /certs endpoint]
             └─ create_user(...)                 → [Keycloak Admin REST API]
```

---

## Classes

### `KeycloakClient`

> Thin wrapper around Keycloak's OpenID Connect and Admin REST endpoints.

**Inherits from:** `None`

**Constructor** (Dataclass)
```python
KeycloakClient(server_url: str, realm: str, client_id: str, client_secret: str)
```

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.server_url` | `str` | Keycloak server address |
| `self.realm` | `str` | Realm name |
| `self.client_id` | `str` | Client ID |
| `self.client_secret` | `str` | Confidential client secret |

---

#### Methods

##### `exchange_credentials(username, password)`

> Exchange user credentials for tokens using ROPC flow.

**Returns:** `dict[str, Any]` (access_token, refresh_token, etc.) (async)

---

##### `refresh_token(refresh_token)`

> Exchange a refresh token for a new token pair.

**Returns:** `dict[str, Any]` (async)

---

##### `logout(refresh_token)`

> Revoke a refresh token (end the Keycloak session).

**Returns:** `None` (async)

---

##### `create_user(username, password_hash, email, first_name, last_name, realm_roles, client_roles, enabled)`

> Creates a user in Keycloak via the Admin REST API and applies roles. Reuses bcrypt hashes to prevent password resets.

**Returns:** `str` — Keycloak user ID. (async)

---

##### `fetch_jwks()`

> Fetches the realm's JSON Web Key Set for token verification used by `TokenValidator`.

**Returns:** `dict[str, Any]` (async)

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

Typically instantiated with variables from `APIGatewayConfig`: `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`.

---

## Usage Example

```python
client = KeycloakClient(
    server_url="http://keycloak:8080",
    realm="intelligent-logistics",
    client_id="api-gateway",
    client_secret="secret"
)
tokens = await client.exchange_credentials("admin", "password123")
```

---

## Error Handling

Network connection errors or JSON parse errors are caught and raised as structured `HTTPException(502 Bad Gateway)`. Invalid credentials explicitly raise `HTTPException(401 Unauthorized)`. User creation conflicts (409) skip creation and proceed to return the existing user ID.

---

## Testing

Tested indirectly via API Gateway integration tests or mocked HTTP client tests.

---

## Known Issues / TODOs

> N/A

---

## Changelog

> N/A

---

## Related Docs

- [`token_validator.md`](./token_validator.md)
- [`api_gateway.md`](../api_gateway.md)
