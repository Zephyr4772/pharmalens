"""Alert dispatcher as a scheduled job, so its health shows on the FEED screen."""
from .. import alerts
from .base import Connector


class AlertsDispatch(Connector):
    name = "alerts_dispatch"
    title = "Alert Dispatcher"
    agency = "PharmaLens"
    schedule = {"trigger": "interval", "minutes": 2}
    description = "Matches new events to watchlist and shelf subscriptions; sends Telegram, email and webhook alerts and daily digests."

    def run(self):
        s = alerts.dispatch()
        # counts go in the note, not rows_new, so the scheduler does not trigger a derived refresh
        self.stats.notes.append(f"{s['messages']} alerts · {s['shelf_checks']} shelf checks · {s['digests']} digests · {s['subscriptions']} subs")
