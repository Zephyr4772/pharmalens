# PharmaLens Database Coverage

- **Generated:** 2026-10-22T12:25:16+05:30
- **Database:** `D:\pharmacopy\pharmalens\data\pharmalens.duckdb`
- **File size:** 876.01 MB (918,564,864 bytes)
- **Inspection mode:** DuckDB opened read-only; no table contents or sample records exported.

> Exact row counts may take time on large tables or views. A failed count is recorded as an error rather than guessed.

## Summary

- **Tables/views discovered:** 52
- **Exact counts requested:** Yes

## Table inventory

| Catalog | Schema | Object | Type | Exact rows |
|---|---|---|---|---:|
| pharmalens | main | alert_messages | BASE TABLE | 0 |
| pharmalens | main | alert_subscriptions | BASE TABLE | 0 |
| pharmalens | main | brand_registry | BASE TABLE | 90,425 |
| pharmalens | main | build_meta | BASE TABLE | 12 |
| pharmalens | main | cdci_brand | BASE TABLE | 93,019 |
| pharmalens | main | cdci_doseform | BASE TABLE | 422 |
| pharmalens | main | cdci_generic | BASE TABLE | 10,174 |
| pharmalens | main | cdci_product | BASE TABLE | 71,503 |
| pharmalens | main | cdci_route | BASE TABLE | 160 |
| pharmalens | main | cdci_substance | BASE TABLE | 3,274 |
| pharmalens | main | cdci_supplier | BASE TABLE | 8,121 |
| pharmalens | main | combos | BASE TABLE | 40,179 |
| pharmalens | main | companies | BASE TABLE | 15,680 |
| pharmalens | main | connector_runs | BASE TABLE | 140 |
| pharmalens | main | connector_state | BASE TABLE | 205 |
| pharmalens | main | corp_announcements | BASE TABLE | 35,970 |
| pharmalens | main | drugsetu_products | BASE TABLE | 456 |
| pharmalens | main | drugsetu_state | BASE TABLE | 3 |
| pharmalens | main | ema_medicines | BASE TABLE | 2,754 |
| pharmalens | main | events | BASE TABLE | 1,287 |
| pharmalens | main | id_registry | BASE TABLE | 609,007 |
| pharmalens | main | interactions | BASE TABLE | 7,472 |
| pharmalens | main | inventory_items | BASE TABLE | 0 |
| pharmalens | main | jan_aushadhi | BASE TABLE | 2,439 |
| pharmalens | main | molecule_enrichment | BASE TABLE | 2,592 |
| pharmalens | main | molecules | BASE TABLE | 5,155 |
| pharmalens | main | news | BASE TABLE | 573 |
| pharmalens | main | nlem | BASE TABLE | 485 |
| pharmalens | main | nppa_ceiling | BASE TABLE | 908 |
| pharmalens | main | parents | BASE TABLE | 74 |
| pharmalens | main | price_observations | BASE TABLE | 651,160 |
| pharmalens | main | procurement_rates | BASE TABLE | 8,004 |
| pharmalens | main | product_info | BASE TABLE | 154,516 |
| pharmalens | main | product_molecules | BASE TABLE | 807,632 |
| pharmalens | main | products | BASE TABLE | 543,274 |
| pharmalens | main | quote_history | BASE TABLE | 10,305 |
| pharmalens | main | quotes | BASE TABLE | 44 |
| pharmalens | main | reg_approvals | BASE TABLE | 3,999 |
| pharmalens | main | reg_banned_fdc | BASE TABLE | 690 |
| pharmalens | main | reg_documents | BASE TABLE | 2,532 |
| pharmalens | main | reg_nsq | BASE TABLE | 6,681 |
| pharmalens | main | sec_items | BASE TABLE | 2,046 |
| pharmalens | main | segment_share | BASE TABLE | 671,223 |
| pharmalens | main | segment_stats | BASE TABLE | 29,778 |
| pharmalens | main | shortages | BASE TABLE | 3,400 |
| pharmalens | main | trials | BASE TABLE | 1,984 |
| pharmalens | main | us_applications | BASE TABLE | 29,390 |
| pharmalens | main | us_ndc | BASE TABLE | 138,319 |
| pharmalens | main | us_orange_book | BASE TABLE | 48,865 |
| pharmalens | main | us_patents | BASE TABLE | 19,963 |
| pharmalens | main | usfda_actions | BASE TABLE | 627 |
| pharmalens | main | who_pq | BASE TABLE | 655 |

## Column-level schema

### `main.alert_messages`

- **Object type:** BASE TABLE
- **Exact rows:** 0

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | BIGINT | NO | nextval('seq_alert_msg') |
| 2 | sub_id | BIGINT | YES |  |
| 3 | event_id | BIGINT | YES |  |
| 4 | kind | VARCHAR | YES |  |
| 5 | severity | VARCHAR | YES |  |
| 6 | title | VARCHAR | YES |  |
| 7 | body | VARCHAR | YES |  |
| 8 | url | VARCHAR | YES |  |
| 9 | reason | VARCHAR | YES |  |
| 10 | created_at | TIMESTAMP | YES |  |
| 11 | read_at | TIMESTAMP | YES |  |
| 12 | deliveries | JSON | YES |  |

