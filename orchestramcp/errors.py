import httpx

MAX_ERROR_BODY_CHARS = 500
MAX_ERROR_LIST_ITEMS = 5


class OrchestraAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"{status_code}: {message}")


def parse_error_response(response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:
        text = (response.text or "").strip()
        return (
            text[:MAX_ERROR_BODY_CHARS]
            if len(text) > MAX_ERROR_BODY_CHARS
            else text or f"HTTP {response.status_code}"
        )

    if not isinstance(data, dict):
        return str(data)[:MAX_ERROR_BODY_CHARS]

    for key in ("detail", "message", "error", "msg"):
        if key in data and data[key] is not None:
            val = data[key]
            if isinstance(val, str):
                return val
            if isinstance(val, list) and val:
                return "; ".join(str(x) for x in val[:MAX_ERROR_LIST_ITEMS])
            return str(val)

    if "errors" in data and isinstance(data["errors"], list) and data["errors"]:
        return "; ".join(str(e) for e in data["errors"][:MAX_ERROR_LIST_ITEMS])

    return response.text[:MAX_ERROR_BODY_CHARS] if response.text else f"HTTP {response.status_code}"
