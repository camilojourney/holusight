"""Bounded public HTTPS research, independent of private indexes and model providers.

Only caller-supplied URLs are fetched. A cited claim is an exact excerpt, not a
model-generated inference. This deliberately narrow synthesis prevents claims
that cannot be mechanically checked against the fetched source.
"""

from __future__ import annotations

import hashlib
import html
import html.parser
import http.client
import ipaddress
import json
import re
import secrets
import socket
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote as url_quote
from urllib.parse import urlsplit

from .control_storage import safe_atomic_write

MAX_BYTES = 512_000
MAX_CLAIMS = 6
OUTPUT_ROOT = Path(".holusight/public-research")


class ResearchError(ValueError):
    """A public URL, fetch, or verification failed closed."""


class _Text(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "nav", "footer"}:
            self.hidden += 1
        if tag in {"p", "div", "li", "h1", "h2", "h3", "br"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "footer"} and self.hidden:
            self.hidden -= 1
        if tag in {"p", "div", "li", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def validate_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ResearchError("invalid public HTTPS URL") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or port not in (None, 443)
        or "\\" in url
        or any(ord(c) < 33 or ord(c) == 127 for c in url)
    ):
        raise ResearchError("only explicit public HTTPS URLs on port 443 are allowed")
    host = parsed.hostname.rstrip(".")
    if (
        not host
        or len(host) > 253
        or host == "localhost"
        or host.endswith(".localhost")
        or "." not in host
        or not all(
            re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
            for label in host.split(".")
        )
    ):
        raise ResearchError("URL host must be a public DNS name")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ResearchError("IP literal URLs are not allowed")
    return host


