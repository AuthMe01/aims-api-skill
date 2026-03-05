"""
AIMS Demo API — 使用 FastAPI 展示 AIMS 人臉辨識串接。

此範例由 aims-api skill 產生，包含三個主要功能：
1. 1:1 身份驗證（eKYC）
2. 1:N 人臉搜尋（門禁/VIP 辨識）
3. 活體偵測

啟動方式：
    cp .env.example .env   # 填入你的 client_id 和 client_secret
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000
"""

import os
import tempfile
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from aims_client import AIMSClient, AIMSError

load_dotenv()


# ── 初始化 ────────────────────────────────────────────

client: AIMSClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    base_url = os.environ.get("AIMS_BASE_URL", "https://stage.aims.authme.com")
    client_id = os.environ["AIMS_CLIENT_ID"]
    client_secret = os.environ["AIMS_CLIENT_SECRET"]
    client = AIMSClient(base_url, client_id, client_secret)
    yield
    client.close()


app = FastAPI(
    title="AIMS Demo API",
    description="Authme AIMS 人臉辨識 API 串接範例",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Helper ────────────────────────────────────────────

async def save_upload(upload: UploadFile) -> str:
    """將上傳檔案存到暫存路徑，回傳路徑。"""
    suffix = os.path.splitext(upload.filename or "img.jpg")[1]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    content = await upload.read()
    tmp.write(content)
    tmp.close()
    return tmp.name


def handle_aims_error(e: AIMSError):
    """將 AIMSError 轉換為 HTTP 回應。"""
    status_map = {401: 401, 451: 400, 440: 400, 461: 400, 404: 400, 503: 503}
    status = status_map.get(e.code, 500)
    raise HTTPException(
        status_code=status,
        detail={"aims_code": e.code, "message": e.message, "request_id": e.request_id},
    )


# ── 健康檢查 ──────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ── 1:1 身份驗證 ──────────────────────────────────────

@app.post("/api/verify-identity")
async def verify_identity(
    id_card: UploadFile = File(..., description="證件照"),
    selfie: UploadFile = File(..., description="自拍照"),
    similarity_threshold: float = Form(0.7, description="相似度門檻"),
):
    """
    1:1 身份驗證 — 比對證件照與自拍照。

    流程：活體偵測 → 人臉偵測(×2) → 人臉比對
    """
    id_path = await save_upload(id_card)
    selfie_path = await save_upload(selfie)
    try:
        result = client.verify_identity(
            id_card_path=id_path,
            selfie_path=selfie_path,
            similarity_threshold=similarity_threshold,
        )
        return result
    except AIMSError as e:
        handle_aims_error(e)
    finally:
        os.unlink(id_path)
        os.unlink(selfie_path)


# ── 活體偵測 ──────────────────────────────────────────

@app.post("/api/liveness")
async def liveness_check(
    image: UploadFile = File(..., description="人臉照片"),
):
    """活體偵測 — 判斷照片是否為真人。"""
    path = await save_upload(image)
    try:
        score = client.liveness_check(path)
        return {
            "liveness_score": score,
            "is_live": score >= 0.5,
        }
    except AIMSError as e:
        handle_aims_error(e)
    finally:
        os.unlink(path)


# ── FaceSet 管理 ──────────────────────────────────────

@app.post("/api/facesets")
async def create_faceset(
    display_name: str = Form(...),
    outer_id: str = Form(...),
):
    """建立 FaceSet。"""
    try:
        faceset = client.create_faceset(display_name, outer_id)
        return faceset
    except AIMSError as e:
        handle_aims_error(e)


@app.get("/api/facesets")
def list_facesets():
    """列出所有 FaceSet。"""
    try:
        return {"facesets": client.list_facesets()}
    except AIMSError as e:
        handle_aims_error(e)


# ── 人臉註冊 ──────────────────────────────────────────

@app.post("/api/facesets/{faceset_token}/register")
async def register_face(
    faceset_token: str,
    image: UploadFile = File(..., description="人臉照片"),
    display_name: str = Form("", description="顯示名稱（如姓名）"),
    external_id: str = Form("", description="外部 ID（如員工編號）"),
):
    """
    偵測人臉並註冊到指定 FaceSet。

    一步完成 detect + register。
    """
    path = await save_upload(image)
    try:
        face_token = client.detect_one(path)
        client.register_face(faceset_token, face_token, display_name, external_id)
        return {
            "face_token": face_token,
            "display_name": display_name,
            "external_id": external_id,
            "registered": True,
        }
    except AIMSError as e:
        handle_aims_error(e)
    finally:
        os.unlink(path)


# ── 1:N 人臉搜尋 ─────────────────────────────────────

@app.post("/api/facesets/{faceset_token}/identify")
async def identify_face(
    faceset_token: str,
    image: UploadFile = File(..., description="待辨識的人臉照片"),
    top_n: int = Form(3, description="回傳前 N 筆結果"),
    check_liveness: bool = Form(True, description="是否進行活體偵測"),
):
    """
    1:N 人臉搜尋 — 在 FaceSet 中找出最相似的人。

    流程：（活體偵測 →）人臉偵測 → 搜尋比對
    """
    path = await save_upload(image)
    try:
        result = {"liveness_score": None, "matches": []}

        # 選用：活體偵測
        if check_liveness:
            score = client.liveness_check(path)
            result["liveness_score"] = score
            if score < 0.5:
                result["is_live"] = False
                return result

        # 偵測 + 搜尋
        face_token = client.detect_one(path)
        matches = client.identify(face_token, faceset_token, top_n)
        result["matches"] = matches
        result["identified"] = bool(matches and matches[0]["similarity"] >= 0.7)
        return result
    except AIMSError as e:
        handle_aims_error(e)
    finally:
        os.unlink(path)
