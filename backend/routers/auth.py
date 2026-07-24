from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from models.ticket import AuthSession
from services.auth_service import (
    SESSION_COOKIE,
    STATE_COOKIE,
    create_oauth_url,
    create_session,
    create_state,
    demo_helper,
    exchange_code,
    parse_session,
)


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
        return RedirectResponse("/?auth=failed", status_code=302)
    helper = await exchange_code(code)
    response = RedirectResponse("/", status_code=302)
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
async def session(request: Request) -> AuthSession:
    helper = parse_session(request.cookies.get(SESSION_COOKIE))
    return AuthSession(authenticated=helper is not None, helper=helper)


@router.post("/demo-session", response_model=AuthSession)
async def start_demo_session(response: Response) -> AuthSession:
    helper = demo_helper()
    response.set_cookie(
        SESSION_COOKIE,
        create_session(helper),
        max_age=43200,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return AuthSession(authenticated=True, helper=helper)


@router.post("/logout", response_model=AuthSession)
async def logout(response: Response) -> AuthSession:
    response.delete_cookie(SESSION_COOKIE)
    return AuthSession(authenticated=False, helper=None)