def _public_address(host: str) -> str:
    try:
        addresses = {
            entry[4][0] for entry in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise ResearchError("public DNS lookup failed") from exc
    if not addresses or any(not ipaddress.ip_address(addr).is_global for addr in addresses):
        raise ResearchError("URL resolves to a non-public address")
    return sorted(addresses)[0]


class _PinnedHTTPS(http.client.HTTPSConnection):
    """Use the vetted IP for the socket; retain hostname for TLS and Host."""

    def __init__(self, host: str, address: str) -> None:
        super().__init__(host, port=443, timeout=10, context=ssl.create_default_context())
        self.address = address

    def connect(self) -> None:
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def fetch(url: str) -> tuple[str, str]:
    """Fetch a single limited public text page; never follow a redirect."""
    host = validate_url(url)
    address = _public_address(host)
    path = urlsplit(url).path or "/"
    if urlsplit(url).query:
        path += "?" + urlsplit(url).query
    connection = _PinnedHTTPS(host, address)
    try:
        connection.request(
            "GET",
            path,
            headers={
                "Accept": "text/html, text/plain",
                "User-Agent": "Holusight-public-research/1",
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ResearchError("source returned non-200 status (redirects are not followed)")
        media = response.getheader("Content-Type", "").split(";")[0].strip().lower()
        if media not in {"text/html", "text/plain"}:
            raise ResearchError("source is not HTML or plain text")
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise ResearchError("compressed sources are not supported")
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ResearchError("source exceeds the 512 KB limit")
        text = data.decode("utf-8", errors="replace")
        if media == "text/html":
            parser = _Text()
            parser.feed(text)
            text = " ".join(parser.parts)
        text = re.sub(r"\s+", " ", text).strip()
        return text, datetime.now(timezone.utc).isoformat()
    except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
        raise ResearchError("public HTTPS fetch failed") from exc
    finally:
        connection.close()


def _excerpts(question: str, text: str) -> list[str]:
    words = {w.lower() for w in re.findall(r"[a-zA-Z0-9]{4,}", question)} - {
        "what",
        "which",
        "where",
        "when",
        "does",
        "with",
        "from",
        "about",
        "that",
        "this",
    }
    if not words:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    scored = []
    for sentence in sentences:
        sentence = sentence.strip()
        score = len(words & set(re.findall(r"[a-zA-Z0-9]{4,}", sentence.lower())))
        if score and 24 <= len(sentence) <= 320:
            scored.append((score, sentence))
    return [sentence for _, sentence in sorted(scored, key=lambda x: -x[0])[:MAX_CLAIMS]]


def verify_claims(claims: list[dict], sources: list[dict]) -> list[str]:
    """Return explicit failures; exact excerpt matching is not semantic entailment."""
    failures = []
    by_id = {source["id"]: source for source in sources}
    for index, claim in enumerate(claims, 1):
        source = by_id.get(claim.get("source_id"))
        quote = claim.get("quote")
        if not source or not isinstance(quote, str) or not quote.strip():
            failures.append(f"claim {index}: missing source or excerpt")
        elif hashlib.sha256(source["text"].encode()).hexdigest() != source["sha256"]:
            failures.append(f"claim {index}: source digest mismatch")
        elif (
            claim.get("text") != quote
            or quote not in source["text"]
            or not any(
                e["id"] == claim.get("excerpt_id") and e["text"] == quote
                for e in source.get("excerpts", [])
            )
        ):
            failures.append(f"claim {index}: claim/citation does not match retrieved excerpt")
    return failures


def run(
    question: str, urls: list[str], *, allow_egress: bool, repo_root: Path, fetcher=None
) -> tuple[dict, int]:
    if fetcher is None:
        fetcher = fetch
    if not question.strip() or len(question) > 1000:
        raise ResearchError("provide one nonempty question (at most 1000 characters)")
    if len(urls) not in (2, 3) or len(set(urls)) != len(urls):
        raise ResearchError("supply 2 or 3 distinct public HTTPS URLs")
    # Check syntax before any network call. The opt-in gate precedes DNS and fetch.
    for url in urls:
        validate_url(url)
    if not allow_egress:
        raise ResearchError("egress denied; pass --allow-egress to fetch supplied public URLs")
    sources = []
    for index, url in enumerate(urls, 1):
        text, fetched_at = fetcher(url)
        sources.append(
            {
                "id": f"S{index}",
                "url": url,
                "fetched_at": fetched_at,
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "text": text,
            }
        )
    claims = []
    for source in sources:
        source["excerpts"] = [
            {"id": f"{source['id']}:E{index}", "text": excerpt}
            for index, excerpt in enumerate(_excerpts(question, source["text"])[:2], 1)
        ]
        for excerpt in source["excerpts"]:
            claims.append(
                {
                    "text": excerpt["text"],
                    "quote": excerpt["text"],
                    "source_id": source["id"],
                    "excerpt_id": excerpt["id"],
                }
            )
    claims = claims[:MAX_CLAIMS]
    failures = verify_claims(claims, sources)
    status = (
        "verification_failed" if failures else ("verified_excerpts" if claims else "no_evidence")
    )
    now = datetime.now(timezone.utc)
    receipt = {
        "question": question,
        "status": status,
        "created_at": now.isoformat(),
        "egress": {"allowed": True, "occurred": True, "destinations": urls},
        "sources": [{k: v for k, v in source.items() if k != "text"} for source in sources],
        "claims": [{**claim, "verified": not failures} for claim in claims],
        "verification_failures": failures,
        "limitations": (
            "Exact excerpt matching only; no semantic entailment or independent fact checking."
        ),
    }
    lines = [
        f"# Public URL research - {now.date().isoformat()}",
        "",
        f"Question: {html.escape(question)}",
        "",
        f"Status: **{status}**",
        "",
        "Only exact retrieved excerpts are reported, not inferred facts.",
        "",
    ]
    if failures:
        lines += ["## Verification failures", *[f"- {failure}" for failure in failures], ""]
    elif not claims:
        lines += ["No matching excerpts found. The question is unanswered.", ""]
    else:
        lines += ["## Retrieved excerpts", ""]
        for claim in claims:
            source = next(s for s in sources if s["id"] == claim["source_id"])
            safe_quote = html.escape(claim["quote"])
            safe_url = url_quote(source["url"], safe="/:#?&=%+-._~@")
            lines += [
                f'- "{safe_quote}" [{claim["excerpt_id"]}]({safe_url}) '
                f"(fetched {source['fetched_at']}; SHA-256 {source['sha256']})"
            ]
    lines += ["", "## Sources", ""]
    lines += [
        f"- {s['id']}: {html.escape(s['url'])} (fetched {s['fetched_at']}; SHA-256 {s['sha256']})"
        for s in sources
    ]
    lines += ["", f"Limitations: {receipt['limitations']}", ""]
    stem = now.strftime("%Y-%m-%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    report = safe_atomic_write(
        repo_root,
        OUTPUT_ROOT / (stem + ".md"),
        "\n".join(lines).encode(),
        allowed_repo_root=OUTPUT_ROOT,
    )
    result = safe_atomic_write(
        repo_root,
        OUTPUT_ROOT / (stem + ".json"),
        (json.dumps(receipt, indent=2) + "\n").encode(),
        allowed_repo_root=OUTPUT_ROOT,
    )
    return {
        "status": status,
        "report": str(report),
        "receipt": str(result),
        "claims_verified": len(claims) if not failures else 0,
        "verification_failures": failures,
    }, 1 if failures else 0
