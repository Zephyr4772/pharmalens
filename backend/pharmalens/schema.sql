-- PharmaLens v4 schema. Core catalog tables are rebuilt by pipeline/build_core.py;
-- live tables (events, reg_*, quotes, news, connector_runs, inventory_*) are
-- created IF NOT EXISTS and survive core rebuilds.

-- ---------------------------------------------------------------- core catalog
CREATE TABLE IF NOT EXISTS parents (
    id          INTEGER PRIMARY KEY,
    slug        VARCHAR UNIQUE,
    name        VARCHAR,
    ticker      VARCHAR,          -- NSE symbol, NULL if unlisted
    hq          VARCHAR,
    ownership   VARCHAR,          -- indian_listed | indian_private | mnc_subsidiary | ...
    notes       VARCHAR
);

CREATE TABLE IF NOT EXISTS companies (
    id              INTEGER PRIMARY KEY,
    slug            VARCHAR UNIQUE,
    name            VARCHAR,
    name_norm       VARCHAR,
    parent_id       INTEGER,      -- NULL = standalone
    product_count   INTEGER,
    active_count    INTEGER,
    molecule_count  INTEGER,
    median_mrp      DOUBLE,
    top_class       VARCHAR
);

CREATE TABLE IF NOT EXISTS molecules (
    id                INTEGER PRIMARY KEY,
    mkey              VARCHAR UNIQUE,
    name              VARCHAR,
    product_count     INTEGER,
    company_count     INTEGER,
    combo_count       INTEGER,
    therapeutic_class VARCHAR,
    action_class      VARCHAR,
    chemical_class    VARCHAR,
    nppa_ceiling      DOUBLE,
    is_nlem           BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS combos (
    id              INTEGER PRIMARY KEY,
    ckey            VARCHAR UNIQUE,  -- sorted molecule:strength list + '#' + form family
    mkey            VARCHAR,         -- sorted molecule list (strength-agnostic)
    label           VARCHAR,
    molecule_count  INTEGER,
    product_count   INTEGER,
    company_count   INTEGER,
    min_mrp         DOUBLE,
    median_mrp      DOUBLE,
    max_mrp         DOUBLE,
    therapeutic_class VARCHAR,
    is_banned       BOOLEAN DEFAULT FALSE,
    form_family     VARCHAR,         -- tablet | capsule | injection | oral liquid | topical | ...
    min_unit        DOUBLE,          -- per-unit price band (outliers below 15% of median excluded)
    median_unit     DOUBLE,
    max_unit        DOUBLE,
    banned_skus     INTEGER
);

CREATE TABLE IF NOT EXISTS products (
    id                INTEGER PRIMARY KEY,
    src_id            VARCHAR,       -- master dataset medicine_id
    name              VARCHAR,
    name_norm         VARCHAR,
    company_id        INTEGER,
    manufacturer_raw  VARCHAR,
    dosage_form       VARCHAR,
    pack_size         VARCHAR,
    pack_qty          DOUBLE,
    mrp               DOUBLE,        -- best known MRP (newest source wins)
    mrp_asof          VARCHAR,       -- '2025' | '2024' | '2022' | 'live:<date>'
    mrp_legacy        DOUBLE,        -- older catalog MRP, for change tracking
    unit_price        DOUBLE,        -- mrp / pack_qty
    composition       VARCHAR,
    combo_id          INTEGER,
    molecule_count    INTEGER,
    rx_required       BOOLEAN,
    is_discontinued   BOOLEAN,
    in_stock          BOOLEAN,       -- last seen purchasable on an e-pharmacy
    therapeutic_class VARCHAR,
    action_class      VARCHAR,
    chemical_class    VARCHAR,
    habit_forming     BOOLEAN,
    indication_group  VARCHAR,       -- retailer category (Diabetes, Hypertension, ...)
    schedule          VARCHAR,       -- H / H1 / X / OTC when known
    uses              VARCHAR,
    side_effects      VARCHAR,
    image_url         VARCHAR,
    source_count      INTEGER,
    sources           VARCHAR,
    first_seen        DATE,
    last_seen         DATE
);

CREATE TABLE IF NOT EXISTS product_molecules (
    product_id   INTEGER,
    molecule_id  INTEGER,
    strength     VARCHAR
);

CREATE TABLE IF NOT EXISTS interactions (
    product_id INTEGER,
    raw        VARCHAR
);

CREATE TABLE IF NOT EXISTS nppa_ceiling (
    id               INTEGER,
    molecule_id      INTEGER,
    molecule_name    VARCHAR,
    form_strength    VARCHAR,
    ceiling_price    DOUBLE,
    unit             VARCHAR,
    notification     VARCHAR,
    year             INTEGER,
    source           VARCHAR
);

CREATE TABLE IF NOT EXISTS build_meta (
    key   VARCHAR PRIMARY KEY,
    value VARCHAR
);

-- ---------------------------------------------------------------- live layer
CREATE SEQUENCE IF NOT EXISTS seq_events START 1;
CREATE TABLE IF NOT EXISTS events (
    id          BIGINT DEFAULT nextval('seq_events') PRIMARY KEY,
    ts          TIMESTAMP,         -- when it happened (source date) or detected
    detected_at TIMESTAMP,
    kind        VARCHAR,           -- nsq | spurious | ban | price_notification | approval | recall | launch | usfda | news | stock | shortage | gazette | tender
    severity    VARCHAR,           -- critical | high | medium | info
    title       VARCHAR,
    body        VARCHAR,
    source      VARCHAR,
    url         VARCHAR,
    entity_type VARCHAR,           -- product | molecule | combo | company | parent | null
    entity_id   INTEGER,
    dedupe_key  VARCHAR UNIQUE,
    payload     JSON
);

CREATE SEQUENCE IF NOT EXISTS seq_nsq START 1;
CREATE TABLE IF NOT EXISTS reg_nsq (
    id             BIGINT DEFAULT nextval('seq_nsq') PRIMARY KEY,
    alert_month    VARCHAR,        -- YYYY-MM of CDSCO list
    category       VARCHAR,        -- NSQ | SPURIOUS
    product_text   VARCHAR,
    batch_no       VARCHAR,
    mfg_date       VARCHAR,
    exp_date       VARCHAR,
    manufacturer   VARCHAR,
    reason         VARCHAR,
    drawn_by       VARCHAR,
    lab            VARCHAR,
    source_url     VARCHAR,
    company_id     INTEGER,
    molecule_ids   VARCHAR,        -- comma list of matched molecule ids
    dedupe_key     VARCHAR UNIQUE,
    fetched_at     TIMESTAMP
);

CREATE SEQUENCE IF NOT EXISTS seq_ban START 1;
CREATE TABLE IF NOT EXISTS reg_banned_fdc (
    id             BIGINT DEFAULT nextval('seq_ban') PRIMARY KEY,
    combo_text     VARCHAR,
    mkey           VARCHAR,        -- normalized sorted molecule keys
    notification   VARCHAR,
    notified_on    DATE,
    status         VARCHAR,        -- banned | restricted | stayed
    source_url     VARCHAR,
    dedupe_key     VARCHAR UNIQUE,
    fetched_at     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nppa_retail_prices (   -- official retail prices NPPA fixes for new drugs (DPCO 2013 para 5/15)
    key          VARCHAR PRIMARY KEY,  -- doc url | serial | marketer index
    notified_on  DATE,
    so_number    VARCHAR,              -- Gazette S.O. number, e.g. '4264(E)'
    kind         VARCHAR,              -- new_drug | without_prior_approval | revision
    title        VARCHAR,
    doc_url      VARCHAR,
    sl_no        VARCHAR,
    formulation  VARCHAR,
    strength     VARCHAR,
    unit         VARCHAR,
    manufacturer VARCHAR,
    marketer     VARCHAR,
    company_id   INTEGER,              -- the marketer, resolved to companies.id
    price        DOUBLE,               -- per unit, excluding GST
    molecule_ids VARCHAR,              -- sorted, comma-separated molecules.id
    fetched_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS brand_first_seen (   -- when a brand first appeared in a registry: launch / pipeline signal
    source       VARCHAR,              -- cdsco_84ab (CDSCO brand registry) | cdci (national drug terminology)
    key          VARCHAR,
    brand        VARCHAR,
    brand_norm   VARCHAR,
    firm         VARCHAR,
    generic      VARCHAR,
    license      VARCHAR,
    company_id   INTEGER,
    first_seen   DATE,
    baseline     BOOLEAN,              -- present when tracking began: existing, not new
    PRIMARY KEY (source, key)
);

CREATE TABLE IF NOT EXISTS mfr_prices (   -- manufacturers' statutory price lists (DPCO Form V / GST revision lists)
    key           VARCHAR PRIMARY KEY,  -- doc url | row number
    doc_url       VARCHAR,
    doc_title     VARCHAR,
    doc_host      VARCHAR,              -- company site or the e-pharmacy index that hosts the manufacturer's PDF
    company_label VARCHAR,              -- manufacturer as named on the document
    parent_id     INTEGER,              -- its corporate group (match scope)
    company_id    INTEGER,
    effective_on  DATE,
    code          VARCHAR,              -- manufacturer's SKU code, when listed
    product       VARCHAR,
    composition   VARCHAR,
    pack          VARCHAR,
    pack_qty      DOUBLE,
    gst           DOUBLE,
    ptr           DOUBLE,               -- price to retailer, excluding tax
    pts           DOUBLE,               -- price to stockist / distributor, excluding tax
    mrp_old       DOUBLE,
    mrp           DOUBLE,               -- maximum retail price incl. taxes, for the listed pack
    status        VARCHAR,              -- e.g. 'De-Cont' when the list marks it
    product_id    INTEGER,              -- matched catalog product
    match_name    VARCHAR,              -- its name_norm (rebuilds re-apply by name)
    match_kind    VARCHAR,              -- same_pack | scaled | name_only
    pack_mrp      DOUBLE,               -- MRP for the catalog product's pack
    fetched_at    TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fin_results (   -- quarterly results of listed pharma groups (NSE integrated filing), ₹ crore
    symbol         VARCHAR,
    parent_id      INTEGER,
    period_start   DATE,
    period_end     DATE,
    consolidated   BOOLEAN,
    audited        VARCHAR,
    revenue        DOUBLE,            -- revenue from operations
    other_income   DOUBLE,
    total_income   DOUBLE,
    total_expenses DOUBLE,
    employee_cost  DOUBLE,
    finance_costs  DOUBLE,
    depreciation   DOUBLE,
    pbt            DOUBLE,            -- profit before tax
    tax            DOUBLE,
    net_profit     DOUBLE,            -- total profit for the period
    profit_owners  DOUBLE,            -- attributable to owners of the parent
    eps            DOUBLE,            -- basic EPS, ₹
    filed_at       TIMESTAMP,
    source_url     VARCHAR,
    fetched_at     TIMESTAMP,
    PRIMARY KEY (symbol, period_start, period_end, consolidated)
);

CREATE TABLE IF NOT EXISTS results_calendar (   -- board meetings announced to NSE (results dates)
    symbol       VARCHAR,
    parent_id    INTEGER,
    meeting_date DATE,
    purpose      VARCHAR,
    description  VARCHAR,
    announced_at TIMESTAMP,
    PRIMARY KEY (symbol, meeting_date, purpose)
);

CREATE TABLE IF NOT EXISTS watchlist (   -- one watchlist per user (Tailscale login), shared by terminal, Specs and alerts
    owner     VARCHAR,
    key       VARCHAR,                   -- g:<group slug> | co:<company slug> | m:<molecule id> | c:<combo id> | p:<product id>
    label     VARCHAR,
    href      VARCHAR,
    added_at  TIMESTAMP,
    PRIMARY KEY (owner, key)
);

CREATE SEQUENCE IF NOT EXISTS seq_docs START 1;
CREATE TABLE IF NOT EXISTS reg_documents (   -- regulator notices/circulars/gazette/price orders
    id           BIGINT DEFAULT nextval('seq_docs') PRIMARY KEY,
    agency       VARCHAR,          -- CDSCO | NPPA | DoP | eGazette | MoHFW | PMBI | ...
    doc_type     VARCHAR,
    title        VARCHAR,
    published_on DATE,
    url          VARCHAR,
    dedupe_key   VARCHAR UNIQUE,
    fetched_at   TIMESTAMP
);

CREATE SEQUENCE IF NOT EXISTS seq_approvals START 1;
CREATE TABLE IF NOT EXISTS reg_approvals (
    id           BIGINT DEFAULT nextval('seq_approvals') PRIMARY KEY,
    agency       VARCHAR,
    drug_text    VARCHAR,
    indication   VARCHAR,
    approved_on  DATE,
    applicant    VARCHAR,
    approval_type VARCHAR,
    source_url   VARCHAR,
    molecule_ids VARCHAR,
    dedupe_key   VARCHAR UNIQUE,
    fetched_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jan_aushadhi (
    drug_code     VARCHAR PRIMARY KEY,
    name          VARCHAR,
    unit_size     VARCHAR,
    mrp           DOUBLE,
    group_name    VARCHAR,
    molecule_ids  VARCHAR,
    fetched_at    TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nlem (
    molecule_name VARCHAR,
    molecule_id   INTEGER,
    section       VARCHAR,
    level         VARCHAR,
    dosage        VARCHAR,
    edition       VARCHAR
);

CREATE TABLE IF NOT EXISTS usfda_actions (
    id           VARCHAR PRIMARY KEY,
    kind         VARCHAR,          -- warning_letter | import_alert | recall | 483
    firm         VARCHAR,
    country      VARCHAR,
    subject      VARCHAR,
    issued_on    DATE,
    url          VARCHAR,
    parent_id    INTEGER,
    fetched_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quotes (
    ticker       VARCHAR PRIMARY KEY,
    name         VARCHAR,
    price        DOUBLE,
    prev_close   DOUBLE,
    change_pct   DOUBLE,
    day_high     DOUBLE,
    day_low      DOUBLE,
    volume       DOUBLE,
    market_cap   DOUBLE,
    pe           DOUBLE,
    week52_high  DOUBLE,
    week52_low   DOUBLE,
    currency     VARCHAR,
    quoted_at    TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quote_history (
    ticker VARCHAR,
    d      DATE,
    close  DOUBLE,
    volume DOUBLE,
    PRIMARY KEY (ticker, d)
);

CREATE SEQUENCE IF NOT EXISTS seq_news START 1;
CREATE TABLE IF NOT EXISTS news (
    id           BIGINT DEFAULT nextval('seq_news') PRIMARY KEY,
    published_at TIMESTAMP,
    source       VARCHAR,
    title        VARCHAR,
    url          VARCHAR UNIQUE,
    summary      VARCHAR,
    topic        VARCHAR,          -- regulatory | pricing | approval | recall | deal | earnings | litigation | supply | policy | general
    parent_ids   VARCHAR,
    molecule_ids VARCHAR,
    fetched_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS price_observations (  -- every price we ever saw, for history
    product_id  INTEGER,
    observed_on DATE,
    mrp         DOUBLE,
    source      VARCHAR,
    PRIMARY KEY (product_id, observed_on, source)
);

CREATE TABLE IF NOT EXISTS shortages (
    id           VARCHAR PRIMARY KEY,
    region       VARCHAR,          -- US | IN
    molecule_text VARCHAR,
    company      VARCHAR,
    status       VARCHAR,
    reason       VARCHAR,
    category     VARCHAR,
    updated_on   DATE,
    source       VARCHAR,
    molecule_ids VARCHAR
);

CREATE SEQUENCE IF NOT EXISTS seq_runs START 1;
CREATE TABLE IF NOT EXISTS connector_runs (
    id          BIGINT DEFAULT nextval('seq_runs') PRIMARY KEY,
    connector   VARCHAR,
    started_at  TIMESTAMP,
    finished_at TIMESTAMP,
    status      VARCHAR,           -- ok | error | partial
    rows_seen   INTEGER,
    rows_new    INTEGER,
    events_new  INTEGER,
    message     VARCHAR
);

CREATE SEQUENCE IF NOT EXISTS seq_inv START 1;
CREATE TABLE IF NOT EXISTS inventory_items (
    id           BIGINT DEFAULT nextval('seq_inv') PRIMARY KEY,
    list_name    VARCHAR,
    raw_name     VARCHAR,
    batch_no     VARCHAR,
    qty          DOUBLE,
    expiry       DATE,
    product_id   INTEGER,
    match_score  DOUBLE,
    added_at     TIMESTAMP
);

-- DrugSetu (api.drugsetu.com): live product records, newest-first launch scanning + on-demand enrichment
CREATE TABLE IF NOT EXISTS drugsetu_products (
    product_id         VARCHAR PRIMARY KEY,
    name               VARCHAR,
    name_norm          VARCHAR,
    product_type       VARCHAR,
    composition        VARCHAR,
    marketing_company  VARCHAR,
    manufacturing_company VARCHAR,
    mrp                DOUBLE,
    packaging          VARCHAR,
    product_form       VARCHAR,
    therapeutic_class  VARCHAR,
    action_class       VARCHAR,
    chemical_class     VARCHAR,
    habit_forming      BOOLEAN,
    safety             JSON,          -- alcohol/pregnancy/breastfeeding/driving/kidney/liver {severity, description}
    raw                JSON,
    catalog_product_id INTEGER,
    first_seen         TIMESTAMP,
    fetched_at         TIMESTAMP
);
CREATE TABLE IF NOT EXISTS drugsetu_state (
    key   VARCHAR PRIMARY KEY,
    value VARCHAR
);

-- CDSCO Subject Expert Committee (SEC) agenda items: clinical-trial, marketing and BE permissions
CREATE SEQUENCE IF NOT EXISTS seq_sec START 1;
CREATE TABLE IF NOT EXISTS sec_items (
    id             BIGINT DEFAULT nextval('seq_sec') PRIMARY KEY,
    meeting_date   DATE,
    committee      VARCHAR,
    division       VARCHAR,       -- clinical_trial | new_drug | be | biological | medical_device | other
    file_no        VARCHAR,
    drug_text      VARCHAR,
    firm           VARCHAR,
    recommendation VARCHAR,
    outcome        VARCHAR,       -- recommended | not_recommended | deferred | noted
    molecule_ids   VARCHAR,
    company_id     INTEGER,
    parent_id      INTEGER,
    source_url     VARCHAR,
    dedupe_key     VARCHAR UNIQUE,
    fetched_at     TIMESTAMP
);

-- Clinical trials with Indian sites (ClinicalTrials.gov API v2; CTRI ids from secondary identifiers)
CREATE TABLE IF NOT EXISTS trials (
    nct_id        VARCHAR PRIMARY KEY,
    ctri_id       VARCHAR,
    title         VARCHAR,
    sponsor       VARCHAR,
    sponsor_class VARCHAR,
    phase         VARCHAR,
    status        VARCHAR,
    conditions    VARCHAR,
    interventions VARCHAR,
    start_date    VARCHAR,
    completion_date VARCHAR,
    india_sites   INTEGER,
    enrollment    INTEGER,
    last_update   DATE,
    molecule_ids  VARCHAR,
    parent_id     INTEGER,
    fetched_at    TIMESTAMP
);

-- Alert subscriptions: a watchlist and/or a shelf (inventory) list routed to channels
CREATE SEQUENCE IF NOT EXISTS seq_alert_sub START 1;
CREATE TABLE IF NOT EXISTS alert_subscriptions (
    id            BIGINT DEFAULT nextval('seq_alert_sub') PRIMARY KEY,
    name          VARCHAR,
    channels      JSON,          -- [{"type": "telegram", "chat_id": "..."}, {"type": "email", "to": "..."}, {"type": "webhook", "url": "..."}]
    kinds         VARCHAR,       -- comma list of event kinds; NULL = all
    min_severity  VARCHAR,       -- info | medium | high | critical
    watch         JSON,          -- [{"key": "m:123", "label": "Paracetamol"}, ...]
    shelf_csv     VARCHAR,       -- inventory list re-checked against new regulator data
    shelf_state   JSON,          -- last set of shelf flags, to alert only on new ones
    digest_hour   INTEGER,       -- local hour for a daily digest; NULL = instant only
    instant       BOOLEAN DEFAULT TRUE,
    active        BOOLEAN DEFAULT TRUE,
    last_event_id BIGINT DEFAULT 0,
    last_nsq_id   BIGINT DEFAULT 0,
    last_digest   DATE,
    created_at    TIMESTAMP
);
CREATE SEQUENCE IF NOT EXISTS seq_alert_msg START 1;
CREATE TABLE IF NOT EXISTS alert_messages (
    id          BIGINT DEFAULT nextval('seq_alert_msg') PRIMARY KEY,
    sub_id      BIGINT,
    event_id    BIGINT,
    kind        VARCHAR,          -- event | shelf | digest | test
    severity    VARCHAR,
    title       VARCHAR,
    body        VARCHAR,
    url         VARCHAR,
    reason      VARCHAR,          -- why it matched
    created_at  TIMESTAMP,
    read_at     TIMESTAMP,
    deliveries  JSON              -- [{"channel": "telegram", "status": "sent" | "error: ..."}]
);

-- Generic per-connector progress markers (months fetched, cursors, ...)
CREATE TABLE IF NOT EXISTS connector_state (
    key   VARCHAR PRIMARY KEY,
    value VARCHAR
);

-- CDSCO Rule 84AB brand-name registry
CREATE TABLE IF NOT EXISTS brand_registry (
    firm_name      VARCHAR,
    license_number VARCHAR,
    generic_name   VARCHAR,
    brand_name     VARCHAR,
    brand_norm     VARCHAR,
    company_id     INTEGER,
    fetched_at     TIMESTAMP
);

-- US FDA (openFDA bulk)
CREATE TABLE IF NOT EXISTS us_applications (
    application_number VARCHAR, sponsor VARCHAR, parent_id INTEGER, app_type VARCHAR, brands VARCHAR, ingredients VARCHAR,
    dosage_forms VARCHAR, marketing_status VARCHAR, first_approval DATE, last_action DATE, n_submissions INTEGER, molecule_ids VARCHAR
);
CREATE TABLE IF NOT EXISTS us_orange_book (
    application_number VARCHAR, product_number VARCHAR, brand VARCHAR, ingredients VARCHAR, strengths VARCHAR, dosage_form VARCHAR,
    route VARCHAR, app_type VARCHAR, rld BOOLEAN, marketing_status VARCHAR, approval_date DATE, applicant VARCHAR, parent_id INTEGER,
    molecule_ids VARCHAR
);
CREATE TABLE IF NOT EXISTS us_patents (
    application_number VARCHAR, product_number VARCHAR, kind VARCHAR, code VARCHAR, use_code VARCHAR, expires_on DATE,
    ingredients VARCHAR, molecule_ids VARCHAR
);
CREATE TABLE IF NOT EXISTS us_ndc (
    product_ndc VARCHAR, labeler VARCHAR, parent_id INTEGER, brand VARCHAR, generic VARCHAR, dosage_form VARCHAR,
    marketing_category VARCHAR, application_number VARCHAR, manufacturer VARCHAR, molecule_ids VARCHAR
);
CREATE TABLE IF NOT EXISTS who_pq (
    ref VARCHAR, inn VARCHAR, product_type VARCHAR, therapeutic_area VARCHAR, applicant VARCHAR, dosage_form VARCHAR,
    basis VARCHAR, prequalified_on DATE, parent_id INTEGER, molecule_ids VARCHAR
);
CREATE TABLE IF NOT EXISTS corp_announcements (
    seq_id VARCHAR PRIMARY KEY, symbol VARCHAR, parent_id INTEGER, announced_at TIMESTAMP, category VARCHAR, text VARCHAR,
    attachment VARCHAR, topic VARCHAR, fetched_at TIMESTAMP
);

-- Public procurement rate contracts (state medical corporations)
CREATE TABLE IF NOT EXISTS procurement_rates (
    buyer VARCHAR, state VARCHAR, item_code VARCHAR, item VARCHAR, kind VARCHAR, tender_no VARCHAR, supplier VARCHAR,
    company_id INTEGER, unit VARCHAR, rate DOUBLE, gst VARCHAR, level VARCHAR, valid_from DATE, valid_to DATE,
    molecule_ids VARCHAR, source_url VARCHAR, fetched_at TIMESTAMP,
    category VARCHAR, order_share DOUBLE        -- TNMSC: tender category and share of orders given to this supplier
);

-- Per-molecule enrichment (ChEMBL pharmacology, openFDA label sections, FAERS top reactions)
CREATE TABLE IF NOT EXISTS molecule_enrichment (
    molecule_id INTEGER PRIMARY KEY, chembl_id VARCHAR, atc JSON, max_phase DOUBLE, first_approval INTEGER,
    molecule_type VARCHAR, withdrawn BOOLEAN, black_box BOOLEAN, mechanisms JSON, indications JSON,
    faers_top JSON, faers_total INTEGER, us_label JSON, us_label_meta JSON, us_name VARCHAR, fetched_at TIMESTAMP,
    faers_co JSON,              -- drugs most often co-reported in the same FAERS reports (confounding context)
    faers_names JSON,           -- exact openFDA generic names counted as this molecule
    chembl_ambiguous JSON       -- why no ChEMBL compound was assigned (class name / several candidates)
);


-- Every catalog id ever issued (never dropped by a rebuild): keys keep their ids across builds, even when a build
-- is interrupted after dropping the core tables, and a retired id is never handed to a different entity
CREATE TABLE IF NOT EXISTS id_registry (
    kind VARCHAR,       -- molecule | company | combo | product
    key  VARCHAR,       -- mkey | name_norm | ckey | name_norm
    id   INTEGER,
    first_seen TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (kind, key)
);

-- State procurement agencies' firm blacklisting / debarment orders (mostly for NSQ batches)
CREATE TABLE IF NOT EXISTS firm_debarments (
    authority VARCHAR, state VARCHAR, firm VARCHAR, address VARCHAR, subject VARCHAR, drug_text VARCHAR, reason VARCHAR,
    order_no VARCHAR, ordered_on DATE, years DOUBLE, document_url VARCHAR, company_id INTEGER, parent_id INTEGER,
    molecule_ids VARCHAR, source_url VARCHAR, dedupe_key VARCHAR UNIQUE, fetched_at TIMESTAMP
);

-- Notified ceiling prices by year (NPPA): 2011/2015/2022 notifications from the master dataset + a yearly snapshot of
-- the official compendium, so price-control history accumulates
CREATE TABLE IF NOT EXISTS nppa_ceiling_history (
    year INTEGER, molecule_id INTEGER, molecule_name VARCHAR, form_strength VARCHAR, ceiling_price DOUBLE, unit VARCHAR,
    notification VARCHAR, source VARCHAR
);

-- India's Pharmacovigilance Programme (IPC) drug safety alerts since 2016
CREATE TABLE IF NOT EXISTS pvpi_alerts (
    sno INTEGER, issue_month DATE, drug_text VARCHAR, indication VARCHAR, reaction VARCHAR, molecule_ids VARCHAR,
    source_url VARCHAR, dedupe_key VARCHAR UNIQUE, fetched_at TIMESTAMP
);
