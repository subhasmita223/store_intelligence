import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Store Intelligence",
  description: "Real-time retail analytics platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full antialiased">{children}</body>
    </html>
  );
}
