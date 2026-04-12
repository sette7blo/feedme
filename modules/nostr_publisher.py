"""
modules/nostr_publisher.py — Sign Nostr events for recipe publishing
Uses pynostr for key management and Schnorr signing.
Publishing to the relay is done client-side via WebSocket.
Image upload uses NIP-96 (nostr.build) with NIP-98 HTTP Auth.
"""
import base64
import json
import mimetypes
import uuid
import urllib.request
import urllib.error
from pathlib import Path

from pynostr.key import PrivateKey
from pynostr.event import Event


NOSTR_KIND = 30078
NOSTRBUILDS_UPLOAD_URL = "https://nostr.build/api/v2/upload/files"
IMAGES_DIR = Path(__file__).parent.parent / "images"


def _public_image(url: str) -> str:
    """Return the image URL only if it's a public https:// link, else empty string."""
    url = (url or "").strip()
    return url if url.startswith("https://") or url.startswith("http://") else ""


def _is_local_image(url: str) -> bool:
    return bool(url) and not url.startswith("http://") and not url.startswith("https://")


def generate_keypair() -> dict:
    """Generate a new Nostr keypair. Returns {nsec, npub}."""
    pk = PrivateKey()
    return {
        "nsec": pk.bech32(),
        "npub": pk.public_key.bech32(),
    }


def get_pubkey(nsec: str) -> str:
    """Derive npub from a stored nsec (bech32 or hex)."""
    pk = _load_key(nsec)
    return pk.public_key.bech32()


def _load_key(nsec: str) -> PrivateKey:
    """Load a PrivateKey from nsec (bech32) or hex string."""
    nsec = nsec.strip()
    if nsec.startswith("nsec"):
        return PrivateKey.from_nsec(nsec)
    return PrivateKey(bytes.fromhex(nsec))


def _nip98_auth_header(url: str, method: str, pk: PrivateKey, payload_hash: str = None) -> str:
    """Build a NIP-98 Authorization header value for the given request."""
    tags = [
        ["u", url],
        ["method", method.upper()],
    ]
    if payload_hash:
        tags.append(["payload", payload_hash])
    auth_event = Event(
        content="",
        pubkey=pk.public_key.hex(),
        kind=27235,
        tags=tags,
    )
    auth_event.sign(pk.hex())
    encoded = base64.b64encode(json.dumps(auth_event.to_dict()).encode()).decode()
    return f"Nostr {encoded}"


def upload_image(image_url: str, nsec: str) -> str:
    """
    Upload a local image to nostr.build via NIP-96 with NIP-98 auth.
    image_url: relative path like 'images/slug.webp'
    Returns the public https:// URL.
    Raises ValueError on failure.
    """
    if not _is_local_image(image_url):
        url = _public_image(image_url)
        if url:
            return url
        raise ValueError(f"Not a valid public image URL: {image_url}")

    # Resolve local path
    path = IMAGES_DIR.parent / image_url
    if not path.exists():
        raise ValueError(f"Image file not found: {path}")

    file_bytes = path.read_bytes()
    filename = path.name
    mime_type = mimetypes.guess_type(filename)[0] or "image/jpeg"

    # Build multipart body first so we can hash it for NIP-98
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

    import hashlib
    payload_hash = hashlib.sha256(body).hexdigest()

    pk = _load_key(nsec)
    auth_header = _nip98_auth_header(NOSTRBUILDS_UPLOAD_URL, "POST", pk, payload_hash)

    req = urllib.request.Request(
        NOSTRBUILDS_UPLOAD_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": auth_header,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"nostr.build upload failed (HTTP {exc.code}): {body_text}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"nostr.build unreachable: {exc.reason}") from exc

    # nostr.build response format: data[0].url
    data = result.get("data", [])
    if data and data[0].get("url"):
        return data[0]["url"]

    # NIP-96 standard fallback: nip94_event.tags contains ["url", "https://..."]
    tags = result.get("nip94_event", {}).get("tags", [])
    for tag in tags:
        if len(tag) >= 2 and tag[0] == "url":
            return tag[1]

    raise ValueError(f"nostr.build returned unexpected response: {result}")


def sign_recipe_event_full(recipe_db: dict, recipe_full: dict, nsec: str, image_url: str = None) -> dict:
    """
    Build and sign using both DB row (metadata) and full JSON (instructions etc).
    image_url: optional override for the image (e.g. after nostr.build upload).
    """
    instructions = recipe_full.get("recipeInstructions", [])
    ingredients  = recipe_full.get("recipeIngredient", recipe_db.get("ingredients") or [])

    if image_url is None:
        image_url = _public_image(recipe_db.get("image_url", ""))

    pk = _load_key(nsec)

    content = json.dumps({
        "@context":           "https://schema.org",
        "@type":              "Recipe",
        "name":               recipe_db.get("name", ""),
        "slug":               recipe_db.get("slug", ""),
        "description":        recipe_db.get("description", ""),
        "prepTime":           recipe_db.get("prep_time", ""),
        "cookTime":           recipe_db.get("cook_time", ""),
        "totalTime":          recipe_db.get("total_time", ""),
        "recipeYield":        str(recipe_db.get("servings", "")) if recipe_db.get("servings") else "",
        "recipeCategory":     recipe_db.get("category", ""),
        "recipeCuisine":      recipe_db.get("cuisine", ""),
        "keywords":           recipe_db.get("tags") if isinstance(recipe_db.get("tags"), str) else ", ".join(recipe_db.get("tags") or []),
        "recipeIngredient":   ingredients,
        "recipeInstructions": instructions,
        "image":              image_url or "",
        "source_url":         recipe_db.get("source_url", ""),
        "source_type":        recipe_db.get("source_type", "manual"),
    }, ensure_ascii=False)

    event = Event(
        content=content,
        pubkey=pk.public_key.hex(),
        kind=NOSTR_KIND,
        tags=[
            ["d", recipe_db.get("slug", "")],
            ["t", "feedme"],
            ["t", "recipe"],
        ],
    )
    event.sign(pk.hex())

    return event.to_dict()
