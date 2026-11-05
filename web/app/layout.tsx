import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Clueless | Learning buddy",
  description: "A personalised, evidence-based learning buddy for IIT Bhubaneswar students.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-page text-ink antialiased">{children}</body>
    </html>
  );
}
