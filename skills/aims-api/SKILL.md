---
name: aims-api
description: Integrate with Authme AIMS face recognition API. Use when users want to add face detection, 1:1 verification, 1:N identification, liveness detection, or FaceSet management to their application.
---

# AIMS API Integration Skill

Help developers integrate Authme AIMS face recognition API into their applications. Guide them through authentication, API call sequences, and error handling based on their use case.

## When to Trigger

Activate when the user wants to:
- Integrate face recognition into their app
- Add face detection, verification (1:1), or identification (1:N)
- Implement liveness / anti-spoofing detection
- Manage FaceSets (face databases)
- Authenticate with AIMS API (HMAC-SHA256)

Do NOT trigger for general image processing, OCR, or non-face-related AI tasks.

## Step 1: Identify the Use Case

Ask the user which scenario they need:

| Scenario | Description | APIs Used |
|---|---|---|
| **1:1 Verification** | Confirm a person's identity (e.g., selfie vs. ID card) | auth → liveness → detect × 2 → verify |
| **1:N Identification** | Find a person in a database (e.g., access control, VIP recognition) | auth → (faceset setup) → liveness → detect → identify |
| **Liveness Only** | Check if the image is a real person (anti-spoofing) | auth → liveness |
| **FaceSet Management** | Create/manage face databases for 1:N search | auth → facesets CRUD + detect + register |

## Step 2: Generate Authentication Code

All AIMS API calls require a Bearer token. Generate the auth helper first.

The signing algorithm:
1. Concatenate `client_id` + unix timestamp as string
2. HMAC-SHA256 with `client_secret` as key
3. Output as hex string

Provide the auth code in the user's language. Reference `references/api-spec.md` for endpoint details.

Key rules:
- `client_secret` must NEVER appear in frontend code, mobile apps, or version control
- Cache the token in backend; refresh 30 seconds before expiry (token lives 300 seconds)
- Server time must be NTP-synced; ±5 minute tolerance on `time` parameter

## Step 3: Implement the API Flow

### For 1:1 Verification (eKYC, identity check)

Generate code following this exact sequence:

```
1. POST /aims/auth/token          → access_token
2. POST /aims/liveness/image      → liveness_score (≥ 0.5 to proceed)
3. POST /aims/face/detect (ID)    → face_token_A
4. POST /aims/face/detect (selfie)→ face_token_B
5. POST /aims/face/verify         → similarity (≥ 0.7 = same person)
```

Always include liveness detection before verify. Explain why: prevents photo/screen replay attacks.

### For 1:N Identification (access control, VIP recognition)

Two phases:

**Setup phase (one-time):**
```
1. POST /aims/facesets                              → faceset_token
2. For each person:
   POST /aims/face/detect (photo)                   → face_token
   POST /aims/facesets/{faceset_token}/register      → registered
```

**Runtime phase (per query):**
```
1. POST /aims/auth/token           → access_token
2. POST /aims/liveness/image       → liveness_score (optional per scenario)
3. POST /aims/face/detect          → face_token
4. POST /aims/face/identify        → top N matches with similarity scores
```

### For Liveness Only

```
1. POST /aims/auth/token           → access_token
2. POST /aims/liveness/image       → liveness_score
```

Score interpretation: ≥ 0.5 = real person, < 0.5 = suspected spoof.

## Step 4: Error Handling

Always generate error handling code. Use this error code table:

**Auth errors:**
| Code | Meaning | Action |
|---|---|---|
| 400 | Bad request parameters | Check request body format |
| 401 | Auth failed (bad client_id/sign/expired token) | Re-check credentials or get new token |
| 451 | Timestamp out of range (±5 min) | Sync server clock with NTP |

**Face operation errors:**
| Code | Meaning | Action |
|---|---|---|
| 440 | Parameter binding failed | Check parameter names and format |
| 461 | face_token invalid or expired | Re-run detect to get new face_token |
| 462 | No permission for this FaceSet | Verify FaceSet belongs to current client |
| 480 | FaceSet not found | Check faceset_token is correct |

**FaceSet errors:**
| Code | Meaning | Action |
|---|---|---|
| 4010 | face_token invalid | Re-run detect |
| 4012 | FaceSet not found or no access | Check faceset_token |
| 4013 | Face not in specified FaceSet | Verify face is registered |
| 4014 | external_id already exists | Use different external_id or remove old one |
| 4021 | display_name already exists | Use different display_name |
| 544 | FaceSet still has faces, can't delete | Remove all faces first |

**Liveness errors:**
| Code | Meaning | Action |
|---|---|---|
| 404 | No face detected in image | Ensure clear frontal face in photo |
| 503 | Liveness service not enabled | Contact support |

## Step 5: Best Practices

Include these in generated code as comments or documentation:

1. **Token caching**: Cache access_token, refresh 30s before expiry. Never call auth per-request.
2. **Image quality**: Use clear frontal photos. Supported formats: JPG, JPEG, PNG, BMP, WebP, TIFF. Max recommended: 5000×5000px.
3. **face_token lifecycle**: Registered tokens are permanent. Unregistered tokens may expire — complete operations promptly after detect.
4. **Similarity thresholds**: 0.7 is the default threshold. Finance/security: raise to 0.8. Convenience-first: lower to 0.6.
5. **Multi-face handling**: detect may return up to 10 faces. For single-face scenarios (selfie), use `faces[0]`. For multi-face, filter by `box` coordinates.
6. **Request tracking**: All responses include `request_id`. Optionally send `X-Request-ID` header for custom tracking.
7. **Liveness detection**: Always recommend for user-facing scenarios. Backend batch processing can skip it.

## Output Format

When generating integration code:
- Use the user's preferred language (Python, Node.js, Go, Java, etc.)
- Include complete, runnable code — not fragments
- Add inline comments in the user's spoken language if they're using Chinese
- Structure as a reusable module/class, not just a script
- Include a usage example at the end
- Set base URL as a configurable constant: `https://stage.aims.authme.com`

## Stage Environment

| Item | Value |
|---|---|
| **Endpoint** | `https://stage.aims.authme.com/` |
| **Health check** | `POST /aims/ping` → `{"message": "pong"}` |
| **Rate limit** | ~120 detect/sec on stage |

All API paths are prefixed with this endpoint. Example: `POST /aims/face/detect` = `POST https://stage.aims.authme.com/aims/face/detect`
