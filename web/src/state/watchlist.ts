import { create } from "zustand";
import { persist } from "zustand/middleware";
import { get as apiGet, send } from "../lib/api";

// Watched entities, keyed "<type>:<id>" — p: product, m: molecule, c: combo, g: group (slug), co: company (slug).
// The server keeps the list (per Tailscale login) and shares it with Specs and the alert engine; this store is the
// browser's cache of it, so stars show instantly and still work if the server is briefly unreachable.
export interface WatchItem {
  key: string;
  label: string;
  href: string;
  added: string;
}

interface WatchState {
  items: WatchItem[];
  lastSeenEventId: number;
  synced: boolean;
  load: () => Promise<void>;
  toggle: (it: Omit<WatchItem, "added">) => void;
  has: (key: string) => boolean;
  remove: (key: string) => void;
  setLastSeen: (id: number) => void;
}

const path = (key: string) => `/watchlist/${encodeURIComponent(key)}`;

export const useWatchlist = create<WatchState>()(
  persist(
    (set, get) => ({
      items: [],
      lastSeenEventId: 0,
      synced: false,
      load: async () => {
        try {
          const r = await apiGet<{ data: any[]; signed_in: boolean }>("/watchlist");
          if (!r.signed_in) return;
          const server: WatchItem[] = r.data.map((x) => ({ key: x.key, label: x.label, href: x.href ?? "", added: x.added_at }));
          // one-time move of stars made before the list lived on the server
          if (!get().synced) {
            const have = new Set(server.map((x) => x.key));
            for (const it of get().items.filter((x) => !have.has(x.key))) {
              await send("PUT", "/watchlist", { key: it.key, label: it.label, href: it.href });
              server.push(it);
            }
          }
          set({ items: server, synced: true });
        } catch {
          /* offline or not signed in: keep the cached list */
        }
      },
      toggle: (it) => {
        const on = get().items.some((x) => x.key === it.key);
        set((s) => ({
          items: on ? s.items.filter((x) => x.key !== it.key) : [...s.items, { ...it, added: new Date().toISOString() }],
        }));
        (on ? send("DELETE", path(it.key)) : send("PUT", "/watchlist", { key: it.key, label: it.label, href: it.href })).catch(() => {});
      },
      has: (key) => get().items.some((x) => x.key === key),
      remove: (key) => {
        set((s) => ({ items: s.items.filter((x) => x.key !== key) }));
        send("DELETE", path(key)).catch(() => {});
      },
      setLastSeen: (id) => set({ lastSeenEventId: id }),
    }),
    { name: "pharmalens.watch.v4" }
  )
);
