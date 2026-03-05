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
