# Password Reset Security Architecture

## 1. Threat Model & Design Principles

The password reset workflow is one of the highest-risk attack surfaces in modern SaaS platforms. SocietySphere secures this workflow against four specific attack classes:
1. **Account Enumeration**: Attackers attempting to discover whether an email or phone number is registered.
2. **Token Guessing & Pre-computation**: Attackers attempting to brute-force short or predictable reset codes.
3. **Token Replay / Reuse**: Attackers reusing a previously intercepted reset link.
4. **Session Hijacking Persistence**: Compromised devices retaining valid sessions after the user changes their password.

---

## 2. Cryptographic Token Lifecycle

```
[ User Request ] 
       |
       v
+-----------------------------+
| Check User Existence        |
| - If not found: return 200  | (Neutral message, zero enumeration)
| - If found: proceed         |
+--------------+--------------+
               |
               v
+-----------------------------+
| Generate High-Entropy Token | (384-bit CSPRNG secrets.token_urlsafe(48))
+--------------+--------------+
               |
               v
+-----------------------------+
| Compute SHA-256 Digest      |
| Persist H(Token) to DB      | (Never persist raw token in DB or logs)
| Expiration: 15 minutes      |
+--------------+--------------+
               |
               v
[ User Consumes Token ]
       |
       v
+-----------------------------+
| Verify H(Token), Expiration |
| Mark is_used = TRUE         | (Single-use enforcement)
| Update Argon2id Password    |
| Revoke ALL Active Sessions  | (Neutralize all active devices)
| Log Audit Trail             |
+-----------------------------+
```

### Technical Specifications
- **Entropy**: 384 bits generated via Python `secrets.token_urlsafe(48)`.
- **Digest Storage**: `password_reset_tokens.token_hash` stores the SHA-256 digest (`VARCHAR(64)`). Raw tokens are strictly held in memory only long enough to transmit to the notification dispatcher.
- **Validity Window**: Strict 15-minute expiration (`PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 15`).
- **Single-Use Enforcement**: The record maintains `is_used BOOLEAN NOT NULL DEFAULT FALSE` and `used_at TIMESTAMPTZ`. Once consumed, any subsequent attempt fails with HTTP 400 (`INVALID_RESET_TOKEN`).

---

## 3. Account Enumeration Defense

The endpoint `POST /api/v1/auth/password-reset/request` returns an identical response whether an account exists or not:
```json
{
  "message": "If an account matches this identifier, password reset instructions have been sent."
}
```
In production environments (`APP_ENV = 'production'`), no token is ever returned in the HTTP response body.

---

## 4. Mandatory Session Termination upon Reset

When a user successfully submits a valid reset token via `POST /api/v1/auth/password-reset/confirm`:
1. The token is marked consumed.
2. The user's `password_hash` is updated to the newly provided Argon2id hash.
3. The server immediately executes an atomic session revocation across **all devices and clients**:
   ```sql
   UPDATE user_sessions
   SET is_revoked = TRUE, revoked_at = NOW(), revoke_reason = 'PASSWORD_RESET'
   WHERE user_id = :user_id AND is_revoked = FALSE;
   ```
4. An immutable audit record `PASSWORD_RESET_CONFIRMED` is recorded in `audit_logs`.
