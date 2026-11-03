# Sample: US FDA inspection -> site (50 random links, 2026-11-03)

Linker `site:records`, source `fda_inspections` (FDA Data Dashboard, licence fda_web / open). Draw: `ORDER BY hash(src_key || 'q3') LIMIT 50`.
Methods: `locality_match` 0.85 (the maker's one PIN site sharing the address's place words), `district_site` 0.85 (maker + state + district:
FDA's city plus the state our other Indian addresses give that city), `address_postal` 0.9 (abroad: only joins a site an Indian approval
already lists), `same_fei` 0.95 (another inspection with this FEI is placed and all agree). FDA gives Indian firms no PIN, so no `address_pin`.

| # | method | firm (FDA) | city | country | project | site | check |
|---|---|---|---|---|---|---|---|
| 1 | district_site | Alembic Pharmaceuticals Limited | Panchmahal | India | Drug Quality Assurance | `st:alembic pharma|gujarat:panchmahal` | ok |
| 2 | district_site | Choksi Laboratories Limited | Indore | India | Drug Quality Assurance | `st:choksi labs|madhya pradesh:indore` | ok |
| 3 | address_postal | BASF Corporation | Bishop | United States | Drug Quality Assurance | `st:basf|states:78343` | ok |
| 4 | locality_match | Torrent Pharmaceuticals Limited | Indrad | India | Drug Quality Assurance | `st:torrent pharma|382721` | ok |
| 5 | address_postal | Jubilant HollisterStier LLC | Spokane | United States | Drug Quality Assurance | `st:jubilant hollisterstier llc|states:99207` | ok |
| 6 | district_site | Apotex Research Private Limited | Bengaluru | India | Drug Quality Assurance | `st:apotex research|karnataka:bengaluru` | ok |
| 7 | district_site | Lee Pharma Ltd. | Hyderabad | India | Drug Quality Assurance | `st:lee pharma|telangana:hyderabad` | ok |
| 8 | address_postal | Amgen Manufacturing Limited LLC | Juncos | United States | Drug Quality Assurance | `st:amgen manufacturing|states:00777` | ok |
| 9 | district_site | Cohance Lifesciences Limited | Medchal-Malkajgiri | India | Drug Quality Assurance | `st:cohance lifesciences|telangana:malkajgiri` | ok |
| 10 | locality_match | Sentiss Pharma Private Ltd. | District Solan | India | Drug Quality Assurance | `st:sentiss pharma|174101` | ok |
| 11 | district_site | Cipla, Ltd. | Kurkumbh Village, Dist. Pune | India | Drug Quality Assurance | `st:cipla|maharashtra:pune` | ok |
| 12 | district_site | Hetero Labs Limited - Unit III | Hyderabad | India | Drug Quality Assurance | `st:hetero labs|telangana:hyderabad` | ok |
| 13 | locality_match | Emnar Pharma Private Limited | Anakapalli District | India | Drug Quality Assurance | `st:emnar pharma|531019` | ok |
| 14 | district_site | Dasami Lab Private Limited | Nalgonda | India | Drug Quality Assurance | `st:dasami labs|telangana:nalgonda` | ok |
| 15 | locality_match | Fresenius Kabi Oncology Limited | Baddi | India | Drug Quality Assurance | `st:fresenius kabi oncology|173205` | ok |
| 16 | locality_match | Virupaksha Organics Limited, Unit-I | Sangareddy Dist. | India | Drug Quality Assurance | `st:virupaksha organics|502319` | ok |
| 17 | district_site | Brassica Pharma Private Ltd | Thane | India | Drug Quality Assurance | `st:brassica pharma|maharashtra:thane` | ok |
| 18 | district_site | SGS India Private Ltd. | Chennai | India | Drug Quality Assurance | `st:sgs|tamil nadu:chennai` | ok |
| 19 | locality_match | Ajanta Pharma Ltd. | Paithan | India | Drug Quality Assurance | `st:ajanta pharma|431105` | ok |
| 20 | district_site | Softgel Healthcare Private Limited | Pudupakkam, Kancheepuram | India | Drug Quality Assurance | `st:softgel healthcare|tamil nadu:kancheepuram` | ok |
| 21 | address_postal | Patheon Pharmaceuticals Inc. | Cincinnati | United States | Drug Quality Assurance | `st:patheon pharma|states:45237` | ok |
| 22 | locality_match | OneSource Specialty Pharma Limited | Bengaluru | India | Drug Quality Assurance | `st:onesource specialty pharma|561203` | ok |
| 23 | district_site | Teva API India Private Ltd. | Gajraula, Amroha | India | Drug Quality Assurance | `st:teva api|uttar pradesh:gajraula` | ok |
| 24 | locality_match | Cipla Ltd. | Bangalore | India | Drug Quality Assurance | `st:cipla|560105` | ok |
| 25 | locality_match | Laurus Labs Limited | Anikapalli District | India | Drug Quality Assurance | `st:laurus labs|531021` | ok |
| 26 | locality_match | Glenmark Pharmaceuticals Limited | Colvale | India | Drug Quality Assurance | `st:glenmark pharma|403513` | ok |
| 27 | district_site | DKR Labs Analytical Services | Hyderabad | India | Drug Quality Assurance | `st:dkr labs analytical services|telangana:hyderabad` | ok |
| 28 | locality_match | Zydus Lifesciences Limited | Dabhasa, Vadodara | India | Drug Quality Assurance | `st:zydus lifesciences|391440` | ok |
| 29 | district_site | Acutaas Chemicals Limited | Surat | India | Drug Quality Assurance | `st:acutaas chemicals|gujarat:surat` | ok |
| 30 | locality_match | Vital Laboratories Pvt Ltd Plant II | Vapi | India | Drug Quality Assurance | `st:vital labs|396195` | ok |
| 31 | district_site | Alivus Life Sciences Limited | Ankleshwar | India | Drug Quality Assurance | `st:alivus lifesciences|gujarat:bharuch` | ok |
| 32 | locality_match | APL HEALTHCARE LIMITED | Tirupati | India | Drug Quality Assurance | `st:apl healthcare|524421` | ok |
| 33 | locality_match | Indoco Remedies Limited | Verna | India | Drug Quality Assurance | `st:indoco remedies|403722` | ok |
| 34 | district_site | Dasami Lab Private Limited | Nalgonda | India | Drug Quality Assurance | `st:dasami labs|telangana:nalgonda` | ok |
| 35 | district_site | SCL Lifesciences Limited | Derabassi | India | Drug Quality Assurance | `st:scl lifesciences|punjab:derabassi` | ok |
| 36 | address_postal | Gilead Sciences Inc | San Dimas | United States | Drug Quality Assurance | `st:gilead sciences|states:91773` | ok |
| 37 | locality_match | Glenmark Pharmaceuticals Limited | Dhar | India | Drug Quality Assurance | `st:glenmark pharma|454774` | ok |
| 38 | address_postal | Lonza Manufacturing LLC | Vacaville | United States | Drug Quality Assurance | `st:lonza manufacturing llc|states:95688` | ok |
| 39 | locality_match | Wanbury Limited | Tanuku | India | Drug Quality Assurance | `st:wanbury|534217` | ok |
| 40 | district_site | ApiCore Pharmaceuticals Private Limited | Anakapalli | India | Drug Quality Assurance | `st:apicore pharma|andhra pradesh:anakapalli` | ok |
| 41 | address_postal | Amgen Manufacturing Limited LLC | Juncos | United States | Drug Quality Assurance | `st:amgen manufacturing|states:00777` | ok |
| 42 | address_postal | Amgen Manufacturing Limited LLC | Juncos | United States | Drug Quality Assurance | `st:amgen manufacturing|states:00777` | ok |
| 43 | locality_match | Apex Healthcare Limited | Ankleshwar | India | Drug Quality Assurance | `st:apex healthcare|393002` | ok |
| 44 | locality_match | Nuray Chemicals Private Limited | Kakkalur Village, Thiruvallur District | India | Drug Quality Assurance | `st:nuray chemicals|602003` | ok |
| 45 | district_site | Ami Lifesciences Private Ltd. | Vadodara | India | Drug Quality Assurance | `st:ami lifesciences|gujarat:vadodara` | ok |
| 46 | locality_match | Glenmark Pharmaceuticals Ltd. | Navi Mumbai | India | Bioresearch Monitoring | `st:glenmark pharma|400026` | ok |
| 47 | district_site | Strides Pharma Private Limited | Chengalpattu | India | Drug Quality Assurance | `st:strides pharma|tamil nadu:chengalpattu` | ok |
| 48 | locality_match | Aurobindo Pharma Ltd | Medchal | India | Drug Quality Assurance | `st:aurobindo pharma|500090` | ok |
| 49 | district_site | Jubilant Pharmova Limited | Mysore | India | Drug Quality Assurance | `st:jubilant pharmova|karnataka:mysore` | ok |
| 50 | district_site | Seema International | New Delhi | India | Drug Quality Assurance | `st:seema international|delhi:mangolpuri` | ok |

Review: 50 / 50 right firm and place. Caveats: district sites are district-level, not plant-level (Hetero Labs Unit III ->
`telangana:hyderabad`, shared with Hetero's other Hyderabad units); the Glenmark Bioresearch Monitoring row is a known maker's
bioequivalence centre, kept by design.

Errors found in earlier draws and fixed before this one: clinical investigators and hospitals (BIMO) made sites; survey numbers read as
PINs (Makson "182, 183" -> 182183); US parents joined to Indian namesakes (Merck & Co -> Merck Ltd, Century Pharmaceuticals Inc ->
Century Pharmaceuticals Ltd); 13,000 sites created for foreign firms with no Indian link.
