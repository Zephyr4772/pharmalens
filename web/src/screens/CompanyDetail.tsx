import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { get, inr, num } from "../lib/api";
import { Dossier } from "../components/Dossier";
import { AutoGroup, CompanyApprovals, LaunchSignals, Timeline } from "../components/Linked";
import { Debarments, Licences, Tenders } from "../components/Depth";
import { ErrorBox, Kpi, Loading, Star } from "../components/ui";

export default function CompanyDetail() {
  const { slug } = useParams();
  const c = useQuery({ queryKey: ["company", slug], queryFn: () => get(`/companies/${slug}`) });
  if (c.isLoading) return <Loading />;
  if (c.error) return <ErrorBox e={c.error} />;
  const d = c.data;
  return (
    <div className="stack">
      <div className="detail-head">
        <Star k={`co:${d.slug}`} label={d.name} href={`/co/${d.slug}`} />
        <span className="detail-title">{d.name}</span>
        {d.parent && <span>part of <Link to={`/g/${d.parent_slug}`}>{d.parent}</Link></span>}
        <span className="muted">{d.top_class}</span>
      </div>
      <div className="kpis">
        <Kpi label="SKUs" value={num(d.product_count)} />
        <Kpi label="Active" value={num(d.active_count)} />
        <Kpi label="Molecules" value={num(d.molecule_count)} />
        <Kpi label="Median MRP" value={inr(d.median_mrp)} tone="amber" />
        <Kpi label="NSQ listings" value={num(d.nsq.length)} tone={d.nsq.length ? "down" : undefined} />
        <Kpi label="Banned-FDC SKUs" value={num(d.banned_skus.length)} tone={d.banned_skus.length ? "down" : undefined} />
      </div>
      <div className="grid cols-2">
        <Tenders rows={d.tenders} />
        <Licences rows={d.licences} />
      </div>
      <Debarments rows={d.debarments} />
      <div className="grid cols-2">
        <AutoGroup g={d.auto_group} />
        <CompanyApprovals rows={d.approvals_linked} />
      </div>
      <div className="grid cols-2">
        <Timeline rows={d.timeline} sub="events linked to this marketer (NSQ, debarments, launches, recalls) and its group" />
        <LaunchSignals rows={d.launches} showCompany={false} />
      </div>
      <Dossier d={d} />
    </div>
  );
}
