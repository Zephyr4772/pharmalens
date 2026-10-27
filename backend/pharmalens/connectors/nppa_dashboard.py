"""Client for NPPA's public IPDMS dashboard (Compendium of Prices / ceiling prices).

The dashboard page is public, but its widget requests are wrapped by the page's own
`security.js`: request parameters are sorted, AES-128-CBC encrypted with a random key,
and the key is RSA-encrypted (PKCS#1 v1.5) with the site's published public key.
This module reproduces exactly what the browser sends; no authentication is involved.
"""
import base64
import json
import os
import re
from datetime import date

import httpx
from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .. import tls

HOST = "https://nppaipdms.gov.in"
PAGE = (HOST + "/HISUtilities/dashboard/dashBoardACTION.cnt?groupId=ODM=&dashboardFor=TlBQQQ=="
        "&hospitalCode=998&seatId=10001&isGlobal=1&isPreview=0")
PUBLIC_KEY = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEApCT+kp7+qSALD5EP6c6vay3YNvI6P0vK/25BpcvgnUa2dRihAccgTLVZn6UsM1RStjo4fJ4VBAn4xqiK/ErREa9T6h1JtLhMpiIrDPm6frA50j+/mISIwQJJfTmRAnckXbTBmLik3M7AsM9PP+PXp8xX4ZfZ6N3h73EdmxXW/ZJl3OvjgHCK6KsNmxhTbz/F3ifqdDtw8Pr7jUoxzecBV60XqpPFZWBAqu1NcZXLU2IWgZE6yPc6I1kCI9HuJble0YNlGUxFtzsfAcn4IyUx9oJtf56Cqn3sSM3IMOTFn8I2SbbRlE+MCVfgSXzJx0gjulsiUzh8xC5oVhzZZzNOLwIDAQAB
-----END PUBLIC KEY-----"""
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"

# widget ids on the "Ceiling Prices" tab
WIDGETS = {"ceiling": "30", "special": "244"}


def _encrypt(params: dict) -> str:
    """Mirror of security.js: sort -> JSON -> AES-CBC (hex key) -> RSA-wrap key -> JSON string."""
    lst = [{"name": k, "value": "" if v is None else str(v)} for k, v in params.items()]
    lst.sort(key=lambda x: x["name"].lower())
    plain = json.dumps(lst, separators=(",", ":"), ensure_ascii=False)
    key_hex = os.urandom(16).hex()
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    data = padder.update(plain.encode("utf-8")) + padder.finalize()
    enc = Cipher(algorithms.AES(bytes.fromhex(key_hex)), modes.CBC(iv)).encryptor()
    ct = enc.update(data) + enc.finalize()
    pub = serialization.load_pem_public_key(PUBLIC_KEY)
    wrapped = pub.encrypt(key_hex.encode(), rsa_padding.PKCS1v15())
    return json.dumps({"encryptedData": base64.b64encode(ct).decode(), "iv": iv.hex(),
                       "key": base64.b64encode(wrapped).decode(), "alg": 1}, separators=(",", ":"))


class NppaDashboard:
    def __init__(self):
        # the CSRF endpoint answers "Session Expired" unless the request looks same-origin
        self.c = httpx.Client(headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest", "Origin": HOST,
                                       "Referer": HOST + "/HISUtilities/dashboard/dashBoardACTION.cnt"},
                              timeout=90, verify=tls.CONTEXT, follow_redirects=True)
        page = self.c.get(PAGE).text
        m = re.search(r"""name=['"]tid['"][^>]*value=['"]([^'"]+)""", page)
        self.tid = m.group(1) if m else ""

    def _token(self) -> str:
        r = self.c.post(HOST + "/HISUtilities/generateToken/CSRFActionCNT.cnt", content=b"",
                        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        tok = r.text.strip()
        if not re.fullmatch(r"[0-9a-f]{32,256}", tok):
            raise RuntimeError("NPPA dashboard refused CSRF token request")
        return tok

    def widget(self, rpt_id: str) -> dict:
        params = {
            "hmode": "GET_WIDGET_DATA", "groupId": "83", "dashboardId": "10", "sectionId": "1", "rptId": rpt_id,
            "currentPageNo": -1, "currentblock": 1, "dateOptions": "", "fromDate": "", "toDate": "", "searchVal": "",
            "strparaId": "4", "strparaValue": "0", "strFilterId": "", "strFilterValue": "", "strFilterName": "",
            "strFilterDisplayName": "", "key": f"10_1_{rpt_id}", "primaryKey": "", "graphTypeSelected": "",
            "isZoomOut": "0", "currDate": date.today().strftime("%d-%b-%Y"), "loadFromDatabase": 1,
            "selectedCriteriaId": 0, "windowHeight": 900, "windowWidth": 1400, "strGroupParaId": "",
            "strGroupParaValue": "", "hospitalCode": "998", "seatId": "10001", "isGlobal": "1", "tid": self.tid,
            "processName": "dashboardMainPage", "isOnClickofKPI": 0, "isPreview": "0", "dashboardFor": "NPPA",
            "cachingStatus": "Stop Caching", "printButton": "Yes", "limitHTMLFromDb": "",
            "csrfToken": self._token(), "isAjaxRequest": "1",
        }
        r = self.c.get(HOST + "/HISUtilities/dashboard/dashBoardACTION.cnt",
                       params={"dbfhttf": json.dumps(_encrypt(params))})
        r.raise_for_status()
        # responses are mostly UTF-8 but contain stray Latin-1 bytes
        return json.loads(r.content.decode("utf-8", errors="replace"))

    def close(self):
        self.c.close()
