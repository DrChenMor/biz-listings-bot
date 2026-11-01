import { signIn } from "@/lib/actions";

export default async function Login({ searchParams }: { searchParams: Promise<{ wrong?: string }> }) {
  const { wrong } = await searchParams;
  return (
    <div className="loginwrap">
      <form action={signIn} className="card login">
        <h1>Deal desk</h1>
        {wrong ? <p className="note warn">That password didn't work.</p> : null}
        <label className="field">Who are you?
          <select name="name" defaultValue="Chen">
            <option>Chen</option>
            <option>Partner</option>
          </select>
        </label>
        <label className="field">Password
          <input className="input" type="password" name="password" required autoComplete="current-password" />
        </label>
        <button type="submit" className="btn primary">Sign in</button>
      </form>
    </div>
  );
}
