import { useQuery } from "@tanstack/react-query";
import { get } from "../lib/api";

// Who is viewing: the server reads the Tailscale identity. Guests (shared access) get read-only screens;
// admin actions and alerts are the owner's. Until the answer arrives, assume guest (hide, never flash controls).
export function useMe() {
  const q = useQuery({
    queryKey: ["me"],
    queryFn: () => get<{ login: string | null; name: string | null; owner: boolean }>("/me"),
    staleTime: Infinity,
  });
  return { owner: q.data?.owner ?? false, name: q.data?.name ?? q.data?.login ?? null, loaded: q.isSuccess };
}
