"""
AIMS API Client — 封裝 Authme AIMS 人臉辨識 API 的呼叫邏輯。

此模組由 aims-api skill 產生，示範完整的 API 串接方式，
包含 Token 快取、簽章產生、錯誤處理等最佳實踐。
"""

import hmac
import hashlib
import time
import threading
from dataclasses import dataclass

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
    """AIMS API 回傳的錯誤。"""
    def __init__(self, code: int, message: str, request_id: str = ""):
        self.code = code
        self.message = message
        self.request_id = request_id
        super().__init__(f"AIMS Error {code}: {message} (request_id={request_id})")


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

            ts = int(time.time())
            sign = self._make_sign(ts)
            resp = self._http.post(
                f"{self.base_url}/aims/auth/token",
                json={"client_id": self.client_id, "time": ts, "sign": sign},
            )
            data = resp.json()
            if data["code"] != 0:
                raise AIMSError(data["code"], data["message"])

            self._token_cache.access_token = data["access_token"]
            self._token_cache.expires_at = time.time() + data["expires_in"]
            return self._token_cache.access_token

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.get_token()}"}

    def _check_response(self, data: dict):
        if data["code"] != 0:
            raise AIMSError(
                data["code"],
                data.get("message", "Unknown error"),
                data.get("request_id", ""),
            )

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
        data = resp.json()
        self._check_response(data)
        faces = data["result"]["faces"]
        if not faces:
            raise AIMSError(404, "照片中未偵測到人臉")
        return faces[0]["liveness_score"]

    # ── 人臉偵測 ──────────────────────────────────────

    def detect(self, image_path: str) -> list[dict]:
        """
        偵測圖片中所有人臉，回傳 face list。
        每個 face 包含 face_token、box、landmarks。
        """
        with open(image_path, "rb") as f:
            resp = self._http.post(
                f"{self.base_url}/aims/face/detect",
                headers=self._auth_headers(),
                files={"image": f},
            )
        data = resp.json()
        self._check_response(data)
        return data["result"]["faces"]

    def detect_one(self, image_path: str) -> str:
        """偵測並回傳第一張臉的 face_token。若無人臉則拋出例外。"""
        faces = self.detect(image_path)
        if not faces:
            raise AIMSError(0, "圖片中未偵測到人臉")
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
        data = resp.json()
        self._check_response(data)
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
        top_n: int = 3,
    ) -> list[dict]:
        """在 FaceSet 中搜尋最相似的人臉，回傳 top_n 筆結果。"""
        resp = self._http.post(
            f"{self.base_url}/aims/face/identify",
            headers=self._auth_headers(),
            data={
                "face_token": face_token,
                "faceset_token": faceset_token,
                "top_n": top_n,
            },
        )
        data = resp.json()
        self._check_response(data)
        return data["result"]["results"]

    # ── FaceSet 管理 ──────────────────────────────────

    def create_faceset(
        self, display_name: str, outer_id: str, tags: list[str] = None
    ) -> dict:
        """建立 FaceSet，回傳 faceset 資料（含 faceset_token）。"""
        body = {"display_name": display_name, "outer_id": outer_id}
        if tags:
            body["tags"] = tags
        resp = self._http.post(
            f"{self.base_url}/aims/facesets",
            headers=self._auth_headers(),
            json=body,
        )
        data = resp.json()
        self._check_response(data)
        return data["faceset"]

    def list_facesets(self) -> list[dict]:
        """列出所有 FaceSet。"""
        resp = self._http.get(
            f"{self.base_url}/aims/facesets",
            headers=self._auth_headers(),
        )
        data = resp.json()
        self._check_response(data)
        return data["facesets"]

    def register_face(
        self,
        faceset_token: str,
        face_token: str,
        display_name: str = "",
        external_id: str = "",
    ) -> None:
        """將 face_token 註冊到 FaceSet。"""
        body = {"face_token": face_token}
        if display_name:
            body["display_name"] = display_name
        if external_id:
            body["external_id"] = external_id
        resp = self._http.post(
            f"{self.base_url}/aims/facesets/{faceset_token}/register",
            headers=self._auth_headers(),
            json=body,
        )
        data = resp.json()
        self._check_response(data)

    def remove_face(self, faceset_token: str, face_token: str) -> None:
        """從 FaceSet 移除人臉。"""
        resp = self._http.delete(
            f"{self.base_url}/aims/facesets/{faceset_token}/faces/{face_token}",
            headers=self._auth_headers(),
        )
        data = resp.json()
        self._check_response(data)
