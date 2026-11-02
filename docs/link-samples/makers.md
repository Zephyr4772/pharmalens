# Link sample: maker entity (plant stage 1)

15 NSQ batch -> maker, 10 US FDA -> maker, 10 maker -> company/group, 15 brand registration -> SKU (contract map), random.

| record | → entity | method | conf | licence | evidence |
|---|---|---|---|---|---|
| reg_nsq: `12817` | maker: mk:mascot health series | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "Mascot Health Series Pvt. Ltd., ' Plot No. 79, 80, Sector-6A, IIE, Sidcul, Haridwar-249403" -> firm key mascot health series |
| reg_nsq: `9903` | maker: mk:overseas healthcare | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "Overseas Healthcare Pvt. Ltd, 335Km, Milestone, National Highway No.1 P.O, Box No.25, Phillaur-144410 (Pb)" -> firm key overseas healthcare |
| reg_nsq: `7663` | maker: mk:tanmed pharma i | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "Tanmed Pharma (I) Pvt Ltd, No.1/429, Multi Industrial Nagar, Gerugambakkam, Chennai-600128" -> firm key tanmed pharma i |
| reg_nsq: `8450` | maker: mk:pushkar pharma | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "M/s. Pushkar Pharma, Kheri, Kala-Amb-173030 (H.P.)" -> firm key pushkar pharma |
| reg_nsq: `5657` | maker: mk:modern labs | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "M/s. Modern Laboratories, 45-47, Sector D-2, Sanwer Road, Indore, Madhya Pradesh - 452015, India" -> firm key modern labs |
| reg_nsq: `13261` | maker: mk:ornate pharma | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "M/s. Ornate Pharma Pvt. Ltd., 2, G.V.M.S.A.V Ltd., Odhav, Ahmedabad 382 410, Gujrat, India" -> firm key ornate pharma |
| reg_nsq: `9531` | maker: mk:prochem pharma | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "Prochem Pharmaceuticals Pvt. Ltd, 140-141, Makkanpur, Bhagwanpur, Roorkee, Dist.Haridwar(UK)-247661" -> firm key prochem pharma |
| reg_nsq: `9563` | maker: mk:candour pharma | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "Candour Pharmaceuticals,Vill. Ogli, Suketi Road, Kala Amb, Distt. Sirmour (HP)-173030" -> firm key candour pharma |
| reg_nsq: `13091` | maker: mk:repacked by kerala state drugs pharma | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "Repacked by :- Kerala State Drugs & Pharmaceuticals Ltd, Kalavoor.P.O, Alappuzha" -> firm key repacked by kerala state drugs pharma |
| reg_nsq: `8934` | maker: mk:apple formulations | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "Apple Formulations Pvt, Ltd, Plot No.208, Kishanpur, Roorkee-247667 (U.K)" -> firm key apple formulations |
| reg_nsq: `12559` | maker: mk:vance health pharma | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "Vance & Health Pharmaceuticals Pvt. Ltd., Khasra No. 410, Karondi, Roorkee-247 667, Uttarakhand" -> firm key vance health pharma |
| reg_nsq: `12652` | maker: mk:shell eastern chemicals s | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "Shell Eastern Chemicals (S), The Metropolis Tower 1, 9 North Buona Vista Drive #07 01, Singapore 138588" -> firm key shell eastern chemicals s |
| reg_nsq: `7301` | maker: mk:agron remedies | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "Agron Remedies Pvt Ltd Sarverkhera Moradabad Road Kashipur 244 713 (Uttarakhand)" -> firm key agron remedies |
| reg_nsq: `8735` | maker: mk:ossiske lifesciences | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "Ossiske Life Science Pvt Ltd. F-18, IGC, Mansa Road Bhatinda" -> firm key ossiske lifesciences |
| reg_nsq: `8656` | maker: mk:nest healthcare | firm_key:batch_manufacturer | 0.90 | permission | batch_manufacturer: "M/s. Nest Healthcare Private Limited. , (A WHO-GMP Certified Company) Plot No. 300 G.I.D.C., Odhav Ahmedabad- 382415  ( " -> firm key nest healthcare |
| usfda_actions: `ia6640-gemini packaging ltd 12071 jacobs` | maker: mk:gemini packaging | firm_key:us_fda_firm | 0.90 | open | us_fda_firm: "Gemini Packaging Ltd." -> firm key gemini packaging |
| usfda_actions: `ia6640-almon healthcare private limited ` | maker: mk:almon healthcare | firm_key:us_fda_firm | 0.90 | open | us_fda_firm: "Almon Healthcare Private Limited" -> firm key almon healthcare |
| usfda_actions: `ia6640-shanwei honghui daily appliance c` | maker: mk:shanwei honghui daily appliance | firm_key:us_fda_firm | 0.90 | open | us_fda_firm: "Shanwei Honghui Daily Appliance Co., Ltd." -> firm key shanwei honghui daily appliance |
| usfda_actions: `recall-D-0426-2025` | maker: mk:kenil healthcare | firm_key:us_fda_firm | 0.90 | open | us_fda_firm: "KENIL HEALTHCARE PRIVATE LIMITED" -> firm key kenil healthcare |
| usfda_actions: `recall-D-0438-2025` | maker: mk:kenil healthcare | firm_key:us_fda_firm | 0.90 | open | us_fda_firm: "KENIL HEALTHCARE PRIVATE LIMITED" -> firm key kenil healthcare |
| usfda_actions: `ia6640-zhejiang gaorong cosmetic co ltd ` | maker: mk:zhejiang gaorong cosmetic | firm_key:us_fda_firm | 0.90 | open | us_fda_firm: "Zhejiang Gaorong Cosmetic Co., Ltd" -> firm key zhejiang gaorong cosmetic |
| usfda_actions: `recall-D-0214-2025` | maker: mk:fdc | firm_key:us_fda_firm | 0.90 | open | us_fda_firm: "FDC Limited" -> firm key fdc |
| usfda_actions: `ia6640-tianjin boai pharmaceutical co lt` | maker: mk:tianjin boai pharma | firm_key:us_fda_firm | 0.90 | open | us_fda_firm: "Tianjin Boai Pharmaceutical Co. Ltd" -> firm key tianjin boai pharma |
| usfda_actions: `ia6640-jiangxi iris chemical co ltd no 5` | maker: mk:jiangxi iris chemical | firm_key:us_fda_firm | 0.90 | open | us_fda_firm: "Jiangxi Iris Chemical Co., Ltd" -> firm key jiangxi iris chemical |
| usfda_actions: `recall-D-0761-2026` | maker: mk:shoolin pharma chem | firm_key:us_fda_firm | 0.90 | open | us_fda_firm: "Shoolin Pharma Chem LLP" -> firm key shoolin pharma chem |
| makers: `mk:ambitus lifesciences` | auto_group: auto:c3966 | via_company | 0.90 | internal | maker Ambitus Life Sciences -> auto-group auto:c3966 |
| makers: `mk:med revive biotec` | company: 5331 | equal_firm_key | 0.90 | internal | maker Med Revive Biotec Llp = catalog company 5331 (equal_firm_key) |
| makers: `mk:mega biosciences` | company: 11804 | equal_firm_key | 0.90 | internal | maker Mega Biosciences Private Limited = catalog company 11804 (equal_firm_key) |
| makers: `mk:snyder healthcare` | company: 2324 | equal_firm_key | 0.90 | internal | maker Snyder Healthcare Private Limited = catalog company 2324 (equal_firm_key) |
| makers: `mk:pristine pearl pharma` | company: 2472 | equal_firm_key | 0.90 | internal | maker Pristine Pearl Pharma Private Limited = catalog company 2472 (equal_firm_key) |
| makers: `mk:aceso pharma` | company: 1380 | equal_firm_key | 0.90 | internal | maker Aceso Pharma Private Limited = catalog company 1380 (equal_firm_key) |
| makers: `mk:trans pharma` | auto_group: auto:c3256 | via_company | 0.90 | internal | maker Trans Pharmaceuticals Private Limited -> auto-group auto:c3256 |
| makers: `mk:angeas healthcare` | company: 4665 | equal_firm_key | 0.90 | internal | maker Angeas Health Care Limited = catalog company 4665 (equal_firm_key) |
| makers: `mk:medstry biotech` | auto_group: auto:c10812 | via_company | 0.90 | internal | maker Medstry Biotech Private Limited -> auto-group auto:c10812 |
| makers: `mk:x med medisciences` | auto_group: auto:c12376 | via_company | 0.90 | internal | maker X Med Medisciences -> auto-group auto:c12376 |
| brand_registry: `M/575/2011|periset 8|Ipca Laboratories L` | product: 377734 | brand_two_words_and_set | 0.85 | internal | registered brand "Periset 8" (Ipca Laboratories Limited, Sikkim) = SKU "Periset 8 Tablet", same ingredients |
| brand_registry: `21/UA/2006|quel sr 300|Ipca Laboratories` | product: 397521 | brand_two_words_and_set | 0.85 | internal | registered brand "Quel SR 300" (Ipca Laboratories Limited) = SKU "Quel Sr 100Mg Tablet", same ingredients |
| brand_registry: `M/563/2010|olmetor am 40|Torrent Pharmac` | product: 350538 | brand_two_words_and_set | 0.85 | internal | registered brand "OLMETOR AM 40" (Torrent Pharmaceuticals Limited) = SKU "Olmetor AM 40 Tablet", same ingredients |
| brand_registry: `MNB08680|glinix mp1|SAPHNIX LIFE SCIENCE` | product: 210166 | brand_two_words_and_set | 0.85 | internal | registered brand "GLINIX-MP1" (SAPHNIX LIFE SCIENCES) = SKU "Glinix-MP1 Tablet", same ingredients |
| brand_registry: `M/563/2010|amazeo od 400|Torrent Pharmac` | product: 28517 | brand_two_words_and_set | 0.85 | internal | registered brand "AMAZEO OD 400" (Torrent Pharmaceuticals Limited) = SKU "Amazeo Od 100Mg Tablet 10 S", same ingredients |
| brand_registry: `164/MN/AP/95/F/R|vildanat m 850|NATCO PH` | product: 509634 | brand_two_words_and_set | 0.85 | internal | registered brand "VILDANAT M 850" (NATCO PHARMA LIMITED) = SKU "Vildanat M 500 Sr Tablet", same ingredients |
| brand_registry: `M/645/2014|ropark 0 25|Sun Pharma Labora` | product: 422453 | brand_two_words_and_set | 0.85 | internal | registered brand "Ropark 0.25" (Sun Pharma Laboratories Limited) = SKU "Ropark 0.5 Tablet", same ingredients |
| brand_registry: `MB/05/106|traxol o|Alkem Laboratories Li` | product: 487828 | brand_two_words_and_set | 0.85 | internal | registered brand "Traxol O" (Alkem Laboratories Limited) = SKU "Traxol O 200mg Tablet", same ingredients |
| brand_registry: `52|frusenex 100|Geno Pharmaceuticals Pvt` | product: 194717 | brand_two_words_and_set | 0.85 | internal | registered brand "FRUSENEX - 100" (Geno Pharmaceuticals Pvt. Ltd.) = SKU "Frusenex 100 Tablet", same ingredients |
| brand_registry: `G/28/623|tear drops|Sun Pharmaceutical M` | product: 467220 | brand_two_words_and_set | 0.85 | internal | registered brand "TEAR DROPS" (Sun Pharmaceutical Medicare Limited) = SKU "Tear Drops Gel 10Ml", same ingredients |
| brand_registry: `JK/01/58|zeptol 200|Sun PharmaLaboratori` | product: 533323 | brand_two_words_and_set | 0.85 | internal | registered brand "Zeptol 200" (Sun PharmaLaboratories Limited) = SKU "Zeptol 200 Tablet", same ingredients |
| brand_registry: `MNB/05/259,|febrex plus tablets|Indoco R` | product: 178308 | brand_two_words_and_set | 0.85 | internal | registered brand "Febrex Plus Tablets" (Indoco Remedies Limited) = SKU "Febrex Plus Oral Drops", same ingredients |
| brand_registry: `313|crixan 250|Sun Pharmaceutical Indust` | product: 114294 | brand_two_words_and_set | 0.85 | internal | registered brand "CRIXAN 250" (Sun Pharmaceutical Industreies Ltd) = SKU "Crixan 250 Tablet", same ingredients |
| brand_registry: `247|glycomet gp 0 5 forte|The Madras Pha` | product: 213924 | brand_two_words_and_set | 0.85 | internal | registered brand "GLYCOMET GP 0.5 FORTE" (The Madras Pharmaceuticals) = SKU "Glycomet-GP 1/850 Tablet SR", same ingredients |
| brand_registry: `M/517/09|olimelt 15|Intas Pharmaceutical` | product: 349640 | brand_two_words_and_set | 0.85 | internal | registered brand "OLIMELT?15" (Intas Pharmaceuticals Limited) = SKU "Olimelt 15 Tablet", same ingredients |
