import type { Metadata, Viewport } from "next";
import { Anton, Hanken_Grotesk, JetBrains_Mono } from "next/font/google";
import "lenis/dist/lenis.css";
import "./globals.css";

const display = Anton({ subsets: ["latin"], weight: "400", variable: "--font-anton", display: "swap" });
const sans = Hanken_Grotesk({ subsets: ["latin"], variable: "--font-hanken", display: "swap" });
// Mono is only for timestamps and message IDs.
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" });

export const metadata: Metadata = {
  title: "AddaMind: every adda, remembered",
  description:
    "Upload your WhatsApp chats and ask four agents about them. Every answer links to the messages it came from.",
};

export const viewport: Viewport = {
  themeColor: "#111111",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${display.variable} ${sans.variable} ${mono.variable} antialiased`}>
      <body>{children}</body>
    </html>
  );
}