### `main.alert_subscriptions`

- **Object type:** BASE TABLE
- **Exact rows:** 0

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | BIGINT | NO | nextval('seq_alert_sub') |
| 2 | name | VARCHAR | YES |  |
| 3 | channels | JSON | YES |  |
| 4 | kinds | VARCHAR | YES |  |
| 5 | min_severity | VARCHAR | YES |  |
| 6 | watch | JSON | YES |  |
| 7 | shelf_csv | VARCHAR | YES |  |
| 8 | shelf_state | JSON | YES |  |
| 9 | digest_hour | INTEGER | YES |  |
| 10 | instant | BOOLEAN | YES | CAST('t' AS BOOLEAN) |
| 11 | active | BOOLEAN | YES | CAST('t' AS BOOLEAN) |
| 12 | last_event_id | BIGINT | YES | 0 |
| 13 | last_nsq_id | BIGINT | YES | 0 |
| 14 | last_digest | DATE | YES |  |
| 15 | created_at | TIMESTAMP | YES |  |

### `main.brand_registry`

- **Object type:** BASE TABLE
- **Exact rows:** 90,425

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | firm_name | VARCHAR | YES |  |
| 2 | license_number | VARCHAR | YES |  |
| 3 | generic_name | VARCHAR | YES |  |
| 4 | brand_name | VARCHAR | YES |  |
| 5 | brand_norm | VARCHAR | YES |  |
| 6 | company_id | INTEGER | YES |  |
| 7 | fetched_at | TIMESTAMP | YES |  |

### `main.build_meta`

- **Object type:** BASE TABLE
- **Exact rows:** 12

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | key | VARCHAR | NO |  |
| 2 | value | VARCHAR | YES |  |

### `main.cdci_brand`

- **Object type:** BASE TABLE
- **Exact rows:** 93,019

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | identifier | VARCHAR | YES |  |
| 2 | brand_name | VARCHAR | YES |  |
| 3 | product_identifier | VARCHAR | YES |  |
| 4 | supplier_identifier | VARCHAR | YES |  |
| 5 | generic_identifier | VARCHAR | YES |  |
| 6 | license_number | INTEGER | YES |  |
| 7 | license_status | VARCHAR | YES |  |
| 8 | excipient | INTEGER | YES |  |
| 9 | last_updated_on | VARCHAR | YES |  |
| 10 | brand_short | VARCHAR | YES |  |

### `main.cdci_doseform`

- **Object type:** BASE TABLE
- **Exact rows:** 422

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | identifier | VARCHAR | YES |  |
| 2 | dose_form | VARCHAR | YES |  |

### `main.cdci_generic`

- **Object type:** BASE TABLE
- **Exact rows:** 10,174

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | identifier | VARCHAR | YES |  |
| 2 | generic_name | VARCHAR | YES |  |
| 3 | substance_identifier | VARCHAR | YES |  |
| 4 | route_of_administration | VARCHAR | YES |  |
| 5 | dose_form | VARCHAR | YES |  |
| 6 | therapeutic_role | VARCHAR | YES |  |
| 7 | indication | VARCHAR | YES |  |
| 8 | contra_indication | VARCHAR | YES |  |
| 9 | interaction_with_drugs | VARCHAR | YES |  |
| 10 | classification_of_drugs | VARCHAR | YES |  |
| 11 | source_regulatory | VARCHAR | YES |  |
| 12 | last_updated_on | VARCHAR | YES |  |

### `main.cdci_product`

- **Object type:** BASE TABLE
- **Exact rows:** 71,503

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | identifier | VARCHAR | YES |  |
| 2 | product_name | VARCHAR | YES |  |

### `main.cdci_route`

- **Object type:** BASE TABLE
- **Exact rows:** 160

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | identifier | VARCHAR | YES |  |
| 2 | routeofadministration | VARCHAR | YES |  |

### `main.cdci_substance`

- **Object type:** BASE TABLE
- **Exact rows:** 3,274

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | identifier | VARCHAR | YES |  |
| 2 | substance_name | VARCHAR | YES |  |
| 3 | cas_number | VARCHAR | YES |  |
| 4 | unii | VARCHAR | YES |  |
| 5 | substance_description | VARCHAR | YES |  |
| 6 | molecular_weight | VARCHAR | YES |  |
| 7 | toxicity | VARCHAR | YES |  |
| 8 | smile | VARCHAR | YES |  |
| 9 | inchi | VARCHAR | YES |  |
| 10 | iupac_name | VARCHAR | YES |  |
| 11 | molecular_formula | VARCHAR | YES |  |
| 12 | last_updated_on | VARCHAR | YES |  |
| 13 | molecule_id | DOUBLE | YES |  |

### `main.cdci_supplier`

- **Object type:** BASE TABLE
- **Exact rows:** 8,121

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | identifier | VARCHAR | YES |  |
| 2 | supplier_name | VARCHAR | YES |  |
| 3 | country | VARCHAR | YES |  |

### `main.combos`

