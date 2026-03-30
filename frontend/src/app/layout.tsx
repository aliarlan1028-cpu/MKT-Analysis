import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CryptoEdge Pro - 合约交易分析",
  description: "AI驱动的加密货币合约交易分析平台",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased dark">
      <body className="min-h-full flex flex-col bg-background text-foreground">
        {children}
      </body>
    </html>
  );
}
