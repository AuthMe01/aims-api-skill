---
name: aims-api
description: Integrate with Authme AIMS — face recognition, liveness, FaceSet management, and OCR document recognition. Use when users want to add identity verification, person identification, anti-spoofing, or document OCR (ID card, passport, etc.) to their application.
---

# AIMS API Integration Skill

Help developers integrate Authme AIMS into their applications. AIMS covers face recognition (detect / verify / identify), liveness detection, FaceSet management, and OCR document recognition. Guide users through authentication, correct API call sequences, and error handling based on their use case.

## When to Trigger

Activate when the user wants to:
- Integrate face recognition into their app
- Add face detection, verification (1:1), or identification (1:N)
- Implement liveness / anti-spoofing detection
- Manage FaceSets (face databases)
- Authenticate with AIMS API (HMAC-SHA256)
- **OCR document recognition** (ID cards, passports, driver's licenses, health insurance cards) — new in v1.2
- **Image quality checks** for documents before OCR — new in v1.2

Do NOT trigger for: unrelated image processing, face APIs from other vendors, or non-AIMS workflows.

## Step 1: Identify the Use Case

Ask the user which scenario they need:

| Scenario | Description | APIs Used |
|---|---|---|
| **1:1 Verification** | Confirm a person's identity (e.g., selfie vs. ID card) | auth → liveness → detect × 2 → verify |
| **1:N Identification** | Find a person in a database (access control, VIP) | auth → (faceset setup) → liveness → detect → identify |
| **Liveness Only** | Check if the image is a real person (anti-spoofing) | auth → liveness |
| **FaceSet Management** | Create/manage face databases for 1:N search | auth → facesets CRUD + detect + register |
| **OCR Document Recognition** | Extract text from ID cards, passports, etc. | auth → qualitycheck → ocr/image |
| **OCR Usage Reporting** | Query OCR call counts for reconciliation | auth → ocr/calls |

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
   POST /aims/facesets/{faceset_token}/register     → registered
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

### For OCR Document Recognition (v1.2)

Recommended two-step flow — quality gate first, then OCR. The quality check is cheap and prevents wasted OCR calls on bad images.

```
1. POST /aims/auth/token              → access_token
2. POST /aims/ocr/qualitycheck        → pass / fail (12 fail codes; guide user)
   - Body: image, cardType (e.g. TWN_IDCard_Front)
3. POST /aims/ocr/image               → card type + extracted text fields
   - Body: image, optional autoRotate=true
   - Optional header: Idempotency-Key (see below)
```

**Card types to choose `cardType` from:**
`TWN_IDCard_Front`, `TWN_IDCard_Back`, `TWN_HealthCard_Front`, `TWN_DriverLicense_Front`, `TWN_Passport_Front`, `TWN_ResidentCard_Front`.

**autoRotate**: pass `autoRotate=true` (form field) to have AIMS automatically retry at 90°/270°/180° when 0° fails validation. Useful when the camera doesn't auto-rotate (mobile web, some kiosks). Default `false`.

**Idempotency-Key** (recommended if your client retries on transient errors):
- Send header `Idempotency-Key: <uuid>` on `/aims/ocr/image`
- Same key + same body within 10 minutes returns the cached response (no double-billing, no second engine run). Response includes `X-Idempotent-Replay: true` when cached
- Same key + DIFFERENT body returns HTTP 409 (treat as a client bug)
- **Generate one UUID per logical OCR operation, not per HTTP attempt.** Reuse the same UUID across all retries of that operation.

```python
# Example (Python):
import uuid, time, httpx
key = str(uuid.uuid4())  # one key for this logical OCR operation
for attempt in range(3):
    resp = httpx.post(
        f"{base_url}/aims/ocr/image",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        files={"image": image_bytes},
        data={"autoRotate": "true"},
        timeout=30.0,
    )
    if resp.status_code == 200:
        break
    time.sleep(2 ** attempt)
```

### For OCR Usage Reporting

```
1. POST /aims/auth/token           → access_token
2. GET  /aims/ocr/calls            → cumulative counts (api_calls, api_calls_by_channel)
```

The response includes a `resp_sign` (HMAC-SHA256) that callers can verify with their reporting secret.

OCR success is counted only when **all three** are true: HTTP 200, card type ≠ Unknown, at least 1 extracted text field. Idempotency replays do NOT count.

## Step 4: Error Handling

Always generate error handling code. Use this error code table:

**Auth errors:**
| Code | Meaning | Action |
|---|---|---|
| 400 | Bad request parameters | Check request body format |
| 401 | Auth failed (bad client_id/sign/expired token) | Re-check credentials or get new token |
| 403 | Token authenticated but lacks permission for this endpoint | The client's token is missing a required scope. Contact Authme to enable it; the client code cannot self-request scopes. |
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

**OCR / Quality Check errors:**
| Code | Meaning | Action |
|---|---|---|
| 400 | Missing `image` parameter | Check form fields |
| 404 | OCR could not detect a card | Have user provide a clearer photo |
| 409 | `Idempotency-Key` reused with different body | Client bug — do not reuse key across different requests |
| 422 | Card image reflective / no text found | Have user retake away from light |
| 429 | System backpressure (resource exhaustion) | Retry with exponential backoff |
| 503 | OCR service is disabled | Contact your business representative |

**Quality check status codes** (returned on HTTP 200 with `code != 0`, `result.status = "failed"`):

| Code | Reason | User-facing guidance |
|---|---|---|
| 457 | No card detected | "Please make sure the entire card is visible in the frame." |
| 458 | Card partially outside frame | "Center the card so it's fully inside the frame." |
| 459 | Card not in expected position | "Align the card with the on-screen guide." |
| 460 | Invalid brightness/contrast | "Move to a well-lit area and try again." |
| 461 | Card type mismatch | "The card detected does not match the expected type." |
| 462 | Grayscale image, color required | "Please use a color image." |
| 463 | Image too blurry | "Hold the camera steady and make sure the card is in focus." |
| 464 | Glare detected (CV method) | "Avoid direct light reflecting off the card." |
| 465 | Glare detected (model method) | "Avoid direct light reflecting off the card." |
| 466 | No face detected on card | "Make sure the front side of the card is being captured." |
| 468 | Unexpected engine error | "Something went wrong. Please try again." |

Map these to localized user messages in the generated code — do not return raw codes to end users.

## Step 5: Best Practices

Include these in generated code as comments or documentation:

1. **Token caching**: Cache access_token, refresh 30s before expiry. Never call auth per-request.
2. **Image quality**: Use clear frontal photos. Supported formats: JPG, JPEG, PNG, BMP, WebP, TIFF. Max recommended: 5000×5000px.
3. **face_token lifecycle**: Registered tokens are permanent. Unregistered tokens may expire — complete operations promptly after detect.
4. **Similarity thresholds**: 0.7 is the default threshold. Finance/security: raise to 0.8. Convenience-first: lower to 0.6.
5. **Multi-face handling**: detect may return up to 10 faces. For single-face scenarios (selfie), use `faces[0]`. For multi-face, filter by `box` coordinates.
6. **Request tracking**: All responses include `request_id`. Optionally send `X-Request-ID` header for custom tracking.
7. **Liveness detection**: Always recommend for user-facing scenarios. Backend batch processing can skip it.
8. **OCR quality gate**: Always call `/aims/ocr/qualitycheck` before `/aims/ocr/image` to avoid wasted OCR billing on bad images.
9. **OCR idempotency**: If your client has retry logic, set `Idempotency-Key` on `/aims/ocr/image` calls. Generate one UUID per logical OCR operation, reuse across retries.
10. **Permission scopes (v1.2)**: Token scopes are pre-configured per `client_id` by Authme. If you see HTTP 403, contact Authme to enable the missing scope. The client cannot request scopes at runtime.

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