- **Object type:** BASE TABLE
- **Exact rows:** 40,179

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | INTEGER | NO |  |
| 2 | ckey | VARCHAR | YES |  |
| 3 | mkey | VARCHAR | YES |  |
| 4 | label | VARCHAR | YES |  |
| 5 | molecule_count | INTEGER | YES |  |
| 6 | product_count | INTEGER | YES |  |
| 7 | company_count | INTEGER | YES |  |
| 8 | min_mrp | DOUBLE | YES |  |
| 9 | median_mrp | DOUBLE | YES |  |
| 10 | max_mrp | DOUBLE | YES |  |
| 11 | therapeutic_class | VARCHAR | YES |  |
| 12 | is_banned | BOOLEAN | YES | CAST('f' AS BOOLEAN) |
| 13 | form_family | VARCHAR | YES |  |
| 14 | min_unit | DOUBLE | YES |  |
| 15 | median_unit | DOUBLE | YES |  |
| 16 | max_unit | DOUBLE | YES |  |
| 17 | banned_skus | INTEGER | YES |  |

### `main.companies`

- **Object type:** BASE TABLE
- **Exact rows:** 15,680

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | INTEGER | NO |  |
| 2 | slug | VARCHAR | YES |  |
| 3 | name | VARCHAR | YES |  |
| 4 | name_norm | VARCHAR | YES |  |
| 5 | parent_id | INTEGER | YES |  |
| 6 | product_count | INTEGER | YES |  |
| 7 | active_count | INTEGER | YES |  |
| 8 | molecule_count | INTEGER | YES |  |
| 9 | median_mrp | DOUBLE | YES |  |
| 10 | top_class | VARCHAR | YES |  |

### `main.connector_runs`

- **Object type:** BASE TABLE
- **Exact rows:** 140

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | BIGINT | NO | nextval('seq_runs') |
| 2 | connector | VARCHAR | YES |  |
| 3 | started_at | TIMESTAMP | YES |  |
| 4 | finished_at | TIMESTAMP | YES |  |
| 5 | status | VARCHAR | YES |  |
| 6 | rows_seen | INTEGER | YES |  |
| 7 | rows_new | INTEGER | YES |  |
| 8 | events_new | INTEGER | YES |  |
| 9 | message | VARCHAR | YES |  |

### `main.connector_state`

- **Object type:** BASE TABLE
- **Exact rows:** 205

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | key | VARCHAR | NO |  |
| 2 | value | VARCHAR | YES |  |

### `main.corp_announcements`

- **Object type:** BASE TABLE
- **Exact rows:** 35,970

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | seq_id | VARCHAR | NO |  |
| 2 | symbol | VARCHAR | YES |  |
| 3 | parent_id | INTEGER | YES |  |
| 4 | announced_at | TIMESTAMP | YES |  |
| 5 | category | VARCHAR | YES |  |
| 6 | text | VARCHAR | YES |  |
| 7 | attachment | VARCHAR | YES |  |
| 8 | topic | VARCHAR | YES |  |
| 9 | fetched_at | TIMESTAMP | YES |  |

### `main.drugsetu_products`

- **Object type:** BASE TABLE
- **Exact rows:** 456

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | product_id | VARCHAR | NO |  |
| 2 | name | VARCHAR | YES |  |
| 3 | name_norm | VARCHAR | YES |  |
| 4 | product_type | VARCHAR | YES |  |
| 5 | composition | VARCHAR | YES |  |
| 6 | marketing_company | VARCHAR | YES |  |
| 7 | manufacturing_company | VARCHAR | YES |  |
| 8 | mrp | DOUBLE | YES |  |
| 9 | packaging | VARCHAR | YES |  |
| 10 | product_form | VARCHAR | YES |  |
| 11 | therapeutic_class | VARCHAR | YES |  |
| 12 | action_class | VARCHAR | YES |  |
| 13 | chemical_class | VARCHAR | YES |  |
| 14 | habit_forming | BOOLEAN | YES |  |
| 15 | safety | JSON | YES |  |
| 16 | raw | JSON | YES |  |
| 17 | catalog_product_id | INTEGER | YES |  |
| 18 | first_seen | TIMESTAMP | YES |  |
| 19 | fetched_at | TIMESTAMP | YES |  |

### `main.drugsetu_state`

- **Object type:** BASE TABLE
- **Exact rows:** 3

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | key | VARCHAR | NO |  |
| 2 | value | VARCHAR | YES |  |

### `main.ema_medicines`

