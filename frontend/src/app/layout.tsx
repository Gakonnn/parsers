import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ParserDesk | Parsers Platform",
  description: "Многопользовательская платформа для управления парсерами 2GIS, OLX, Krisha и Kolesa.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
