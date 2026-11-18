import type { Metadata } from "next";
import { Bricolage_Grotesque, DM_Sans } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";

// The same pair as Lumi: Bricolage Grotesque for headings, DM Sans for everything else.
const display = Bricolage_Grotesque({ variable: "--font-display", subsets: ["latin"], weight: ["500", "600", "700", "800"] });
const body = DM_Sans({ variable: "--font-body", subsets: ["latin"] });

export const metadata: Metadata = { title: "Deal desk", robots: { index: false, follow: false } };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body>{children}</body>
    </html>
  );
}
