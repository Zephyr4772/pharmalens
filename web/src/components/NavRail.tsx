import { useLocation, useNavigate } from "react-router-dom";
import { useLive } from "../state/live";
import { useMe } from "../state/me";

export const NAV = [
  { key: "1", name: "TODAY", path: "/", title: "Today: watchlist, signals, results this week" },
  { key: "2", name: "COS", path: "/companies", title: "Companies screener: listed pharma groups" },
  { key: "3", name: "MKT", path: "/market", title: "Market structure monitor" },
  { key: "4", name: "REG", path: "/reg", title: "Government & regulatory desk" },
  { key: "5", name: "PIPE", path: "/pipeline", title: "Approvals, SEC recommendations, clinical trials" },
  { key: "6", name: "SCRN", path: "/screener", title: "Product screener" },
  { key: "7", name: "MOL", path: "/molecules", title: "Molecules / salts" },
  { key: "8", name: "FDC", path: "/fdc", title: "Salt combinations & price spreads" },
  { key: "9", name: "GRP", path: "/groups", title: "All companies & groups, market share" },
  { key: "0", name: "EQ", path: "/equities", title: "Listed pharma equities" },
  { key: "n", name: "NEWS", path: "/news", title: "News wire" },
  { key: "s", name: "SHELF", path: "/shelf", title: "Inventory compliance check" },
  { key: "f", name: "FEED", path: "/feeds", title: "Data feeds & methodology" },
  { key: "w", name: "WATCH", path: "/watch", title: "Watchlist" },
  { key: "a", name: "ALERT", path: "/alerts", title: "Alert subscriptions & inbox" },
];

export function NavRail() {
  const nav = useNavigate();
  const loc = useLocation();
  const unseen = useLive((s) => s.unseen);
  const { owner } = useMe();
  const active = (p: string) => (p === "/" ? loc.pathname === "/" : loc.pathname.startsWith(p));
  return (
    <nav className="rail">
      {NAV.filter((it) => owner || it.path !== "/alerts").map((it) => (
        <div key={it.path} title={it.title} className={"rail-item" + (active(it.path) ? " active" : "")} onClick={() => nav(it.path)}>
          <span className="rail-key">{it.key.toUpperCase()}</span>
          <span className="rail-name">{it.name}</span>
          {it.name === "TODAY" && unseen > 0 && <span className="rail-dot">{unseen > 99 ? "99+" : unseen}</span>}
        </div>
      ))}
    </nav>
  );
}
