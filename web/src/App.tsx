import { useEffect, useState } from "react";
import { Route, Routes, useNavigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TopBar } from "./components/TopBar";
import { TickerTape } from "./components/TickerTape";
import { NavRail } from "./components/NavRail";
import { StatusBar } from "./components/StatusBar";
import { CommandPalette } from "./components/CommandPalette";

import Market from "./screens/Market";
import Screener from "./screens/Screener";
import Molecules from "./screens/Molecules";
import Companies from "./screens/Companies";
import CompanyDetail from "./screens/CompanyDetail";
import DrugDetail from "./screens/DrugDetail";
import MoleculeDetail from "./screens/MoleculeDetail";
import Alerts from "./screens/Alerts";
import Watchlist from "./screens/Watchlist";

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const SCREEN_KEYS: Record<string, string> = {
  "/": "1", "/screener": "2", "/molecules": "3",
  "/companies": "4", "/alerts": "5", "/watchlist": "6",
};

function GlobalKeys() {
  const nav = useNavigate();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const el = document.activeElement;
      if (el && (el.tagName === "INPUT" || el.tagName === "SELECT" || el.tagName === "TEXTAREA")) return;
      for (const [path, key] of Object.entries(SCREEN_KEYS)) {
        if (e.key === key) {
          nav(path);
          break;
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [nav]);
  return null;
}

function Shell() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  return (
    <div className="shell">
      <GlobalKeys />
      <TopBar onOpenPalette={() => setPaletteOpen(true)} />
      <TickerTape />
      <div className="shell-body">
        <NavRail />
        <main className="screen">
          <Routes>
            <Route path="/" element={<Market />} />
            <Route path="/screener" element={<Screener />} />
            <Route path="/drugs/:id" element={<DrugDetail />} />
            <Route path="/molecules" element={<Molecules />} />
            <Route path="/molecules/:id" element={<MoleculeDetail />} />
            <Route path="/companies" element={<Companies />} />
            <Route path="/companies/:slug" element={<CompanyDetail />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/watchlist" element={<Watchlist />} />
          </Routes>
        </main>
      </div>
      <StatusBar />
      <CommandPalette open={paletteOpen} setOpen={setPaletteOpen} />
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <Shell />
    </QueryClientProvider>
  );
}
