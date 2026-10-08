import type { Metadata } from "next";
import { Plus_Jakarta_Sans, Caveat, Instrument_Serif } from "next/font/google";
import "./globals.css";

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const display = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
  variable: "--font-display",
  display: "swap",
});

const caveat = Caveat({
  subsets: ["latin"],
  variable: "--font-handwriting",
  display: "swap",
});

export const metadata: Metadata = {
  title: "MyRep — Your AI Professional Representative",
  description: "An AI-powered professional representative that represents your work, answers questions, and speaks for you.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${jakarta.variable} ${display.variable} ${caveat.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-screen w-full max-w-none bg-[#FBF8F4] text-[#16161D] font-sans antialiased selection:bg-[#F3E8C8] selection:text-[#16161D]">
        {children}
      </body>
    </html>
  );
}
