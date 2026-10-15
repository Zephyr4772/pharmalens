import { useEffect, useState } from "react";
import { Command } from "cmdk";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { get, inr, num, type Row } from "../lib/api";
import { NAV } from "./NavRail";

export function CommandPalette({ open, setOpen }: { open: boolean; setOpen: (v: boolean) => void }) {
  const nav = useNavigate();
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { if (!open) setTerm(""); }, [open]);
  useEffect(() => { const t = setTimeout(() => setDebounced(term.trim()), 160); return () => clearTimeout(t); }, [term]);

  const search = useQuery({
    queryKey: ["palette", debounced],
    queryFn: () => get<Record<string, Row[]>>("/search", { q: debounced, limit: 8 }),
    enabled: open && debounced.length >= 2,
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen(!open); }
      if (e.key === "/" && !open && !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName ?? "")) { e.preventDefault(); setOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  const go = (to: string) => { setOpen(false); nav(to); };
  const d = search.data;
  const group = (heading: string, rows: Row[] | undefined, render: (r: Row) => [string, string, React.ReactNode, React.ReactNode?]) =>
    rows && rows.length > 0 ? (
      <Command.Group heading={heading}>
        {rows.map((r) => {
          const [type, to, label, sub] = render(r);
          return (
            <Command.Item key={to} value={to} onSelect={() => go(to)}>
              <span className="cmd-type">{type}</span>
              <span style={{ color: "var(--text)" }}>{label}</span>
              {sub && <span className="cmd-sub">{sub}</span>}
            </Command.Item>
          );
        })}
      </Command.Group>
    ) : null;

  return (
    <Command.Dialog open={open} onOpenChange={setOpen} label="Search" shouldFilter={false}>
      <Command.Input value={term} onValueChange={setTerm} placeholder="Dolo 650 · amoxicillin · cefixime + ofloxacin · Cipla · SUNPHARMA" autoFocus />
      <Command.List>
        <Command.Empty>{term.trim().length < 2 ? "Type at least 2 characters…" : search.isFetching ? "searching…" : "No matches."}</Command.Empty>
        {group("Groups / tickers", d?.parents, (r) => ["GRP", `/g/${r.slug}`, r.name, r.ticker])}
        {group("Brands / SKUs", d?.products, (r) => ["SKU", `/p/${r.id}`, r.name, <>{r.company} · {inr(r.mrp)}</>])}
        {group("Molecules", d?.molecules, (r) => ["MOL", `/m/${r.id}`, r.name, `${num(r.product_count)} SKUs`])}
        {group("Combinations", d?.combos, (r) => ["FDC", `/c/${r.id}`, r.label, `${num(r.product_count)} brands`])}
        {group("Companies", d?.companies, (r) => ["CO", `/co/${r.slug}`, r.name, `${num(r.product_count)} SKUs`])}
        <Command.Group heading="Screens">
          {NAV.map((n) => (
            <Command.Item key={n.path} value={`nav-${n.name}-${n.title}`} onSelect={() => go(n.path)}>
              <span className="cmd-type">{n.key.toUpperCase()}</span> {n.name} <span className="cmd-sub">{n.title}</span>
            </Command.Item>
          ))}
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}
