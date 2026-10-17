from .alerts_job import AlertsDispatch
from .cdsco import CdscoAlerts, CdscoBannedFdc, CdscoGazette, CdscoNsq, NsqMirror
from .drugsetu import DrugSetuLaunches
from .global_reg import OpenFdaIndiaRecalls
from .gov_india import JanAushadhi, NppaOrders
from .markets import NseFundamentals, NseQuotes
from .news import PharmaNews
from .pipeline_feeds import CdscoApprovals, CdscoSec, ClinicalTrialsIndia, Nlem, NppaCompendium

REGISTRY = {c.name: c for c in [
    CdscoNsq, NsqMirror, CdscoBannedFdc, CdscoGazette, CdscoAlerts,
    NppaOrders, JanAushadhi,
    NseQuotes, NseFundamentals,
    PharmaNews, OpenFdaIndiaRecalls, DrugSetuLaunches,
    CdscoApprovals, CdscoSec, Nlem, ClinicalTrialsIndia, NppaCompendium,
    AlertsDispatch,
]}
