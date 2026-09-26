"""
Azure Resource Name Availability Checker
-----------------------------------------
A small FastAPI service that checks whether a proposed name for a globally-
unique Azure resource (Storage Account, Key Vault, Container Registry,
Web/Function App, SQL Server, Cosmos DB) is available, before you try to
create it with Terraform / Bicep / the CLI.

Run locally:
    export AZURE_SUBSCRIPTION_ID=<your-subscription-id>
    az login
    uvicorn app:app --host 0.0.0.0 --port 8000

Call it:
    curl -X POST http://localhost:8000/api/check-name \
      -H "Content-Type: application/json" \
      -d '{"resource_type": "storage_account", "name": "stmyapp01"}'
"""

from __future__ import annotations

import logging
import os
import re
from enum import Enum

import httpx
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import DefaultAzureCredential
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("name-check")

ARM_BASE = "https://management.azure.com"
ARM_SCOPE = "https://management.azure.com/.default"
REQUEST_TIMEOUT_SECONDS = 15.0

SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID", "").strip()

app = FastAPI(title="Azure Resource Name Availability Checker", version="1.0.0")

_credential: DefaultAzureCredential | None = None


def get_credential() -> DefaultAzureCredential:
    """Lazily create the credential so the app can still boot (and serve
    /healthz) even if identity isn't configured yet — failures surface on
    the first real request instead of crashing the container at startup."""
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential


def get_arm_token() -> str:
    try:
        return get_credential().get_token(ARM_SCOPE).token
    except ClientAuthenticationError as exc:
        logger.error("Failed to acquire ARM token: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Could not authenticate to Azure. Check the container's managed identity "
                   "is enabled, or that AZURE_CLIENT_ID/TENANT_ID/CLIENT_SECRET are set correctly.",
        ) from exc


class ResourceType(str, Enum):
    storage_account = "storage_account"
    key_vault = "key_vault"
    container_registry = "container_registry"
    web_app = "web_app"
    sql_server = "sql_server"
    cosmos_db = "cosmos_db"


# (regex, min_len, max_len) — used for a fast local pre-check before ever
# calling Azure, so obviously-invalid names fail with a clear message
# instead of a confusing ARM error.
NAME_RULES: dict[ResourceType, re.Pattern] = {
    ResourceType.storage_account: re.compile(r"^[a-z0-9]{3,24}$"),
    ResourceType.key_vault: re.compile(r"^[a-zA-Z0-9-]{3,24}$"),
    ResourceType.container_registry: re.compile(r"^[a-zA-Z0-9]{5,50}$"),
    ResourceType.web_app: re.compile(r"^[a-zA-Z0-9-]{2,60}$"),
    ResourceType.sql_server: re.compile(r"^[a-z0-9-]{1,63}$"),
    ResourceType.cosmos_db: re.compile(r"^[a-z0-9-]{3,44}$"),
}

NAME_RULE_HINTS: dict[ResourceType, str] = {
    ResourceType.storage_account: "3-24 lowercase letters and digits only",
    ResourceType.key_vault: "3-24 characters: letters, digits, hyphens",
    ResourceType.container_registry: "5-50 alphanumeric characters only",
    ResourceType.web_app: "2-60 characters: letters, digits, hyphens",
    ResourceType.sql_server: "1-63 characters: lowercase letters, digits, hyphens",
    ResourceType.cosmos_db: "3-44 characters: lowercase letters, digits, hyphens",
}


class CheckNameRequest(BaseModel):
    resource_type: ResourceType
    name: str = Field(..., min_length=1, max_length=90)


class CheckNameResponse(BaseModel):
    resource_type: ResourceType
    name: str
    available: bool
    reason: str | None = None
    message: str | None = None


class CheckNamesRequest(BaseModel):
    resources: list[CheckNameRequest] = Field(..., min_length=1, max_length=100)


def local_format_check(resource_type: ResourceType, name: str) -> str | None:
    """Returns an error message if the name fails basic format rules, else None."""
    pattern = NAME_RULES[resource_type]
    if not pattern.match(name):
        return f"Invalid name format for {resource_type.value}: expected {NAME_RULE_HINTS[resource_type]}."
    return None


async def arm_post(path: str, body: dict, api_version: str) -> dict:
    token = get_arm_token()
    url = f"{ARM_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, params={"api-version": api_version}, json=body, headers=headers)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Timed out calling Azure Resource Manager.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Error calling Azure Resource Manager: {exc}") from exc

    if resp.status_code >= 400:
        logger.warning("ARM %s returned %s: %s", url, resp.status_code, resp.text)
        raise HTTPException(
            status_code=502,
            detail=f"Azure Resource Manager returned {resp.status_code}: {resp.text[:500]}",
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Azure Resource Manager returned a non-JSON response.") from exc


async def arm_get(path: str, api_version: str) -> httpx.Response:
    token = get_arm_token()
    url = f"{ARM_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            return await client.get(url, params={"api-version": api_version}, headers=headers)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Timed out calling Azure Resource Manager.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Error calling Azure Resource Manager: {exc}") from exc


async def check_storage_account(name: str) -> CheckNameResponse:
    result = await arm_post(
        f"/subscriptions/{SUBSCRIPTION_ID}/providers/Microsoft.Storage/checkNameAvailability",
        {"name": name, "type": "Microsoft.Storage/storageAccounts"},
        "2023-01-01",
    )
    return CheckNameResponse(
        resource_type=ResourceType.storage_account,
        name=name,
        available=bool(result.get("nameAvailable", False)),
        reason=result.get("reason"),
        message=result.get("message"),
    )


