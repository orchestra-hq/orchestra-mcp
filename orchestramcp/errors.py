import httpx

MAX_ERROR_BODY_CHARS = 500
MAX_ERROR_LIST_ITEMS = 5

# Statuses whose API message names a problem but no next step. The hint is appended
# to what the agent sees, so a call that fails on credentials or workspace
# permissions says how to fix it instead of only that it failed.
STATUS_HINTS = {
    401: (
        "The Orchestra API key is missing, invalid or expired. Check the key sent as "
        "'Authorization: Bearer <key>' (ORCHESTRA_API_KEY when running the server locally); "
        "keys are issued in Orchestra workspace settings."
    ),
    403: (
        "The key is valid but this workspace cannot read that. The Metadata API may not be "
        "enabled for it — ask an Orchestra workspace admin to enable it."
    ),
}


class OrchestraAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        hint = STATUS_HINTS.get(status_code)
        super().__init__(f"{status_code}: {message}" + (f" {hint}" if hint else ""))


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
