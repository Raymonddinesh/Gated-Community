# Session Security & Refresh Token Rotation Architecture

## 1. Refresh Token Architecture & Security Properties

SocietySphere employs a rotating refresh token strategy with cryptographically secure single-use tokens and token family replay detection.

```
+---------------+        Step 1: Login
|    Client     | ----------------------------> Generates Family F1, Session S1
+---------------+                               Refresh Token T1 (Digest: H(T1))
        |
        |                Step 2: Refresh (T1)
        | ----------------------------> Revokes S1 (Reason: ROTATED)
        |                               Issues Session S2 (Family F1)
        |                               Refresh Token T2 (Digest: H(T2))
        |
        |                Step 3: Replay Attack (Compromised T1 presented)
        | ----------------------------> DETECTS REPLAY!
                                        Immediately revokes ALL sessions in F1 (S1, S2)
                                        Logs AUTH_REFRESH_REPLAY_DETECTED audit
                                        Returns HTTP 401 TOKEN_REPLAY_DETECTED
```

### Cryptographic Entropy & Digest Storage
- **Generation**: Generated via `secrets.token_urlsafe(48)`, providing 384 bits of cryptographically secure pseudo-random entropy.
- **Zero Raw Persistence**: The database **never** stores raw refresh tokens. Instead, the SHA-256 digest (`hash_token(raw_token)`) is computed and indexed (`user_sessions.refresh_token_hash`).
- **Database Schema**:
  ```sql
  CREATE TABLE user_sessions (
      id UUID PRIMARY KEY,
      user_id UUID NOT NULL REFERENCES users(id),
      family_id UUID NOT NULL,
      refresh_token_hash VARCHAR(64) UNIQUE NOT NULL,
      user_agent VARCHAR(500),
      ip_address VARCHAR(45),
      is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
      revoked_at TIMESTAMPTZ,
      revoke_reason VARCHAR(50),
      expires_at TIMESTAMPTZ NOT NULL,
      last_used_at TIMESTAMPTZ NOT NULL,
      created_at TIMESTAMPTZ NOT NULL,
      updated_at TIMESTAMPTZ NOT NULL
  );
  ```

---

## 2. Token Family Replay Detection Mechanism

When a client submits a refresh token:
1. The server hashes the token: `H = sha256(refresh_token)`.
2. The server queries `user_sessions` for `refresh_token_hash = H`.
3. If no session matches: Rejected with HTTP 401 (`INVALID_REFRESH_TOKEN`).
4. **Replay Condition**: If the session matches, but `is_revoked == TRUE`:
   - An attacker or compromised client has submitted an already-used or revoked token.
   - The system immediately neutralizes the breach by issuing an atomic batch update:
     ```sql
     UPDATE user_sessions
     SET is_revoked = TRUE, revoked_at = NOW(), revoke_reason = 'REPLAY_DETECTED'
     WHERE family_id = :family_id AND is_revoked = FALSE;
     ```
   - An immutable audit trail entry is logged: `AUTH_REFRESH_REPLAY_DETECTED`.
   - The request is terminated with HTTP 401 (`TOKEN_REPLAY_DETECTED`).
5. **Legitimate Refresh**: If `is_revoked == FALSE` and `expires_at > NOW()`:
   - The old session `S1` is marked revoked (`is_revoked = TRUE, revoke_reason = 'ROTATED'`).
   - A new token `T2` and session `S2` are created carrying the **same `family_id`**.
   - A new short-lived access token is generated.

---

## 3. Session Revocation Vectors

The platform provides explicit revocation primitives:
- **Single Session Logout (`POST /api/v1/auth/logout`)**: Revokes the specific session ID bound to the active Bearer token.
- **Global Device Logout (`POST /api/v1/auth/logout-all`)**: Revokes all active sessions for the authenticated user across all devices and browsers.
- **Password Reset Revocation**: Changing or resetting a password immediately revokes all active sessions belonging to that user.
- **Administrative Account Suspension**: Marking a user record as inactive (`status != 'ACTIVE'`) invalidates all existing sessions during dependency evaluation.
