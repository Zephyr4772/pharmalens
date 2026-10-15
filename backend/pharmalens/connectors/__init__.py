from .cdsco import CdscoAlerts, CdscoBannedFdc, CdscoGazette, CdscoNsq, NsqMirror
from .drugsetu import DrugSetuLaunches
from .global_reg import OpenFdaIndiaRecalls
from .gov_india import JanAushadhi, NppaOrders
from .markets import NseFundamentals, NseQuotes
from .news import PharmaNews

REGISTRY = {c.name: c for c in [
    CdscoNsq, NsqMirror, CdscoBannedFdc, CdscoGazette, CdscoAlerts,
    NppaOrders, JanAushadhi,
    NseQuotes, NseFundamentals,
    PharmaNews, OpenFdaIndiaRecalls, DrugSetuLaunches,
]}
