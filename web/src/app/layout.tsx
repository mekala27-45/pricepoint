import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "pricepoint | The shape of demand",
  description:
    "Explore price, demand and uncertainty through a measured retail pricing system built on public data.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
