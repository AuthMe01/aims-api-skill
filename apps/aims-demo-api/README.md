# AIMS Demo API

使用 FastAPI 展示 Authme AIMS 人臉辨識 API 的串接範例。

此專案由 **aims-api skill** 產生，展示完整的串接最佳實踐。

## 功能

| 端點 | 說明 |
|---|---|
| `POST /api/verify-identity` | 1:1 身分驗證（證件照 vs 自拍照） |
| `POST /api/liveness` | 活體偵測 |
| `POST /api/facesets` | 建立 FaceSet |
| `GET /api/facesets` | 列出所有 FaceSet |
| `POST /api/facesets/{token}/register` | 偵測並註冊人臉到 FaceSet |
| `POST /api/facesets/{token}/identify` | 1:N 人臉搜尋 |
| `DELETE /api/facesets/{token}/faces/{face_token}` | 從 FaceSet 移除人臉（保留人臉資料） |
| `DELETE /api/faces/{face_token}` | 永久刪除人臉資料（從所有 FaceSet 移除） |
| `POST /api/ocr/qualitycheck` | OCR 前的影像品質檢查 |
| `POST /api/ocr/recognize` | OCR 辨識（含 Idempotency-Key） |
| `POST /api/ocr/quality-then-recognize` | 品質檢查通過才送 OCR |
| `GET /api/ocr/usage` | OCR 用量查詢 |

對應 **AIMS v2.3** 規格。

## 快速開始

```bash
cd apps/aims-demo-api
cp .env.example .env
# 編輯 .env 填入你的 client_id 和 client_secret

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

開啟 http://localhost:8000/docs 查看 Swagger UI。

## 架構

```
aims_client.py   ← AIMS API 客戶端（Token 快取、簽章、錯誤處理）
main.py          ← FastAPI 應用程式（REST 端點）
.env.example     ← 環境變數範本
```

## 重點設計

- **Token 快取**：`AIMSClient` 自動快取 access_token，到期前 30 秒自動更新
- **Thread-safe**：Token 更新使用 lock 保護，適用於多 worker 部署
- **活體偵測**：1:1 驗證預設啟用活體偵測；1:N 搜尋可選擇開關
- **錯誤處理**：`AIMSError` 保留 AIMS 的 HTTP 狀態碼、`code` 和 request_id，demo API 直接透傳 HTTP 狀態碼，細部判斷用 `aims_code`（例如 441 格式錯誤、450 缺參數、4010 face_token 不存在、4012 FaceSet 不存在）
- **空結果**：detect 沒有人臉、identify 的 FaceSet 沒有人臉時，AIMS 回 `code` 0 和空陣列，client 會檢查長度
