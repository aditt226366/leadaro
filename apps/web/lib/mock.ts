/**
 * Seed data for UI development. Every shape here matches the API response
 * schema in services/api/schemas.py, so swapping to live data is a fetch call,
 * not a refactor. Delete once all screens are wired.
 */
import type { Mode } from "@/components/shell/Sidebar";

export const trend = [
  { d: "May 1",  calls: 3120, answered: 1180, interested: 402 },
  { d: "May 5",  calls: 3560, answered: 1402, interested: 468 },
  { d: "May 9",  calls: 4180, answered: 1690, interested: 552 },
  { d: "May 13", calls: 3890, answered: 1544, interested: 511 },
  { d: "May 17", calls: 4620, answered: 1902, interested: 646 },
  { d: "May 21", calls: 5240, answered: 2210, interested: 742 },
  { d: "May 25", calls: 4980, answered: 2088, interested: 705 },
  { d: "May 29", calls: 5610, answered: 2412, interested: 813 },
];

export const weekday = [
  { d: "Sun", connected: 620 },
  { d: "Mon", connected: 1840 },
  { d: "Tue", connected: 2470 },
  { d: "Wed", connected: 1960 },
  { d: "Thu", connected: 2110 },
  { d: "Fri", connected: 1730 },
  { d: "Sat", connected: 880 },
];

export const outcomes = [
  { name: "Interested",     value: 4280 },
  { name: "Not Interested", value: 3610 },
  { name: "Voicemail",      value: 1850 },
  { name: "Callback",       value: 1750 },
  { name: "Wrong Number",   value: 640 },
];

export const hourly = [
  { h: "9a", rate: 22 }, { h: "10a", rate: 31 }, { h: "11a", rate: 38 },
  { h: "12p", rate: 26 }, { h: "1p", rate: 19 }, { h: "2p", rate: 34 },
  { h: "3p", rate: 41 }, { h: "4p", rate: 36 }, { h: "5p", rate: 28 },
];

export type CampaignRow = {
  id: string;
  name: string;
  type: string;
  status: "active" | "paused" | "completed" | "scheduled" | "draft";
  leads: number;
  calls: number;
  answered: number;
  interested: number;
  conversion: number;
};

export const campaigns: CampaignRow[] = [
  { id: "c1", name: "SaaS Outreach — May", type: "Demo Booking",    status: "active",    leads: 5000, calls: 3960, answered: 1640, interested: 548, conversion: 35.2 },
  { id: "c2", name: "Renewal Drive Q2",    type: "Renewal Reminder", status: "active",    leads: 2600, calls: 2410, answered: 1180, interested: 342, conversion: 30.4 },
  { id: "c3", name: "Demo Booking Sprint", type: "Cold Calling",     status: "scheduled", leads: 3000, calls: 0,    answered: 0,    interested: 0,   conversion: 0 },
  { id: "c4", name: "Insurance Follow-up", type: "Follow-up Calls",  status: "paused",    leads: 1800, calls: 1204, answered: 502,  interested: 168, conversion: 27.9 },
  { id: "c5", name: "Recruiter Screening", type: "Recruitment",      status: "completed", leads: 940,  calls: 940,  answered: 431,  interested: 205, conversion: 47.6 },
];

/** Headline KPIs differ per surface — Voice is AI-only, Call includes transfers. */
export function kpis(mode: Mode) {
  return mode === "voice"
    ? [
        { label: "Calls Initiated",  value: "12,540", delta: 18.2 },
        { label: "Answer Rate",      value: "42.6%",  delta: 6.4 },
        { label: "Interested Leads", value: "2,350",  delta: 12.9 },
      ]
    : [
        { label: "Active Calls",     value: "12,450", delta: 18.2 },
        { label: "Meetings Booked",  value: "1,245",  delta: 8.3 },
        { label: "Revenue Attributed", value: "$245,680", delta: 32.4 },
      ];
}

/** Secondary strip — the remaining FRD dashboard metrics. */
export function secondaryStats(mode: Mode) {
  const shared = [
    { label: "Avg Duration",     value: "2:45" },
    { label: "Voicemails",       value: "1,850" },
    { label: "Callbacks",        value: "1,750" },
    { label: "Conversion",       value: "18.7%" },
  ];
  return mode === "voice"
    ? [
        { label: "Total Campaigns", value: "24" },
        { label: "AI Speaking Time", value: "6,782m" },
        ...shared,
      ]
    : [
        { label: "Queued Calls",    value: "980" },
        { label: "Transferred",     value: "1,250" },
        ...shared,
      ];
}