- **Object type:** BASE TABLE
- **Exact rows:** 2,754

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | category | VARCHAR | YES |  |
| 2 | name_of_medicine | VARCHAR | YES |  |
| 3 | ema_product_number | VARCHAR | YES |  |
| 4 | medicine_status | VARCHAR | YES |  |
| 5 | opinion_status | VARCHAR | YES |  |
| 6 | latest_procedure_affecting_product_information | VARCHAR | YES |  |
| 7 | international_non_proprietary_name_inn_common_name | VARCHAR | YES |  |
| 8 | active_substance | VARCHAR | YES |  |
| 9 | therapeutic_area_mesh | VARCHAR | YES |  |
| 10 | species_veterinary | VARCHAR | YES |  |
| 11 | patient_safety | VARCHAR | YES |  |
| 12 | atc_code_human | VARCHAR | YES |  |
| 13 | atcvet_code_veterinary | VARCHAR | YES |  |
| 14 | pharmacotherapeutic_group_human | VARCHAR | YES |  |
| 15 | pharmacotherapeutic_group_veterinary | VARCHAR | YES |  |
| 16 | therapeutic_indication | VARCHAR | YES |  |
| 17 | accelerated_assessment | VARCHAR | YES |  |
| 18 | additional_monitoring | VARCHAR | YES |  |
| 19 | advanced_therapy | VARCHAR | YES |  |
| 20 | biosimilar | VARCHAR | YES |  |
| 21 | conditional_approval | VARCHAR | YES |  |
| 22 | exceptional_circumstances | VARCHAR | YES |  |
| 23 | generic | VARCHAR | YES |  |
| 24 | orphan_medicine | VARCHAR | YES |  |
| 25 | prime_priority_medicine | VARCHAR | YES |  |
| 26 | marketing_authorisation_developer_applicant_holder | VARCHAR | YES |  |
| 27 | european_commission_decision_date | VARCHAR | YES |  |
| 28 | start_of_rolling_review_date | VARCHAR | YES |  |
| 29 | start_of_evaluation_date | VARCHAR | YES |  |
| 30 | opinion_adopted_date | VARCHAR | YES |  |
| 31 | withdrawal_of_application_date | VARCHAR | YES |  |
| 32 | marketing_authorisation_date | VARCHAR | YES |  |
| 33 | refusal_of_marketing_authorisation_date | VARCHAR | YES |  |
| 34 | withdrawal_expiry_revocation_lapse_of_marketing_authorisation_date | VARCHAR | YES |  |
| 35 | suspension_of_marketing_authorisation_date | VARCHAR | YES |  |
| 36 | revision_number | DOUBLE | YES |  |
| 37 | first_published_date | VARCHAR | YES |  |
| 38 | last_updated_date | VARCHAR | YES |  |
| 39 | medicine_url | VARCHAR | YES |  |
| 40 | parent_id | DOUBLE | YES |  |
| 41 | molecule_ids | VARCHAR | YES |  |

### `main.events`

- **Object type:** BASE TABLE
- **Exact rows:** 1,287

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | BIGINT | NO | nextval('seq_events') |
| 2 | ts | TIMESTAMP | YES |  |
| 3 | detected_at | TIMESTAMP | YES |  |
| 4 | kind | VARCHAR | YES |  |
| 5 | severity | VARCHAR | YES |  |
| 6 | title | VARCHAR | YES |  |
| 7 | body | VARCHAR | YES |  |
| 8 | source | VARCHAR | YES |  |
| 9 | url | VARCHAR | YES |  |
| 10 | entity_type | VARCHAR | YES |  |
| 11 | entity_id | INTEGER | YES |  |
| 12 | dedupe_key | VARCHAR | YES |  |
| 13 | payload | JSON | YES |  |

### `main.id_registry`

- **Object type:** BASE TABLE
- **Exact rows:** 609,007

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | kind | VARCHAR | NO |  |
| 2 | key | VARCHAR | NO |  |
| 3 | id | INTEGER | YES |  |
| 4 | first_seen | TIMESTAMP | YES | current_timestamp |

### `main.interactions`

- **Object type:** BASE TABLE
- **Exact rows:** 7,472

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | product_id | INTEGER | YES |  |
| 2 | raw | VARCHAR | YES |  |

### `main.inventory_items`

- **Object type:** BASE TABLE
- **Exact rows:** 0

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | BIGINT | NO | nextval('seq_inv') |
| 2 | list_name | VARCHAR | YES |  |
| 3 | raw_name | VARCHAR | YES |  |
| 4 | batch_no | VARCHAR | YES |  |
| 5 | qty | DOUBLE | YES |  |
| 6 | expiry | DATE | YES |  |
| 7 | product_id | INTEGER | YES |  |
| 8 | match_score | DOUBLE | YES |  |
| 9 | added_at | TIMESTAMP | YES |  |

### `main.jan_aushadhi`

- **Object type:** BASE TABLE
- **Exact rows:** 2,439

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | drug_code | VARCHAR | NO |  |
| 2 | name | VARCHAR | YES |  |
| 3 | unit_size | VARCHAR | YES |  |
| 4 | mrp | DOUBLE | YES |  |
| 5 | group_name | VARCHAR | YES |  |
| 6 | molecule_ids | VARCHAR | YES |  |
| 7 | fetched_at | TIMESTAMP | YES |  |

### `main.molecule_enrichment`

- **Object type:** BASE TABLE
- **Exact rows:** 2,592

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | molecule_id | INTEGER | NO |  |
| 2 | chembl_id | VARCHAR | YES |  |
| 3 | atc | JSON | YES |  |
| 4 | max_phase | DOUBLE | YES |  |
| 5 | first_approval | INTEGER | YES |  |
| 6 | molecule_type | VARCHAR | YES |  |
| 7 | withdrawn | BOOLEAN | YES |  |
| 8 | black_box | BOOLEAN | YES |  |
| 9 | mechanisms | JSON | YES |  |
| 10 | indications | JSON | YES |  |
| 11 | faers_top | JSON | YES |  |
| 12 | faers_total | INTEGER | YES |  |
| 13 | us_label | JSON | YES |  |
| 14 | us_label_meta | JSON | YES |  |
| 15 | us_name | VARCHAR | YES |  |
| 16 | fetched_at | TIMESTAMP | YES |  |
| 17 | faers_co | JSON | YES |  |
| 18 | faers_names | JSON | YES |  |
| 19 | chembl_ambiguous | JSON | YES |  |

