import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ago, get, type Row } from "../lib/api";
import { useWatchlist } from "../state/watchlist";
import { useMe } from "../state/me";
import { Empty, Kpi, Loading, Panel, Sev, Tabs } from "../components/ui";

type Tab = "inbox" | "subs" | "new";
const SHELF_STORE = "pharmalens.shelf.v1";

async function send(method: string, path: string, body?: unknown) {
  const r = await fetch(`/api/v1${path}`, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText);
  return r.json();
}

function savedShelfCsv(): string {
  try { return JSON.parse(localStorage.getItem(SHELF_STORE) || "{}").csv ?? ""; } catch { return ""; }
}

export default function Alerts() {
  const me = useMe();
  if (!me.loaded) return <Loading />;
  if (!me.owner) return <Empty>Alerts and subscriptions are the owner's. Everything else in the terminal is open to you.</Empty>;
  return <OwnerAlerts />;
}

function OwnerAlerts() {
  const [tab, setTab] = useState<Tab>("inbox");
  const [editing, setEditing] = useState<Row | null>(null);
  const subs = useQuery({ queryKey: ["alert-subs"], queryFn: () => get("/alerts/subscriptions") });
  const meta = useQuery({ queryKey: ["alert-meta"], queryFn: () => get("/alerts/meta"), staleTime: 600_000 });
  const inbox = useQuery({ queryKey: ["alert-inbox"], queryFn: () => get("/alerts/inbox", { limit: 200 }), refetchInterval: 60_000 });
  const n = subs.data?.data?.length ?? 0;
  return (
    <div className="stack">
      <div className="kpis">
        <Kpi label="Unread alerts" value={inbox.data?.unread ?? "—"} tone={inbox.data?.unread ? "down" : undefined} />
        <Kpi label="Subscriptions" value={n} />
        <Kpi label="Telegram" value={meta.data?.channels.telegram ? "ready" : "not set"} tone={meta.data?.channels.telegram ? "up" : undefined} />
        <Kpi label="Email (SMTP)" value={meta.data?.channels.email ? "ready" : "not set"} tone={meta.data?.channels.email ? "up" : undefined} />
        <Kpi label="Webhooks" value="ready" tone="up" sub="Slack · Discord · Teams" />
      </div>
      <Tabs<Tab> value={tab} onChange={(t) => { setTab(t); if (t === "new") setEditing(null); }} tabs={[
        ["inbox", `INBOX${inbox.data?.unread ? ` (${inbox.data.unread})` : ""}`], ["subs", `SUBSCRIPTIONS (${n})`], ["new", editing ? "EDIT SUBSCRIPTION" : "+ NEW SUBSCRIPTION"],
      ]} />
      {tab === "inbox" && <Inbox data={inbox.data} loading={inbox.isLoading} />}
      {tab === "subs" && <Subs rows={subs.data?.data ?? []} onEdit={(r) => { setEditing(r); setTab("new"); }} />}
      {tab === "new" && <Editor initial={editing} meta={meta.data} onDone={() => { setEditing(null); setTab("subs"); }} />}
    </div>
  );
}

