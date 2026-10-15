import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { get, hhiLabel, num, share, signed, type Row } from "../lib/api";
import { useLive } from "../state/live";
import { Bar, ErrorBox, EventRow, Kpi, Loading, Panel, Sev } from "../components/ui";

export default function Market() {
  const nav = useNavigate();
  const ov = useQuery({ queryKey: ["overview"], queryFn: () => get("/market/overview"), refetchInterval: 120_000 });
  const crit = useQuery({ queryKey: ["events", "critical"], queryFn: () => get("/events", { severity: "critical,high", limit: 40 }), refetchInterval: 60_000 });
  const all = useQuery({ queryKey: ["events", "all"], queryFn: () => get("/events", { limit: 60 }), refetchInterval: 60_000 });
  const news = useQuery({ queryKey: ["news", "home"], queryFn: () => get("/news", { limit: 14 }), refetchInterval: 300_000 });
  const live = useLive();
  useEffect(() => { live.markSeen(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (ov.isLoading) return <Loading what="loading market" />;
  if (ov.error) return <ErrorBox e={ov.error} />;
  const o = ov.data;
  const k = o.kpis;
  const idx = (t: string) => o.indexes.find((x: Row) => x.ticker === t);
  const np = idx("^CNXPHARMA");
  const maxGroup = Math.max(...o.top_groups.map((g: Row) => g.value_share));
  const tape = [...live.events, ...(all.data?.data ?? [])].filter((e, i, arr) => arr.findIndex((x) => x.id === e.id) === i).slice(0, 60);

  return (
    <div className="stack">
      <div className="kpis">
        <Kpi label="Nifty Pharma" value={np?.price ? np.price.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "—"}
          sub={<span className={np?.change_pct >= 0 ? "pos" : "neg"}>{signed(np?.change_pct)}</span>} tone="amber" />
        <Kpi label="Active SKUs" value={num(k.active_products)} sub={`${num(k.in_stock)} seen in stock`} />
        <Kpi label="Molecules · FDCs" value={`${num(k.molecules)} · ${num(k.fdcs)}`} sub={`${num(k.companies)} marketers`} />
        <Kpi label="Prohibited SKUs listed" value={num(k.banned_skus_listed)} sub={`+${num(k.ban_review_skus)} need pack check`} tone="down" />
        <Kpi label="NSQ batches (90d)" value={num(k.nsq_90d)} sub={`latest list ${k.nsq_latest_month ?? "—"}`} tone="down" />
        <Kpi label="Jan Aushadhi SKUs" value={num(k.jan_aushadhi_skus)} sub="PMBI generic MRPs" />
        <Kpi label="Events 24h" value={num(k.events_24h)} sub={`${num(k.news_24h)} news items`} />
      </div>

      <div className="grid cols-3">
        <Panel title="Critical & high-severity" sub="bans · NSQ · spurious · recalls" className="span-2 tall"
          right={<Link to="/reg">REG desk ›</Link>}>
          {crit.data?.data?.map((e: Row) => <EventRow key={e.id} e={e} />)}
        </Panel>
        <Panel title="Live event tape" sub={live.connected ? "streaming" : "reconnecting"} className="tall">
          {tape.map((e) => <EventRow key={e.id} e={e} compact />)}
        </Panel>
      </div>

      <div className="grid cols-3">
        <Panel title="Therapy segments" sub="estimated value share · HHI concentration" className="span-2">
          <table className="tt">
            <thead><tr><th>Segment</th><th className="num">SKUs</th><th className="num">Marketers</th><th className="num">HHI</th><th>Structure</th><th>Leader (est. value share)</th></tr></thead>
            <tbody>
              {o.classes.map((c: Row) => (
                <tr key={c.therapeutic_class} onClick={() => nav(`/screener?therapeutic_class=${encodeURIComponent(c.therapeutic_class)}`)}>
                  <td>{c.therapeutic_class}</td>
                  <td className="num">{num(c.skus)}</td>
                  <td className="num">{num(c.owners)}</td>
                  <td className="num">{num(c.hhi)}</td>
                  <td className="mut">{hhiLabel(c.hhi)}</td>
                  <td>{c.leader} <span className="amb">{share(c.leader_share)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="Largest groups" sub="share of estimated retail value" right={<Link to="/groups">CO ›</Link>}>
          {o.top_groups.map((g: Row) => (
            <Bar key={g.slug} label={g.name} to={`/g/${g.slug}`} value={g.value_share} max={maxGroup} text={share(g.value_share)} />
          ))}
          <div className="faint" style={{ marginTop: 6 }}>Estimate from MRP × availability × listing breadth. <Link to="/feeds#method">method</Link></div>
        </Panel>
      </div>

      <div className="grid cols-3">
        <Panel title="Equity movers" right={<Link to="/equities">EQ ›</Link>}>
          <table className="tt"><tbody>
            {o.movers.map((m: Row) => (
              <tr key={m.ticker} onClick={() => nav(`/g/${m.slug}`)}>
                <td>{m.ticker.replace(".NS", "")}</td><td className="mut">{m.name}</td>
                <td className="num">{m.price?.toLocaleString("en-IN", { maximumFractionDigits: 1 })}</td>
                <td className={`num ${m.change_pct >= 0 ? "pos" : "neg"}`}>{signed(m.change_pct)}</td>
              </tr>
            ))}
          </tbody></table>
        </Panel>
        <Panel title="News wire" className="span-2" right={<Link to="/news">NEWS ›</Link>}>
          {news.data?.data?.map((n: Row) => (
            <div className="ev" key={n.id}>
              <span className="ev-time">{new Date(n.published_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}</span>
              <span className={`ev-kind topic-${n.topic}`}>{n.topic.toUpperCase()}</span>
              <a className="ev-title" href={n.url} target="_blank" rel="noreferrer">{n.title}</a>
              <span className="ev-src">{n.source}</span>
            </div>
          ))}
        </Panel>
      </div>
      {crit.data?.kinds && (
        <div className="faint">Event counts: {crit.data.kinds.map((x: Row) => <span key={x.kind} className="chip">{x.kind} {num(x.n)}</span>)} <Sev s="critical" /> <Sev s="high" /> <Sev s="medium" /> <Sev s="info" /></div>
      )}
    </div>
  );
}
