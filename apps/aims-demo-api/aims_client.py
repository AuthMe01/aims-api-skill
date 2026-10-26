"""
AIMS API Client — 封裝 Authme AIMS 人臉辨識 API 的呼叫邏輯。

此模組由 aims-api skill 產生，示範完整的 API 串接方式，
包含 Token 快取、簽章產生、錯誤處理等最佳實踐。
"""

import hmac
import hashlib
import time
import threading
import uuid
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class TokenCache:
    """快取 access_token，避免每次呼叫都重新取得。"""
    access_token: str = ""
    expires_at: float = 0.0
    lock: threading.Lock = None

    def __post_init__(self):
        self.lock = threading.Lock()

    def is_valid(self) -> bool:
        # 提前 30 秒更新
        return self.access_token and time.time() < (self.expires_at - 30)


class AIMSError(Exception):
    """
    AIMS API 回傳的錯誤。

    code 是 AIMS 回應 JSON 裡的 code（例如 441、4010），請用它判斷錯誤類型；
    http_status 是原始 HTTP 狀態碼，可直接透傳給上層。
    """
    def __init__(
        self, code: int, message: str, request_id: str = "", http_status: int = 500
    ):
        self.code = code
        self.message = message
        self.request_id = request_id
        self.http_status = http_status
        super().__init__(
            f"AIMS Error {code} (HTTP {http_status}): {message} (request_id={request_id})"
        )


# 缺少 scope 時（HTTP 403 / code 473）用來提示要開通哪個 scope
ENDPOINT_SCOPES: dict[str, str] = {
    "/aims/face/detect": "face:detect",
    "/aims/face/verify": "face:verify",
    "/aims/face/identify": "face:identify",
    "/aims/liveness/image": "liveness:image",
    "/aims/ocr/qualitycheck": "ocr:quality_check",
    "/aims/ocr/image": "ocr:image",
}


