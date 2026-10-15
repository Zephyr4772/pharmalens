import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

export function TopBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const ist = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(now);

  return (
    <header className="topbar">
      <Link to="/" style={{ textDecoration: "none" }}>
        <span className="logo">
          PHARMALENS<span className="tm">TERMINAL</span>
        </span>
      </Link>
      <button className="search-trigger" onClick={onOpenPalette} aria-label="Search">
        <span>⌕</span>
        <span style={{ flex: 1 }}>search drugs · molecules · companies</span>
        <kbd>CTRL</kbd>
        <kbd>K</kbd>
      </button>
      <div className="topbar-clock">
        IST <b>{ist}</b>
      </div>
    </header>
  );
}
