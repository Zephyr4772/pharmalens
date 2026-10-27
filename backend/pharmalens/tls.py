"""TLS for every outbound feed request: full certificate verification, plus a weekly revocation check.

Verification uses the standard public roots (certifi) plus intermediates that some government sites fail to send:
nppa.gov.in serves only its own certificate, without Sectigo's "Public Server Authentication CA DV R36". That
intermediate is pinned in certs/ (fetched from the URL its certificate names, checked to chain to Sectigo's root);
it only helps build chains to roots we already trust, it is never trusted on its own.

Python does not check revocation, so `revocation_status()` asks each host's OCSP responder once a week (health_watch).
"""
import ssl
import warnings
from pathlib import Path

import certifi
import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509 import ocsp
from cryptography.x509.oid import AuthorityInformationAccessOID, ExtensionOID

CERTS = Path(__file__).parent / "certs"

# hosts the feeds fetch from; checked weekly for revoked certificates
FEED_HOSTS = [
    "cdsco.gov.in", "cdscoonline.gov.in", "nppa.gov.in", "nppaipdms.gov.in", "janaushadhi.gov.in", "ipc.gov.in",
    "hmscl.org.in", "tnmsc.tn.gov.in", "rmsc.health.rajasthan.gov.in", "upmsc.in", "api.fda.gov",
    "download.open.fda.gov", "www.accessdata.fda.gov", "dailymed.nlm.nih.gov", "clinicaltrials.gov", "www.who.int",
    "extranet.who.int", "www.ema.europa.eu", "www.ebi.ac.uk", "www.nseindia.com", "api.gdeltproject.org",
    "news.google.com", "health.economictimes.indiatimes.com", "www.expresspharma.in", "thehealthmaster.com",
    "www.netmeds.com", "apiv2.netmeds.com", "www.ipca.com", "raw.githubusercontent.com", "api.drugsetu.com",
]
BENIGN_REVOCATION = {"superseded", "cessation_of_operation", "affiliation_changed"}


def context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    for pem in sorted(CERTS.glob("*.pem")):
        ctx.load_verify_locations(cafile=str(pem))
    # chains must still end at a public root: an intermediate in the store is not an anchor by itself
    if hasattr(ssl, "VERIFY_X509_PARTIAL_CHAIN"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
    return ctx


CONTEXT = context()


def _issuer_for(cert: x509.Certificate) -> x509.Certificate | None:
    """The issuing CA's certificate: pinned locally if we have it, else from the URL the certificate names."""
    for pem in sorted(CERTS.glob("*.pem")):
        c = x509.load_pem_x509_certificate(pem.read_bytes())
        if c.subject == cert.issuer:
            return c
    try:
        aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
    except x509.ExtensionNotFound:
        return None
    for d in aia:
        if d.access_method == AuthorityInformationAccessOID.CA_ISSUERS:
            body = httpx.get(d.access_location.value, timeout=20, follow_redirects=True).content
            # CAs publish their certificate as DER, PEM or a PKCS#7 bundle (eMudhra)
            for load in (lambda b: [x509.load_der_x509_certificate(b)], lambda b: [x509.load_pem_x509_certificate(b)],
                         pkcs7.load_der_pkcs7_certificates, pkcs7.load_pem_pkcs7_certificates):
                try:
                    with warnings.catch_warnings():     # eMudhra's bundle needs the (warned) BER fallback
                        warnings.simplefilter("ignore", UserWarning)
                        found = [c for c in load(body) if c.subject == cert.issuer]
                except ValueError:
                    continue
                if found:
                    return found[0]
    return None


def revocation_status(host: str) -> dict:
    """{'status': good | revoked | unknown | error, 'reason', 'detail'} for the certificate `host` serves."""
    try:
        # read the served certificate as is (verification is not the question here, revocation is)
        cert = x509.load_pem_x509_certificate(ssl.get_server_certificate((host, 443), timeout=20).encode())
        aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
        urls = [d.access_location.value for d in aia if d.access_method == AuthorityInformationAccessOID.OCSP]
        issuer = _issuer_for(cert)
        if not urls or issuer is None:
            return {"status": "unknown", "reason": None, "detail": "no OCSP responder or issuer certificate"}
        req = ocsp.OCSPRequestBuilder().add_certificate(cert, issuer, hashes.SHA1()).build()
        r = httpx.post(urls[0], content=req.public_bytes(serialization.Encoding.DER),
                       headers={"Content-Type": "application/ocsp-request"}, timeout=20)
        resp = ocsp.load_der_ocsp_response(r.content)
        if resp.response_status != ocsp.OCSPResponseStatus.SUCCESSFUL:
            return {"status": "unknown", "reason": None, "detail": f"OCSP {resp.response_status.name}"}
        st = resp.certificate_status
        if st == ocsp.OCSPCertStatus.REVOKED:
            reason = resp.revocation_reason.name if resp.revocation_reason else "unspecified"
            when = resp.revocation_time_utc if hasattr(resp, "revocation_time_utc") else resp.revocation_time
            return {"status": "revoked", "reason": reason, "detail": f"revoked {when:%d %b %Y}, expires {cert.not_valid_after_utc:%d %b %Y}"}
        return {"status": "good" if st == ocsp.OCSPCertStatus.GOOD else "unknown", "reason": None,
                "detail": f"expires {cert.not_valid_after_utc:%d %b %Y}"}
    except Exception as e:  # noqa: BLE001 — an unreachable host is the feeds' problem, not this check's
        return {"status": "error", "reason": None, "detail": f"{type(e).__name__}: {str(e)[:120]}"}
