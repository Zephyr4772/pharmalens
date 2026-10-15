import { useEffect, useState } from "react";
import { Command } from "cmdk";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, inr } from "../lib/api";

export function CommandPalette({ open, setOpen }: { open: boolean; setOpen: (v: boolean) => void }) {
  const nav = useNavigate();
  const [term, setTerm] = useState("");

  useEffect(() => {
    if (!open) setTerm("");
  }, [open]);

  const search = useQuery({
    queryKey: ["palette", term],
    queryFn: () => api.search(term, 10),
    enabled: open && term.trim().length >= 2,
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!open);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  const go = (to: string) => {
    setOpen(false);
    nav(to);
  };

  const results = search.data?.results ?? [];
  return (
    <Command.Dialog open={open} onOpenChange={setOpen} label="Global command palette" shouldFilter={false}>
      <Command.Input
        value={term}
        onValueChange={setTerm}
        placeholder="Search drugs, molecules, companies…"
        autoFocus
      />
      <Command.List>
        <Command.Empty>
          {term.trim().length < 2 ? "Type at least 2 characters…" : "No matches."}
        </Command.Empty>

        {results.length > 0 && (
          <Command.Group heading="Securities">
            {results.map((r) => (
              <Command.Item
                key={`${r.type}-${r.id}`}
                value={`${r.type}-${r.id}-${r.label}`}
                onSelect={() => {
                  if (r.type === "drug") go(`/drugs/${r.id}`);
                  else if (r.type === "molecule") go(`/molecules/${r.id}`);
                  else if (r.slug) go(`/companies/${r.slug}`);
                }}
              >
                <span className="cmd-type">{r.type.slice(0, 3).toUpperCase()}</span>
                <span style={{ color: "var(--text)" }}>{r.label}</span>
                {typeof r.mrp === "number" && <span className="cmd-sub">{inr(r.mrp)}</span>}
                <span className="cmd-sub">{r.sub}</span>
              </Command.Item>
            ))}
          </Command.Group>
        )}

        <Command.Group heading="Screens">
          <Command.Item value="go-market" onSelect={() => go("/")}>
            <span className="cmd-type">NAV</span> Market Overview
          </Command.Item>
          <Command.Item value="go-screener" onSelect={() => go("/screener")}>
            <span className="cmd-type">NAV</span> Drug Screener
          </Command.Item>
          <Command.Item value="go-molecules" onSelect={() => go("/molecules")}>
            <span className="cmd-type">NAV</span> Molecules
          </Command.Item>
          <Command.Item value="go-companies" onSelect={() => go("/companies")}>
            <span className="cmd-type">NAV</span> Companies
          </Command.Item>
          <Command.Item value="go-alerts" onSelect={() => go("/alerts")}>
            <span className="cmd-type">NAV</span> NSQ Alerts (CDSCO)
          </Command.Item>
          <Command.Item value="go-watch" onSelect={() => go("/watchlist")}>
            <span className="cmd-type">NAV</span> Watchlist
          </Command.Item>
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}
