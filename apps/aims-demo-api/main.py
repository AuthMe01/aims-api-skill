"""
AIMS Demo API — 使用 FastAPI 展示 AIMS 串接。

此範例由 aims-api skill 產生，涵蓋的功能：
1. 1:1 身分驗證（eKYC）
2. 1:N 人臉搜尋（門禁/VIP 辨識）
3. 活體偵測
4. FaceSet 管理
5. OCR 文件辨識（v1.2 新增）

啟動方式：
    cp .env.example .env   # 填入你的 client_id 和 client_secret
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000
"""

import os
import tempfile
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from aims_client import AIMSClient, AIMSError, QC_GUIDANCE

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
    status_map = {
        401: 401,
        # 403: token 通過驗證但缺少該 endpoint 的 scope。
        # 這是 server-side 設定問題（AuthMe 後台配置），client 無法解決，
        # 透傳 403 並附上 hint。
        403: 403,
        451: 400,
        440: 400,
        461: 400,
        404: 400,
        409: 409,
        422: 422,
        429: 429,
        503: 503,
    }
    status = status_map.get(e.code, 500)
    detail = {"aims_code": e.code, "message": e.message, "request_id": e.request_id}
    if e.code == 403:
        detail["hint"] = (
            "Token 缺少此 endpoint 的權限（permission scope）。"
            "Scope 由 AuthMe 後台依 client_id 預先配置，無法在 client 端請求；"
            "請聯繫 AuthMe 業務窗口開通對應 scope。"
        )
    raise HTTPException(status_code=status, detail=detail)


# ── 健康檢查 ──────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ── 1:1 身分驗證 ──────────────────────────────────────

@app.post("/api/verify-identity")
async def verify_identity(
    id_card: UploadFile = File(..., description="證件照"),
    selfie: UploadFile = File(..., description="自拍照"),
    similarity_threshold: float = Form(0.7, description="相似度門檻"),
):
    """
    1:1 身分驗證 — 比對證件照與自拍照。

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


# ── OCR 文件辨識（v1.2 新增）──────────────────────────

@app.post("/api/ocr/qualitycheck")
async def ocr_quality_check(
    image: UploadFile = File(..., description="證件圖片"),
    card_type: str = Form(
        ...,
        description="證件類型，例如 TWN_IDCard_Front、TWN_Passport_Front",
    ),
):
    """
    OCR 品質檢查 — 在送 OCR 之前先擋掉低品質照片。

    回傳 passed=True/False，未通過時提供使用者引導文案。
    """
    path = await save_upload(image)
    try:
        result = client.ocr_quality_check(path, card_type)
        if not result["passed"]:
            result["user_guidance"] = QC_GUIDANCE.get(
                result["code"],
                "影像品質檢查未通過，請重新拍攝。",
            )
        return result
    except AIMSError as e:
        handle_aims_error(e)
    finally:
        os.unlink(path)


@app.post("/api/ocr/recognize")
async def ocr_recognize(
    image: UploadFile = File(..., description="證件圖片"),
    auto_rotate: bool = Form(True, description="自動旋轉重試"),
    idempotency_key: Optional[str] = Form(
        None,
        description=(
            "重試保護用 UUID。若 client 有 retry 邏輯，請對同一筆操作"
            "傳同一個 key（不要每次 retry 都產新的）；留空會自動產生。"
        ),
    ),
):
    """
    OCR 辨識 — 回傳偵測到的證件類型與欄位文字。

    內含 Idempotency-Key 防止重試造成重複扣費。
    """
    path = await save_upload(image)
    try:
        result = client.ocr_image(
            path,
            auto_rotate=auto_rotate,
            idempotency_key=idempotency_key,
        )
        return result
    except AIMSError as e:
        handle_aims_error(e)
    finally:
        os.unlink(path)


@app.post("/api/ocr/quality-then-recognize")
async def ocr_quality_then_recognize(
    image: UploadFile = File(..., description="證件圖片"),
    card_type: str = Form(
        ...,
        description="證件類型，例如 TWN_IDCard_Front、TWN_Passport_Front",
    ),
    auto_rotate: bool = Form(True),
):
    """
    一次完成「品質檢查 → OCR」的高階 API。

    品質未通過時直接回 quality_failed，不會去打 OCR，省下不必要的計費。
    OCR 使用單一 idempotency_key，方便 client 重試。
    """
    path = await save_upload(image)
    idempotency_key = str(uuid.uuid4())
    try:
        # Step 1: 品質檢查
        qc = client.ocr_quality_check(path, card_type)
        if not qc["passed"]:
            return {
                "stage": "quality_check",
                "passed": False,
                "code": qc["code"],
                "message": qc["message"],
                "user_guidance": QC_GUIDANCE.get(
                    qc["code"], "影像品質檢查未通過，請重新拍攝。"
                ),
            }

        # Step 2: OCR
        ocr = client.ocr_image(
            path,
            auto_rotate=auto_rotate,
            idempotency_key=idempotency_key,
        )
        return {
            "stage": "ocr",
            "passed": True,
            "card_type": ocr["card"]["type"],
            "text": ocr["text"],
            "rotation_applied": ocr.get("rotation_applied", 0),
            "idempotent_replay": ocr.get("idempotent_replay", False),
            "idempotency_key": idempotency_key,
        }
    except AIMSError as e:
        handle_aims_error(e)
    finally:
        os.unlink(path)


@app.get("/api/ocr/usage")
def ocr_usage():
    """查詢累計 OCR / quality check 用量（依 channel 細分）。"""
    try:
        return client.ocr_calls()
    except AIMSError as e:
        handle_aims_error(e)
