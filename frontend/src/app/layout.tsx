import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Quartet · Engineering Console", description: "Your four-agent Python engineering team" };

export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
