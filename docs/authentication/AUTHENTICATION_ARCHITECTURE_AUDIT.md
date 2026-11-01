# EventFlow AI — Authentication Architecture Audit

**Status:** Completed (Stage 1)  
**Author:** Principal Backend Architect & Full-Stack Security Engineer  
**Date:** November 2026  
**Scope:** Investigation of existing backend and frontend authentication systems, identity data models, credential lifecycles, and evaluation of user authentication requirements.

---

## 1. Executive Summary

EventFlow AI is an event-driven workflow orchestration and operational intelligence platform. An architectural audit of the current authentication system was conducted to determine how authentication is enforced across all tiers and whether a human user authentication system (signup, login, session management, password reset) is required alongside the existing API client authentication mechanism.

### Key Audit Findings:
1. **Existing Authentication Is Machine-Only:** The backend currently implements only machine-to-machine client credential authentication (`APIClientAuthentication`), accepting Bearer tokens formatted as `<client-uuid>.<secret>`.
2. **"Tenant" Equals "APIClient":** Data isolation across events, workflows, incidents, and analytics is enforced by filtering on `Event.client` (a foreign key to `APIClient`). There is currently no concept of a human user account, team, or user-owned workspace.
3. **No User-Facing Authentication Exists:** There are zero registration, login, logout, password reset, or user profile endpoints.
4. **Django User Model Is Intact But Unused:** Django's default `django.contrib.auth.models.User` table exists in PostgreSQL (migrations `0001` through `0012` applied), with 0 user records.
5. **Frontend Relies on In-Memory Machine Credentials:** The React frontend requires human operators to manually run a Docker CLI command, generate an API client secret, and paste the raw token into the Settings page. This token is stored only in JavaScript memory and is lost on page refresh.
6. **Architectural Recommendation (Option C - Dual Authentication):** EventFlow AI must support **both** User Authentication (for human operators and engineers using the frontend console) and API Client Authentication (for automated microservices and event producers submitting events). Existing API client ingestion must not be broken or altered.

---

## 2. Existing Backend Authentication Architecture

### 2.1 The `APIClient` Model (`apps/common/models.py`)
```python
class APIClient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    secret_hash = models.CharField(max_length=256)
    can_view_analytics = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)
```
- **Secret Storage:** The raw secret is never stored. Secrets are hashed using Django’s cryptographic password hasher (`make_password`) and stored in `secret_hash`.
- **Duck-Typing Django User:** `APIClient` implements properties `@property def is_authenticated(self): return True` and `@property def is_active(self): return self.revoked_at is None`. This allows DRF's authentication pipeline to set `request.user = api_client`.

### 2.2 Token Format & Generation (`apps/common/services.py`)
- Generated via CLI: `python manage.py client_credentials create --name <name> [--analytics-access]`
- Raw Secret: 32 bytes URL-safe base64 (`secrets.token_urlsafe(32)`).
- Token String: `<client.id>.<secret>` (e.g. `851b31f5-3185-430f-a76c-309a8ed73734.en2hJMvEz0y90K6fvH8DZWIEjmRA4mvEUZmI8vqfMpE`).
- Display Policy: The secret is displayed once in the terminal and cannot be retrieved again.

### 2.3 Authentication Lifecycle (`apps/common/authentication.py`)
```
Incoming Request
  │
  ▼
[RequestIDMiddleware] ── Attaches X-Request-ID
  │
  ▼
[APIClientAuthentication]
  ├── Reads "Authorization: Bearer <client_uuid>.<secret>"
  ├── Splits on first "." to extract client_id and secret
  ├── Queries APIClient where id=client_uuid and revoked_at IS NULL
  ├── If client missing: executes dummy check_password() to prevent timing attacks -> raises 401
  ├── Validates secret with check_password(secret, client.secret_hash)
  └── Returns (client, None) -> Sets request.user = client
  │
  ▼
[Permission Classes]
  ├── IsAuthenticated (checks request.user.is_authenticated)
  └── CanViewAnalytics (checks request.user.can_view_analytics)
  │
  ▼
[View Handler] ── Filters records by client=request.user
```

