import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "CRM Gallo",
  description: "AI-powered multilingual CRM",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
