import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const COOKIE = "deal-desk";
const THIRTY_DAYS = 30 * 24 * 60 * 60;

function secret(): string {
  const value = process.env.APP_SECRET;
  if (!value) throw new Error("APP_SECRET is not set");
  return value;
}

function sign(payload: string): string {
  return createHmac("sha256", secret()).update(payload).digest("hex");
}

function same(a: string, b: string): boolean {
  const hash = (text: string) => createHash("sha256").update(text).digest();
  return timingSafeEqual(hash(a), hash(b));
}

export function passwordIsRight(password: string): boolean {
  const expected = process.env.APP_PASSWORD;
  return Boolean(expected) && same(password, expected as string);
}

export async function startSession(name: string): Promise<void> {
  const payload = `${encodeURIComponent(name)}.${Math.floor(Date.now() / 1000) + THIRTY_DAYS}`;
  (await cookies()).set(COOKIE, `${payload}.${sign(payload)}`, {
    httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: THIRTY_DAYS,
  });
}

export async function endSession(): Promise<void> {
  (await cookies()).delete(COOKIE);
}

/** Who is signed in. Every page and action calls this: the data is never shown without a valid session. */
export async function requireUser(): Promise<string> {
  const [name, expires, signature] = ((await cookies()).get(COOKIE)?.value ?? "").split(".");
  const valid = name && expires && signature && same(signature, sign(`${name}.${expires}`)) && Number(expires) * 1000 > Date.now();
  if (!valid) redirect("/login");
  return decodeURIComponent(name);
}
