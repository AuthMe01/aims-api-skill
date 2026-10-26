# AIMS API Specification Reference (v2.3)

Source of truth: AIMS v2.3 documentation at https://docs.authme.com/docs/aims/v2.3

## Health and Version (no auth)

### GET /aims/ping
Response: `{"message": "pong"}` (no `code` field).

### GET /aims/version
Response (top level, no envelope):
```json
{"system": {"aims": "2.3.1", "engine": "9.1.0"}, "dependencies": {"cuda": "...", "onnxruntime": "...", "opencv": "...", "openssl": "...", "tensorrt": "..."}}
```
v2.3 behavior applies when `system.aims` starts with `2.3`.

## Authentication

### POST /aims/auth/token
Content-Type: `application/json`

Request:
- `client_id` (string, UUID, required) — Client identifier
- `time` (integer, required) — Unix timestamp in seconds, ±5 min tolerance
- `sign` (string, required) — HMAC-SHA256(`{client_id}{time}`, client_secret) as hex; upper or lower case accepted

Response (top level, no `result`/`data` envelope):
- `code` (int) — 0 = success
- `access_token` (string) — Bearer token for subsequent calls
- `token_type` (string) — "bearer"
- `expires_in` (int) — 300 (seconds). No refresh token.

Errors:
| HTTP | code | message | Scenario |
|---|---|---|---|
| 400 | 441 | `Invalid JSON request body` / `Invalid 'time' format, must be an integer` / `Invalid client_id format` | Malformed body, `time` not an integer (a JSON string `time` is also 441), or `client_id` not a UUID |
| 400 | 450 | `Validation failed: ...` | Missing parameter |

A missing `client_id` is 450; a present but non-UUID `client_id` is 441 (since AIMS 2.3.2, in both DB and non-DB modes — the undeployed 2.3.1 build returned 450).
| 401 | 401 | `Client not found or inactive` | Unknown or disabled client_id |
| 401 | 401 | `Invalid signature` | Bad signature |
| 401 | 401 | `Replay detected` | Same `time` + `sign` already used (e.g. two requests in the same second) |
| 401 | 451 | `Timestamp out of range` | `time` off by more than ±5 min |
| 415 | 415 | `Unsupported Content-Type` | Not JSON / form |
| 500 | 500 | `Internal server error` | — |

### Permission scopes
Scopes are pre-configured per `client_id`; missing scope → HTTP 403, `code` 473.

| Endpoint | Scope |
|---|---|
| `POST /aims/face/detect` | `face:detect` |
| `POST /aims/face/verify` | `face:verify` |
| `POST /aims/face/identify` | `face:identify` |
| `DELETE /aims/face/{face_token}` | `face:register` |
| `POST /aims/facesets/{token}/register` | `face:register` |
| `GET /aims/facesets`, `GET /aims/facesets/{token}` | `faceset:read` |
| `POST /aims/facesets`, `PATCH`/`DELETE /aims/facesets/{token}`, `DELETE /aims/facesets/{token}/faces/{face_token}` | `faceset:write` |
| `POST /aims/liveness/image` | `liveness:image` |
| `POST /aims/ocr/qualitycheck` | `ocr:quality_check` |
| `POST /aims/ocr/image` | `ocr:image` |
| `GET /aims/ocr/calls` | none |

## Face Detection

### POST /aims/face/detect
Content-Type: multipart/form-data
Authorization: Bearer {access_token}

Request:
- `image` (file/string, required) — Image file (multipart), base64 string, or public URL

Response:
- `result.face_number` (int) — Number of faces detected (max 10)
- `result.faces[].face_token` (string, UUID) — Unique face identifier
- `result.faces[].box` (object) — `{x, y, width, height}` in pixels
- `result.faces[].landmarks` (object) — `{eye_left, eye_right, nose, mouth_left, mouth_right}` each `{x, y}`
- `result.faces[].encoding.vector` (string) — Base64-encoded feature vector
- `result.faces[].encoding.version` (string) — Model version

