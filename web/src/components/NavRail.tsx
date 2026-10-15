import { useLocation, useNavigate } from "react-router-dom";

const ITEMS = [
  { key: "1", name: "MKT", path: "/" },
  { key: "2", name: "SCRN", path: "/screener" },
  { key: "3", name: "MOL", path: "/molecules" },
  { key: "4", name: "COMP", path: "/companies" },
  { key: "5", name: "NSQ", path: "/alerts" },
  { key: "6", name: "WATCH", path: "/watchlist" },
];

export function NavRail() {
  const nav = useNavigate();
  const loc = useLocation();
  return (
    <nav className="rail">
      {ITEMS.map((it) => (
        <div
          key={it.path}
          className={"rail-item" + (loc.pathname === it.path ? " active" : "")}
          onClick={() => nav(it.path)}
        >
          <span className="rail-key">{it.key}</span>
          <span className="rail-name">{it.name}</span>
        </div>
      ))}
    </nav>
  );
}
