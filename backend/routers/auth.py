import os
from urllib.parse import quote

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
    is_staff_helper,
    parse_session,
)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://iris.loasis.app")
COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN", ".loasis.app")

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
        domain=COOKIE_DOMAIN,
    )
    return response


@router.get("/discord/callback")
async def discord_callback(code: str, state: str, request: Request) -> RedirectResponse:
    if state != request.cookies.get(STATE_COOKIE):
        return RedirectResponse(f"{FRONTEND_URL}/?auth_error=Session+expir%C3%A9e%2C+r%C3%A9essayez.", status_code=302)
    try:
        helper = await exchange_code(code)
    except HTTPException as error:
        message = quote(str(error.detail))
        return RedirectResponse(f"{FRONTEND_URL}/?auth_error={message}", status_code=302)
    response = RedirectResponse(FRONTEND_URL, status_code=302)
    response.set_cookie(
        SESSION_COOKIE,
        create_session(helper),
        max_age=43200,
        httponly=True,
        secure=True,
        samesite="lax",
        domain=COOKIE_DOMAIN,
    )
    response.delete_cookie(STATE_COOKIE, domain=COOKIE_DOMAIN)
    return response


@router.get("/session", response_model=AuthSession)
async def session(request: Request, response: Response) -> AuthSession:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    raw_session = request.cookies.get(SESSION_COOKIE)
    helper = parse_session(raw_session)
    if raw_session and not helper:
        response.delete_cookie(SESSION_COOKIE, domain=COOKIE_DOMAIN)
        response.delete_cookie(SESSION_COOKIE)
        return AuthSession(authenticated=False, helper=None, is_admin=False, is_staff=False)
    is_admin = False
    is_staff = False
    if helper:
        try:
            if not await has_iris_access(helper.id) and not await is_staff_helper(helper.id):
                response.delete_cookie(SESSION_COOKIE, domain=COOKIE_DOMAIN)
                response.delete_cookie(SESSION_COOKIE)
                return AuthSession(authenticated=False, helper=None, is_admin=False, is_staff=False)
            is_admin = await is_admin_helper(helper.id)
            is_staff = await is_staff_helper(helper.id)
        except HTTPException:
            response.delete_cookie(SESSION_COOKIE, domain=COOKIE_DOMAIN)
            response.delete_cookie(SESSION_COOKIE)
            return AuthSession(authenticated=False, helper=None, is_admin=False, is_staff=False)
    return AuthSession(authenticated=helper is not None, helper=helper, is_admin=is_admin, is_staff=is_staff)


@router.post("/logout", response_model=AuthSession)
async def logout(response: Response) -> AuthSession:
    response.delete_cookie(SESSION_COOKIE, domain=COOKIE_DOMAIN)
    response.delete_cookie(SESSION_COOKIE)
    return AuthSession(authenticated=False, helper=None, is_admin=False, is_staff=False)
