from .alerts_job import AlertsDispatch
from .cdci import Cdci
from .catalog_sync import NppaHistory, ParentSync
from .health import HealthWatch
from .pulse import Pulse
from .procurement_safety import FdaImportAlert6640, HmsclRates, PvpiAlerts, RmsclRates, TnmscRates, UpmsclDebarments, WhoAlerts
from .enrichment import MoleculeEnrichment
from .cdsco_portal import CdscoApprovalsDb, CdscoBrandRegistry, CdscoNsqPortal
from .cdsco import CdscoAlerts, CdscoBannedFdc, CdscoGazette, CdscoNsq, NsqMirror
from .global_reg import OpenFdaIndiaRecalls
from .international import EmaMedicines, NseFilings, OpenFdaBulk, WhoPrequal
from .gov_india import JanAushadhi, NppaOrders
from .nppa_prices import NppaRetailPrices
from .mfr_prices import MfrPriceLists
from .markets import NseFundamentals, NseHistory, NseQuotes
from .news import NewsArchive, PharmaNews
from .pipeline_feeds import CdscoApprovals, CdscoSec, ClinicalTrialsIndia, Nlem, NppaCompendium

REGISTRY = {c.name: c for c in [
    CdscoNsq, NsqMirror, CdscoBannedFdc, CdscoGazette, CdscoAlerts,
    NppaOrders, NppaRetailPrices, MfrPriceLists, JanAushadhi,
    NseQuotes, NseFundamentals, NseHistory,
    PharmaNews, NewsArchive, OpenFdaIndiaRecalls,
    CdscoApprovals, CdscoSec, Nlem, ClinicalTrialsIndia, NppaCompendium,
    CdscoNsqPortal, CdscoApprovalsDb, CdscoBrandRegistry,
    OpenFdaBulk, WhoPrequal, EmaMedicines, NseFilings, Cdci,
    ParentSync, NppaHistory, PvpiAlerts, RmsclRates, TnmscRates, HmsclRates, UpmsclDebarments, WhoAlerts, FdaImportAlert6640, MoleculeEnrichment,
    AlertsDispatch, HealthWatch, Pulse,
]}
