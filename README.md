# aims-api-skill

[Claude Code](https://claude.com/claude-code) plugin for integrating with **Authme AIMS** — face recognition, liveness, FaceSet management, and OCR document recognition.

Install this plugin and let Claude generate complete, production-ready integration code for your application — in any language.

## Install

```bash
claude plugin add https://github.com/AuthMe01/aims-api-skill
```

## What It Does

When you describe an AIMS use case to Claude, the `aims-api` skill automatically activates and generates code with:

- **HMAC-SHA256 authentication** with token caching
- **Correct API call sequences** for your scenario
- **Liveness detection** (anti-spoofing)
- **OCR with quality gate** + user-facing guidance for quality failures
- **Idempotency-Key** for OCR retry protection (no double-billing)
- **Error handling** with all AIMS error codes (including 403 scope errors)
- **Best practices** (token refresh, thread safety, image specs)

## Supported Scenarios

| Scenario | Description |
|---|---|
| **1:1 Verification** | Compare selfie vs. ID card (eKYC, identity check) |
| **1:N Identification** | Search a face database (access control, VIP recognition) |
| **Liveness Detection** | Check if image is a real person |
| **FaceSet Management** | Create and manage face databases |
| **OCR Document Recognition** (v1.2) | Quality check + OCR for ID cards, passports, driver's licenses, health insurance cards |
| **OCR Usage Reporting** (v1.2) | Query cumulative OCR / quality check counts for reconciliation |

## Usage Examples

```
> Help me build a Python backend for eKYC identity verification using AIMS API.

> Create a Node.js Express API for office access control with face recognition.

> Write a Go function to check liveness using AIMS API.

> Help me OCR a Taiwan ID card with AIMS — run quality check first,
  then OCR with auto-rotate, and produce user-facing guidance when QC fails.
```

## Demo App

See `apps/aims-demo-api/` for a complete FastAPI example with all scenarios implemented.

```bash
cd apps/aims-demo-api
cp .env.example .env   # Fill in your client_id and client_secret
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Prerequisites

- [Claude Code](https://claude.com/claude-code) installed
- AIMS API credentials (`client_id` and `client_secret`) from Authme

## API Documentation

Full API documentation: [AIMS API Docs](https://github.com/AuthMe01/aims-docs)

## License

MIT
