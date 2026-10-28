# Permission requests: drafts to send

Drafted 2026-10-28 for the owner to review and send from their own email. Fill the `[…]` fields first. Send the
CDSCO and NPPA letters first: they unlock most of DrugDen's core data (see `docs/LICENSING.md`). When a reply grants
permission, record it in `PERMISSIONS` in `backend/pharmalens/licensing.py` with the reference and date.

Fields to fill everywhere:
- `[Your name]`, `[Your phone]`, `[Your email]`
- `[Organisation]`: DrugDen's legal form (sole proprietorship / LLP / company) and registration number, if any.
  Government offices answer registered entities faster.
- `[Website]`: once the site is live; leave the line out until then.

---

## 1. CDSCO

**To:** dci@nic.in
**Postal:** Drugs Controller General (India), Central Drugs Standard Control Organisation, FDA Bhavan, ITO,
Kotla Road, New Delhi 110002
**Subject:** Request for permission to reproduce published CDSCO information, with attribution

Respected Sir/Madam,

I am writing on behalf of DrugDen ([Organisation]), an Indian service that compiles publicly available regulatory
information on medicines into structured, searchable datasets for public-health researchers, NGOs, hospitals and
pharmaceutical companies.

CDSCO's website policy states that its contents may not be reproduced without due permission. We therefore
request your written permission to reproduce the following information, which CDSCO already publishes, in our
datasets and data service, including to paying subscribers:

1. Lists of drug samples declared Not of Standard Quality and spurious (cdscoonline.gov.in, public NSQ section, and
   the monthly alert lists on cdsco.gov.in);
2. The approvals information on cdscoonline.gov.in (drug, composition, applicant, approval date);
3. Subject Expert Committee recommendations (meeting minutes);
4. The Rule 84AB brand name registry (brand, licensed manufacturer, licence number, generic name);
5. Public notices, circulars, alerts and lists of prohibited fixed-dose combinations (titles, dates and links).

We would reproduce this information on the following terms:
- every record carries the attribution "Source: CDSCO, Government of India", its publication date and a link to
  the original page or document;
- the content is not altered in substance and is never presented in a misleading context;
- we state clearly that DrugDen is independent and not endorsed by CDSCO;
- we update promptly when CDSCO revises or withdraws a list, and correct any error brought to our notice;
- our collection is light and rate-limited, so it places no meaningful load on CDSCO's servers.

Please let us know if CDSCO requires any further conditions, a particular form of attribution, or a formal
application. We would be glad to share a sample of the dataset.

Thank you for your consideration.

Yours faithfully,
[Your name]
[Organisation]
[Your phone] · [Your email]
[Website]

---

## 2. NPPA

**To:** Member Secretary, National Pharmaceutical Pricing Authority
**Email:** pallav.chittej@gov.in (Web Information Manager, Shri Pallav Kumar Chittej, Deputy Director), with a
request to forward to the Member Secretary
**Postal:** NPPA, 3rd/5th Floor, YMCA Cultural Centre Building 1, Jai Singh Road, New Delhi 110001
**Subject:** Request for permission to reproduce NPPA price information, with attribution

Respected Sir/Madam,

I am writing on behalf of DrugDen ([Organisation]), an Indian service that compiles publicly available information
on medicine prices and regulation into structured datasets for researchers, NGOs, hospitals and pharmaceutical
companies.

We request NPPA's permission, or confirmation that no permission is needed, to reproduce the following information
that NPPA publishes, in our datasets and data service, including to paying subscribers:

1. Retail prices fixed for new drugs and other price notifications (Gazette S.O. orders);
2. Ceiling prices of scheduled formulations, as published in the Compendium of Prices on the IPDMS dashboard;
3. Titles, dates and links of NPPA orders, circulars, Authority meeting minutes and overcharging-case statements.

We understand that matter published in the Official Gazette may be reproduced under Section 52(1)(q) of the
Copyright Act, 1957, and would be grateful for confirmation, together with permission for the material published
only on NPPA's websites.

Every record would carry the attribution "Source: NPPA, Government of India", the notification number and date
and a link to the original; content would not be altered in substance or used in a misleading context; we would
state that DrugDen is independent and not endorsed by NPPA, and update promptly on any revision.

A note for the website team, offered in good faith: since 19 October 2026 nppaipdms.gov.in has been serving a TLS
certificate that its issuer (eMudhra) has revoked as "superseded". Browsers that check revocation, including
Windows, refuse the site. Installing the replacement certificate on the server should resolve it.

Thank you for your consideration.

Yours faithfully,
[Your name]
[Organisation]
[Your phone] · [Your email]
[Website]

---

## 3. State and other agencies (short form)

Use this body for each, changing the bracketed agency and data:

**Subject:** Request for permission to reproduce published [data], with attribution

Respected Sir/Madam,

I am writing on behalf of DrugDen ([Organisation]), an Indian service that compiles publicly available information
on medicines into structured datasets for researchers, NGOs, hospitals and pharmaceutical companies.

We request [Agency]'s permission to reproduce the following information it publishes on its website, in our
datasets and data service, including to paying subscribers: [data]. Every record would carry the attribution
"Source: [Agency]", its date and a link to the original page; the content would not be altered in substance or
presented misleadingly; we would state that DrugDen is independent and not endorsed by [Agency], and update promptly
on any revision. Our collection is light and rate-limited.

Please let us know of any conditions or a preferred form of attribution.

Yours faithfully,
[Your name] · [Organisation] · [Your phone] · [Your email]

| Agency | Send to | Data to name | Notes |
|---|---|---|---|
| Tamil Nadu Medical Services Corporation (TNMSC) | md.tnmsc@tn.gov.in, cc gmdrug.tnmsc@tn.gov.in and srsymngr.tnmsc@tn.gov.in (Website Information Manager) | tender rates (L1 rate per item, supplier, order share) | 417 Pantheon Road, Egmore, Chennai 600008. Their old enquiry address was closed in 2020 |
| Rajasthan Medical Services Corporation (RMSCL) | edlrmsc@nic.in (ED (L), nodal officer for the website) | drug rate contracts (item, supplier, rate, GST, validity) | phone 0141-2228065 |
| Haryana Medical Services Corporation (HMSCL) | hmsclmd@gmail.com (as listed on hmscl.org.in) | drug rate contracts | Plot 09, DHL Square Building, HSIIDC IT Park, Sector 22, Panchkula 134112 |
| Indian Pharmacopoeia Commission (PvPI) | lab.ipc@gov.in, addressed to the Secretary-cum-Scientific Director | list of drug safety alerts issued by PvPI | Sector 23, Raj Nagar, Ghaziabad 201002; no PvPI-specific address found |
| PMBI (Jan Aushadhi) | check janaushadhi.gov.in contact page (only procurement officers' addresses found) | Jan Aushadhi product list and MRPs | older tenders give 8th Floor, Videocon Tower, Jhandewalan Extension, New Delhi 110055 |
| UPMSCL (Uttar Pradesh) | check upmsc.in contact page (site blocks cloud servers; open it from your laptop) | list of debarred / blacklisted firms | |

Not worth writing yet: WHO (their data stays internal; ask only if it becomes important) and NSE (market data
needs a paid data agreement, not a letter).
