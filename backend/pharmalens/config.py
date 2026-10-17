import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
load_dotenv(REPO_ROOT / ".env")

DATA_DIR = REPO_ROOT / "data"
SOURCES_DIR = DATA_DIR / "sources"
RAW_DIR = DATA_DIR / "raw"  # archived connector responses, one folder per connector
DB_PATH = Path(os.getenv("PHARMALENS_DB", DATA_DIR / "pharmalens.duckdb"))
# DuckDB spills to disk next to the data (never the system drive) and is capped so a big build cannot exhaust RAM
DUCKDB_TEMP = Path(os.getenv("PHARMALENS_DUCKDB_TEMP", DATA_DIR / "duckdb_tmp"))
DUCKDB_MEMORY = os.getenv("PHARMALENS_DUCKDB_MEMORY", "3GB")


def duckdb_settings(con):
    DUCKDB_TEMP.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory = '{DUCKDB_TEMP.as_posix()}'")
    con.execute(f"SET memory_limit = '{DUCKDB_MEMORY}'")
    con.execute("SET preserve_insertion_order = false")
if not DB_PATH.is_absolute():
    DB_PATH = REPO_ROOT / DB_PATH

KAGGLE_DIR = SOURCES_DIR / "kaggle"
MASTER_DIR = KAGGLE_DIR / "indian-medicine-master-dataset" / "Indian-Medicine-Dataset (1)" / "out_india"
ONEMG_2025_CSV = KAGGLE_DIR / "india-medicines-and-drug-info-dataset" / "India Medicines and Drug Info Dataset.csv"
LEGACY_DIR = SOURCES_DIR / "legacy"
SEED_DIR = Path(__file__).resolve().parent / "seed"

WEB_DIST = REPO_ROOT / "web" / "dist"

USER_AGENT = "PharmaLens/4.0 (+research; contact via repo)"
HTTP_TIMEOUT = 45.0

DRUGSETU_API_KEY = os.getenv("DRUGSETU_API_KEY", "")
OPENFDA_API_KEY = os.getenv("OPENFDA_API_KEY", "")

SCHEMA_VERSION = "4.0.0"
