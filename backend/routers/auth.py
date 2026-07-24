import os

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from models.ticket import AuthSession
from services.auth_service import (
    SESSION_COOKIE,
    STATE_COOKIE,
    create_oauth_url,
    create_session,
    create_state,
    exchange_code,
    has_iris_access,
    is_admin_helper,
    parse_session,
)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://iris.loasis.app")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/discord/login")
async def discord_login() -> RedirectResponse:
    state = create_state()
    response = RedirectResponse(create_oauth_url(state), status_code=302)
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@router.get("/discord/callback")
async def discord_callback(code: str, state: str, request: Request) -> RedirectResponse:
    if state != request.cookies.get(STATE_COOKIE):
        return RedirectResponse(f"{FRONTEND_URL}/?auth=failed", status_code=302)
    helper = await exchange_code(code)
    response = RedirectResponse(FRONTEND_URL, status_code=302)
    response.set_cookie(
        SESSION_COOKIE,
        create_session(helper),
        max_age=43200,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    response.delete_cookie(STATE_COOKIE)
    return response


@router.get("/session", response_model=AuthSession)
async def session(request: Request, response: Response) -> AuthSession:
    raw_session = request.cookies.get(SESSION_COOKIE)
    helper = parse_session(raw_session)
    if raw_session and not helper:
        response.delete_cookie(SESSION_COOKIE)
        return AuthSession(authenticated=False, helper=None, is_admin=False)
    if helper:
        try:
            if not await has_iris_access(helper.id):
                response.delete_cookie(SESSION_COOKIE)
                return AuthSession(authenticated=False, helper=None, is_admin=False)
            is_admin = await is_admin_helper(helper.id)
        except HTTPException:
            response.delete_cookie(SESSION_COOKIE)
            return AuthSession(authenticated=False, helper=None, is_admin=False)
    else:
        is_admin = False
    return AuthSession(authenticated=helper is not None, helper=helper, is_admin=is_admin)


@router.post("/logout", response_model=AuthSession)
async def logout(response: Response) -> AuthSession:
    response.delete_cookie(SESSION_COOKIE)
    return AuthSession(authenticated=False, helper=None, is_admin=False)
