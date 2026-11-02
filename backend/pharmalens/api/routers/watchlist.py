"""The signed-in user's watchlist (Tailscale identity); the owner's list also drives Specs' Telegram alerts."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ... import watchlist as wl
from ..common import cleanrows

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class Item(BaseModel):
    key: str
    label: str
    href: str | None = None


def _who(request: Request) -> str:
    from ..main import OWNERS, REQUIRE_OWNER
    login = (request.headers.get("tailscale-user-login") or "").lower()
    if login:
        return login
    if not OWNERS and not REQUIRE_OWNER:
        return wl.owner_login()          # local development: one list
    raise HTTPException(401, "sign in through Tailscale to keep a watchlist")


@router.get("")
def get_watchlist(request: Request):
    try:
        who = _who(request)
    except HTTPException:
        return {"data": [], "signed_in": False}
    return {"data": cleanrows(wl.items(who)), "signed_in": True}


@router.put("")
def add_item(item: Item, request: Request):
    return {"added": wl.add(_who(request), item.key, item.label, item.href)}


@router.delete("/{key:path}")
def remove_item(key: str, request: Request):
    return {"removed": wl.remove(_who(request), key)}
