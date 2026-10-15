import { create } from "zustand";
import type { Row } from "../lib/api";

// Live event feed fed by the /api/v1/stream SSE connection.
interface LiveState {
  connected: boolean;
  events: Row[];
  quotesAt: string | null;
  unseen: number;
  push: (e: Row) => void;
  setConnected: (v: boolean) => void;
  setQuotesAt: (v: string) => void;
  markSeen: () => void;
}

export const useLive = create<LiveState>()((set) => ({
  connected: false,
  events: [],
  quotesAt: null,
  unseen: 0,
  push: (e) => set((s) => ({ events: [e, ...s.events].slice(0, 200), unseen: s.unseen + 1 })),
  setConnected: (v) => set({ connected: v }),
  setQuotesAt: (v) => set({ quotesAt: v }),
  markSeen: () => set({ unseen: 0 }),
}));

let es: EventSource | null = null;

export function connectStream(onQuotes: () => void, onEvent: () => void) {
  if (es) return;
  const open = () => {
    es = new EventSource("/api/v1/stream");
    es.addEventListener("hello", () => useLive.getState().setConnected(true));
    es.addEventListener("event", (m) => {
      useLive.getState().push(JSON.parse((m as MessageEvent).data));
      onEvent();
    });
    es.addEventListener("quotes", (m) => {
      useLive.getState().setQuotesAt(JSON.parse((m as MessageEvent).data).at);
      onQuotes();
    });
    es.onerror = () => {
      useLive.getState().setConnected(false);
      es?.close();
      es = null;
      setTimeout(open, 5000);
    };
  };
  open();
}
