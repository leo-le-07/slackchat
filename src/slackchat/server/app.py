"""FastAPI daemon on 127.0.0.1. Calls process(), serialises the Result, logs.

There is deliberately nothing else in this module. If a behaviour appears here
that the CLI does not have, the "one shared core service" property is gone.
"""

from __future__ import annotations

import dataclasses
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from slackchat.config import Config, load_config
from slackchat.core.types import EmptyInputError
from slackchat.server.token import TOKEN_HEADER, resolve_token
from slackchat.service import Service, build_service

BIND_HOST = "127.0.0.1"


class ProcessRequest(BaseModel):
    text: str
    mode: Literal["correction", "translation"] | None = None


def create_app(
    service: Service | None = None,
    config: Config | None = None,
    token: str | None = None,
) -> FastAPI:
    resolved_config = config if config is not None else load_config()
    resolved_token = token if token is not None else resolve_token(resolved_config)
    resolved_service = service if service is not None else build_service(resolved_config)

    app = FastAPI(title="slackchat", docs_url=None, redoc_url=None)

    if resolved_config.server.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved_config.server.allowed_origins),
            allow_methods=["POST", "GET"],
            allow_headers=[TOKEN_HEADER, "Content-Type"],
        )

    def require_token(
        provided: str | None = Header(default=None, alias=TOKEN_HEADER),
    ) -> None:
        # Loopback is not access control: any open page can fetch 127.0.0.1.
        if provided != resolved_token:
            raise HTTPException(status_code=401, detail="missing or invalid token")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/process", dependencies=[Depends(require_token)])
    def process_endpoint(payload: ProcessRequest) -> dict[str, object]:
        try:
            result = resolved_service.run(payload.text, payload.mode, client="server")
        except EmptyInputError as exc:
            raise HTTPException(status_code=400, detail="input is empty") from exc
        return dataclasses.asdict(result)

    return app


def serve(config: Config | None = None) -> int:
    """Run the daemon on loopback only."""
    import uvicorn

    resolved = config if config is not None else load_config()
    token = resolve_token(resolved)
    print(f"slackchat serving on http://{BIND_HOST}:{resolved.server.port}")
    print(f"{TOKEN_HEADER}: {token}")
    uvicorn.run(
        create_app(config=resolved, token=token),
        host=BIND_HOST,
        port=resolved.server.port,
        log_level="warning",
    )
    return 0
