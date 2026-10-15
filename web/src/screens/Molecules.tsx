import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { get, hhiLabel, inr, num, share, type Row } from "../lib/api";
import { Loading, Pager, Panel, Star, Tabs } from "../components/ui";

type Mode = "all" | "concentrated" | "fragmented";

export default function Molecules() {
  const nav = useNavigate();
  const [mode, setMode] = useState<Mode>("all");
  const [q, setQ] = useState("");
  const [cls, setCls] = useState("");
  const [ctrl, setCtrl] = useState("");
  const [sort, setSort] = useState("products");
  const [page, setPage] = useState(1);
  const meta = useQuery({ queryKey: ["classes"], queryFn: () => get("/market/classes"), staleTime: 3600_000 });
  const list = useQuery({
    queryKey: ["molecules", q, cls, ctrl, sort, page], enabled: mode === "all",
    queryFn: () => get("/molecules", { q, therapeutic_class: cls, controlled: ctrl, sort, page, limit: 80 }),
  });
  const conc = useQuery({
    queryKey: ["concentration", mode, page], enabled: mode !== "all",
    queryFn: () => get("/market/concentration", { type: "molecule", order: mode === "concentrated" ? "hhi_desc" : "hhi_asc", min_skus: 30, page, limit: 80 }),
  });
  return (
    <div className="stack">
      <Tabs<Mode> value={mode} onChange={(m) => { setMode(m); setPage(1); }} tabs={[
        ["all", "ALL MOLECULES"], ["concentrated", "MOST CONCENTRATED (entry barriers)"], ["fragmented", "MOST FRAGMENTED (price competition)"],
      ]} />
      {mode === "all" ? (
        <>
          <div className="filterbar">
            <label>search</label><input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="salt / molecule" />
            <label>class</label>
            <select value={cls} onChange={(e) => { setCls(e.target.value); setPage(1); }}>
              <option value="">all</option>{meta.data?.data.map((c: string) => <option key={c}>{c}</option>)}
            </select>
            <label>price control</label>
            <select value={ctrl} onChange={(e) => { setCtrl(e.target.value); setPage(1); }}>
              <option value="">any</option><option value="true">NPPA ceiling</option><option value="false">uncontrolled</option>
            </select>
            <label>sort</label>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="products">SKUs</option><option value="companies">marketers</option><option value="combos">combinations</option><option value="hhi">concentration</option><option value="name">name</option>
            </select>
          </div>
          <Panel title="Molecules / salts" sub={list.data ? `${num(list.data.meta.total)} molecules` : ""}>
            {list.isLoading ? <Loading /> : (
              <table className="tt">
                <thead><tr><th /><th>Molecule</th><th>Class</th><th>Action</th><th className="num">SKUs</th><th className="num">Marketers</th><th className="num">Combos</th><th className="num">HHI</th><th>Leader</th><th className="num">NPPA ceiling</th></tr></thead>
                <tbody>
                  {list.data?.data.map((m: Row) => (
                    <tr key={m.id} onClick={() => nav(`/m/${m.id}`)}>
                      <td><Star k={`m:${m.id}`} label={m.name} href={`/m/${m.id}`} /></td>
                      <td>{m.name}</td><td className="mut">{m.therapeutic_class}</td><td className="mut" title={m.action_class}>{m.action_class}</td>
                      <td className="num">{num(m.product_count)}</td><td className="num">{num(m.company_count)}</td><td className="num">{num(m.combo_count)}</td>
                      <td className="num" title={hhiLabel(m.hhi)}>{num(m.hhi)}</td>
                      <td>{m.leader} <span className="amb">{share(m.leader_share)}</span></td>
                      <td className="num">{inr(m.nppa_ceiling)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <Pager meta={list.data?.meta} page={page} setPage={setPage} />
          </Panel>
        </>
      ) : (
        <Panel title={mode === "concentrated" ? "Concentrated molecules" : "Fragmented molecules"}
          sub="HHI on estimated value share; ≥30 SKUs. High HHI = few players dominate; low HHI = crowded generic market">
          {conc.isLoading ? <Loading /> : (
            <table className="tt">
              <thead><tr><th>Molecule</th><th className="num">SKUs</th><th className="num">Marketers</th><th className="num">HHI</th><th>Structure</th><th>Leader</th></tr></thead>
              <tbody>{conc.data?.data.map((m: Row) => (
                <tr key={m.id} onClick={() => nav(`/m/${m.id}`)}>
                  <td>{m.name}</td><td className="num">{num(m.skus)}</td><td className="num">{num(m.owners)}</td><td className="num">{num(m.hhi)}</td>
                  <td className="mut">{hhiLabel(m.hhi)}</td><td>{m.leader} <span className="amb">{share(m.leader_share)}</span></td>
                </tr>
              ))}</tbody>
            </table>
          )}
          <Pager meta={conc.data?.meta} page={page} setPage={setPage} />
        </Panel>
      )}
    </div>
  );
}
