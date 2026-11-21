import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

import { CommandPalette, Rail, StatusBar } from "@/components/shell";
import { AnalysisProvider } from "@/lib/analysis-store";

import "./globals.css";

const plexSans = IBM_Plex_Sans({ variable: "--font-plex-sans", subsets: ["latin", "latin-ext"], weight: ["400", "500", "600"] });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin", "latin-ext"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "SCAM DNA",
  description: "Łączenie fałszywych reklam w kampanie na podstawie wspólnych śladów",
};

// Motyw ustawiamy przed pierwszym malowaniem, żeby jasny nie mignął ciemnym.
const themeScript = `try{document.documentElement.dataset.theme=localStorage.getItem("scamdna.theme")==="light"?"light":"dark"}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pl" data-theme="dark" suppressHydrationWarning className={`${plexSans.variable} ${plexMono.variable} h-full antialiased`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="flex h-full overflow-hidden">
        <AnalysisProvider>
          <Rail />
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            <div className="flex min-h-0 flex-1 flex-col">{children}</div>
            <StatusBar />
          </div>
          <CommandPalette />
        </AnalysisProvider>
      </body>
    </html>
  );
}
