import type { Metadata } from "next";

export const metadata: Metadata = { title: "Privacy · Deal desk" };

/** The privacy page Google asks for before the Google sign-in can leave testing mode. Public: no sign-in needed. */
export default function Privacy() {
  return (
    <main className="main" style={{ maxWidth: 720, margin: "0 auto" }}>
      <h1>Deal desk privacy</h1>
      <p className="lede">Deal desk is a private tool used only by its two owners, Chen and Tom, to keep track of businesses they may buy.</p>
      <section className="card stack">
        <h2>What it does with your Google account</h2>
        <p>When Tom connects his Google account, Deal desk can read and add files in the business folders in his Google Drive, such as saving a filled-in worksheet or an uploaded document into a business&apos;s folder. It only does this when Chen or Tom asks it to, on the website.</p>
        <p>The sign-in is kept encrypted in Deal desk&apos;s own database. It is never shared with, sold to or shown to anyone else, and it is not used for advertising.</p>
        <p>To stop it at any time, press Disconnect on the Sources page, or remove Deal desk at <a href="https://myaccount.google.com/permissions">myaccount.google.com/permissions</a>.</p>
        <h2>Who can use it</h2>
        <p>Only Chen and Tom can sign in. Deal desk has no other users and collects nothing from the public.</p>
        <h2>Contact</h2>
        <p>Questions: email contacttomharari@gmail.com.</p>
      </section>
    </main>
  );
}
