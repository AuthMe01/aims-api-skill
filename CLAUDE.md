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
- FaceSet CRUD（建立、列表、查詢單筆、更新、刪除、註冊人臉、移除人臉）
- **`POST /aims/ocr/qualitycheck`** — 影像品質檢查（v1.2 新增）
- **`POST /aims/ocr/image`** — OCR 文字辨識（v1.2 新增，含 `Idempotency-Key` 與 `autoRotate`）
- **`GET /aims/ocr/calls`** — 用量查詢（v1.2 新增）

## v1.2 新增的關鍵概念

- **Permission scopes**：每個 endpoint 對應一個 scope（例如 `ocr:image`、`face:detect`）。Scope 由 AuthMe 後台依 `client_id` 預先配置；client 無法在 runtime 請求 scope。Token 缺少 scope 時 server 回 HTTP 403。skill 在錯誤處理告知使用者該聯繫 AuthMe。
- **Idempotency-Key**：OCR `/image` 接受此 header（UUID），同 key + 同 body 在 10 分鐘內回傳 cache、不重複扣費。產生 key 的原則是「一次邏輯操作一個 UUID」，重試共用同一個。
- **autoRotate**：OCR `/image` 的可選參數，啟用後 0° 失敗會自動嘗試 90°/270°/180°。
- **QC 狀態碼 457–468**：12 個品質失敗代碼，需轉換為使用者友善訊息（範例參見 `apps/aims-demo-api/aims_client.py` 的 `QC_GUIDANCE`）。

## 修改 Skill 後的測試

修改 `SKILL.md` 後，可用 evals 驗證：
1. 參考 `evals/evals.json` 中的 4 個測試案例（含 OCR）
2. 每個案例有 prompt 和 expectations
3. 確認產生的程式碼滿足所有 expectations

## 相關資源

- API 完整文件：https://github.com/AuthMe01/aims-docs
- AIMS 後端原始碼：`F:\Git\go_projects\aims\`（內部參考用）