### `main.molecules`

- **Object type:** BASE TABLE
- **Exact rows:** 5,155

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | INTEGER | NO |  |
| 2 | mkey | VARCHAR | YES |  |
| 3 | name | VARCHAR | YES |  |
| 4 | product_count | INTEGER | YES |  |
| 5 | company_count | INTEGER | YES |  |
| 6 | combo_count | INTEGER | YES |  |
| 7 | therapeutic_class | VARCHAR | YES |  |
| 8 | action_class | VARCHAR | YES |  |
| 9 | chemical_class | VARCHAR | YES |  |
| 10 | nppa_ceiling | DOUBLE | YES |  |
| 11 | is_nlem | BOOLEAN | YES | CAST('f' AS BOOLEAN) |

### `main.news`

- **Object type:** BASE TABLE
- **Exact rows:** 573

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | BIGINT | NO | nextval('seq_news') |
| 2 | published_at | TIMESTAMP | YES |  |
| 3 | source | VARCHAR | YES |  |
| 4 | title | VARCHAR | YES |  |
| 5 | url | VARCHAR | YES |  |
| 6 | summary | VARCHAR | YES |  |
| 7 | topic | VARCHAR | YES |  |
| 8 | parent_ids | VARCHAR | YES |  |
| 9 | molecule_ids | VARCHAR | YES |  |
| 10 | fetched_at | TIMESTAMP | YES |  |

### `main.nlem`

- **Object type:** BASE TABLE
- **Exact rows:** 485

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | molecule_name | VARCHAR | YES |  |
| 2 | molecule_id | INTEGER | YES |  |
| 3 | section | VARCHAR | YES |  |
| 4 | level | VARCHAR | YES |  |
| 5 | dosage | VARCHAR | YES |  |
| 6 | edition | VARCHAR | YES |  |

### `main.nppa_ceiling`

- **Object type:** BASE TABLE
- **Exact rows:** 908

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | INTEGER | YES |  |
| 2 | molecule_id | INTEGER | YES |  |
| 3 | molecule_name | VARCHAR | YES |  |
| 4 | form_strength | VARCHAR | YES |  |
| 5 | ceiling_price | DOUBLE | YES |  |
| 6 | unit | VARCHAR | YES |  |
| 7 | notification | VARCHAR | YES |  |
| 8 | year | INTEGER | YES |  |
| 9 | source | VARCHAR | YES |  |

### `main.parents`

- **Object type:** BASE TABLE
- **Exact rows:** 74

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | INTEGER | NO |  |
| 2 | slug | VARCHAR | YES |  |
| 3 | name | VARCHAR | YES |  |
| 4 | ticker | VARCHAR | YES |  |
| 5 | hq | VARCHAR | YES |  |
| 6 | ownership | VARCHAR | YES |  |
| 7 | notes | VARCHAR | YES |  |

### `main.price_observations`

- **Object type:** BASE TABLE
- **Exact rows:** 651,160

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | product_id | INTEGER | NO |  |
| 2 | observed_on | DATE | NO |  |
| 3 | mrp | DOUBLE | YES |  |
| 4 | source | VARCHAR | NO |  |

### `main.procurement_rates`

- **Object type:** BASE TABLE
- **Exact rows:** 8,004

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | buyer | VARCHAR | YES |  |
| 2 | state | VARCHAR | YES |  |
| 3 | item_code | VARCHAR | YES |  |
| 4 | item | VARCHAR | YES |  |
| 5 | kind | VARCHAR | YES |  |
| 6 | tender_no | VARCHAR | YES |  |
| 7 | supplier | VARCHAR | YES |  |
| 8 | company_id | INTEGER | YES |  |
| 9 | unit | VARCHAR | YES |  |
| 10 | rate | DOUBLE | YES |  |
| 11 | gst | VARCHAR | YES |  |
| 12 | level | VARCHAR | YES |  |
| 13 | valid_from | DATE | YES |  |
| 14 | valid_to | DATE | YES |  |
| 15 | molecule_ids | VARCHAR | YES |  |
| 16 | source_url | VARCHAR | YES |  |
| 17 | fetched_at | TIMESTAMP | YES |  |
| 18 | category | VARCHAR | YES |  |
| 19 | order_share | DOUBLE | YES |  |

### `main.product_info`

- **Object type:** BASE TABLE
- **Exact rows:** 154,516

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | product_id | INTEGER | NO |  |
| 2 | introduction | VARCHAR | YES |  |
| 3 | benefits | JSON | YES |  |
| 4 | how_to_use | VARCHAR | YES |  |
| 5 | how_it_works | VARCHAR | YES |  |
| 6 | quick_tips | JSON | YES |  |
| 7 | side_effects | JSON | YES |  |
| 8 | safety | JSON | YES |  |
| 9 | source | VARCHAR | YES |  |

### `main.product_molecules`

- **Object type:** BASE TABLE
- **Exact rows:** 807,632

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | product_id | INTEGER | YES |  |
| 2 | molecule_id | INTEGER | YES |  |
| 3 | strength | VARCHAR | YES |  |

