import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Telugu <-> English Voice Translator",
  description:
    "Real-time microphone translation between Telugu and English with Windows audio-device routing.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
