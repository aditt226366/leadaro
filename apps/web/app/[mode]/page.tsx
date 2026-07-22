import type { Mode } from "@/components/shell/Sidebar";
import DashboardClient from "./DashboardClient";

export default async function Page({
  params,
}: {
  params: Promise<{ mode: string }>;
}) {
  const { mode } = await params;
  return <DashboardClient mode={mode as Mode} />;
}