### `main.products`

- **Object type:** BASE TABLE
- **Exact rows:** 543,274

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | INTEGER | NO |  |
| 2 | src_id | VARCHAR | YES |  |
| 3 | name | VARCHAR | YES |  |
| 4 | name_norm | VARCHAR | YES |  |
| 5 | company_id | INTEGER | YES |  |
| 6 | manufacturer_raw | VARCHAR | YES |  |
| 7 | dosage_form | VARCHAR | YES |  |
| 8 | pack_size | VARCHAR | YES |  |
| 9 | pack_qty | DOUBLE | YES |  |
| 10 | mrp | DOUBLE | YES |  |
| 11 | mrp_asof | VARCHAR | YES |  |
| 12 | mrp_legacy | DOUBLE | YES |  |
| 13 | unit_price | DOUBLE | YES |  |
| 14 | composition | VARCHAR | YES |  |
| 15 | combo_id | INTEGER | YES |  |
| 16 | molecule_count | INTEGER | YES |  |
| 17 | rx_required | BOOLEAN | YES |  |
| 18 | is_discontinued | BOOLEAN | YES |  |
| 19 | in_stock | BOOLEAN | YES |  |
| 20 | therapeutic_class | VARCHAR | YES |  |
| 21 | action_class | VARCHAR | YES |  |
| 22 | chemical_class | VARCHAR | YES |  |
| 23 | habit_forming | BOOLEAN | YES |  |
| 24 | indication_group | VARCHAR | YES |  |
| 25 | schedule | VARCHAR | YES |  |
| 26 | uses | VARCHAR | YES |  |
| 27 | side_effects | VARCHAR | YES |  |
| 28 | image_url | VARCHAR | YES |  |
| 29 | source_count | INTEGER | YES |  |
| 30 | sources | VARCHAR | YES |  |
| 31 | first_seen | DATE | YES |  |
| 32 | last_seen | DATE | YES |  |
| 33 | ban_level | VARCHAR | YES |  |
| 34 | ban_id | BIGINT | YES |  |

### `main.quote_history`

- **Object type:** BASE TABLE
- **Exact rows:** 10,305

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | ticker | VARCHAR | NO |  |
| 2 | d | DATE | NO |  |
| 3 | close | DOUBLE | YES |  |
| 4 | volume | DOUBLE | YES |  |

### `main.quotes`

- **Object type:** BASE TABLE
- **Exact rows:** 44

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | ticker | VARCHAR | NO |  |
| 2 | name | VARCHAR | YES |  |
| 3 | price | DOUBLE | YES |  |
| 4 | prev_close | DOUBLE | YES |  |
| 5 | change_pct | DOUBLE | YES |  |
| 6 | day_high | DOUBLE | YES |  |
| 7 | day_low | DOUBLE | YES |  |
| 8 | volume | DOUBLE | YES |  |
| 9 | market_cap | DOUBLE | YES |  |
| 10 | pe | DOUBLE | YES |  |
| 11 | week52_high | DOUBLE | YES |  |
| 12 | week52_low | DOUBLE | YES |  |
| 13 | currency | VARCHAR | YES |  |
| 14 | quoted_at | TIMESTAMP | YES |  |

### `main.reg_approvals`

- **Object type:** BASE TABLE
- **Exact rows:** 3,999

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | BIGINT | NO | nextval('seq_approvals') |
| 2 | agency | VARCHAR | YES |  |
| 3 | drug_text | VARCHAR | YES |  |
| 4 | indication | VARCHAR | YES |  |
| 5 | approved_on | DATE | YES |  |
| 6 | applicant | VARCHAR | YES |  |
| 7 | approval_type | VARCHAR | YES |  |
| 8 | source_url | VARCHAR | YES |  |
| 9 | molecule_ids | VARCHAR | YES |  |
| 10 | dedupe_key | VARCHAR | YES |  |
| 11 | fetched_at | TIMESTAMP | YES |  |
| 12 | composition | VARCHAR | YES |  |
| 13 | dosage_form | VARCHAR | YES |  |
| 14 | sites | JSON | YES |  |
| 15 | division | VARCHAR | YES |  |
| 16 | applied_for | VARCHAR | YES |  |
| 17 | form_id | BIGINT | YES |  |

### `main.reg_banned_fdc`

- **Object type:** BASE TABLE
- **Exact rows:** 690

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | BIGINT | NO | nextval('seq_ban') |
| 2 | combo_text | VARCHAR | YES |  |
| 3 | mkey | VARCHAR | YES |  |
| 4 | notification | VARCHAR | YES |  |
| 5 | notified_on | DATE | YES |  |
| 6 | status | VARCHAR | YES |  |
| 7 | source_url | VARCHAR | YES |  |
| 8 | dedupe_key | VARCHAR | YES |  |
| 9 | fetched_at | TIMESTAMP | YES |  |

### `main.reg_documents`

- **Object type:** BASE TABLE
- **Exact rows:** 2,532

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | BIGINT | NO | nextval('seq_docs') |
| 2 | agency | VARCHAR | YES |  |
| 3 | doc_type | VARCHAR | YES |  |
| 4 | title | VARCHAR | YES |  |
| 5 | published_on | DATE | YES |  |
| 6 | url | VARCHAR | YES |  |
| 7 | dedupe_key | VARCHAR | YES |  |
| 8 | fetched_at | TIMESTAMP | YES |  |