function Inbox({ data, loading }: { data?: Row; loading: boolean }) {
  const qc = useQueryClient();
  const read = useMutation({ mutationFn: (ids?: number[]) => send("POST", "/alerts/inbox/read", ids ?? null), onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-inbox"] }) });
  const dispatch = useMutation({ mutationFn: () => send("POST", "/alerts/dispatch"), onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-inbox"] }) });
  if (loading) return <Loading />;
  const rows: Row[] = data?.data ?? [];
  return (
    <Panel title="Alert inbox" sub="every alert sent to any subscription, with delivery status per channel"
      right={<span className="row-gap" style={{ marginTop: 0 }}>
        <button onClick={() => dispatch.mutate()} disabled={dispatch.isPending}>{dispatch.isPending ? "CHECKING…" : "CHECK NOW"}</button>
        <button onClick={() => read.mutate(undefined)}>MARK ALL READ</button></span>}>
      {!rows.length ? <Empty>No alerts yet. Create a subscription, then new bans, NSQ batches, recalls and news about what you watch land here.</Empty> :
        rows.map((m) => (
          <div key={m.id} className={`alert-row ${m.read_at ? "" : "unread"}`} onClick={() => !m.read_at && read.mutate([m.id])}>
            <div className="shelf-head">
              <Sev s={m.severity} />
              <span className="chip">{m.kind}</span>
              <b>{m.title}</b>
              <span className="spacer" />
              <span className="faint">{m.subscription} · {ago(m.created_at)} ago</span>
            </div>
            {m.body && <div className="flag" style={{ whiteSpace: "pre-wrap" }}>{m.body}</div>}
            <div className="faint" style={{ paddingLeft: 12 }}>
              matched: {m.reason}
              {m.url && <> · <a href={m.url} target="_blank" rel="noreferrer">source</a></>}
              {(m.deliveries ?? []).map((d: Row, i: number) => (
                <span key={i} className={`chip ${String(d.status).startsWith("error") ? "neg" : "pos"}`} title={d.status}>{d.channel}: {String(d.status).startsWith("error") ? "failed" : "sent"}</span>
              ))}
            </div>
          </div>
        ))}
    </Panel>
  );
}

function Subs({ rows, onEdit }: { rows: Row[]; onEdit: (r: Row) => void }) {
  const qc = useQueryClient();
  const del = useMutation({ mutationFn: (id: number) => send("DELETE", `/alerts/subscriptions/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-subs"] }) });
  const test = useMutation({ mutationFn: (id: number) => send("POST", `/alerts/subscriptions/${id}/test`), onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-inbox"] }) });
  if (!rows.length) return <Empty>No subscriptions yet — add one under "+ NEW SUBSCRIPTION".</Empty>;
  return (
    <Panel title="Subscriptions">
      <table className="tt">
        <thead><tr><th>Name</th><th>Watching</th><th>Shelf items</th><th>Filters</th><th>Channels</th><th>Mode</th><th className="num">Alerts</th><th>Last</th><th /></tr></thead>
        <tbody>{rows.map((s) => (
          <tr key={s.id}>
            <td>{s.name}{!s.active && <span className="badge b-mute">PAUSED</span>}</td>
            <td className="mut">{s.watch.length ? `${s.watch.length} items` : "—"}</td>
            <td className="mut">{s.shelf_items || "—"}</td>
            <td className="mut">{s.kinds.length ? s.kinds.join(", ") : "all kinds"} · ≥{s.min_severity}</td>
            <td>{s.channels.length ? s.channels.map((c: Row, i: number) => <span key={i} className="chip">{c.type}</span>) : <span className="faint">inbox only</span>}</td>
            <td className="mut">{s.instant ? "instant" : ""}{s.digest_hour != null ? `${s.instant ? " + " : ""}digest ${s.digest_hour}:00` : ""}</td>
            <td className="num">{s.messages}</td>
            <td className="mut">{s.last_message ? `${ago(s.last_message)} ago` : "—"}</td>
            <td style={{ whiteSpace: "nowrap" }}>
              <button onClick={() => test.mutate(s.id)} disabled={test.isPending}>TEST</button>{" "}
              <button onClick={() => onEdit(s)}>EDIT</button>{" "}
              <button onClick={() => { if (confirm(`Delete subscription "${s.name}" and its alert history?`)) del.mutate(s.id); }}>✕</button>
            </td>
          </tr>
        ))}</tbody>
      </table>
      {test.data && <div className="note">Test sent: {test.data.deliveries.length ? test.data.deliveries.map((d: Row) => `${d.channel} → ${d.status}`).join(" · ") : "inbox only (no channels)"}</div>}
      {test.error && <div className="err">{String((test.error as Error).message)}</div>}
    </Panel>
  );
}

const ALL_KINDS: [string, string][] = [
  ["ban", "Bans"], ["nsq", "NSQ batches"], ["spurious", "Spurious"], ["recall", "Recalls"], ["price_notification", "Price notices"],
  ["approval", "Approvals / SEC"], ["launch", "Launches"], ["trial", "Trials"], ["gazette", "Gazette"], ["news", "News"], ["stock", "Stock moves"],
];

function Editor({ initial, meta, onDone }: { initial: Row | null; meta?: Row; onDone: () => void }) {
  const qc = useQueryClient();
  const watchlist = useWatchlist((s) => s.items);
  const [name, setName] = useState(initial?.name ?? "My pharmacy");
  const [useWatch, setUseWatch] = useState<boolean>(initial ? initial.watch.length > 0 : watchlist.length > 0);
  const [watch, setWatch] = useState<Row[]>(initial?.watch ?? watchlist.map((w) => ({ key: w.key, label: w.label })));
  const [shelf, setShelf] = useState<string>(initial?.shelf_csv ?? "");
  const [kinds, setKinds] = useState<string[]>(initial?.kinds ?? []);
  const [sev, setSev] = useState<string>(initial?.min_severity ?? "medium");
  const [instant, setInstant] = useState<boolean>(initial?.instant ?? true);
  const [digest, setDigest] = useState<string>(initial?.digest_hour != null ? String(initial.digest_hour) : "8");
  const [tg, setTg] = useState<string>(initial?.channels.find((c: Row) => c.type === "telegram")?.chat_id ?? "");
  const [email, setEmail] = useState<string>(initial?.channels.find((c: Row) => c.type === "email")?.to ?? "");
  const [hook, setHook] = useState<string>(initial?.channels.find((c: Row) => c.type === "webhook")?.url ?? "");
  const [chats, setChats] = useState<Row[] | null>(null);
  useEffect(() => { if (!initial && useWatch) setWatch(watchlist.map((w) => ({ key: w.key, label: w.label }))); }, [watchlist]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useMutation({
    mutationFn: () => {
      const channels = [
        ...(tg ? [{ type: "telegram", chat_id: tg.trim() }] : []),
        ...(email ? [{ type: "email", to: email.trim() }] : []),
        ...(hook ? [{ type: "webhook", url: hook.trim() }] : []),
      ];
      const body = { name, channels, kinds, min_severity: sev, watch: useWatch ? watch : [], shelf_csv: shelf.trim() || null,
                     digest_hour: digest === "" ? null : Number(digest), instant, active: initial?.active ?? true };
      return initial ? send("PUT", `/alerts/subscriptions/${initial.id}`, body) : send("POST", "/alerts/subscriptions", body);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["alert-subs"] }); onDone(); },
  });
  const findChats = async () => {
    try { setChats((await get("/alerts/telegram/chats")).data); } catch (e) { alert(String((e as Error).message)); }
  };
  const toggleKind = (k: string) => setKinds(kinds.includes(k) ? kinds.filter((x) => x !== k) : [...kinds, k]);

  return (
    <div className="grid cols-2">
      <Panel title="What to watch">
        <div className="form">
          <label>Name <input value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label className="check"><input type="checkbox" checked={useWatch} onChange={(e) => setUseWatch(e.target.checked)} />
            Watchlist — {watch.length} items {watch.length === 0 && <span className="faint">(star ☆ SKUs, molecules, combinations, companies or groups first)</span>}</label>
          {useWatch && watch.length > 0 && (
            <div className="chips">{watch.map((w) => (
              <span key={w.key} className="chip">{w.label} <span className="star" onClick={() => setWatch(watch.filter((x) => x.key !== w.key))}>✕</span></span>
            ))}</div>
          )}
          <label>Shelf list (CSV) — re-checked whenever new bans, NSQ lists, recalls or price notices arrive
            <textarea className="code" rows={6} value={shelf} onChange={(e) => setShelf(e.target.value)} placeholder="name,batch,qty,expiry,manufacturer" />
          </label>
          <div className="row-gap" style={{ marginTop: 0 }}>
            <button onClick={() => setShelf(savedShelfCsv())}>USE MY SHELF LIST</button>
            <Link to="/shelf">edit on SHELF ›</Link>
          </div>
          <div className="faint">With no watchlist and no shelf list, the subscription receives every event that passes the filters below.</div>
          <label>Event kinds (none = all)</label>
          <div className="chips">{ALL_KINDS.map(([k, l]) => (
            <button key={k} className={kinds.includes(k) ? "active" : ""} onClick={() => toggleKind(k)}>{l}</button>
          ))}</div>
          <label>Minimum severity
            <select value={sev} onChange={(e) => setSev(e.target.value)}>
              <option value="info">info (everything)</option><option value="medium">medium</option><option value="high">high</option><option value="critical">critical only</option>
            </select>
          </label>
        </div>
      </Panel>
      <Panel title="Where to send it">
        <div className="form">
          <label className="check"><input type="checkbox" checked={instant} onChange={(e) => setInstant(e.target.checked)} /> Instant alerts (as each feed lands)</label>
          <label>Daily digest at (IST hour, blank = none)
            <select value={digest} onChange={(e) => setDigest(e.target.value)}>
              <option value="">no digest</option>{Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
            </select>
          </label>
          <label>Telegram chat id {!meta?.channels.telegram && <span className="neg"> — set TELEGRAM_BOT_TOKEN in .env first</span>}
            <span className="row-gap" style={{ marginTop: 0 }}>
              <input value={tg} onChange={(e) => setTg(e.target.value)} placeholder="e.g. 123456789" />
              <button disabled={!meta?.channels.telegram} onClick={findChats}>FIND MY CHAT</button>
            </span>
          </label>
          {chats && (chats.length ? <div className="chips">{chats.map((c) => <button key={c.chat_id} onClick={() => setTg(String(c.chat_id))}>{c.name} · {c.chat_id}</button>)}</div>
            : <div className="faint">No chats yet — open your bot in Telegram, send it any message, then press FIND MY CHAT again.</div>)}
          <label>Email {!meta?.channels.email && <span className="neg"> — set SMTP_* in .env first</span>}
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" /></label>
          <label>Webhook URL (Slack / Discord / Teams incoming webhook, https)
            <input value={hook} onChange={(e) => setHook(e.target.value)} placeholder="https://hooks.slack.com/services/…" /></label>
          <div className="faint">Every alert is also kept in the inbox here, whatever channels you choose.</div>
          <div className="row-gap">
            <button className="active" onClick={() => save.mutate()} disabled={save.isPending || !name.trim()}>{save.isPending ? "SAVING…" : initial ? "SAVE CHANGES" : "CREATE SUBSCRIPTION"}</button>
            <button onClick={onDone}>CANCEL</button>
          </div>
          {save.error && <div className="err">{String((save.error as Error).message)}</div>}
        </div>
      </Panel>
    </div>
  );
}
