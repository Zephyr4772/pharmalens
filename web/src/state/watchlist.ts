import { create } from "zustand";
import { persist } from "zustand/middleware";

// Watched entities, keyed "<type>:<id>" — p: product, m: molecule, c: combo, g: group (slug), co: company (slug)
export interface WatchItem {
  key: string;
  label: string;
  href: string;
  added: string;
}

interface WatchState {
  items: WatchItem[];
  lastSeenEventId: number;
  toggle: (it: Omit<WatchItem, "added">) => void;
  has: (key: string) => boolean;
  remove: (key: string) => void;
  setLastSeen: (id: number) => void;
}

export const useWatchlist = create<WatchState>()(
  persist(
    (set, get) => ({
      items: [],
      lastSeenEventId: 0,
      toggle: (it) =>
        set((s) =>
          s.items.some((x) => x.key === it.key)
            ? { items: s.items.filter((x) => x.key !== it.key) }
            : { items: [...s.items, { ...it, added: new Date().toISOString() }] }
        ),
      has: (key) => get().items.some((x) => x.key === key),
      remove: (key) => set((s) => ({ items: s.items.filter((x) => x.key !== key) })),
      setLastSeen: (id) => set({ lastSeenEventId: id }),
    }),
    { name: "pharmalens.watch.v4" }
  )
);