async def check_key_vault(name: str) -> CheckNameResponse:
    result = await arm_post(
        f"/subscriptions/{SUBSCRIPTION_ID}/providers/Microsoft.KeyVault/checkNameAvailability",
        {"name": name, "type": "Microsoft.KeyVault/vaults"},
        "2023-07-01",
    )
    return CheckNameResponse(
        resource_type=ResourceType.key_vault,
        name=name,
        available=bool(result.get("nameAvailable", False)),
        reason=result.get("reason"),
        message=result.get("message"),
    )


async def check_container_registry(name: str) -> CheckNameResponse:
    result = await arm_post(
        f"/subscriptions/{SUBSCRIPTION_ID}/providers/Microsoft.ContainerRegistry/checkNameAvailability",
        {"name": name, "type": "Microsoft.ContainerRegistry/registries"},
        "2023-07-01",
    )
    return CheckNameResponse(
        resource_type=ResourceType.container_registry,
        name=name,
        available=bool(result.get("nameAvailable", False)),
        reason=result.get("reason"),
        message=result.get("message"),
    )


async def check_web_app(name: str) -> CheckNameResponse:
    result = await arm_post(
        f"/subscriptions/{SUBSCRIPTION_ID}/providers/Microsoft.Web/checkNameAvailability",
        {"name": name, "type": "Microsoft.Web/sites"},
        "2022-03-01",
    )
    return CheckNameResponse(
        resource_type=ResourceType.web_app,
        name=name,
        available=bool(result.get("nameAvailable", False)),
        reason=result.get("reason"),
        message=result.get("message"),
    )


async def check_sql_server(name: str) -> CheckNameResponse:
    result = await arm_post(
        f"/subscriptions/{SUBSCRIPTION_ID}/providers/Microsoft.Sql/checkNameAvailability",
        {"name": name, "type": "Microsoft.Sql/servers"},
        "2023-08-01-preview",
    )
    return CheckNameResponse(
        resource_type=ResourceType.sql_server,
        name=name,
        available=bool(result.get("available", False)),
        reason=result.get("reason"),
        message=result.get("message"),
    )


async def check_cosmos_db(name: str) -> CheckNameResponse:
    # Cosmos DB has no POST checkNameAvailability; a GET 404s if the name is
    # free and 200s if it's taken.
    resp = await arm_get(
        f"/subscriptions/{SUBSCRIPTION_ID}/providers/Microsoft.DocumentDB/databaseAccountNames/{name}",
        "2023-04-15",
    )
    if resp.status_code == 404:
        return CheckNameResponse(resource_type=ResourceType.cosmos_db, name=name, available=True)
    if resp.status_code == 200:
        return CheckNameResponse(
            resource_type=ResourceType.cosmos_db, name=name, available=False,
            reason="AlreadyExists", message="A Cosmos DB account with this name already exists.",
        )
    logger.warning("Unexpected Cosmos DB check status %s: %s", resp.status_code, resp.text)
    raise HTTPException(
        status_code=502,
        detail=f"Azure Resource Manager returned an unexpected status {resp.status_code} for Cosmos DB check.",
    )


CHECKERS = {
    ResourceType.storage_account: check_storage_account,
    ResourceType.key_vault: check_key_vault,
    ResourceType.container_registry: check_container_registry,
    ResourceType.web_app: check_web_app,
    ResourceType.sql_server: check_sql_server,
    ResourceType.cosmos_db: check_cosmos_db,
}


async def check_one(req: CheckNameRequest) -> CheckNameResponse:
    """Shared logic behind both /api/check-name and /api/check-names."""
    if not SUBSCRIPTION_ID:
        raise HTTPException(status_code=500, detail="Server misconfigured: AZURE_SUBSCRIPTION_ID is not set.")

    format_error = local_format_check(req.resource_type, req.name)
    if format_error:
        return CheckNameResponse(
            resource_type=req.resource_type, name=req.name, available=False,
            reason="InvalidName", message=format_error,
        )

    checker = CHECKERS[req.resource_type]
    return await checker(req.name)


@app.on_event("startup")
async def validate_config() -> None:
    if not SUBSCRIPTION_ID:
        # Don't crash the container — /healthz should still respond so the
        # platform doesn't loop-restart it — but every real check will fail
        # loudly and clearly until this is fixed.
        logger.error("AZURE_SUBSCRIPTION_ID is not set. /api/check-name will return 500 until it is.")


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "subscription_configured": bool(SUBSCRIPTION_ID)}


@app.post("/api/check-name", response_model=CheckNameResponse)
async def check_name(req: CheckNameRequest) -> CheckNameResponse:
    return await check_one(req)


@app.post("/api/check-names", response_model=list[CheckNameResponse])
async def check_names(req: CheckNamesRequest) -> list[CheckNameResponse]:
    """Check a list of proposed names in a single call.

    Runs the checks concurrently rather than one-by-one, and never lets one
    resource's failure take down the whole batch — a failure comes back as
    an item with available=False and the error in `message`, so partial
    results are still usable by the caller.
    """
    import asyncio

    async def safe_check_one(item: CheckNameRequest) -> CheckNameResponse:
        try:
            return await check_one(item)
        except HTTPException as exc:
            return CheckNameResponse(
                resource_type=item.resource_type, name=item.name, available=False,
                reason="CheckFailed", message=str(exc.detail),
            )

    return list(await asyncio.gather(*(safe_check_one(item) for item in req.resources)))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s", request.url)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})