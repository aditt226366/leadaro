"use client";
import { useState } from "react";
import {
  PhoneOutgoing, PhoneIncoming, Target, CalendarDays, SlidersHorizontal,
  Download, ArrowUpDown, MoreHorizontal, TrendingUp, PieChart as PieIcon, Users,
} from "lucide-react";
import { PageHeader } from "@/components/shell/TopBar";
import { Card, StatCard, ChartCard } from "@/components/ui/Card";
import { Button, PillSelect } from "@/components/ui/Button";
import { Chip, StatusChip } from "@/components/ui/Chip";
import { DataTable, IconCell, MiniBar, type Column } from "@/components/ui/DataTable";
import { TrendArea, HighlightBars, Donut, LegendList } from "@/components/ui/Charts";
import type { Mode } from "@/components/shell/Sidebar";
import {
  trend, weekday, outcomes, campaigns, kpis, secondaryStats, type CampaignRow,
} from "@/lib/mock";
import { num } from "@/lib/cn";

const KPI_ICONS = [PhoneOutgoing, Target, PhoneIncoming];

export default function DashboardClient({ mode }: { mode: Mode }) {
  const [period, setPeriod] = useState("monthly");
  const [range, setRange] = useState("may");

  const cards = kpis(mode);
  const totalOutcomes = outcomes.reduce((s, o) => s + o.value, 0);

  const columns: Column<CampaignRow>[] = [
    {
      key: "name",
      header: "Campaign",
      cell: (r) => (
        <IconCell
          icon={r.name.slice(0, 2).toUpperCase()}
          title={r.name}
          subtitle={r.type}
        />
      ),
    },
    { key: "status", header: "Status", cell: (r) => <StatusChip status={r.status} /> },
    { key: "leads", header: "Leads", align: "right", cell: (r) => num(r.leads) },
    { key: "calls", header: "Calls", align: "right", cell: (r) => num(r.calls) },
    { key: "answered", header: "Answered", align: "right", cell: (r) => num(r.answered) },
    {
      key: "conversion",
      header: "Conversion",
      cell: (r) => <MiniBar value={r.conversion} />,
    },
    {
      key: "actions",
      header: "",
      align: "right",
      width: "44px",
      cell: () => (
        <button className="text-faint hover:text-ink" aria-label="Row actions">
          <MoreHorizontal size={15} />
        </button>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle={
          mode === "voice"
            ? "AI voice campaigns — reach, engagement and conversion at a glance."
            : "Connect with qualified leads through automated call campaigns powered by smart AI routing."
        }
      >
        <PillSelect
          icon={CalendarDays}
          value={range}
          onChange={setRange}
          options={[
            { value: "may", label: "May 1 – May 31" },
            { value: "apr", label: "Apr 1 – Apr 30" },
            { value: "q2", label: "Q2 2026" },
          ]}
        />
        <PillSelect
          value={period}
          onChange={setPeriod}
          options={[
            { value: "daily", label: "Daily" },
            { value: "weekly", label: "Weekly" },
            { value: "monthly", label: "Monthly" },
          ]}
        />
        <Button><SlidersHorizontal size={13} /> Filter</Button>
        <Button><Download size={13} /> Export</Button>
      </PageHeader>

      {/* ── row 1: headline KPIs ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-card sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((k, i) => (
          <StatCard
            key={k.label}
            icon={KPI_ICONS[i]}
            label={k.label}
            value={k.value}
            delta={k.delta}
            hint={`${k.label} vs previous period`}
          />
        ))}
      </div>

      {/* secondary metric strip — the rest of the FRD dashboard cards */}
      <Card className="mt-card" pad={false}>
        <dl className="grid grid-cols-2 divide-line sm:grid-cols-3 lg:grid-cols-6 lg:divide-x">
          {secondaryStats(mode).map((s) => (
            <div key={s.label} className="px-card py-3.5">
              <dt className="text-sm text-muted">{s.label}</dt>
              <dd className="tnum mt-0.5 text-lg font-semibold text-ink">{s.value}</dd>
            </div>
          ))}
        </dl>
      </Card>

      {/* ── row 2: performance trend + weekday connect ──────────────────── */}
      <div className="mt-card grid grid-cols-1 gap-card lg:grid-cols-3">
        <ChartCard
          className="lg:col-span-2"
          title="Call Performance Overview"
          icon={TrendingUp}
          lead={{ value: "12,540", delta: 18.2, caption: "+1,920 calls vs last period" }}
          actions={
            <>
              <Button><SlidersHorizontal size={12} /> Filter</Button>
              <Button><ArrowUpDown size={12} /> Sort</Button>
              <Button variant="ghost" className="px-1.5"><MoreHorizontal size={14} /></Button>
            </>
          }
        >
          <TrendArea
            data={trend}
            x="d"
            series={[
              { key: "calls", label: "Calls" },
              { key: "answered", label: "Answered" },
              { key: "interested", label: "Interested" },
            ]}
          />
        </ChartCard>

        <ChartCard
          title="Connected by Day"
          icon={Users}
          lead={{ value: "11,610", delta: 8.3, caption: "+749 connected" }}
          actions={
            <PillSelect
              value={period}
              onChange={setPeriod}
              options={[
                { value: "weekly", label: "Weekly" },
                { value: "monthly", label: "Monthly" },
              ]}
            />
          }
        >
          <HighlightBars data={weekday} x="d" y="connected" />
        </ChartCard>
      </div>

      {/* ── row 3: outcome split + recent campaigns ─────────────────────── */}
      <div className="mt-card grid grid-cols-1 gap-card lg:grid-cols-3">
        <ChartCard
          title="Call Outcomes"
          icon={PieIcon}
          actions={
            <PillSelect
              value={period}
              onChange={setPeriod}
              options={[
                { value: "monthly", label: "Monthly" },
                { value: "weekly", label: "Weekly" },
              ]}
            />
          }
        >
          <Donut
            data={outcomes}
            centerValue={num(totalOutcomes)}
            centerLabel="Total Calls"
          />
          <div className="mt-4 border-t border-line pt-4">
            <LegendList
              items={outcomes.map((o) => ({
                name: o.name,
                value: `${num(o.value)}  ·  ${((o.value / totalOutcomes) * 100).toFixed(1)}%`,
              }))}
            />
          </div>
        </ChartCard>

        <Card className="lg:col-span-2" pad={false}>
          <div className="flex items-center justify-between px-card pb-3 pt-card">
            <h3 className="text-base font-semibold text-ink">Recent Campaigns</h3>
            <div className="flex items-center gap-2">
              <Chip tone="primary">{campaigns.length} total</Chip>
              <a
                href={`/${mode}/campaigns`}
                className="text-sm font-semibold text-primary-ink hover:underline"
              >
                View All
              </a>
            </div>
          </div>
          <div className="px-card pb-card">
            <DataTable columns={columns} rows={campaigns} selectable />
          </div>
        </Card>
      </div>
    </>
  );
}
