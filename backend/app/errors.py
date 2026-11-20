from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


async def api_error(_request: Request, error: ApiError):
    return JSONResponse({"detail": {"code": error.code, "message": str(error)}}, error.status)
