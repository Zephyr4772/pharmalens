import { useLocation, useNavigate } from "react-router-dom";
import { useLive } from "../state/live";

export const NAV = [
  { key: "1", name: "MKT", path: "/", title: "Market monitor" },
  { key: "2", name: "REG", path: "/reg", title: "Government & regulatory desk" },
  { key: "3", name: "SHELF", path: "/shelf", title: "Inventory compliance check" },
  { key: "p", name: "PIPE", path: "/pipeline", title: "Approvals, SEC recommendations, clinical trials" },
  { key: "4", name: "SCRN", path: "/screener", title: "Product screener" },
  { key: "5", name: "MOL", path: "/molecules", title: "Molecules / salts" },
  { key: "6", name: "FDC", path: "/fdc", title: "Salt combinations & price spreads" },
  { key: "7", name: "CO", path: "/groups", title: "Companies & groups, market share" },
  { key: "8", name: "EQ", path: "/equities", title: "Listed pharma equities" },
  { key: "9", name: "NEWS", path: "/news", title: "News wire" },
  { key: "0", name: "FEED", path: "/feeds", title: "Data feeds & methodology" },
  { key: "w", name: "WATCH", path: "/watch", title: "Watchlist" },
  { key: "a", name: "ALERT", path: "/alerts", title: "Alert subscriptions & inbox" },
];

export function NavRail() {
  const nav = useNavigate();
  const loc = useLocation();
  const unseen = useLive((s) => s.unseen);
  const active = (p: string) => (p === "/" ? loc.pathname === "/" : loc.pathname.startsWith(p));
  return (
    <nav className="rail">
      {NAV.map((it) => (
        <div key={it.path} title={it.title} className={"rail-item" + (active(it.path) ? " active" : "")} onClick={() => nav(it.path)}>
          <span className="rail-key">{it.key.toUpperCase()}</span>
          <span className="rail-name">{it.name}</span>
          {it.name === "MKT" && unseen > 0 && <span className="rail-dot">{unseen > 99 ? "99+" : unseen}</span>}
        </div>
      ))}
    </nav>
  );
}
