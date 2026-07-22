import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

// The reference UI uses a geometric grotesque with tight apertures.
// Plus Jakarta is the closest widely-available match; the system stack is the
// fallback so a build without network access still renders sensibly.
const sans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  fallback: ["ui-sans-serif", "system-ui", "Segoe UI", "Helvetica Neue", "Arial"],
});

export const metadata: Metadata = {
  title: "Leadaro — Outreach",
  description: "AI voice and call outreach campaigns",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={sans.className}>
      <body>{children}</body>
    </html>
  );
}
