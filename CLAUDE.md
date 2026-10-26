# CLAUDE.md — aims-api-skill

## 專案概述

Authme AIMS 人臉辨識 API 的 Claude Code plugin。安裝後 Claude 能自動根據使用者的應用情境產生完整的串接程式碼。

目前對應 **AIMS v2.3** 規格。規格的來源是 ekyc-doc repo 的 `content/docs/aims/v2.3/`（線上：https://docs.authme.com/docs/aims/v2.3）；文件更新時，這個 repo 的 `SKILL.md`、`references/api-spec.md`、demo app 都要一起同步。

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
  .env.example                 ← 環境變數範本（AIMS_BASE_URL / AIMS_CLIENT_ID / AIMS_CLIENT_SECRET）
```

## Skill 涵蓋的 API

- `POST /aims/auth/token` — 驗證（HMAC-SHA256 簽章）
- `POST /aims/face/detect` — 人臉偵測
- `POST /aims/face/verify` — 1:1 比對
- `POST /aims/face/identify` — 1:N 搜尋（`top_n` 選填，預設 1）
- `DELETE /aims/face/{face_token}` — 永久刪除人臉資料（v2.3 新增文件）
- `POST /aims/liveness/image` — 活體偵測
- FaceSet CRUD（建立、列表、查詢單筆、更新、刪除、註冊人臉、移除人臉）
- `POST /aims/ocr/qualitycheck` — 影像品質檢查
- `POST /aims/ocr/image` — OCR 文字辨識（含 `Idempotency-Key` 與 `autoRotate`）
- `GET /aims/ocr/calls` — 用量查詢

## v2.3 的關鍵變更（相對 v1.2）

- **錯誤碼統一**：所有 face / FaceSet / auth API 的參數錯誤都是 HTTP 400 + `code` **441**（格式錯誤）或 **450**（缺漏或超出範圍）。舊文件的 `440`、`461`、`462`、`480`、`4013` 不再由 face / FaceSet API 回傳（`461`/`462` 只剩 OCR 品質檢查在用）。
- **資源錯誤**：`4010` face_token 不存在、`4011` face_token 不在此 FaceSet、`4012` FaceSet 不存在；HTTP 是 400 或 404，各 API 不同，見 `references/api-spec.md`。
- **時間誤差**：`time` 超過 ±5 分鐘回 HTTP 401 + `code` **451**；簽章錯誤仍是 `code` 401。同一組 `time` + `sign` 只能用一次（Replay detected）。
- **空結果**：detect 沒有人臉回 `faces: []`，identify 的 FaceSet 沒有人臉回 `results: []`，都是 `code` 0。
- **register 的 `external_id` 是必填**（v1.2 文件誤寫為選填）。
- **活體偵測回應**：`faces[]` 的框座標是平的欄位 `x/y/width/height` 加 `confidence`，沒有 `box` 物件。

## 其他關鍵概念

- **Permission scopes**：每個 endpoint 對應一個 scope（例如 `ocr:image`、`face:detect`）。Scope 由 AuthMe 後台依 `client_id` 預先配置；client 無法在 runtime 請求 scope。Token 缺少 scope 時 server 回 HTTP 403 + `code` 473。skill 在錯誤處理告知使用者該聯繫 AuthMe。
- **Idempotency-Key**：OCR `/image` 接受此 header（UUID），同 key + 同 body 在 10 分鐘內回傳 cache、不重複扣費。產生 key 的原則是「一次邏輯操作一個 UUID」，重試共用同一個。
- **autoRotate**：OCR `/image` 的可選參數，啟用後 0° 失敗會自動嘗試 90°/270°/180°。
- **QC 狀態碼 457–468**：12 個品質失敗代碼，需轉換為使用者友善訊息（範例參見 `apps/aims-demo-api/aims_client.py` 的 `QC_GUIDANCE`）。

## 修改 Skill 後的測試

修改 `SKILL.md` 後，可用 evals 驗證：
1. 參考 `evals/evals.json` 中的 5 個測試案例（含 OCR、人臉資料刪除）
2. 每個案例有 prompt 和 expectations
3. 確認產生的程式碼滿足所有 expectations

## 相關資源

- API 完整文件：https://docs.authme.com/docs/aims/v2.3（原始檔在 ekyc-doc repo 的 `content/docs/aims/v2.3/`）
- AIMS 後端原始碼：`D:\Git\go_projects\aims\`（內部參考用）
