import { Bot, Database, KanbanSquare, LogOut, Search, Sun } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { signOut } from "@/lib/actions";

const SCREENS = [
  { href: "/", label: "Today", icon: Sun },
  { href: "/find", label: "Find", icon: Search },
  { href: "/pipeline", label: "Pipeline", icon: KanbanSquare },
  { href: "/agent", label: "Agent", icon: Bot },
  { href: "/sources", label: "Sources", icon: Database },
];

export function Shell({ user, active, children }: { user: string; active: string; children: ReactNode }) {
  return (
    <div className="app">
      <aside className="side noprint">
        <div className="brand"><span className="brandmark" aria-hidden="true" />Deal desk<span className="brandsub">WA businesses to approach</span></div>
        <nav className="navlist" aria-label="Main">
          {SCREENS.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} className={href === active ? "nav on" : "nav"} aria-current={href === active ? "page" : undefined}>
              <Icon className="navicon" aria-hidden="true" />{label}
            </Link>
          ))}
        </nav>
        <form action={signOut} className="who">
          <span className="avatar" aria-hidden="true">{user.slice(0, 1)}</span>
          <span className="whoname">{user}</span>
          <button type="submit" className="iconbtn" aria-label="Sign out" title="Sign out"><LogOut aria-hidden="true" /></button>
        </form>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
