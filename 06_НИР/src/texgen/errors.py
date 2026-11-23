"""Общий HTTP-контракт ошибок сервисов НИР."""
import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


from .contracts import error


class ServiceError(HTTPException):
    def __init__(self, status, code, message, *, retry_after=None):
        headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
        super().__init__(status, code, headers=headers)
        self.code = code
        self.message = message


def service_app(service, **options):
    app = FastAPI(responses={500: error("internal_error")}, **options)

    def response(status, code, message, *, headers=None, fields=None, incident=None):
        error = dict(service=service, code=code, message=message)
        if fields:
            error["fields"] = fields
        if incident:
            error["incident_id"] = incident
        return JSONResponse({"error": error}, status_code=status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Значения полей могут содержать промпт или целое изображение.
        fields = [{"location": err["loc"], "type": err["type"]} for err in exc.errors()]
        return response(422, "invalid_request", "Проверьте параметры запроса.", fields=fields)

    @app.exception_handler(ServiceError)
    async def domain_error(request: Request, exc: ServiceError):
        return response(exc.status_code, exc.code, exc.message, headers=exc.headers)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        codes = {404: "not_found", 405: "method_not_allowed"}
        return response(exc.status_code, codes.get(exc.status_code, "http_error"),
                        "Запрос отклонён.", headers=exc.headers)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        incident = uuid4().hex
        logging.getLogger(__name__).exception("Сбой сервиса %s, incident_id=%s", service, incident)
        return response(500, "internal_error", "Не удалось выполнить запрос.", incident=incident)

    return app
