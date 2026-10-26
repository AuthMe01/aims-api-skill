---
name: aims-api
description: Integrate with Authme AIMS — face recognition, liveness, FaceSet management, and OCR document recognition. Use when users want to add identity verification, person identification, anti-spoofing, or document OCR (ID card, passport, etc.) to their application.
---

# AIMS API Integration Skill

Help developers integrate Authme AIMS into their applications. AIMS covers face recognition (detect / verify / identify), liveness detection, FaceSet management, and OCR document recognition. Guide users through authentication, correct API call sequences, and error handling based on their use case.

This skill targets **AIMS v2.3** (the current specification). If the user says they are on v1.2 or earlier, see "Migrating from v1.2" at the end of this file.

## When to Trigger

Activate when the user wants to:
- Integrate face recognition into their app
- Add face detection, verification (1:1), or identification (1:N)
- Implement liveness / anti-spoofing detection
- Manage FaceSets (face databases)
- Authenticate with AIMS API (HMAC-SHA256)
- Delete face data (e.g., right-to-erasure / account deletion)
- **OCR document recognition** (ID cards, passports, driver's licenses, health insurance cards)
- **Image quality checks** for documents before OCR

Do NOT trigger for: unrelated image processing, face APIs from other vendors, or non-AIMS workflows.

## Step 1: Identify the Use Case

Ask the user which scenario they need:

| Scenario | Description | APIs Used |
|---|---|---|
| **1:1 Verification** | Confirm a person's identity (e.g., selfie vs. ID card) | auth → liveness → detect × 2 → verify |
| **1:N Identification** | Find a person in a database (access control, VIP) | auth → (faceset setup) → liveness → detect → identify |
| **Liveness Only** | Check if the image is a real person (anti-spoofing) | auth → liveness |
| **FaceSet Management** | Create/manage face databases for 1:N search | auth → facesets CRUD + detect + register |
| **Face Data Deletion** | Permanently erase a person's face data | auth → `DELETE /aims/face/{face_token}` |
| **OCR Document Recognition** | Extract text from ID cards, passports, etc. | auth → qualitycheck → ocr/image |
| **OCR Usage Reporting** | Query OCR call counts for reconciliation | auth → ocr/calls |

## Step 2: Generate Authentication Code

All AIMS API calls require a Bearer token. Generate the auth helper first.

The signing algorithm:
1. Concatenate `client_id` + unix timestamp (seconds) as string
2. HMAC-SHA256 with `client_secret` as key
3. Output as hex string (upper or lower case both accepted)

Provide the auth code in the user's language. Reference `references/api-spec.md` for endpoint details.

Key rules:
- `client_secret` must NEVER appear in frontend code, mobile apps, or version control
- Cache the token in backend; refresh 30 seconds before expiry (token lives 300 seconds). There is no refresh token — just sign again.
- Server time must be NTP-synced; ±5 minute tolerance on `time` parameter (otherwise HTTP 401 / `code` 451)
- **Replay protection**: each `time` + `sign` pair is accepted only once. Because `sign` depends only on `client_id` + `time`, two token requests for the same client in the same second produce the same pair and the second is rejected (`401`, `Replay detected`). Guard token refresh with a lock (or single-flight) so concurrent requests don't all re-sign at once, and if you must re-sign (e.g. after a 401 mid-flow), make sure `time` has advanced past the previous sign's second.
- The token response is top-level: `{code, message, access_token, token_type, expires_in}` (no `result`/`data` envelope). Send the request as JSON.

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

When an image has no face, detect returns `code` 0 with `faces: []` (not an error). Generated code must check for an empty array and return a clear "no face found" result instead of indexing `faces[0]`.

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

Notes for generated code:
- `external_id` is **required** on register and must be unique within the FaceSet — map it to the user/employee ID in the caller's system so `results[].face_id` maps back directly.
- `top_n` is optional (1~20, default **1**). Pass it explicitly when the UI shows several candidates.
- `results` is sorted by similarity but **not filtered by threshold** — apply the 0.7 threshold yourself.
- `results` is `[]` when the FaceSet has no faces. Check the length before reading `results[0]`.

### For Face Data Deletion

```
1. POST /aims/auth/token               → access_token
2. DELETE /aims/face/{face_token}      → face data erased, removed from every FaceSet
```

This is irreversible. To only stop a face from matching in one FaceSet, use `DELETE /aims/facesets/{faceset_token}/faces/{face_token}` instead (keeps the face data). Generated code that deletes should store the `face_token` returned at registration time, because there is no lookup by `external_id`.

- No need to remove the face from each FaceSet first — the delete does that.
- Requires the `face:register` scope (the same scope that registers faces).
- Treat 404 / `code` 4010 as "already deleted" in erasure flows, so retries are idempotent.

### For Liveness Only

```
1. POST /aims/auth/token           → access_token
2. POST /aims/liveness/image       → liveness_score
```

Score interpretation: ≥ 0.5 = real person, < 0.5 = suspected spoof.

Response shape: `result.face_count` and `result.faces[]`, where each face has `liveness_score`, `x`, `y`, `width`, `height`, `confidence` (the box fields are flat — there is no `box` object, unlike detect). When no face is found the response is HTTP 404 with `code` 404 and no `result`.

With several faces, each gets its own score. For a selfie, judge the largest face (by `width * height`) rather than assuming `faces[0]` is the subject.

### For OCR Document Recognition

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

Always generate error handling code. Every error response carries both an HTTP status and a JSON `code`. **Branch on `code`** (one HTTP status maps to several codes); use the HTTP status only as a coarse category. Never branch on the `message` string — it is English developer text and its wording may change.

**Parameter errors (all face / FaceSet / auth APIs):**
| HTTP | Code | Meaning | Action |
|---|---|---|---|
| 400 | 441 | Malformed parameter (token / client_id not a UUID, body not valid JSON, `time` not an integer). Known server deviation: AIMS **2.3.1** returns 450 for a non-UUID `client_id` on the token endpoint; releases after 2.3.1 return 441 as documented. Treat both as a credentials/config error. On `verify` it can also mean the two face_tokens were produced by incompatible model versions | Fix the request format — a client bug. For verify with valid UUIDs, re-run detect on both images |
| 400 | 450 | Missing required parameter, or value out of range (e.g. `top_n` outside 1~20) | Add/fix the parameter — client bug |
| 415 | 415 | Unsupported `Content-Type` | Use JSON or form as documented per endpoint |

**Auth / permission errors:**
| HTTP | Code | Meaning | Action |
|---|---|---|---|
| 401 | 401 | Token request: client_id not found/disabled, bad signature, or replayed `time`+`sign`. Other APIs: token missing/invalid/expired | On other APIs: drop the cached token, fetch a new one, retry **once**. On the token endpoint: check credentials |
| 401 | 451 | `time` differs from server clock by more than ±5 min | Sync server clock with NTP (do not retry blindly) |
| 403 | 473 | Token lacks the scope this endpoint requires | Contact Authme to enable the scope; the client cannot request scopes at runtime. Surface the endpoint's scope name (see `references/api-spec.md`) in the error |

**Face operation errors (`/aims/face/*`):**
| HTTP | Code | Meaning | Action |
|---|---|---|---|
| 400 | 442 | `image` is not a file, URL, or base64 | Check the `image` field |
| 400 | 443 | Multipart filename has no / an unsupported extension | Give the multipart part a filename ending in `.jpg`/`.png`/etc. (see Best Practices #2) |
| 400 | 446 | Image cannot be decoded (corrupted base64) | Check the encoding |
| 400 | 449 | No image uploaded / unreadable image | Ensure a supported format is uploaded |
| 429 | 445 | System busy | Retry with exponential backoff |
| 400 / 404 | 4010 | face_token not found, expired, or not owned by this account (400 on verify/identify/register, 404 on delete) | Re-run detect to get a new face_token |
| 404 | 4012 | FaceSet not found or not owned by this account | Check faceset_token |

**FaceSet errors (`/aims/facesets/*`):**
| HTTP | Code | Meaning | Action |
|---|---|---|---|
| 400 / 404 | 4010 | face_token not found / expired / not owned | Re-run detect |
| 404 | 4011 | face_token exists but is not registered in this FaceSet (incl. already removed) | Treat as already removed if the goal was removal |
| 404 | 4012 | FaceSet not found or not owned | Check faceset_token |
| 400 | 4014 | external_id already exists in this FaceSet | Use a different external_id, or remove the old face first |
| 400 | 4021 | display_name already exists in this account | Use a different display_name |
| 409 | 544 | FaceSet still has faces, can't delete | Remove all faces first |

"Not found" and "belongs to another account" deliberately return the same code (4010 / 4012).

**Server errors:**
| HTTP | Code | Meaning | Action |
|---|---|---|---|
| 500 | 500 | Internal error | Log `request_id`, contact support |
| 500 | 502 | Data access error | Retry later; if persistent, contact support with `request_id` |

**Liveness errors** (`/aims/liveness/image` — here `code` equals the HTTP status, except an unreadable image which is HTTP 400 / `code` 449):
| HTTP / Code | Meaning | Action |
|---|---|---|
| 400 | Missing `image` | Check form fields |
| 404 | No face detected in image | Ensure clear frontal face in photo |
| 429 | System busy | Retry with backoff |
| 500 | Inference failed | Contact support with `request_id` |
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
2. **Image upload**: For multipart uploads the server picks the decoder from the **filename extension** of the `image` part — the `Content-Type` is ignored. The filename must end in `.jpg`, `.jpeg`, `.jpe`, `.png`, `.bmp`, `.tif`, `.tiff`, or `.webp` (case-insensitive), otherwise HTTP 400 / `code` 443. This bites code that uploads raw bytes: Node `FormData.append("image", blob)` sends `blob`, Go `CreateFormFile("image", "image")`, Python `files={"image": bytes}` — always pass an explicit filename such as `"image.jpg"` (the extension need not match the real format). Use clear frontal photos; max recommended 5000×5000px.
3. **face_token lifecycle**: Registered tokens are permanent. Unregistered tokens may expire — complete operations promptly after detect.
4. **Similarity thresholds**: 0.7 is the default threshold. Finance/security: raise to 0.8. Convenience-first: lower to 0.6.
5. **Multi-face handling**: detect may return up to 10 faces. For single-face scenarios (selfie), use `faces[0]`. For multi-face, filter by `box` coordinates.
6. **Request tracking**: AI inference responses (detect / verify / identify / liveness / ocr) include `request_id`; FaceSet CRUD responses use a `data` envelope without it. Optionally send `X-Request-ID` header for custom tracking.
7. **Liveness detection**: Always recommend for user-facing scenarios. Backend batch processing can skip it.
8. **OCR quality gate**: Always call `/aims/ocr/qualitycheck` before `/aims/ocr/image` to avoid wasted OCR billing on bad images.
9. **OCR idempotency**: If your client has retry logic, set `Idempotency-Key` on `/aims/ocr/image` calls. Generate one UUID per logical OCR operation, reuse across retries.
10. **Permission scopes**: Token scopes are pre-configured per `client_id` by Authme. If you see HTTP 403 / `code` 473, contact Authme to enable the missing scope. The client cannot request scopes at runtime.
11. **Empty results are not errors**: detect `faces` and identify `results` come back as `[]` with `code` 0. Always check length.
12. **Preserve HTTP status in the error type**: wrap errors as `{http_status, code, message, request_id}` so callers can map them without a hand-written code→status table.

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
| **Endpoint** | `https://stage.aims.authme.com` (no trailing slash; paths start with `/aims/...`) |
| **Health check** | `GET /aims/ping` → `{"message": "pong"}` (no auth, no `code` field) |
| **Server version** | `GET /aims/version` (no auth) → `{"system": {"aims": "2.3.1", "engine": "..."}, "dependencies": {...}}`. Check `system.aims` starts with `2.3` before relying on v2.3 error codes; older servers return `code` 400 for parameter errors on `/aims/facesets/*` and `/aims/auth/token` |
| **Rate limit** | ~120 detect/sec on stage |

All API paths are prefixed with this endpoint. Example: `POST /aims/face/detect` = `POST https://stage.aims.authme.com/aims/face/detect`

Do not stress-test stage without authorization.

## Migrating from v1.2

If the user has existing code written against the v1.2 docs, check these items:

| API | Scenario | v2.3 behavior |
|---|---|---|
| `POST /aims/auth/token` | `time` off by more than ±5 min | HTTP 401, `code` **451** (bad signature stays `code` 401) |
| `POST /aims/auth/token` | Signature hex letter case | Both accepted |
| `POST /aims/face/detect` | No face in image | `faces` is `[]` |
| `POST /aims/face/identify` | FaceSet has no faces | `results` is `[]` |
| `POST /aims/face/identify` | FaceSet does not exist | HTTP 404, `code` **4012** |
| `POST /aims/face/identify`, `/verify` | face_token does not exist | HTTP 400, `code` **4010** |
| FaceSet APIs | FaceSet does not exist | HTTP 404, `code` **4012** |
| `DELETE /aims/facesets/{fs}/faces/{ft}` | face_token does not exist | HTTP 404, `code` **4010** |
| `DELETE /aims/facesets/{fs}/faces/{ft}` | face_token not in this FaceSet | HTTP 404, `code` **4011** |
| `POST /aims/facesets` | `outer_id` | Optional, uniqueness not checked |
| `POST /aims/face/identify` | `top_n` omitted | Optional, defaults to **1** |
| `/aims/facesets/*`, `/aims/auth/token` | Malformed / missing parameter | `code` changed from 400 to **441** / **450**; HTTP stays 400 |
| `DELETE /aims/face/{face_token}` | — | Newly documented |
| `POST /aims/facesets/{fs}/register` | `external_id` | **Required** (v1.2 docs wrongly said optional; behavior unchanged) |

Old face-error codes from pre-v2.3 docs (`440`, `461`, `462`, `480`, `4013`) are no longer returned by face/FaceSet APIs — replace them with the tables above. (`461`/`462` still exist, but only as OCR quality-check codes.)
