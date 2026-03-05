# AIMS Demo API

使用 FastAPI 展示 Authme AIMS 人臉辨識 API 的串接範例。

此專案由 **aims-api skill** 產生，展示完整的串接最佳實踐。

## 功能

| 端點 | 說明 |
|---|---|
| `POST /api/verify-identity` | 1:1 身份驗證（證件照 vs 自拍照） |
| `POST /api/liveness` | 活體偵測 |
| `POST /api/facesets` | 建立 FaceSet |
| `GET /api/facesets` | 列出所有 FaceSet |
| `POST /api/facesets/{token}/register` | 偵測並註冊人臉到 FaceSet |
| `POST /api/facesets/{token}/identify` | 1:N 人臉搜尋 |

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
- **錯誤處理**：所有 AIMS 錯誤轉為 HTTP 回應，保留 aims_code 和 request_id 方便追蹤
