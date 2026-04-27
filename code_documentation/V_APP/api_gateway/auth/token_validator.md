# `token_validator.py`

> JWT token validation using Keycloak's RS256 public keys, exposing FastAPI dependencies for role-based access control.

---

## Overview

`TokenValidator` acts as the security guard for the API Gateway's REST endpoints and WebSockets. It fetches and caches the Keycloak JWKS public keys on startup and uses them to cryptographically verify incoming Bearer JWTs. It decodes the token claims to extract the user's identity (e.g. `preferred_username` or `sub`) and their embedded realm/client roles into a typed `TokenPayload`.

The module exposes robust FastAPI dependencies (`get_current_user`, `require_role`) that can be plugged into router endpoints to effortlessly enforce Role-Based Access Control (RBAC).

---

## Location
```
src/V_APP/api_gateway/src/auth/token_validator.py
```

## Dependencies

### Internal
> N/A

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `PyJWT` | — | JWT decoding and JWKS caching |
| `fastapi` | — | `Depends`, `HTTPException`, `OAuth2PasswordBearer` |

---

## Architecture & Flow

```
[Request with Bearer Token] 
             │
             ▼
  FastAPI Route Dependency (require_role / get_current_user)
             │
             ▼
  TokenValidator.decode(token) 
      ├─ Verifies signature against Keycloak JWKS cache
      ├─ Verifies exp, iss, aud
      └─ Extracts roles and identity
             │
             ▼
       [TokenPayload]
```

---

## Classes

### `TokenPayload` (Dataclass)

> Decoded JWT claims relevant to the application.

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `sub` | `str` | Subject (email or drivers_license) |
| `roles` | `list[str]` | Realm roles |
| `client_roles` | `list[str]` | Client roles |

---

### `TokenValidator`

> Validates Keycloak-issued JWTs using the realm's JWKS endpoint.

**Inherits from:** `None`

**Constructor**
```python
TokenValidator(jwks_url: str, issuer: str, audience: str | None = None)
```

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self._jwks_client` | `PyJWKClient` | Caching JWKS HTTP client |
| `self._issuer` | `str` | Expected token issuer |

---

#### Methods

##### `decode(token)`

> Decodes and validates a JWT, returning a TokenPayload.

**Returns:** `TokenPayload`

**Raises:** `HTTPException` (401) on missing signature, expired token, or invalid formatting.

---

## Standalone Functions

### `get_current_user(request, token)`

> FastAPI dependency that extracts and validates the Bearer token. 

### `require_role(*allowed_roles)`

> Factory that returns a FastAPI dependency enforcing role membership.

### `validate_ws_token(request, token)`

> Validates a token passed as a WebSocket query parameter (synchronous wrapper for WS handlers).

---

## Configuration & Environment Variables

> N/A

---

## Usage Example

```python
from auth.token_validator import require_role, TokenPayload

@router.get("/secure-data")
async def get_data(user: TokenPayload = Depends(require_role("manager", "operator"))):
    return {"message": f"Hello {user.sub}, you have access!"}
```

---

## Error Handling

Token manipulation catches `jwt.ExpiredSignatureError` and `jwt.InvalidTokenError`, mapping them to standardized `401 Unauthorized` HTTP exceptions to instantly reject bad requests before business logic is executed. Role checking returns `403 Forbidden` if the user lacks the correct permissions.

---

## Testing

Tested indirectly via API integration tests with mocked tokens and PyJWK responses.

---

## Known Issues / TODOs

> N/A

---

## Changelog

> N/A

---

## Related Docs

- [`keycloak_client.md`](./keycloak_client.md)
- [`api_gateway.md`](../api_gateway.md)
