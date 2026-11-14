import { useEffect, useState } from "react";
import { Route, Routes, useNavigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TopBar } from "./components/TopBar";
import { TickerTape } from "./components/TickerTape";
import { NavRail, NAV } from "./components/NavRail";
import { StatusBar } from "./components/StatusBar";
import { CommandPalette } from "./components/CommandPalette";
import { connectStream } from "./state/live";
import { useWatchlist } from "./state/watchlist";

import Today from "./screens/Today";
import Companies from "./screens/Companies";
import Market from "./screens/Market";
import Regulatory from "./screens/Regulatory";
import Shelf from "./screens/Shelf";
import Screener from "./screens/Screener";
import Molecules from "./screens/Molecules";
import MoleculeDetail from "./screens/MoleculeDetail";
import Combos from "./screens/Combos";
import ComboDetail from "./screens/ComboDetail";
import Groups from "./screens/Groups";
import GroupDetail from "./screens/GroupDetail";
import CompanyDetail from "./screens/CompanyDetail";
import MakerDetail from "./screens/MakerDetail";
import SiteDetail from "./screens/SiteDetail";
import ProductDetail from "./screens/ProductDetail";
import Equities from "./screens/Equities";
import News from "./screens/News";
import Feeds from "./screens/Feeds";
import Watchlist from "./screens/Watchlist";
import Pipeline from "./screens/Pipeline";
import Alerts from "./screens/Alerts";
import About from "./screens/About";
import { Link } from "react-router-dom";
import { useMe } from "./state/me";

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 60_000 } },
});

function GlobalKeys() {
  const nav = useNavigate();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const el = document.activeElement;
      if (el && ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName)) return;
      const hit = NAV.find((n) => n.key.toLowerCase() === e.key.toLowerCase());
      if (hit) nav(hit.path);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [nav]);
  return null;
}

// Shown to visitors who reach the terminal from outside the private network.
function PublicBanner() {
  const me = useMe();
  if (!me.public) return null;
  return (
    <div className="public-banner">
      Public view · read-only · the data stays on the server · <Link to="/about">How this works →</Link>
    </div>
  );
}

function Shell() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  useEffect(() => {
    useWatchlist.getState().load();   // the server's watchlist (shared with Specs and alerts)
    connectStream(
      () => qc.invalidateQueries({ queryKey: ["quotes"] }),
      () => {
        qc.invalidateQueries({ queryKey: ["events"] });
        qc.invalidateQueries({ queryKey: ["overview"] });
        qc.invalidateQueries({ queryKey: ["today"] });
        qc.invalidateQueries({ queryKey: ["alert-inbox"] });
        qc.invalidateQueries({ queryKey: ["alert-unread"] });
      }
    );
  }, []);
  return (
    <div className="shell">
      <GlobalKeys />
      <TopBar onOpenPalette={() => setPaletteOpen(true)} />
      <PublicBanner />
      <TickerTape />
      <div className="shell-body">
        <NavRail />
        <main className="screen">
          <Routes>
            <Route path="/" element={<Today />} />
            <Route path="/companies" element={<Companies />} />
            <Route path="/market" element={<Market />} />
            <Route path="/reg" element={<Regulatory />} />
            <Route path="/shelf" element={<Shelf />} />
            <Route path="/screener" element={<Screener />} />
            <Route path="/molecules" element={<Molecules />} />
            <Route path="/m/:id" element={<MoleculeDetail />} />
            <Route path="/fdc" element={<Combos />} />
            <Route path="/c/:id" element={<ComboDetail />} />
            <Route path="/groups" element={<Groups />} />
            <Route path="/g/:slug" element={<GroupDetail />} />
            <Route path="/co/:slug" element={<CompanyDetail />} />
            <Route path="/mk/*" element={<MakerDetail />} />
            <Route path="/st/*" element={<SiteDetail />} />
            <Route path="/p/:id" element={<ProductDetail />} />
            <Route path="/equities" element={<Equities />} />
            <Route path="/news" element={<News />} />
            <Route path="/feeds" element={<Feeds />} />
            <Route path="/watch" element={<Watchlist />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/about" element={<About />} />
            <Route path="*" element={<Today />} />
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