### 2.4 Django Settings & Middleware Configuration
- **`AUTH_USER_MODEL`**: Unset (defaults to `django.contrib.auth.models.User`).
- **`REST_FRAMEWORK`**:
  - `DEFAULT_AUTHENTICATION_CLASSES`: `["apps.common.authentication.APIClientAuthentication"]`
  - `DEFAULT_PERMISSION_CLASSES`: `["rest_framework.permissions.IsAuthenticated"]`
- **`MIDDLEWARE`**:
  - `apps.common.middleware.RequestIDMiddleware`
  - `django.middleware.security.SecurityMiddleware`
  - `django.contrib.sessions.middleware.SessionMiddleware`
  - `django.middleware.common.CommonMiddleware`
  - `django.middleware.csrf.CsrfViewMiddleware`
  - `django.contrib.auth.middleware.AuthenticationMiddleware`
  - `django.contrib.messages.middleware.MessageMiddleware`
  - `django.middleware.clickjacking.XFrameOptionsMiddleware`

*Critical note:* Standard Django Session and Authentication middlewares are already active in the pipeline, which makes supporting cookie-based session authentication for web users straightforward and natural.

---

## 3. Protected Endpoints & Access Control Matrix

| Endpoint | Method | Auth Class | Permissions | Scope / Ownership Filter |
|---|---|---|---|---|
| `/health/live` | GET | None | AllowAny | Public process liveness |
| `/health/ready` | GET | None | AllowAny | Public DB/dependency readiness |
| `/health/services` | GET | APIClientAuthentication | IsAuthenticated | Probes broker/analytics health |
| `/metrics` | GET | Token (Prometheus) | Custom Token Check | Operational metrics |
| `/api/schema/` | GET | None | AllowAny | OpenAPI schema |
| `/api/docs/` | GET | None | AllowAny | Swagger UI |
| `/api/v1/events` | POST | APIClientAuthentication | IsAuthenticated | Ingests event for `request.user` |
| `/api/v1/events/batch` | POST | APIClientAuthentication | IsAuthenticated | Batch ingests for `request.user` |
| `/api/v1/events` | GET | APIClientAuthentication | IsAuthenticated | Filters `client=request.user` |
| `/api/v1/events/{id}` | GET | APIClientAuthentication | IsAuthenticated | Filters `client=request.user` |
| `/api/v1/workflows` | GET | APIClientAuthentication | IsAuthenticated | Filters `event__client=request.user` |
| `/api/v1/workflows/{id}` | GET | APIClientAuthentication | IsAuthenticated | Filters `event__client=request.user` |
| `/api/v1/incidents/summaries` | POST | APIClientAuthentication | IsAuthenticated | Filters `event__client=request.user`, rate-limited per client |
| `/api/v1/incidents/summaries` | GET | APIClientAuthentication | IsAuthenticated | Filters `workflow__event__client=request.user` |
| `/api/v1/incidents/summaries/{id}` | GET | APIClientAuthentication | IsAuthenticated | Filters `workflow__event__client=request.user` |
| `/api/v1/analytics/tenant-lifecycle` | GET | APIClientAuthentication | IsAuthenticated | Filters `client=request.user` (PostgreSQL) |
| `/api/v1/analytics/overview` | GET | APIClientAuthentication | IsAuthenticated | Filters `client=request.user` (PostgreSQL) |
| `/api/v1/analytics/lifecycle` | GET | APIClientAuthentication | IsAuthenticated, CanViewAnalytics | Global ClickHouse analytics |

---

## 4. Current Frontend Authentication Analysis

### 4.1 Token Storage & State
- **Token Storage:** Stored in module-level variable `let apiToken: string | null = null` in `frontend/src/api/auth-token.ts`.
- **State Management:** `AuthProvider` in `frontend/src/app/auth.tsx` exposes `token`, `hasToken`, `setToken`, `clearToken`.
- **Request Interceptor:** `frontend/src/api/client.ts` attaches `Authorization: Bearer <token>` to all `/api/v1/` and `/health/services` requests.
- **Handling 401s:** Interceptor clears `apiToken`, resets state, clears TanStack Query cache, and dispatches an `eventflow:unauthorized` window event.

