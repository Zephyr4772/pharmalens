# Link sample: 09-multi-entity-events

50 random new links from `event_entities` in `work.duckdb`, for spot checks. High = confidence ≥ 0.85 (shown by default); lower values are labelled inferred in the UI.

| event | kind | title | → entity | method | conf | licence | evidence |
|---|---|---|---|---|---|---|---|
| 703 | nsq | NSQ: Pantoprazole Gastro-resistant Tablets IP.. (PAN 40) batch 2244207 | parent: Alkem Laboratories | company_group | 1.00 | internal | company 30's group |
| 1299 | nsq | NSQ: L-Carnitine L-Tartrate, Mecobalamin & Folic Acid Tablets batch B9 | molecule: Folic Acid | product_text_complete | 0.95 | internal | 'folic acid' in “L-Carnitine L-Tartrate, Mecobalamin & Folic Acid Tablets” |
| 941 | approval | SEC recommends biological approval: 56525 Nivolumab Concentrate for So | molecule: Nivolumab | product_text_complete | 0.95 | internal | 'nivolumab' in “56525 Nivolumab Concentrate for Solution for Intravenous Infusion 40 mg/4 mL & 100 mg/10 mL single-use v |
| 2307 | price_notification | Jan Aushadhi MRP change: Dextromethorphan Hydrobromide Syrup IP 13.5mg | molecule: Dextromethorphan Hydrobromide | source_record | 0.90 | internal | Jan Aushadhi item 860 |
| 1680 | nsq | NSQ: Paracetamol Tab IP [Parayes -500 ) batch 423- 1582 | parent: Zee Laboratories | company_group | 1.00 | internal | company 272's group |
| 2350 | price_notification | Jan Aushadhi MRP change: Doxofylline (Sustained-release) 400mg and Mon | molecule: Doxofylline | source_record | 0.90 | internal | Jan Aushadhi item 2106 |
| 1313 | nsq | NSQ: Ursodeoxycholic Acid Tablets IP batch GTF3302A | parent: Sun Pharmaceutical Industries | company_group | 1.00 | internal | company 5222's group |
| 1297 | nsq | NSQ: Telmisartan And Metoprolol Succinate Extended Release Tablets (40 | molecule: Telmisartan | product_text_complete | 0.95 | internal | 'telmisartan' in “Telmisartan And Metoprolol Succinate Extended Release Tablets (40 mg+50 mg)” |
| 2315 | price_notification | Jan Aushadhi MRP change: Betamethasone Cream IP 0.1 % w/w ₹9.28 → ₹10. | molecule: Betamethasone | source_record | 0.90 | internal | Jan Aushadhi item 1162 |
| 838 | approval | SEC recommends approval: Fluticasone Furoate 200 mcg + Umeclidinium br | molecule: Fluticasone Furoate | product_text_partial | 0.85 | internal | 'fluticasone furoate 200' in “Fluticasone Furoate 200 mcg + Umeclidinium bromide eq. to Umeclidinium 62.5 mcg + Vilanter |
| 831 | approval | SEC recommends biological approval: 4579 Aflibercept Drug Substance &  | molecule: Aflibercept | product_text_partial | 0.70 | internal | 'aflibercept' in “4579 Aflibercept Drug Substance & Aflibercept Drug Product (40 mg/ml ) Solution for intravitreal injec |
| 1208 | nsq | NSQ: Levetiracetam Tablets IP 500 mg batch N2601077 | parent: Intas Pharmaceuticals | company_group | 1.00 | internal | company 50's group |
| 1110 | approval | CDSCO approval (biological): Inactivated Hepatitis A Vaccine (Adsorbed | molecule: Phosphate | payload_molecule_ids_unconfirmed | 0.70 | internal | connector id not found in “Inactivated Hepatitis A Vaccine (Adsorbed) I.P.” |
| 1670 | nsq | NSQ: Gentamicin Sulphate Injection I.P. 2 ml batch 323-216 | ingredient_set: 2906 | product_text_complete_set | 0.90 | internal | all ingredients resolved from “Gentamicin Sulphate Injection I.P. 2 ml” |
| 1667 | nsq | NSQ: Dexamethasone Sodium Phosphate Injection I.P. (8mg/2ml) batch 323 | parent: Zee Laboratories | company_group | 1.00 | internal | company 272's group |
| 1141 | nsq | NSQ: Levocetirizine  Tablets IP 5mg  Levocet batch GT23624C | parent: Hetero | company_group | 1.00 | internal | company 330's group |
| 1522 | trial | New trial in India: A Study of EloraTZP in Adult Participants With Obe | molecule: Tirzepatide | source_record | 0.95 | internal | trial NCT07881432 interventions |
| 478 | recall | USFDA Class I recall — Kilitch Healthcare India Limited: CVS brand Mul | molecule: Tetrahydrozoline Hydrochloride | source_record | 0.95 | internal | US FDA recall-D-0296-2024 product description |
| 498 | news | Nifty Pharma falls 1.6%; Divi's Labs, Sun Pharma lead losses: What lie | parent: Divi's Laboratories | source_record | 0.95 | internal | news article's group tags |
| 662 | nsq | NSQ: Bisacodyl Gastro- Resistance Tablets IP 5mg (Bisacodyl) batch EGT | molecule: Bisacodyl | product_text_partial | 0.85 | internal | 'bisacodyl' in “Bisacodyl Gastro- Resistance Tablets IP 5mg (Bisacodyl)”; unexplained: resistance |
| 1167 | nsq | NSQ: Amoxycillin and Potassium Clavulanate Tablets IP batch 25442306 | molecule: Amoxycillin | payload_molecule_ids | 0.95 | internal | molecule ids resolved by the connector |
| 1660 | nsq | NSQ: Itraconazole Capsules 100 mg batch Z22-293 | ingredient_set: 3480 | product_text_complete_set | 0.90 | internal | all ingredients resolved from “Itraconazole Capsules 100 mg” |
| 714 | nsq | NSQ: Amlodipine and Perindopril Tablets (Amtas PRP) batch K2201310 | parent: Intas Pharmaceuticals | company_group | 1.00 | internal | company 50's group |
| 1171 | nsq | NSQ: Paracetamol and Domperidone Tablets (Dompar) batch 4C11469 | molecule: Domperidone | payload_molecule_ids | 0.95 | internal | molecule ids resolved by the connector |
| 1097 | approval | CDSCO approval (biological): Pegfilgrastim — LUPIN LIMITED | molecule: Pegfilgrastim | product_text_complete | 0.95 | internal | 'pegfilgrastim' in “Pegfilgrastim” |
| 671 | nsq | NSQ: Miconazole Nitrate and Fluocinolone Acetonide Ointment (Zole - F) | molecule: Miconazole Nitrate | product_text_partial | 0.85 | internal | 'miconazole nitrate' in “Miconazole Nitrate and Fluocinolone Acetonide Ointment (Zole - F)”; unexplained: zole f |
| 729 | nsq | NSQ: Snikuf 4 batch RZAB01 | parent: Akums Drugs & Pharmaceuticals | company_group | 1.00 | internal | company 1031's group |
| 791 | spurious | SPURIOUS: Ofloxacin And Ornidazole Tablets IP batch E-50032 | molecule: Ofloxacin | product_text_complete | 0.95 | internal | 'ofloxacin' in “Ofloxacin And Ornidazole Tablets IP” |
| 1685 | nsq | NSQ: Bupivacaine Hydrochloride Injection IP (Bupicain-0.5%) batch BPC2 | molecule: Bupivacaine | product_text_partial | 0.85 | internal | 'bupivacaine hydrochloride' in “Bupivacaine Hydrochloride Injection IP (Bupicain-0.5%)”; unexplained: bupicain |
| 1255 | recall | WHO alert: Medical Product Alert N°1/2026: Substandard ACCUPAQUE (Iohe | molecule: Iohexol | payload_molecule_ids | 0.95 | internal | molecule ids resolved by the connector |
| 1315 | nsq | NSQ: Clopidogrel and Aspirin Capsules batch SIH0304A | parent: Sun Pharmaceutical Industries | company_group | 1.00 | internal | company 5222's group |
| 602 | news | Dr Reddy’s, Torrent Pharma, Zydus Life: Pharma stocks to post resilien | parent: Zydus Lifesciences | source_record | 0.95 | internal | news article's group tags |
| 2363 | launch | Jan Aushadhi adds Pyridoxine Hydrochloride 10mg, Doxylamine Succinate  | molecule: Doxylamine Succinate | source_record | 0.90 | internal | Jan Aushadhi item 2911 |
| 1662 | nsq | NSQ: SPIRONOLACTONE TABLETS IP 25 mg (ALDACTONE) batch 02A22020 | molecule: Spironolactone | product_text_partial | 0.85 | internal | 'spironolactone' in “SPIRONOLACTONE TABLETS IP 25 mg (ALDACTONE)”; unexplained: aldactone |
| 950 | approval | SEC recommends biological approval: 0442 Ustekinumab injection (r-DNA  | molecule: Ustekinumab | product_text_partial | 0.85 | internal | 'ustekinumab' in “0442 Ustekinumab injection (r-DNA origin) 130mg/26mL (5 mg/mL) in a single- dose vial (Intravenous).”; |
| 856 | approval | SEC recommends approval: Glycopyrronium bromide equivalent to glycopyr | molecule: Glycopyrronium Bromide | product_text_partial | 0.85 | internal | 'glycopyrronium bromide' in “Glycopyrronium bromide equivalent to glycopyrronium 12.5 mcg + Formoterol Fumarate Dihydrat |
| 1312 | nsq | NSQ: Tamsulosin Hydrochloride Modified Release Tablets batch N2600542 | molecule: Tamsulosin | product_text_complete | 0.95 | internal | 'tamsulosin hydrochloride' in “Tamsulosin Hydrochloride Modified Release Tablets” |
| 370 | recall | USFDA Class II recall — Ajanta Pharma Ltd.: Duloxetine Delayed-Release | ingredient_set: 2412 | product_text_complete_set | 0.90 | internal | all ingredients resolved from “Duloxetine Delayed-Release Capsules, 20 mg,  , 60 capsules, ” |
| 1517 | trial | New trial in India: Cefepime-Zidebactam Versus Ceftazidime-Avibactam W | molecule: Avibactam | source_record | 0.95 | internal | trial NCT07885891 interventions |
| 1144 | nsq | NSQ: Clobetasol Propionate, Neomycin, Miconazole Nitrate & Chlorhexidi | molecule: Clobetasol Propionate | product_text_complete | 0.95 | internal | 'clobetasol propionate' in “Clobetasol Propionate, Neomycin, Miconazole Nitrate & Chlorhexidine Cream” |
| 1163 | nsq | NSQ: Telmisartan  & Amlodipine Tablets IP batch BPF251519 | ingredient_set: 653,6208 | product_text_complete_set | 0.90 | internal | all ingredients resolved from “Telmisartan  & Amlodipine Tablets IP” |
| 1559 | approval | SEC recommends biological approval: Semaglutide Tablets 1.5 mg, 4 mg a | molecule: Semaglutide | product_text_partial | 0.85 | internal | 'semaglutide' in “Semaglutide Tablets 1.5 mg, 4 mg and 9 mg (r-DNA origin)”; unexplained: r dna origin |
| 1131 | nsq | NSQ: Atorvastatin and Clopidogrel Capsules batch K2501777 | ingredient_set: 800,1760 | product_text_complete_set | 0.90 | internal | all ingredients resolved from “Atorvastatin and Clopidogrel Capsules” |
| 969 | approval | SEC recommends approval: Rabies Vaccine, Human I.P. (Freeze-Dried) Upd | molecule: Freeze | product_text_partial | 0.70 | internal | 'freeze' in “Rabies Vaccine, Human I.P. (Freeze-Dried) Update in India Prescribing Information [BIO/PostAppr/VAC/2026/45 |
| 749 | nsq | NSQ: Ciprofloxacin Tablets IP 250 mg (Ciprodac 250) batch CT24001 | molecule: Ciprofloxacin | product_text_partial | 0.85 | internal | 'ciprofloxacin' in “Ciprofloxacin Tablets IP 250 mg (Ciprodac 250)”; unexplained: ciprodac |
| 407 | recall | USFDA Class III recall — Macleods Pharmaceuticals Ltd: Levothyroxine S | ingredient_set: 3973 | product_text_complete_set | 0.90 | internal | all ingredients resolved from “Levothyroxine Sodium Tablets, USP 112 mcg (0.112mg), 1000 tablets,  , ” |
| 1673 | nsq | NSQ: Diphtheria,Tetanus,Pertu ssis( Whole cell) ,Hepatitis B (rDNA) &  | parent: Biological E | company_group | 1.00 | internal | company 3307's group |
| 1149 | nsq | NSQ: Baclofen Tablets IP 10 mg batch N2501643 | molecule: Baclofen | product_text_complete | 0.95 | internal | 'baclofen' in “Baclofen Tablets IP 10 mg” |
| 846 | approval | SEC recommends trial permission: Cefepime + Zidebactam — M/s. Wockhard | molecule: Cefepime | product_text_partial | 0.85 | internal | 'cefepime' in “Cefepime + Zidebactam”; unexplained: zidebactam |
| 1115 | approval | CDSCO approval (subsequent new drug): Ceftazidime-Avibactam Bulk Mixtu | molecule: Avibactam | payload_molecule_ids | 0.95 | internal | molecule ids resolved by the connector |
