import Link from "next/link";
import type { ReactNode } from "react";
import { signOut } from "@/lib/actions";

const SCREENS = [["/", "Today"], ["/find", "Find"], ["/pipeline", "Pipeline"], ["/sources", "Sources"]];

export function Shell({ user, active, children }: { user: string; active: string; children: ReactNode }) {
  return (
    <div className="app">
      <aside className="side">
        <div className="brand">Deal desk<span className="brandsub">WA businesses to approach</span></div>
        <nav className="navlist" aria-label="Main">
          {SCREENS.map(([href, label]) => (
            <Link key={href} href={href} className={href === active ? "nav on" : "nav"}>{label}</Link>
          ))}
        </nav>
        <form action={signOut} className="who">
          <span>Signed in as {user}.</span>
          <button type="submit" className="plain">Sign out</button>
        </form>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