### `main.reg_nsq`

- **Object type:** BASE TABLE
- **Exact rows:** 6,681

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | BIGINT | NO | nextval('seq_nsq') |
| 2 | alert_month | VARCHAR | YES |  |
| 3 | category | VARCHAR | YES |  |
| 4 | product_text | VARCHAR | YES |  |
| 5 | batch_no | VARCHAR | YES |  |
| 6 | mfg_date | VARCHAR | YES |  |
| 7 | exp_date | VARCHAR | YES |  |
| 8 | manufacturer | VARCHAR | YES |  |
| 9 | reason | VARCHAR | YES |  |
| 10 | drawn_by | VARCHAR | YES |  |
| 11 | lab | VARCHAR | YES |  |
| 12 | source_url | VARCHAR | YES |  |
| 13 | company_id | INTEGER | YES |  |
| 14 | molecule_ids | VARCHAR | YES |  |
| 15 | dedupe_key | VARCHAR | YES |  |
| 16 | fetched_at | TIMESTAMP | YES |  |

### `main.sec_items`

- **Object type:** BASE TABLE
- **Exact rows:** 2,046

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | BIGINT | NO | nextval('seq_sec') |
| 2 | meeting_date | DATE | YES |  |
| 3 | committee | VARCHAR | YES |  |
| 4 | division | VARCHAR | YES |  |
| 5 | file_no | VARCHAR | YES |  |
| 6 | drug_text | VARCHAR | YES |  |
| 7 | firm | VARCHAR | YES |  |
| 8 | recommendation | VARCHAR | YES |  |
| 9 | outcome | VARCHAR | YES |  |
| 10 | molecule_ids | VARCHAR | YES |  |
| 11 | company_id | INTEGER | YES |  |
| 12 | parent_id | INTEGER | YES |  |
| 13 | source_url | VARCHAR | YES |  |
| 14 | dedupe_key | VARCHAR | YES |  |
| 15 | fetched_at | TIMESTAMP | YES |  |

### `main.segment_share`

- **Object type:** BASE TABLE
- **Exact rows:** 671,223

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | segment_type | VARCHAR | YES |  |
| 2 | segment | VARCHAR | YES |  |
| 3 | owner_type | VARCHAR | YES |  |
| 4 | owner_id | INTEGER | YES |  |
| 5 | skus | HUGEINT | YES |  |
| 6 | w | DOUBLE | YES |  |
| 7 | value_share | DOUBLE | YES |  |
| 8 | breadth_share | DOUBLE | YES |  |
| 9 | rank | BIGINT | YES |  |

### `main.segment_stats`

- **Object type:** BASE TABLE
- **Exact rows:** 29,778

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | segment_type | VARCHAR | YES |  |
| 2 | segment | VARCHAR | YES |  |
| 3 | owners | BIGINT | YES |  |
| 4 | skus | HUGEINT | YES |  |
| 5 | hhi | DOUBLE | YES |  |
| 6 | leader_share | DOUBLE | YES |  |
| 7 | leader | VARCHAR | YES |  |

### `main.shortages`

- **Object type:** BASE TABLE
- **Exact rows:** 3,400

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | VARCHAR | NO |  |
| 2 | region | VARCHAR | YES |  |
| 3 | molecule_text | VARCHAR | YES |  |
| 4 | company | VARCHAR | YES |  |
| 5 | status | VARCHAR | YES |  |
| 6 | reason | VARCHAR | YES |  |
| 7 | category | VARCHAR | YES |  |
| 8 | updated_on | DATE | YES |  |
| 9 | source | VARCHAR | YES |  |
| 10 | molecule_ids | VARCHAR | YES |  |

### `main.trials`

- **Object type:** BASE TABLE
- **Exact rows:** 1,984

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | nct_id | VARCHAR | NO |  |
| 2 | ctri_id | VARCHAR | YES |  |
| 3 | title | VARCHAR | YES |  |
| 4 | sponsor | VARCHAR | YES |  |
| 5 | sponsor_class | VARCHAR | YES |  |
| 6 | phase | VARCHAR | YES |  |
| 7 | status | VARCHAR | YES |  |
| 8 | conditions | VARCHAR | YES |  |
| 9 | interventions | VARCHAR | YES |  |
| 10 | start_date | VARCHAR | YES |  |
| 11 | completion_date | VARCHAR | YES |  |
| 12 | india_sites | INTEGER | YES |  |
| 13 | enrollment | INTEGER | YES |  |
| 14 | last_update | DATE | YES |  |
| 15 | molecule_ids | VARCHAR | YES |  |
| 16 | parent_id | INTEGER | YES |  |
| 17 | fetched_at | TIMESTAMP | YES |  |

### `main.us_applications`

- **Object type:** BASE TABLE
- **Exact rows:** 29,390

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | application_number | VARCHAR | YES |  |
| 2 | sponsor | VARCHAR | YES |  |
| 3 | parent_id | INTEGER | YES |  |
| 4 | app_type | VARCHAR | YES |  |
| 5 | brands | VARCHAR | YES |  |
| 6 | ingredients | VARCHAR | YES |  |
| 7 | dosage_forms | VARCHAR | YES |  |
| 8 | marketing_status | VARCHAR | YES |  |
| 9 | first_approval | DATE | YES |  |
| 10 | last_action | DATE | YES |  |
| 11 | n_submissions | INTEGER | YES |  |
| 12 | molecule_ids | VARCHAR | YES |  |

