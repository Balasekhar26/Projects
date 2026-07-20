# Starlette TestClient HTTP Client Deprecation

Status: non-blocking technical debt  
Release blocker: no

## Current environment

- FastAPI: 0.136.3
- Starlette: 1.3.1
- httpx: 0.28.1

## Warning

Tests constructing `fastapi.testclient.TestClient` emit a
`StarletteDeprecationWarning` stating that the current httpx-backed TestClient
integration is deprecated and suggesting `httpx2`.

## Affected tests

The warning is visible in API integration tests, including Finance Brain and
runtime-readiness contract tests. It does not currently change test outcomes.

## Upgrade candidates

- A compatible FastAPI and Starlette release combination
- The replacement client recommended by the installed Starlette release
- An explicit ASGI transport for tests, if supported by the selected client

## Compatibility requirements

Any dependency change must be tested in an isolated branch against:

- All FastAPI route tests
- Lifespan startup and shutdown
- Synchronous and asynchronous client behavior
- Streaming and WebSocket endpoints
- Exception propagation and dependency overrides

Do not install `httpx2` or broadly upgrade FastAPI/Starlette without that
compatibility run.
