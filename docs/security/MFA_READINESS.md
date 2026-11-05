# Multi-Factor Authentication (MFA) Architectural Readiness

## 1. Executive Summary

While full MFA implementation (TOTP / SMS OTP) is scheduled for a future dedicated security enhancement phase, the Phase 3 Authentication and Session Foundation was engineered from day one with the technical hooks and state-machine provisions required to integrate MFA seamlessly without breaking existing APIs or data schemas.

---

## 2. MFA Authentication Flow State Machine

```
               [ Step 1: Login Request (User + Password) ]
                                    |
                                    v
                     +------------------------------+
                     | Verify Argon2id Credentials  |
                     +--------------+---------------+
                                    |
            +-----------------------+-----------------------+
            | (MFA Disabled)                                | (MFA Enabled)
            v                                               v
+-----------------------+                       +-----------------------------+
| Full Access Token     |                       | Intermediate Challenge Token|
| Issued (type=access)  |                       | Issued (type=mfa_pending)   |
+-----------------------+                       +--------------+--------------+
                                                               |
                                            [ Step 2: Submit TOTP / SMS Code ]
                                                               |
                                                               v
                                                +-----------------------------+
                                                | Verify TOTP Algorithm / Code|
                                                +--------------+--------------+
                                                               |
                                                               v
                                                +-----------------------------+
                                                | Full Access Token Issued    |
                                                +-----------------------------+
```

---

## 3. Database Schema Readiness

The current Phase 2/3 `users` and `user_sessions` tables cleanly accommodate MFA extensions via additive columns:

```sql
-- Planned Future Additive Migration
ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN mfa_secret_encrypted VARCHAR(500); -- AES-256 encrypted TOTP secret
ALTER TABLE users ADD COLUMN mfa_backup_codes_hash JSONB;       -- Array of bcrypt/argon hashes

ALTER TABLE user_sessions ADD COLUMN mfa_authenticated BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE user_sessions ADD COLUMN mfa_method VARCHAR(20);    -- 'TOTP', 'SMS', 'WEBAUTHN'
```

---

## 4. API & Token Decoupling

1. **Intermediate Challenge Token**:
   - When `user.mfa_enabled == True`, `AuthService.login()` issues an access token with `"type": "mfa_pending"` and short 5-minute TTL.
   - FastAPI dependencies reject tokens where `"type" != "access"`.
2. **Dedicated Verification Endpoint**:
   - `POST /api/v1/auth/mfa/verify`: Accepts intermediate token and 6-digit TOTP code.
   - Upon verification, upgrades session to `mfa_authenticated = True` and issues full `"type": "access"` JWT.
3. **Session Replay Immunity**:
   - Because rotating refresh tokens are managed in `user_sessions`, MFA verification binds directly to the active session family, guaranteeing that tokens cannot bypass second-factor checks during refresh cycles.
