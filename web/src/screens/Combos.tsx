import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { csvUrl, get, inr, num, share, type Row } from "../lib/api";
import { Loading, Pager, Panel, Star, Tabs, Csv } from "../components/ui";

type Mode = "spreads" | "browse" | "banned";

export default function Combos() {
  const nav = useNavigate();
  const [mode, setMode] = useState<Mode>("spreads");
  const [cls, setCls] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("brands");
  const [page, setPage] = useState(1);
  const meta = useQuery({ queryKey: ["classes"], queryFn: () => get("/market/classes"), staleTime: 3600_000 });
  const spreads = useQuery({ queryKey: ["spreads", cls], enabled: mode === "spreads", queryFn: () => get("/market/spreads", { therapeutic_class: cls, limit: 150, min_brands: 8 }) });
  const browse = useQuery({
    queryKey: ["combos", q, cls, sort, page, mode], enabled: mode !== "spreads",
    queryFn: () => get("/combos", { q, therapeutic_class: cls, sort, page, limit: 80, banned: mode === "banned" ? true : undefined, min_brands: 1 }),
  });
  return (
    <div className="stack">
      <Tabs<Mode> value={mode} onChange={(m) => { setMode(m); setPage(1); }} tabs={[
        ["spreads", "PRICE SPREADS (same composition)"], ["browse", "ALL SALT COMBINATIONS"], ["banned", "COMBINATIONS WITH BANNED SKUs"],
      ]} />
      <div className="filterbar">
        {mode !== "spreads" && <><label>search</label><input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="e.g. amoxicillin + clav" /></>}
        <label>class</label>
        <select value={cls} onChange={(e) => { setCls(e.target.value); setPage(1); }}>
          <option value="">all</option>{meta.data?.data.map((c: string) => <option key={c}>{c}</option>)}
        </select>
        {mode !== "spreads" && <><label>sort</label>
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="brands">brands</option><option value="companies">marketers</option><option value="spread">price spread</option><option value="median">median MRP</option>
          </select></>}
        <span className="spacer" />
        {mode === "spreads" && <Csv href={csvUrl("/market/spreads", { therapeutic_class: cls, limit: 500 })} />}
      </div>
      {mode === "spreads" ? (
        <Panel title="Same salt, same strength — price spread" sub="same molecules, strengths and dosage form; per-unit prices, outliers excluded; ranked by brands × log(max/min) — the procurement opportunity list">
          {spreads.isLoading ? <Loading /> : (
            <table className="tt">
              <thead><tr><th>Composition</th><th>Class</th><th className="num">Brands</th><th className="num">Marketers</th><th className="num">Cheapest /unit</th><th className="num">Median /unit</th><th className="num">Costliest /unit</th><th className="num">Spread</th><th /></tr></thead>
              <tbody>{spreads.data?.data.map((k: Row) => (
                <tr key={k.id} onClick={() => nav(`/c/${k.id}`)}>
                  <td title={k.label}>{k.label}</td><td className="mut">{k.therapeutic_class}</td><td className="num">{num(k.product_count)}</td><td className="num">{num(k.company_count)}</td>
                  <td className="num pos">{inr(k.min_unit)}</td><td className="num amb">{inr(k.median_unit)}</td><td className="num neg">{inr(k.max_unit)}</td>
                  <td className="num">{k.spread_x}×</td><td>{k.banned_skus > 0 && <span className="badge b-down">BAN</span>}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </Panel>
      ) : (
        <Panel title="Salt combinations" sub={browse.data ? `${num(browse.data.meta.total)} compositions` : ""}>
          {browse.isLoading ? <Loading /> : (
            <table className="tt">
              <thead><tr><th /><th>Composition</th><th>Class</th><th className="num">Brands</th><th className="num">Marketers</th><th className="num">Min</th><th className="num">Median</th><th className="num">Max</th><th className="num">HHI</th><th>Leader</th><th /></tr></thead>
              <tbody>{browse.data?.data.map((k: Row) => (
                <tr key={k.id} onClick={() => nav(`/c/${k.id}`)}>
                  <td><Star k={`c:${k.id}`} label={k.label} href={`/c/${k.id}`} /></td>
                  <td title={k.label}>{k.label}</td><td className="mut">{k.therapeutic_class}</td><td className="num">{num(k.product_count)}</td><td className="num">{num(k.company_count)}</td>
                  <td className="num">{inr(k.min_mrp)}</td><td className="num amb">{inr(k.median_mrp)}</td><td className="num">{inr(k.max_mrp)}</td>
                  <td className="num">{num(k.hhi)}</td><td>{k.leader} <span className="amb">{share(k.leader_share)}</span></td>
                  <td>{k.banned_skus > 0 && <span className="badge b-down">BAN {k.banned_skus}</span>}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
          <Pager meta={browse.data?.meta} page={page} setPage={setPage} />
        </Panel>
      )}
    </div>
  );
}
