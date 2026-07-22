import { notFound } from "next/navigation";
import { Sidebar, type Mode } from "@/components/shell/Sidebar";
import { TopBar } from "@/components/shell/TopBar";

export default async function ModeLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ mode: string }>;
}) {
  const { mode } = await params;
  if (mode !== "voice" && mode !== "call") notFound();

  return (
    <div className="min-h-screen bg-page">
      <Sidebar mode={mode as Mode} />
      {/* Sidebar is an overlay below lg, so the main column takes full width there. */}
      <div className="lg:pl-sidebar">
        <TopBar unread={8} />
        <main className="px-4 py-4 sm:px-6 sm:py-5">{children}</main>
      </div>
    </div>
  );
}

export function generateStaticParams() {
  return [{ mode: "voice" }, { mode: "call" }];
}
