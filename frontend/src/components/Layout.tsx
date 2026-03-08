/** Layout shell — header + content area. */

import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

const NAV = [
  { to: "/", label: "上傳" },
  { to: "/result", label: "結果" },
];

export default function Layout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();

  return (
    <div className="min-h-screen flex flex-col">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:text-indigo-700 focus:shadow"
      >
        跳到主要內容
      </a>

      <header className="sticky top-0 z-30 border-b border-white/70 bg-white/75 backdrop-blur-md">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <div>
            <h1 className="text-lg font-bold tracking-tight text-gray-900">繁中手寫 OCR</h1>
            <p className="text-xs text-gray-500">快速上傳、即時追蹤、一鍵複製結果</p>
          </div>

          <nav className="flex gap-2 rounded-xl border border-gray-200 bg-gray-50 p-1">
          {NAV.map((n) => (
            <Link
              key={n.to}
              to={n.to}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none ${
                pathname === n.to
                  ? "bg-white text-indigo-700 shadow-sm"
                  : "text-gray-600 hover:bg-white hover:text-gray-900"
              }`}
            >
              {n.label}
            </Link>
          ))}
          </nav>
        </div>
      </header>

      <main id="main-content" className="flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <div className="mx-auto w-full max-w-6xl">{children}</div>
      </main>
    </div>
  );
}