### 4.2 Deficiencies in Current Frontend Flow
1. **No User Identity:** The frontend does not know who is logged in. It only knows whether an arbitrary machine string is loaded in memory.
2. **Page Refresh Loss:** Because `apiToken` is strictly held in JS memory, reloading any page or opening a new tab unauthenticates the user and forces them back to Settings to paste the token again.
3. **No Self-Service Onboarding:** A new user cannot create an account, verify their email, or sign in.
4. **No Password Reset:** Users cannot recover lost credentials.
5. **No API Client Self-Service Management:** Users cannot view or provision API tokens from the web UI; everything requires root Docker host shell access.

---

## 5. Security Concerns with Current Architecture

1. **Exposure of Long-Lived Machine Credentials in Browsers:** Machine tokens are meant for server-to-server daemon processes. Requiring human operators to copy/paste long-lived machine bearer tokens into browser inputs is an anti-pattern.
2. **Lack of User Accountability & Audit Logging:** Because all API operations are stamped only with `client_id`, there is no record of *which human operator* investigated an incident, reviewed workflows, or modified settings.
3. **Privilege Escalation Risk:** To see global ClickHouse analytics, the user must paste a token created with `--analytics-access`, giving their browser session wide read access.
4. **Lack of Granular Role-Based Access Control (RBAC):** Every valid API client has identical permissions across their data slice, with only a binary flag `can_view_analytics`.

---

## 6. Architecture Evaluation: A vs. B vs. C

### Option A: API Client Authentication Only (Status Quo)
- **Verdict: REJECTED.**
- Fails the core requirement: The platform cannot be used by other team members or self-registering users without backend CLI intervention.

### Option B: User Authentication Only (Replace API Clients with User Logins)
- **Verdict: REJECTED.**
- Breaks the event-driven ingestion architecture. Microservices, background webhooks, and third-party event producers should not authenticate via human usernames/passwords or interactive sessions. They need lightweight, rotatable, high-throughput machine credentials.

### Option C: Dual Authentication (Separate User Auth & API Client Auth)
- **Verdict: RECOMMENDED.**
- **Human Users:** Register and authenticate via standard email/password using secure, HTTP-only session cookies or JWT. Users log into the React console, view dashboards, trigger incident investigations, and manage API clients.
- **API Clients:** Microservices and event sources continue using Bearer `<client-uuid>.<secret>` tokens for automated ingestion (`/api/v1/events`).
- **Data Association:** An authenticated user belongs to an account/workspace. API clients created by the user inherit their workspace/tenant ownership. Existing standalone API clients remain fully operational.

---

## 7. Recommended Authentication Architecture (Option C Blueprint)

```
                       ┌────────────────────────────────────────────────────────┐
                       │                     CLIENT TIERS                       │
                       └────────────────────────────────────────────────────────┘
                                   │                                │
                    [Human User on React App]          [Microservice / Producer]
                                   │                                │
                       Email + Password Login             Bearer Token (UUID.Secret)
                                   │                                │
                       POST /api/v1/auth/login            POST /api/v1/events
                                   │                                │
                       HttpOnly Session Cookie             Authorization Header
                                   │                                │
                                   ▼                                ▼
                       ┌────────────────────────────────────────────────────────┐
                       │                DJANGO REST FRAMEWORK                   │
                       │           DEFAULT_AUTHENTICATION_CLASSES               │
                       ├────────────────────────────────────────────────────────┤
                       │  1. SessionAuthentication                              │
                       │  2. APIClientAuthentication                            │
                       └────────────────────────────────────────────────────────┘
                                   │                                │
                        request.user = User              request.user = APIClient
                                   │                                │
                                   ▼                                ▼
                       ┌────────────────────────────────────────────────────────┐
                       │                     DATA ACCESS                        │
                       ├────────────────────────────────────────────────────────┤
                       │  If request.user is User:                              │
                       │    Access events for user's owned API clients          │
                       │    (or user's workspace/tenant)                        │
                       │                                                        │
                       │  If request.user is APIClient:                         │
                       │    Access events for this specific client (existing)   │
                       └────────────────────────────────────────────────────────┘
```

