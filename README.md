# aims-api-skill

[Claude Code](https://claude.com/claude-code) plugin for integrating with **Authme AIMS** face recognition API.

Install this plugin and let Claude generate complete, production-ready integration code for your application — in any language.

## Install

```bash
claude plugin add https://github.com/AuthMe01/aims-api-skill
```

## What It Does

When you describe a face recognition use case to Claude, the `aims-api` skill automatically activates and generates code with:

- **HMAC-SHA256 authentication** with token caching
- **Correct API call sequences** for your scenario
- **Liveness detection** (anti-spoofing)
- **Error handling** with all AIMS error codes
- **Best practices** (token refresh, thread safety, image specs)

## Supported Scenarios

| Scenario | Description |
|---|---|
| **1:1 Verification** | Compare selfie vs. ID card (eKYC, identity check) |
| **1:N Identification** | Search a face database (access control, VIP recognition) |
| **Liveness Detection** | Check if image is a real person |
| **FaceSet Management** | Create and manage face databases |

## Usage Examples

```
> Help me build a Python backend for eKYC identity verification using AIMS API.

> Create a Node.js Express API for office access control with face recognition.

> Write a Go function to check liveness using AIMS API.
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
