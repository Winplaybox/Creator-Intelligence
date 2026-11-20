import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Creator Intelligence Studio", template: "%s | Creator Intelligence" },
  description: "AI-powered insights and tools to help YouTube creators plan, analyze, and grow.",
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  robots: { index: false, follow: false }
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
