import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { get, num, type Row } from "../lib/api";
import { Loading, Pager, Panel } from "../components/ui";

export default function News() {
  const [topic, setTopic] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const r = useQuery({ queryKey: ["news", topic, q, page], queryFn: () => get("/news", { topic, q, page, limit: 60 }), refetchInterval: 300_000 });
  return (
    <div className="stack">
      <div className="filterbar">
        <label>search</label>
        <input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="headline" />
        <button className={!topic ? "active" : ""} onClick={() => { setTopic(""); setPage(1); }}>ALL</button>
        {r.data?.topics?.map((t: Row) => (
          <button key={t.topic} className={topic === t.topic ? "active" : ""} onClick={() => { setTopic(t.topic); setPage(1); }}>
            {t.topic.toUpperCase()} <span className="faint">{num(t.n)}</span>
          </button>
        ))}
      </div>
      <Panel title="Pharma news wire" sub="ET HealthWorld · Express Pharma · targeted Google News queries · refreshed every 15 min · auto-tagged to groups">
        {r.isLoading ? <Loading /> : r.data?.data.map((n: Row) => (
          <div className="news-row" key={n.id}>
            <span className="ev-time">{new Date(n.published_at).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
            <span className={`ev-kind topic-${n.topic}`}>{n.topic.toUpperCase()}</span>
            <div className="news-main">
              <a href={n.url} target="_blank" rel="noreferrer">{n.title}</a>
              <div className="faint">{n.source}{n.parents.map((p: Row) => <Link key={p.id} to={`/g/${p.slug}`} className="chip">{p.name}</Link>)}</div>
              {n.summary && <div className="news-sum">{n.summary}</div>}
            </div>
          </div>
        ))}
        <Pager meta={r.data?.meta} page={page} setPage={setPage} />
      </Panel>
    </div>
  );
}
