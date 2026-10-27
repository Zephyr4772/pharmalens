from .alerts_job import AlertsDispatch
from .cdci import Cdci
from .procurement_safety import FdaImportAlert6640, HmsclRates, RmsclRates, TnmscRates, UpmsclDebarments, WhoAlerts
from .enrichment import MoleculeEnrichment
from .cdsco_portal import CdscoApprovalsDb, CdscoBrandRegistry, CdscoNsqPortal
from .cdsco import CdscoAlerts, CdscoBannedFdc, CdscoGazette, CdscoNsq, NsqMirror
from .drugsetu import DrugSetuHarvest, DrugSetuLaunches
from .global_reg import OpenFdaIndiaRecalls
from .international import EmaMedicines, NseFilings, OpenFdaBulk, WhoPrequal
from .gov_india import JanAushadhi, NppaOrders
from .markets import NseFundamentals, NseHistory, NseQuotes
from .news import PharmaNews
from .pipeline_feeds import CdscoApprovals, CdscoSec, ClinicalTrialsIndia, Nlem, NppaCompendium

REGISTRY = {c.name: c for c in [
    CdscoNsq, NsqMirror, CdscoBannedFdc, CdscoGazette, CdscoAlerts,
    NppaOrders, JanAushadhi,
    NseQuotes, NseFundamentals, NseHistory,
    PharmaNews, OpenFdaIndiaRecalls, DrugSetuLaunches, DrugSetuHarvest,
    CdscoApprovals, CdscoSec, Nlem, ClinicalTrialsIndia, NppaCompendium,
    CdscoNsqPortal, CdscoApprovalsDb, CdscoBrandRegistry,
    OpenFdaBulk, WhoPrequal, EmaMedicines, NseFilings, Cdci,
    RmsclRates, TnmscRates, HmsclRates, UpmsclDebarments, WhoAlerts, FdaImportAlert6640, MoleculeEnrichment,
    AlertsDispatch,
]}
