# AIMS API Specification Reference

## Authentication

### POST /aims/auth/token
Request (JSON):
- `client_id` (string, UUID, required) — Client identifier
- `time` (integer, required) — Unix timestamp in seconds, ±5 min tolerance
- `sign` (string, required) — HMAC-SHA256(`{client_id}{time}`, client_secret) as hex

Response:
- `code` (int) — 0 = success
- `access_token` (string) — Bearer token for subsequent calls
- `token_type` (string) — "bearer"
- `expires_in` (int) — 300 (seconds)

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

## Face Verification (1:1)

### POST /aims/face/verify
Content-Type: multipart/form-data
Authorization: Bearer {access_token}

Request:
- `face_token_1` (string, UUID, required)
- `face_token_2` (string, UUID, required)

Response:
- `result.similarity` (float) — 0.0 ~ 1.0

Threshold guidance: ≥0.7 same person (default), ≥0.8 high security, ≥0.6 convenience

## Face Identification (1:N)

### POST /aims/face/identify
Content-Type: multipart/form-data
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

## Liveness Detection

### POST /aims/liveness/image
Content-Type: multipart/form-data
Authorization: Bearer {access_token}

Request:
- `image` (file/string, required) — Image file, base64, or URL

Response:
- `result.faces[].liveness_score` (float) — 0.0 ~ 1.0 (≥0.5 = real person)
- `result.faces[].box` (object) — Face bounding box

Note: Does NOT return face_token. Use /aims/face/detect separately for tokens.

## FaceSet Operations

### POST /aims/facesets
Create a FaceSet.
Request (JSON):
- `display_name` (string, required, unique)
- `outer_id` (string, required, unique)
- `tags` (string[], optional)
- `user_data` (string, optional)

Response:
- `faceset.faceset_token` (string, UUID)
- `faceset.face_count` (int)

### GET /aims/facesets
List all FaceSets.

### GET /aims/facesets/{faceset_token}
Get FaceSet details.

### PATCH /aims/facesets/{faceset_token}
Update FaceSet. Body: `display_name`, `tags`, `user_data` (all optional).

### DELETE /aims/facesets/{faceset_token}
Delete FaceSet. Must remove all faces first (error 544 if not empty).

### POST /aims/facesets/{faceset_token}/register
Register a face to FaceSet.
Request (JSON):
- `face_token` (string, UUID, required)
- `display_name` (string, optional)
- `external_id` (string, optional, unique within FaceSet)

### DELETE /aims/facesets/{faceset_token}/faces/{face_token}
Remove a face from FaceSet (does not delete face data).

## OCR Document Recognition (v1.2)

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

All responses include:
- `code` (int) — 0 = success
- `message` (string) — Status message
- `exec_time_ms` (float) — Execution time in milliseconds
- `request_id` (string) — Request tracking ID

## Image Specifications

- Formats: JPG, JPEG, PNG, BMP, WebP, TIFF
- Recommended max: 5000 × 5000 pixels
- Max faces per detect: 10
- Input methods: multipart file upload (recommended), base64, public URL
