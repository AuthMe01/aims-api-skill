# CLAUDE.md — aims-api-skill

## 專案概述

Authme AIMS 人臉辨識 API 的 Claude Code plugin。安裝後 Claude 能自動根據使用者的應用情境產生完整的串接程式碼。

## 目錄結構

```
.claude-plugin/plugin.json     ← Plugin 設定（名稱、描述）
skills/aims-api/
  SKILL.md                     ← Skill 主文件（觸發條件、API 流程、錯誤碼、最佳實踐）
  references/api-spec.md       ← API 規格參考（所有端點、參數、回應格式）
  evals/evals.json             ← 測試案例（Python 1:1、Node.js 1:N、Go liveness）
apps/aims-demo-api/            ← 範例專案（FastAPI）
  aims_client.py               ← AIMS API 客戶端封裝
  main.py                      ← FastAPI 應用程式
```

## Skill 涵蓋的 API

- `POST /aims/auth/token` — 驗證（HMAC-SHA256 簽章）
- `POST /aims/face/detect` — 人臉偵測
- `POST /aims/face/verify` — 1:1 比對
- `POST /aims/face/identify` — 1:N 搜尋
- `POST /aims/liveness/image` — 活體偵測
- FaceSet CRUD（建立、查詢、註冊、移除、刪除）

## 修改 Skill 後的測試

修改 `SKILL.md` 後，可用 evals 驗證：
1. 參考 `evals/evals.json` 中的 3 個測試案例
2. 每個案例有 prompt 和 expectations
3. 確認產生的程式碼滿足所有 expectations

## 相關資源

- API 完整文件：https://github.com/AuthMe01/aims-docs
- AIMS 後端原始碼：`F:\Git\go_projects\aims\`（內部參考用）
