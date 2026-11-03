# Sample: US FDA warning letters and import refusals -> site (50 random links, 2026-11-03)

Linker `site:records`, sources `fda_compliance_actions` and `fda_import_refusals` (FDA Data Dashboard, licence fda_web / open).
Draw: 25 of each, `ORDER BY hash(src_key || 'g7') LIMIT 25`, taken after the PIN-state and FEI-agreement fixes (one later tweak,
'distt' as a generic word, only removed a link).

Methods: `same_fei` 0.95 (an inspection or other record with this FEI is already placed, the placements agree, and this record's
place agrees with the site's: same state, at least one shared place word); `locality_match` 0.85; `district_site` 0.85 (only onto a
district site other records define: a shipper's office is not a plant); `address_postal` 0.9 (abroad, onto sites India-facing
approvals list).

| # | kind | method | firm (FDA) | city | what | site | check |
|---|---|---|---|---|---|---|---|
| 1 | warning | same_fei | Sharp Global Limited | New Delhi | Warning Letter 2014-10-15 | `st:sharp global|delhi:centre` | ok |
| 2 | warning | same_fei | CTX Lifesciences Private Ltd. | Surat | Warning Letter 2019-07-12 | `st:ctx lifesciences|394230` | ok |
| 3 | warning | same_fei | Lupin Limited | Pithampur | Warning Letter 2017-11-06 | `st:lupin|madhya pradesh:dhar` | ok |
| 4 | warning | same_fei | Shimoga Chemicals | Sangli | Warning Letter 2026-07-13 | `st:shimoga chemicals|maharashtra:sangli` | ok |
| 5 | warning | same_fei | Gland Chemicals Private Limited | Chennai | Warning Letter 2019-03-04 | `st:gland chemicals|tamil nadu:chennai` | ok |
| 6 | warning | same_fei | Contacare Ophthalmics & Diagnostics | Dabhasa | Warning Letter 2019-04-23 | `st:contacare ophthalmics diagnostics|391440` | ok |
| 7 | warning | same_fei | Catalent Indiana, LLC | Bloomington | Warning Letter 2025-11-21 | `st:catalent indiana|states:47403` | ok |
| 8 | warning | same_fei | Mahendra Chemicals | Ahmedabad | Warning Letter 2015-07-13 | `st:mahendra chemicals|gujarat:ahmedabad` | ok |
| 9 | warning | locality_match | Amneal Pharmaceuticals Private Limited | Palli | Warning Letter 2025-08-27 | `st:amneal pharma|382165` | ok |
| 10 | warning | same_fei | Indoco Remedies Limited (Plant I) | Verna | Warning Letter 2019-07-09 | `st:indoco remedies|403722` | ok |
| 11 | warning | same_fei | Sentiss Pharma Private Ltd. | District Solan | Warning Letter 2013-08-12 | `st:sentiss pharma|174101` | ok |
| 12 | warning | same_fei | Unimark Remedies Limited | Vapi | Warning Letter 2016-08-12 | `st:unimark remedies|gujarat:vapi` | ok |
| 13 | warning | address_postal | Bristol-Myers Squibb Holdings Pharma Ltd. Liability Company | Manati | Warning Letter 2010-09-30 | `st:bristol myers squibb holdings pharma|states:00674` | ok |
| 14 | warning | same_fei | Hospira, Inc. | Mcpherson | Warning Letter 2017-02-14 | `st:hospira|states:67460` | ok |
| 15 | warning | same_fei | CTX Lifesciences Private Ltd. | Surat | Warning Letter 2017-01-18 | `st:ctx lifesciences|394230` | ok |
| 16 | warning | same_fei | Aarti Drugs Limited | Palghar | Warning Letter 2013-08-02 | `st:aarti drugs|maharashtra:palghar` | ok |
| 17 | warning | same_fei | Centaur Pharmaceuticals Private Ltd. | Thane | Warning Letter 2023-06-05 | `st:centaur pharma|421501` | ok |
| 18 | warning | same_fei | Gland Chemicals Private Limited | Chennai | Warning Letter 2013-05-28 | `st:gland chemicals|tamil nadu:chennai` | ok |
| 19 | warning | same_fei | Synbiotics Limited | Luna | Warning Letter 2010-12-16 | `st:synbiotics|391440` | ok |
| 20 | warning | same_fei | Cipla Limited | Salcette | Warning Letter 2020-02-12 | `st:cipla|403722` | ok |
| 21 | warning | same_fei | Aparna Pharmaceuticals Private Limited | Pyidibhimavaram, Srikakulam | Warning Letter 2019-08-08 | `st:aparna pharma|532409` | ok |
| 22 | warning | same_fei | Vital Laboratories Pvt Ltd Plant II | Vapi | Warning Letter 2017-10-11 | `st:vital labs|396195` | ok |
| 23 | warning | same_fei | Zydus Lifesciences Limited | Ahmedabad | Warning Letter 2015-12-23 | `st:zydus lifesciences|382210` | ok |
| 24 | warning | same_fei | Mylan Laboratories Limited | Pithampur, District Dhar | Warning Letter 2024-12-19 | `st:mylan labs|454775` | ok |
| 25 | warning | same_fei | Resonance Laboratories Private Limited | Doddaballapur | Warning Letter 2017-02-03 | `st:resonance labs|561203` | ok |
| 26 | refusal | same_fei | Cipla Pvt Ltd | Sikkim | FLUCONAZOLE (ANTI-FUNGAL) (NOT ANTIBIOTIC) 2023-12-22 | `st:cipla|737132` | ok |
| 27 | refusal | same_fei | CIPLA LIMITED | Mumbai | LOPINAVIR (ANTI-PROTOZOAL) 2020-04-08 | `st:cipla|400013` | ok |
| 28 | refusal | same_fei | Cipla Ltd. | Rangpo | AMLODIPINE BESYLATE (ANTI-HYPERTENSIVE, PART II) 2026-10-02 | `st:cipla|737132` | ok |
| 29 | refusal | same_fei | Intas Pharmaceuticals Limited | Ahmedabad | RISPERIDONE (TRANQUILIZER (ANTI-PSYCHOTIC) - PART II) 2026-02-27 | `st:intas pharma|gujarat:ahmedabad` | ok |
| 30 | refusal | locality_match | NANOCEUT THERAPEUTICS PVT. LTD | Puducherry | DOMPERIDONE 2026-09-25 | `st:nanoceut therapeutics|605111` | ok |
| 31 | refusal | locality_match | Ami Lifesciences Private Limited | Vadodara | DESVENLAFAXINE SUCCINATE 2020-11-17 | `st:ami lifesciences|390020` | ok |
| 32 | refusal | same_fei | Alkem Laboratories Limited | Ankleshwar | ACETAMINOPHEN (ANALGESIC) 2025-10-07 | `st:alkem labs|393002` | ok |
| 33 | refusal | locality_match | Asoj Soft Caps Pvt.Ltd. | Gujarat | ISOTRETINOIN (KERATOLYTIC) 2025-09-24 | `st:asoj soft caps|391510` | ok |
| 34 | refusal | same_fei | Intas Pharmaceuticals Limited | Ahmedabad | NAPHAZOLINE HCL (ADRENERGIC) 2025-03-04 | `st:intas pharma|gujarat:ahmedabad` | ok |
| 35 | refusal | same_fei | Rxhomeo Private Limited | Hyderabad | MISCELLANEOUS PATENT MEDICINES, ETC. 2022-09-06 | `st:rxhomeo|telangana:hyderabad` | ok |
| 36 | refusal | same_fei | AKRON FORMULATIONS INDIA PRIVATE LIMITED | Hyderabad | ACETAMINOPHEN (ANALGESIC) 2025-02-06 | `st:akron formulations|telangana:hyderabad` | ok |
| 37 | refusal | locality_match | TORRENT PHARMACEUTICALS LTD | Ahmedabad | PRUCALOPRIDE SUCCINATE (CATHARTIC) 2022-04-07 | `st:torrent pharma|382721` | ok |
| 38 | refusal | locality_match | ADWIN PHARMA | Sirmour | LORAZEPAM (TRANQUILIZER) 2020-07-28 | `st:adwin pharma|173030` | ok |
| 39 | refusal | same_fei | Glenmark Pharmaceuticals Limited | Solan | FENOFIBRATE (ANTI-CHOLESTEREMIC) 2024-01-19 | `st:glenmark pharma|173205` | ok |
| 40 | refusal | locality_match | CIPLA LTD | Sikkim | SALMETEROL XINAFOATE (ANTI-ASTHMATIC) 2025-07-02 | `st:cipla|737133` | ok |
| 41 | refusal | locality_match | ALEMBIC PHARMACEUTICALS LTD | Sikkim | HOMEOPATHIC MULTIPLE INDICATIONS 2026-06-01 | `st:alembic pharma|737126` | ok |
| 42 | refusal | same_fei | CIPLA LIMITED | Mumbai | ANTI-INFLAMMATORY N.E.C. 2026-07-24 | `st:cipla|400013` | ok |
| 43 | refusal | same_fei | Reckitt Benckiser | Mysore | CHLOROXYLENOL (ANTI-BACTERIAL) (NOT ANTIBIOTIC) 2017-05-04 | `st:reckitt benckiser|570018` | ok |
| 44 | refusal | same_fei | Torrent Pharmaceuticals Ltd | Ahmedabad | DIAZEPAM (SEDATIVE) 2021-01-26 | `st:torrent pharma|382721` | ok |
| 45 | refusal | same_fei | Cipla Limited | Mumbai | TELMISARTAN (ANTI-HYPERTENSIVE - PART II) 2026-09-09 | `st:cipla|400013` | ok |
| 46 | refusal | same_fei | TORRENT PHARMA | Sikkim | OLANZAPINE (TRANQUILIZER (ANTI-PSYCHOTIC) - PART II 2026-05-02 | `st:torrent pharma|737135` | ok |
| 47 | refusal | locality_match | MICRO LABS LIMITED | Thiruvandar Koil Pudu | ORLISTAT/TETRAHYDROLIPSTATIN (ANOREXIC) 2023-10-17 | `st:micro labs|605102` | ok |
| 48 | refusal | same_fei:generic_firm_name | JM LABORATORIES | Solan | PANTOPRAZOLE SODIUM 2024-02-13 | `st:jm labs|173211` | ok |
| 49 | refusal | same_fei | Alkem Laboratories Ltd | Mumbai | PANTOPRAZOLE SODIUM 2019-08-06 | `st:alkem labs|maharashtra:mumbai` | ok |
| 50 | refusal | same_fei | Micro Labs Limited | Bengaluru | DOMPERIDONE 2020-09-28 | `st:micro labs|560105` | ok |

Review: 50 / 50 right firm and place. Some sites are offices that other sources already list as sites (Cipla `400013`,
Lower Parel; Alkem `maharashtra:mumbai`): refusals filed under a head-office FEI land there, as FDA files them.

Errors found in earlier draws and fixed before this one:
- refusals created new district "plants" from shippers' offices (Sun Pharma Mumbai): refusals and warning letters now only join existing sites;
- a door number read as a PIN (Rxhomeo "4-1-424-426 Bank Street, Hyderabad" -> PIN 424426, Maharashtra): a PIN must now fit a state
  the address names (45 sites across all sources re-keyed);
- one FEI filed under two addresses (Dabur Unit-2, Pant Nagar, joined to Dabur Baddi): FEI joins now need the record's place to agree;
- the firm's own name in its street counted as a shared place word.
