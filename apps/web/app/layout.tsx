"use client"

import { Inter } from "next/font/google"
import "./globals.css"

// #region agent log
import { useEffect } from 'react';
// #endregion

const inter = Inter({ 
  subsets: ["latin", "cyrillic"],
  variable: "--font-inter",
  display: "swap",
})

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // #region agent log
  useEffect(() => {
    // Проверяем, применились ли CSS переменные из globals.css
    const rootStyles = getComputedStyle(document.documentElement);
    const hasTailwindVars = rootStyles.getPropertyValue('--background') !== '';
    
    fetch('http://127.0.0.1:7242/ingest/3fac9a8f-3caa-4120-a5d6-1456b6683183', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        location: 'layout.tsx',
        message: 'RootLayout rendered',
        data: { 
          hasTailwindVars,
          background: rootStyles.backgroundColor,
          className: document.documentElement.className,
          interClass: inter.className
        },
        timestamp: Date.now(),
        sessionId: 'debug-session',
        hypothesisId: 'H2'
      })
    }).catch(() => {});
  }, []);
  // #endregion

  return (
    <html lang="ru" className="dark">
      <body className={inter.className}>{children}</body>
    </html>
  )
}
