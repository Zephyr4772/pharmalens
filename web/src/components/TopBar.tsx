import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { get } from "../lib/api";
import { useLive } from "../state/live";

export function TopBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const [now, setNow] = useState(new Date());
  const connected = useLive((s) => s.connected);
  const unread = useQuery({ queryKey: ["alert-unread"], queryFn: () => get("/alerts/inbox", { unread: true, limit: 1 }), refetchInterval: 60_000 });
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const ist = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata", hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).format(now);
  const d = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "2-digit", month: "short" }).format(now);
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", { timeZone: "Asia/Kolkata", weekday: "short", hour: "numeric", minute: "numeric", hour12: false })
      .formatToParts(now).map((p) => [p.type, p.value])
  );
  const mins = (Number(parts.hour) % 24) * 60 + Number(parts.minute);
  const open = !["Sat", "Sun"].includes(parts.weekday) && mins >= 555 && mins <= 930; // NSE 09:15–15:30 IST

  return (
    <header className="topbar">
      <Link to="/" style={{ textDecoration: "none" }}>
        <span className="logo">PHARMALENS<span className="tm">INDIA PHARMA TERMINAL</span></span>
      </Link>
      <button className="search-trigger" onClick={onOpenPalette} aria-label="Search">
        <span>⌕</span>
        <span style={{ flex: 1, textAlign: "left" }}>brand · salt · combination · company · ticker</span>
        <kbd>CTRL</kbd><kbd>K</kbd>
      </button>
      <div className="topbar-right">
        <Link to="/alerts" className={`bell ${unread.data?.unread ? "hot" : ""}`} title="Alerts">🔔{unread.data?.unread ? <b>{unread.data.unread}</b> : null}</Link>
        <span className={`mkt-pill ${open ? "open" : ""}`}>NSE {open ? "OPEN" : "CLOSED"}</span>
        <span className={`mkt-pill ${connected ? "open" : "down"}`}>{connected ? "● LIVE" : "○ RECONNECTING"}</span>
        <span className="topbar-clock">{d} · IST <b>{ist}</b></span>
      </div>
    </header>
  );
}
