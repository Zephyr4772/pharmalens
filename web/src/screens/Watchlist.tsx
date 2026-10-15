import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { get, type Row } from "../lib/api";
import { useWatchlist } from "../state/watchlist";
import { Empty, EventRow, Panel } from "../components/ui";

const TYPE: Record<string, string> = { p: "SKU", m: "MOLECULE", c: "COMBINATION", g: "GROUP", co: "COMPANY" };

// Events relevant to the watchlist: matched by entity where possible, else by name in the headline.
function useWatchEvents(items: { key: string; label: string }[]) {
  return useQuery({
    queryKey: ["events", "watch", items.map((i) => i.key).join("|")],
    enabled: items.length > 0,
    queryFn: async () => {
      const out: Row[] = [];
      for (const it of items.slice(0, 20)) {
        const word = it.label.split(/\s+/).slice(0, 2).join(" ");
        const r = await get<{ data: Row[] }>("/events", { q: word, limit: 15 });
        out.push(...r.data);
      }
      const seen = new Set<number>();
      return out.filter((e) => !seen.has(e.id) && seen.add(e.id)).sort((a, b) => (a.ts < b.ts ? 1 : -1)).slice(0, 80);
    },
    refetchInterval: 300_000,
  });
}

export default function Watchlist() {
  const { items, remove } = useWatchlist();
  const ev = useWatchEvents(items);
  if (!items.length) return <Empty>Star (☆) any SKU, molecule, combination, company or group to track it here.</Empty>;
  return (
    <div className="grid cols-3">
      <Panel title="Watching" sub={`${items.length} items`}>
        <table className="tt"><tbody>{items.map((i) => (
          <tr key={i.key}>
            <td className="mut">{TYPE[i.key.split(":")[0]] ?? ""}</td>
            <td><Link to={i.href}>{i.label}</Link></td>
            <td className="num"><button onClick={() => remove(i.key)}>✕</button></td>
          </tr>
        ))}</tbody></table>
      </Panel>
      <Panel title="Activity on watched items" sub="bans · NSQ · price notices · launches · news" className="span-2">
        {ev.isLoading ? <div className="loading">loading…</div> : ev.data?.length ? ev.data.map((e) => <EventRow key={e.id} e={e} />) : <Empty>no events mention your watched items yet</Empty>}
      </Panel>
    </div>
  );
}
