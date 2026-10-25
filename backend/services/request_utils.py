import ipaddress

from fastapi import Request

from config import TRUSTED_PROXIES


def _parse_networks(raw: str) -> list:
    networks = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            continue
    return networks


_TRUSTED_NETWORKS = _parse_networks(TRUSTED_PROXIES)


def _is_trusted(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in network for network in _TRUSTED_NETWORKS)


def client_ip(request: Request) -> str | None:
    """IP réelle du client.

    X-Forwarded-For n'est lu que si la connexion TCP vient d'un proxy de confiance,
    et on le parcourt de droite à gauche : le premier saut non fiable est le client.
    Une valeur injectée par le client (à gauche de la chaîne) est donc ignorée.
    """
    peer = request.client.host if request.client else None
    if not peer or not _is_trusted(peer):
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    for hop in reversed(hops):
        try:
            ipaddress.ip_address(hop)
        except ValueError:
            return peer
        if not _is_trusted(hop):
            return hop
    return hops[0] if hops else peer