### 7.1 Backend Authentication Mechanism: SessionAuthentication vs JWT
For a browser-based Single Page Application (SPA) where frontend and backend are hosted on the same domain or proxied:
- **Django Session Authentication (with HttpOnly, SameSite=Lax, Secure cookies):**
  - Completely immune to JavaScript XSS token theft.
  - Native Django session invalidation on logout.
  - Zero token expiration/refresh desynchronization complexity.
  - Standard Django CSRF protection (`django.middleware.csrf.CsrfViewMiddleware` is already in `MIDDLEWARE`).
- **Recommendation:** Implement **Django Session-based User Authentication** for frontend users via DRF, supported by CSRF token exchange, while preserving `APIClientAuthentication` for Bearer headers.

### 7.2 Identity & Ownership Model
1. **User Model:** Use Django's built-in `auth.User` (or a 1-to-1 `UserProfile` / custom model if additional profile fields like full name or workspace are needed).
   *Database Safety Check:* Because `auth_user` is already migrated and active in PostgreSQL, using `django.contrib.auth.models.User` avoids high-risk database re-initialization or foreign-key rewrites.
2. **APIClient Ownership:** Add an optional foreign key `owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="api_clients")` to `APIClient`.
   - Existing 22 API clients remain with `owner=None` (backward compatible).
   - Newly created API clients from the UI are linked to the logged-in user.
   - When a user logs in, their event/workflow views filter across `client__owner=request.user` (or all events if they are an admin/staff).

---

## 8. Required Implementation Roadmap

### Phase 3: Backend Implementation
1. Add `owner` foreign key to `APIClient` model and generate a safe migration.
2. Configure `REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]` to include both `SessionAuthentication` and `APIClientAuthentication`.
3. Create `apps/authentication/` (or extend `apps/common/`):
   - `POST /api/v1/auth/register`: Validate name, unique email, password strength; create active user; establish session.
   - `POST /api/v1/auth/login`: Validate email/password; authenticate; establish session; return safe user payload.
   - `POST /api/v1/auth/logout`: Invalidate session; clear session cookie.
   - `GET /api/v1/auth/me`: Return current user profile, roles, and status.
   - `POST /api/v1/auth/password-reset` & `POST /api/v1/auth/password-reset/confirm`: Secure token-based password reset.
   - `GET /api/v1/auth/csrf`: Provide CSRF cookie/token for SPA initialization.
4. Add API Client Management endpoints:
   - `GET /api/v1/clients`: List API clients owned by current user.
   - `POST /api/v1/clients`: Provision new API client; reveal secret once.
   - `POST /api/v1/clients/{id}/revoke`: Revoke client credential.
5. Update view querysets in `events`, `workflows`, `incidents`, and `analytics` to support requests where `request.user` is a `User` (resolving their owned clients) as well as an `APIClient`.

### Phase 4: Frontend Implementation
1. Add Auth Pages with EventFlow AI Design System:
   - `LoginPage.tsx` (`/login`): Email/password with validation, loading, error states, and "Remember me".
   - `SignupPage.tsx` (`/signup`): Name, email, password strength meter, confirm password.
   - `ForgotPasswordPage.tsx` (`/forgot-password`) & `ResetPasswordPage.tsx` (`/reset-password/:token`).
2. Centralize Authentication State (`frontend/src/app/auth.tsx`):
   - Replace manual token pasting with `user` state, `isAuthenticated`, `login()`, `register()`, `logout()`.
   - Protect dashboard routes (`ProtectedRoute` component); redirect unauthenticated visitors to `/login`.
3. Upgrade Settings Page (`frontend/src/features/settings/SettingsPage.tsx`):
   - User profile section (Name, Email, Role).
   - In-app API Client Management (Generate, list, copy, revoke API keys).
4. Update Axios Client (`frontend/src/api/client.ts`):
   - Enable `withCredentials: true` for automatic HttpOnly session cookie transmission.
   - Attach `X-CSRFToken` header for mutation requests.

---

## 9. Conclusion
The audit confirms that user registration and login are necessary for human access, but existing machine-to-machine API client authentication must remain in place for event ingestion. The proposed dual-authentication architecture provides a production-grade, secure, and seamless experience without rewriting any existing ingestion or workflow pipeline code.