### `main.us_ndc`

- **Object type:** BASE TABLE
- **Exact rows:** 138,319

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | product_ndc | VARCHAR | YES |  |
| 2 | labeler | VARCHAR | YES |  |
| 3 | parent_id | INTEGER | YES |  |
| 4 | brand | VARCHAR | YES |  |
| 5 | generic | VARCHAR | YES |  |
| 6 | dosage_form | VARCHAR | YES |  |
| 7 | marketing_category | VARCHAR | YES |  |
| 8 | application_number | VARCHAR | YES |  |
| 9 | manufacturer | VARCHAR | YES |  |
| 10 | molecule_ids | VARCHAR | YES |  |

### `main.us_orange_book`

- **Object type:** BASE TABLE
- **Exact rows:** 48,865

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | application_number | VARCHAR | YES |  |
| 2 | product_number | VARCHAR | YES |  |
| 3 | brand | VARCHAR | YES |  |
| 4 | ingredients | VARCHAR | YES |  |
| 5 | strengths | VARCHAR | YES |  |
| 6 | dosage_form | VARCHAR | YES |  |
| 7 | route | VARCHAR | YES |  |
| 8 | app_type | VARCHAR | YES |  |
| 9 | rld | BOOLEAN | YES |  |
| 10 | marketing_status | VARCHAR | YES |  |
| 11 | approval_date | DATE | YES |  |
| 12 | applicant | VARCHAR | YES |  |
| 13 | parent_id | INTEGER | YES |  |
| 14 | molecule_ids | VARCHAR | YES |  |

### `main.us_patents`

- **Object type:** BASE TABLE
- **Exact rows:** 19,963

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | application_number | VARCHAR | YES |  |
| 2 | product_number | VARCHAR | YES |  |
| 3 | kind | VARCHAR | YES |  |
| 4 | code | VARCHAR | YES |  |
| 5 | use_code | VARCHAR | YES |  |
| 6 | expires_on | DATE | YES |  |
| 7 | ingredients | VARCHAR | YES |  |
| 8 | molecule_ids | VARCHAR | YES |  |

### `main.usfda_actions`

- **Object type:** BASE TABLE
- **Exact rows:** 627

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | id | VARCHAR | NO |  |
| 2 | kind | VARCHAR | YES |  |
| 3 | firm | VARCHAR | YES |  |
| 4 | country | VARCHAR | YES |  |
| 5 | subject | VARCHAR | YES |  |
| 6 | issued_on | DATE | YES |  |
| 7 | url | VARCHAR | YES |  |
| 8 | parent_id | INTEGER | YES |  |
| 9 | fetched_at | TIMESTAMP | YES |  |

### `main.who_pq`

- **Object type:** BASE TABLE
- **Exact rows:** 655

| Ordinal | Column | Data type | Nullable | Default |
|---:|---|---|---|---|
| 1 | ref | VARCHAR | YES |  |
| 2 | inn | VARCHAR | YES |  |
| 3 | product_type | VARCHAR | YES |  |
| 4 | therapeutic_area | VARCHAR | YES |  |
| 5 | applicant | VARCHAR | YES |  |
| 6 | dosage_form | VARCHAR | YES |  |
| 7 | basis | VARCHAR | YES |  |
| 8 | prequalified_on | DATE | YES |  |
| 9 | parent_id | INTEGER | YES |  |
| 10 | molecule_ids | VARCHAR | YES |  |

## Temporal coverage (typed date/time columns)

Only columns typed as DATE/TIME/TIMESTAMP and with date-like names are checked. The report contains extrema only, not individual records.

| Schema | Object | Column | Type | Minimum | Maximum |
|---|---|---|---|---|---|
| main | alert_messages | created_at | TIMESTAMP |  |  |
| main | alert_subscriptions | created_at | TIMESTAMP |  |  |
| main | news | published_at | TIMESTAMP | 2026-10-02 16:01:15 | 2026-10-17 20:44:48 |
| main | reg_documents | published_on | DATE | 1989-06-17 | 2026-10-14 |
| main | sec_items | meeting_date | DATE | 2025-04-23 | 2026-09-29 |
| main | shortages | updated_on | DATE | 2023-04-28 | 2026-10-15 |
| main | trials | last_update | DATE | 2023-10-16 | 2026-10-14 |
| main | us_orange_book | approval_date | DATE | 1982-01-04 | 2026-10-07 |

## Notes and limitations

- Counts are exact when shown as a number; `ERROR` means DuckDB could not complete that count.
- Views may be expensive to count because they can execute their underlying query.
- This report does not inspect data quality, semantic correctness, source freshness, API success, or join completeness.
- Date extrema are reported only for typed date/time columns with date-like names. Dates stored as text are intentionally not parsed automatically.
- No row samples, credentials, API keys, or source record contents are exported.
- Review this report before sharing it publicly; table and column names can reveal implementation details even though no row values are included.