class AIMSClient:
    """
    AIMS 人臉辨識 API 客戶端。

    用法：
        client = AIMSClient(
            base_url="https://stage.aims.authme.com",
            client_id="your-uuid",
            client_secret="your-secret",
        )
        # 1:1 比對
        result = client.verify_identity("id_card.jpg", "selfie.jpg")
    """

    def __init__(self, base_url: str, client_id: str, client_secret: str):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._token_cache = TokenCache()
        self._http = httpx.Client(timeout=30.0)

    def close(self):
        self._http.close()

    # ── 驗證 ──────────────────────────────────────────

    def _make_sign(self, timestamp: int) -> str:
        """產生 HMAC-SHA256 簽章。"""
        message = f"{self.client_id}{timestamp}".encode()
        return hmac.new(
            self.client_secret.encode(), message, hashlib.sha256
        ).hexdigest()

    def get_token(self) -> str:
        """取得 access_token（自動快取）。"""
        if self._token_cache.is_valid():
            return self._token_cache.access_token

        with self._token_cache.lock:
            # Double-check after acquiring lock
            if self._token_cache.is_valid():
                return self._token_cache.access_token

            # 同一組 time + sign 只能用一次（replay 防護），
            # 所以 token 更新必須在 lock 內，避免同一秒內重複簽章被拒。
            ts = int(time.time())
            sign = self._make_sign(ts)
            resp = self._http.post(
                f"{self.base_url}/aims/auth/token",
                json={"client_id": self.client_id, "time": ts, "sign": sign},
            )
            data = self._parse(resp)

            self._token_cache.access_token = data["access_token"]
            self._token_cache.expires_at = time.time() + data["expires_in"]
            return self._token_cache.access_token

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.get_token()}"}

    def _parse(self, resp: httpx.Response) -> dict:
        """解析回應；code != 0 時拋 AIMSError（保留 HTTP 狀態碼）。"""
        try:
            data = resp.json()
        except ValueError:
            # 少數錯誤（例如 OCR 的 409）可能不是 JSON
            raise AIMSError(
                resp.status_code,
                resp.text or resp.reason_phrase,
                resp.headers.get("X-Request-ID", ""),
                http_status=resp.status_code,
            )
        if data.get("code", 0) != 0:
            code = data["code"]
            if code == 401:
                # token 失效：清掉快取，下一次呼叫會重新取得
                self._token_cache.access_token = ""
            message = data.get("message", "Unknown error")
            if code == 473:
                scope = ENDPOINT_SCOPES.get(resp.request.url.path)
                if scope:
                    message = f"{message} (required scope: {scope})"
            raise AIMSError(
                code, message, data.get("request_id", ""), http_status=resp.status_code
            )
        return data

    # ── 活體偵測 ──────────────────────────────────────

    def liveness_check(self, image_path: str) -> float:
        """
        活體偵測 — 判斷照片中是否為真人。

        回傳 liveness_score（0.0 ~ 1.0），≥ 0.5 為真人。
        若偵測不到人臉會拋出 AIMSError(404)。
        """
        with open(image_path, "rb") as f:
            resp = self._http.post(
                f"{self.base_url}/aims/liveness/image",
                headers=self._auth_headers(),
                files={"image": f},
            )
        data = self._parse(resp)
        # 回應格式：result.face_count + result.faces[]，
        # 每個 face 含 liveness_score、x、y、width、height、confidence（沒有 box 物件）
        faces = data["result"]["faces"]
        if not faces:
            raise AIMSError(404, "照片中未偵測到人臉", http_status=404)
        # 多張臉時以面積最大的那張（通常是自拍主體）為準
        main_face = max(faces, key=lambda f: f["width"] * f["height"])
        return main_face["liveness_score"]

    # ── 人臉偵測 ──────────────────────────────────────

    def detect(self, image_path: str) -> list[dict]:
        """
        偵測圖片中所有人臉，回傳 face list。
        每個 face 包含 face_token、box、landmarks。
        沒有人臉時回傳空 list（AIMS 回 code 0、faces: []，不算錯誤）。
        """
        with open(image_path, "rb") as f:
            resp = self._http.post(
                f"{self.base_url}/aims/face/detect",
                headers=self._auth_headers(),
                files={"image": f},
            )
        data = self._parse(resp)
        return data["result"]["faces"]

    def detect_one(self, image_path: str) -> str:
        """偵測並回傳第一張臉的 face_token。若無人臉則拋出例外。"""
        faces = self.detect(image_path)
        if not faces:
            # AIMS 本身回 code 0；這裡用 404 讓上層知道是「找不到人臉」
            raise AIMSError(404, "圖片中未偵測到人臉", http_status=422)
        return faces[0]["face_token"]

    # ── 1:1 比對 ──────────────────────────────────────

    def verify(self, face_token_1: str, face_token_2: str) -> float:
        """比對兩個 face_token 的相似度（0.0 ~ 1.0）。"""
        resp = self._http.post(
            f"{self.base_url}/aims/face/verify",
            headers=self._auth_headers(),
            data={
                "face_token_1": face_token_1,
                "face_token_2": face_token_2,
            },
        )
        data = self._parse(resp)
        return data["result"]["similarity"]

    def verify_identity(
        self,
        id_card_path: str,
        selfie_path: str,
        liveness_threshold: float = 0.5,
        similarity_threshold: float = 0.7,
    ) -> dict:
        """
        完整 1:1 身分驗證流程（活體偵測 → 偵測 → 比對）。

        回傳 dict:
            - liveness_score: 活體分數
            - similarity: 相似度
            - is_match: 是否判定為同一人
        """
        # Step 1: 活體偵測（自拍照）
        liveness_score = self.liveness_check(selfie_path)
        if liveness_score < liveness_threshold:
            return {
                "liveness_score": liveness_score,
                "similarity": 0.0,
                "is_match": False,
                "reason": "活體偵測未通過",
            }

        # Step 2: 偵測兩張臉
        ft_id = self.detect_one(id_card_path)
        ft_selfie = self.detect_one(selfie_path)

        # Step 3: 比對
        similarity = self.verify(ft_id, ft_selfie)
        return {
            "liveness_score": liveness_score,
            "similarity": similarity,
            "is_match": similarity >= similarity_threshold,
        }

    # ── 1:N 搜尋 ─────────────────────────────────────

    def identify(
        self,
        face_token: str,
        faceset_token: str,
        top_n: Optional[int] = None,
    ) -> list[dict]:
        """
        在 FaceSet 中搜尋最相似的人臉，回傳 top_n 筆結果。

        top_n 選填（1~20），不帶時 AIMS 預設回 1 筆。
        結果依相似度由高到低排序，但不會依門檻過濾；
        FaceSet 內沒有人臉時回傳空 list。
        """
        body = {"face_token": face_token, "faceset_token": faceset_token}
        if top_n is not None:
            body["top_n"] = top_n
        resp = self._http.post(
            f"{self.base_url}/aims/face/identify",
            headers=self._auth_headers(),
            data=body,
        )
        data = self._parse(resp)
        return data["result"]["results"]

    # ── FaceSet 管理 ──────────────────────────────────

    def create_faceset(
        self, display_name: str, outer_id: str = "", tags: list[str] = None
    ) -> dict:
        """建立 FaceSet，回傳 faceset 資料（含 faceset_token）。outer_id 選填。"""
        body = {"display_name": display_name}
        if outer_id:
            body["outer_id"] = outer_id
        if tags:
            body["tags"] = tags
        resp = self._http.post(
            f"{self.base_url}/aims/facesets",
            headers=self._auth_headers(),
            json=body,
        )
        data = self._parse(resp)
        return data["data"]

    def list_facesets(self) -> list[dict]:
        """列出所有 FaceSet。"""
        resp = self._http.get(
            f"{self.base_url}/aims/facesets",
            headers=self._auth_headers(),
        )
        data = self._parse(resp)
        return data["data"]["facesets"]

    def register_face(
        self,
        faceset_token: str,
        face_token: str,
        external_id: str,
        display_name: str = "",
    ) -> None:
        """
        將 face_token 註冊到 FaceSet。

        external_id 必填，且在同一個 FaceSet 內不可重複（重複會拋 4014）。
        建議用你系統裡的使用者 ID，identify 結果的 face_id 就能直接對回去。
        """
        body = {"face_token": face_token, "external_id": external_id}
        if display_name:
            body["display_name"] = display_name
        resp = self._http.post(
            f"{self.base_url}/aims/facesets/{faceset_token}/register",
            headers=self._auth_headers(),
            json=body,
        )
        self._parse(resp)

    def delete_face(self, face_token: str) -> None:
        """
        永久刪除人臉資料（特徵向量與人臉裁切圖），並從所有 FaceSet 移除。

        無法復原。只想讓人臉不再出現在某個 FaceSet 的搜尋結果，請用 remove_face()。
        face_token 不存在或已刪除時拋 AIMSError(4010)。
        """
        resp = self._http.delete(
            f"{self.base_url}/aims/face/{face_token}",
            headers=self._auth_headers(),
        )
        self._parse(resp)

    def remove_face(self, faceset_token: str, face_token: str) -> None:
        """
        從 FaceSet 移除人臉（不刪除人臉資料）。

        face_token 不在此 FaceSet（含已移除）時拋 AIMSError(4011)。
        """
        resp = self._http.delete(
            f"{self.base_url}/aims/facesets/{faceset_token}/faces/{face_token}",
            headers=self._auth_headers(),
        )
        self._parse(resp)

    def get_faceset(self, faceset_token: str) -> dict:
        """取得 FaceSet 詳細資料（含已註冊的 face_tokens）。"""
        resp = self._http.get(
            f"{self.base_url}/aims/facesets/{faceset_token}",
            headers=self._auth_headers(),
        )
        data = self._parse(resp)
        return data["data"]

    def update_faceset(
        self,
        faceset_token: str,
        display_name: Optional[str] = None,
        tags: Optional[list[str]] = None,
        user_data: Optional[str] = None,
    ) -> None:
        """更新 FaceSet 設定。所有欄位皆為選填。"""
        body = {}
        if display_name is not None:
            body["display_name"] = display_name
        if tags is not None:
            body["tags"] = tags
        if user_data is not None:
            body["user_data"] = user_data
        resp = self._http.patch(
            f"{self.base_url}/aims/facesets/{faceset_token}",
            headers=self._auth_headers(),
            json=body,
        )
        self._parse(resp)

    def delete_faceset(self, faceset_token: str) -> None:
        """
        刪除整個 FaceSet。

        若 FaceSet 內仍有已註冊的人臉，會拋 AIMSError(544)，
        需先逐一 remove_face() 後再刪除。
        """
        resp = self._http.delete(
            f"{self.base_url}/aims/facesets/{faceset_token}",
            headers=self._auth_headers(),
        )
        self._parse(resp)

    # ── OCR ──────────────────────────────────────────

    def ocr_quality_check(
        self,
        image_path: str,
        card_type: str,
        channel: str = "default",
    ) -> dict:
        """
        影像品質檢查（OCR 前置）。

        Args:
            image_path: 證件圖片路徑
            card_type: 證件類型，例如 'TWN_IDCard_Front'、'TWN_Passport_Front'
            channel: 用量分類追蹤頻道

        Returns:
            dict: {"passed": bool, "code": int, "message": str}
            - passed=True 表示品質檢查通過，可以送 OCR
            - passed=False 時，code 為 457~468，message 是後端原始訊息；
              產品端建議用 QC_GUIDANCE 對應使用者引導文案。
        """
        with open(image_path, "rb") as f:
            files = {"image": f}
            resp = self._http.post(
                f"{self.base_url}/aims/ocr/qualitycheck",
                headers=self._auth_headers(),
                files=files,
                data={"cardType": card_type, "channel": channel},
            )
        if resp.status_code != 200:
            # 401 / 403 / 400 等是真正的錯誤，不是品質未通過
            self._parse(resp)
        data = resp.json()
        return {
            "passed": data.get("code") == 0,
            "code": data.get("code", 0),
            "message": data.get("message", ""),
            "request_id": data.get("request_id", ""),
        }

    def ocr_image(
        self,
        image_path: str,
        auto_rotate: bool = True,
        channel: str = "default",
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        OCR 文字辨識。

        Args:
            image_path: 證件圖片路徑
            auto_rotate: True 時若 0° 失敗會自動嘗試 90°/270°/180°
            channel: 用量分類追蹤頻道
            idempotency_key: 重試保護。若為 None，會自動產生新的 UUID；
                若會 retry 同一份請求，請傳同一個 key（不要每次重試都產新的）。

        Returns:
            dict 包含 result.card.type、result.text、result.rotation_applied，
            以及 idempotent_replay（True 表示本次是 cache 命中、未實際扣費）。

        Raises:
            AIMSError: 任何非 0 的 code（含 404/422/409 等）
        """
        if idempotency_key is None:
            idempotency_key = str(uuid.uuid4())

        headers = self._auth_headers()
        headers["Idempotency-Key"] = idempotency_key

        with open(image_path, "rb") as f:
            files = {"image": f}
            resp = self._http.post(
                f"{self.base_url}/aims/ocr/image",
                headers=headers,
                files=files,
                data={
                    "channel": channel,
                    "autoRotate": "true" if auto_rotate else "false",
                },
            )

        if resp.status_code == 409:
            raise AIMSError(
                409,
                "Idempotency-Key 重複使用但 body 不同（client bug）",
                resp.headers.get("X-Request-ID", ""),
                http_status=409,
            )
        data = self._parse(resp)

        result = data["result"]
        result["idempotent_replay"] = (
            resp.headers.get("X-Idempotent-Replay", "false").lower() == "true"
        )
        return result

    def ocr_calls(self) -> dict:
        """
        查詢累計 OCR / quality check 呼叫次數。

        Returns:
            dict 包含 api_calls、api_calls_by_channel、channels、time、resp_sign。
            計次規則：HTTP 200 + 已知卡別 + 至少 1 個 text 欄位才計次；
            Idempotency cache 命中的請求不計次。
        """
        resp = self._http.get(
            f"{self.base_url}/aims/ocr/calls",
            headers=self._auth_headers(),
        )
        data = self._parse(resp)
        return data


# ── 品質檢查狀態碼 → 使用者引導文案 ────────────────────
# 後端回的 message 是英文 + 偏技術；產品端建議用這份對照表
# 轉成更友善的引導訊息。可依需求做 i18n。

QC_GUIDANCE: dict[int, str] = {
    457: "請確認整張證件都在畫面內。",
    458: "請把證件完整放進畫面中央。",
    459: "請依畫面引導框對齊證件位置。",
    460: "光線太暗或太亮，請在均勻光源下重新拍攝。",
    461: "偵測到的證件類型與預期不符，請確認上傳的證件。",
    462: "請使用彩色影像，灰階圖片無法辨識。",
    463: "影像太模糊，請穩定拿好並對焦再拍。",
    464: "證件反光，請避開光源或調整角度。",
    465: "證件反光，請避開光源或調整角度。",
    466: "未在證件上偵測到人臉，請確認上傳的是正確證件正面。",
    468: "系統發生未預期錯誤，請稍後再試。",
}