No face → `code` 0, `face_number` 0, `faces: []` (not an error). The result also carries `truncated` (bool) — true when the 10-face limit was hit, meaning the image may contain faces that were not processed (don't rely on detect for crowd photos).

Errors: 400/441 malformed, 400/442 `image` not file/URL/base64, 400/443 multipart filename has no supported extension, 400/446 undecodable image, 400/449 no/unreadable image, 401/401, 403/473, 429/445 busy, 500/500.

## Face Verification (1:1)

### POST /aims/face/verify
Content-Type: application/x-www-form-urlencoded (tokens only, no file upload; also accepts application/json)
Authorization: Bearer {access_token}

Request:
- `face_token_1` (string, UUID, required)
- `face_token_2` (string, UUID, required)

Response:
- `result.similarity` (float) — 0.0 ~ 1.0

Threshold guidance: ≥0.7 same person (default), ≥0.8 high security, ≥0.6 convenience; 0.5~0.7 may warrant manual review

Errors: 400/441 token not a UUID (or the two tokens have incompatible feature versions), 400/450 missing token, 400/4010 face_token not found/expired/not owned, 401/401, 403/473, 500/500.

## Face Identification (1:N)

### POST /aims/face/identify
Content-Type: application/x-www-form-urlencoded (tokens only, no file upload; also accepts application/json)
Authorization: Bearer {access_token}

Request:
- `face_token` (string, UUID, required)
- `faceset_token` (string, UUID, required)
- `top_n` (integer, optional) — 1~20, default 1

Response:
- `result.results[].similarity` (float)
- `result.results[].face_token` (string)
- `result.results[].face_name` (string) — display_name at registration
- `result.results[].face_id` (string) — external_id at registration

`results` is sorted by similarity, highest first, and is NOT filtered by threshold. Empty FaceSet → `code` 0, `results: []`.

Errors: 400/441 token not a UUID, 400/450 missing token or `top_n` outside 1~20, 400/4010 face_token not found/expired/not owned, 401/401, 403/473, 404/4012 FaceSet not found/not owned, 500/500.

### DELETE /aims/face/{face_token}
Authorization: Bearer {access_token}

Permanently deletes the face_token and its face data (feature vector, cropped face image) and removes it from every FaceSet. Irreversible. To only remove it from one FaceSet, use `DELETE /aims/facesets/{faceset_token}/faces/{face_token}`.

Response: `{ "code": 0, "message": "Face with ID <face_token> deleted" }`

Errors: 400/441 not a UUID, 401/401, 403/473, 404/4010 not found / already deleted / not owned, 500/500.

## Liveness Detection

### POST /aims/liveness/image
Content-Type: multipart/form-data
Authorization: Bearer {access_token}

Request:
- `image` (file/string, required) — Image file, base64, or URL
- `channel` (string, optional) — usage tracking channel (default `default`)

Response:
- `result.face_count` (int) — Number of faces (max 10)
- `result.faces[].liveness_score` (float) — 0.0 ~ 1.0 (≥0.5 = real person)
- `result.faces[].x`, `.y`, `.width`, `.height` (float) — Face box, flat fields (no `box` object)
- `result.faces[].confidence` (float) — Face detection confidence

No face → HTTP 404, `{ "code": 404, "message": "No face detected", ... }` without `result`.

Errors (HTTP status = `code`): 400 missing image, 401 unauthorized, 404 no face, 429 busy, 500 inference failure, 503 liveness service not enabled. Unreadable image → HTTP 400 / `code` 449.

Note: Does NOT return face_token. Use /aims/face/detect separately for tokens.

## FaceSet Operations

### POST /aims/facesets
Create a FaceSet.
Request (JSON):
- `display_name` (string, required) — unique within the account
- `outer_id` (string, optional) — no uniqueness constraint; returned as `null` if omitted
- `tags` (string[], optional)
- `user_data` (string, optional)

Response (wrapped in `data`, no exec_time_ms/request_id):
- `data.faceset_token` (string, UUID)
- `data.display_name` (string)
- `data.outer_id` (string | null)
- `data.face_count` (int)

Errors: 400/441 invalid JSON, 400/450 missing `display_name`, 400/4021 `display_name` already exists, 401/401, 403/473, 415/415.

### GET /aims/facesets
List FaceSets. Response wrapped in `data` with pagination:
- `data.total`, `data.page`, `data.page_size`, `data.total_pages` (int)
- `data.facesets[]` — each `{ faceset_token, display_name, outer_id, face_count }`

### GET /aims/facesets/{faceset_token}
Get FaceSet details, including registered faces.

Errors: 400/441 not a UUID, 401/401, 403/473, 404/4012.

### PATCH /aims/facesets/{faceset_token}
Update FaceSet. Body (JSON): `display_name`, `tags`, `user_data` (all optional).

Errors: 400/441 not a UUID or invalid JSON, 400/450 `display_name` is an empty string, 400/4021 new `display_name` already exists, 401/401, 403/473, 404/4012, 415/415.

### DELETE /aims/facesets/{faceset_token}
Delete FaceSet. Must remove all faces first.

Errors: 400/441, 401/401, 403/473, 404/4012, 409/544 FaceSet still has faces.

### POST /aims/facesets/{faceset_token}/register
Register a face to FaceSet.
Request (JSON):
- `face_token` (string, UUID, required)
- `display_name` (string, optional)
- `external_id` (string, **required**, unique within FaceSet) — map to the user ID in your system

Errors: 400/441 not a UUID or invalid JSON, 400/450 missing `face_token` or `external_id`, 400/4010 face_token not found/expired/not owned, 400/4014 `external_id` already exists, 401/401, 403/473, 404/4012, 415/415.

### DELETE /aims/facesets/{faceset_token}/faces/{face_token}
Remove a face from FaceSet (does not delete face data).

Errors: 400/441, 401/401, 403/473, 404/4010 face_token not found, 404/4011 face_token not registered in this FaceSet (incl. already removed), 404/4012 FaceSet not found.

## OCR Document Recognition

### POST /aims/ocr/qualitycheck
Image quality gate. Call before `/aims/ocr/image` to avoid wasting OCR billing on bad images.

Content-Type: `application/json` (or `multipart/form-data` / `application/x-www-form-urlencoded`)
Authorization: Bearer {access_token}

Request:
- `image` (file/string, required) — Image file (multipart), base64 data URI, or public URL
- `cardType` (string, required) — Target card type. Valid values: `TWN_IDCard_Front`, `TWN_IDCard_Back`, `TWN_HealthCard_Front`, `TWN_DriverLicense_Front`, `TWN_Passport_Front`, `TWN_ResidentCard_Front`
- `image_type` (string, optional) — Source hint: `formdata` / `base64` / `url`. Auto-detected by default.
- `channel` (string, optional) — Channel identifier for usage tracking (default `default`)
- `debug` (string, optional) — `true` to include QC thresholds and raw metric scores
- `meta` (string, optional) — `true` to include image EXIF metadata
- `returnCardBase64` (string, optional) — `true` to include the cropped card image when QC passes

Response:
- HTTP 200 with `code = 0` → quality check passed (`result.status = "passed"`)
- HTTP 200 with `code != 0` → quality check failed (`result.status = "failed"`); see Quality Check Status Codes below

Quality Check Status Codes (returned in `code` field):
| Code | Reason |
|---|---|
| 457 | No card detected |
| 458 | Card partially outside frame |
| 459 | Card not in expected position |
| 460 | Invalid brightness/contrast |
| 461 | Detected card type does not match requested `cardType` |
| 462 | Grayscale image, color required |
| 463 | Image too blurry |
| 464 | Glare detected (CV method) |
| 465 | Glare detected (model method) |
| 466 | No face detected on card |
| 468 | Unexpected engine error |

### POST /aims/ocr/image
OCR text extraction. Returns detected card type and extracted fields.

Content-Type: `multipart/form-data`
Authorization: Bearer {access_token}
Optional Header: `Idempotency-Key: <uuid>` — recommended if client has retry logic

Request:
- `image` (file/string, required) — multipart file, base64 data URI, or public URL
- `channel` (string, optional) — usage tracking channel (default `default`)
- `autoRotate` (string, optional) — `true` to auto-retry at 90°/270°/180° when 0° fails validation (default `false`)

Response:
- `result.card.type` (string) — Detected card: `TWN_IDCard_Front`, `TWN_IDCard_Back`, `TWN_HealthCard_Front`, `TWN_DriverLicense_Front`, `Passport`, or `Unknown`
- `result.text` (object) — Extracted fields (key/value); shape depends on card type
- `result.rotation_applied` (int) — Final rotation used (0/90/180/270); always 0 unless `autoRotate=true` and 0° failed
- Response header `X-Idempotent-Replay: true|false` — true means the response was served from cache

Text fields by card type:
- `TWN_IDCard_Front`: `idNumber` (matches `^[A-Z][0-9]{9}$`), `name`, `dateOfBirth`, `issueDate`, `expiryDate`
- `Passport`: `passportNumber` or `documentNumber` (matches `^[A-Z0-9]{9}$`), `surName`, `givenName`, `dateOfBirth`, `expiryDate`, `nationality`, `country`, `gender`
- Other types: any combination of recognized fields

Error codes (returned as HTTP status):
- 400 — Missing `image`
- 404 — No card detected
- 409 — `Idempotency-Key` reused with different body
- 422 — Reflective image or no text found
- 429 — Backpressure (resource exhaustion)
- 500 — OCR inference / service error
- 503 — OCR service disabled

Idempotency behavior:
- Cache TTL: 10 minutes, capacity 10,000 entries (single-instance in-memory)
- Same key + same body → cached 200 response, no execution, no billing, `X-Idempotent-Replay: true`
- Same key + different body → HTTP 409 (client bug)
- Generate one UUID per logical OCR operation; reuse across all HTTP retries of that operation

### GET /aims/ocr/calls
Query cumulative OCR / quality check call counts. Useful for reconciliation.

Authorization: Bearer {access_token}
No body, no query parameters.

Response:
- `api_calls.ocr_image` (int) — Cumulative successful OCR /image calls
- `api_calls.quality_check` (int) — Cumulative quality check calls
- `api_calls_by_channel` (object) — Same structure broken down by channel
- `channels` (string[]) — Channels that have had calls
- `app_name` (string) — System identifier
- `time` (string) — UTC RFC 3339 timestamp
- `resp_sign` (string) — HMAC-SHA256 signature of the api_calls JSON; verify with your reporting secret

OCR success definition (only counted when all three are true):
1. HTTP 200
2. `result.card.type != "Unknown"`
3. At least one non-empty field in `result.text`

Idempotency replays do not count again (handler did not execute).

## Common Response Fields

All responses except `/aims/ping` and `/aims/version` include top-level `code` (int, 0 = success) and `message` (string). Error responses use the same top-level `{code, message}` shape on every endpoint (inference errors also carry `request_id`). Branch on `code`, not `message` (English, wording may change).

Delete / remove / register success bodies are just `{code: 0, message}` (plus `data` on register when present) — check `code == 0`.

Common codes across face / FaceSet / auth APIs: 441 malformed parameter (HTTP 400), 450 missing or out-of-range parameter (HTTP 400), 415 unsupported Content-Type, 401 auth, 451 clock skew (HTTP 401), 473 missing scope (HTTP 403), 500 internal error, 502 data access error (HTTP 500).

AI inference endpoints (detect, verify, identify, liveness, ocr) wrap their payload in `result` and also return:
- `exec_time_ms` (float) — Execution time in milliseconds
- `request_id` (string) — Request tracking ID

FaceSet CRUD endpoints (`/aims/facesets...`) wrap their payload in `data` and do NOT include exec_time_ms / request_id.

## Image Specifications

- Formats: JPG, JPEG, PNG, BMP, WebP, TIFF
- Multipart: the `image` part's **filename must end in** `.jpg` / `.jpeg` / `.jpe` / `.png` / `.bmp` / `.tif` / `.tiff` / `.webp` (case-insensitive). The server chooses the decoder by extension and ignores `Content-Type`; no / unknown extension → HTTP 400, `code` 443 (`PARAMETER ERROR ImageType`). Applies to detect, liveness, and OCR uploads.
- Recommended max: 5000 × 5000 pixels
- Max faces per detect: 10
- Input methods: multipart file upload (recommended), base64, public URL
