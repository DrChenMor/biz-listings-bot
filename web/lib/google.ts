/**
 * "Connect Google Drive": Tom signs in once, and the website can then save files into the Acquisitions folders as Tom.
 * Reading folders stays with the robot account (lib/drive.ts). Needs GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET.
 * Server only.
 */
import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";
import { db } from "./db";

const SCOPES = "openid email https://www.googleapis.com/auth/drive";
const GOOGLE_DOC = "application/vnd.google-apps.document";

export type Connection = { email: string; connected_by: string; connected_at: string };

export function connectReady(): boolean {
  return Boolean(process.env.GOOGLE_OAUTH_CLIENT_ID && process.env.GOOGLE_OAUTH_CLIENT_SECRET);
}

/** The refresh token is stored encrypted, with a key made from APP_SECRET. */
function cipherKey(): Buffer {
  return createHash("sha256").update(`${process.env.APP_SECRET}:google-drive`).digest();
}

function seal(text: string): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", cipherKey(), iv);
  const body = Buffer.concat([cipher.update(text, "utf8"), cipher.final()]);
  return [iv, cipher.getAuthTag(), body].map((b) => b.toString("base64url")).join(".");
}

function unseal(sealed: string): string {
  const [iv, tag, body] = sealed.split(".").map((part) => Buffer.from(part, "base64url"));
  const decipher = createDecipheriv("aes-256-gcm", cipherKey(), iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(body), decipher.final()]).toString("utf8");
}

export function signInLink(redirectUri: string, state: string): string {
  return `https://accounts.google.com/o/oauth2/v2/auth?${new URLSearchParams({
    client_id: process.env.GOOGLE_OAUTH_CLIENT_ID ?? "", redirect_uri: redirectUri, response_type: "code", scope: SCOPES,
    access_type: "offline", prompt: "consent", include_granted_scopes: "true", state,
  })}`;
}

async function tokenCall(params: Record<string, string>) {
  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST", cache: "no-store", headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: process.env.GOOGLE_OAUTH_CLIENT_ID ?? "", client_secret: process.env.GOOGLE_OAUTH_CLIENT_SECRET ?? "", ...params }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(`Google said no: ${data.error_description ?? data.error}`);
  return data;
}

/** Finish the sign-in: keep the refresh token and note whose Drive it is. */
export async function finishSignIn(code: string, redirectUri: string, who: string): Promise<string> {
  const data = await tokenCall({ code, redirect_uri: redirectUri, grant_type: "authorization_code" });
  if (!data.refresh_token) throw new Error("Google didn't give lasting access. Remove Deal desk in your Google account's third-party access, then connect again.");
  const email = JSON.parse(Buffer.from(String(data.id_token).split(".")[1], "base64url").toString()).email as string;
  const { error } = await db().from("google_connections").upsert({ id: "drive", email, refresh_token: seal(data.refresh_token), connected_by: who, connected_at: new Date().toISOString() });
  if (error) throw new Error(error.message);
  return email;
}

export async function connection(): Promise<Connection | null> {
  const { data } = await db().from("google_connections").select("email, connected_by, connected_at").eq("id", "drive").maybeSingle();
  return data as Connection | null;
}

export async function disconnect(): Promise<void> {
  const { data } = await db().from("google_connections").select("refresh_token").eq("id", "drive").maybeSingle();
  if (data) {
    await fetch(`https://oauth2.googleapis.com/revoke?token=${encodeURIComponent(unseal(data.refresh_token))}`, { method: "POST", cache: "no-store" }).catch(() => null);
  }
  await db().from("google_connections").delete().eq("id", "drive");
}

async function accessToken(): Promise<string> {
  const { data } = await db().from("google_connections").select("refresh_token").eq("id", "drive").maybeSingle();
  if (!data) throw new Error("Google Drive isn't connected. Connect it on the Sources page.");
  return (await tokenCall({ refresh_token: unseal(data.refresh_token), grant_type: "refresh_token" })).access_token;
}

export async function createFolder(parentId: string, name: string): Promise<string> {
  const response = await fetch("https://www.googleapis.com/drive/v3/files?fields=id", {
    method: "POST", cache: "no-store", headers: { Authorization: `Bearer ${await accessToken()}`, "Content-Type": "application/json" },
    body: JSON.stringify({ name, mimeType: "application/vnd.google-apps.folder", parents: [parentId] }),
  });
  if (!response.ok) throw new Error(`Google Drive didn't make the folder (HTTP ${response.status}).`);
  return (await response.json()).id;
}

/**
 * Start an upload into a folder. The browser then sends the file straight to the returned address, so big files such
 * as videos never pass through the website. `origin` is the website's address, which Google lets send the file.
 */
export async function startUpload(folderId: string, name: string, type: string, size: number, origin: string): Promise<string> {
  const response = await fetch("https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id", {
    method: "POST", cache: "no-store",
    headers: {
      Authorization: `Bearer ${await accessToken()}`, "Content-Type": "application/json; charset=UTF-8", Origin: origin,
      "X-Upload-Content-Type": type || "application/octet-stream", "X-Upload-Content-Length": String(size),
    },
    body: JSON.stringify({ name, parents: [folderId] }),
  });
  const address = response.headers.get("location");
  if (!response.ok || !address) throw new Error(`Google Drive didn't accept the upload (HTTP ${response.status}).`);
  return address;
}

/**
 * Save HTML as a Google Doc in a folder, as the connected account. With an existing file's ID it updates that Doc
 * instead, unless it has been deleted. Returns the Doc's ID and link.
 */
export async function saveDoc(folderId: string, name: string, html: string, fileId?: string | null): Promise<{ id: string; link: string }> {
  const auth = { Authorization: `Bearer ${await accessToken()}` };
  const fields = "fields=id,webViewLink,trashed";
  if (fileId) {
    const response = await fetch(`https://www.googleapis.com/upload/drive/v3/files/${fileId.replace(/[^\w-]/g, "")}?uploadType=media&${fields}`, {
      method: "PATCH", cache: "no-store", headers: { ...auth, "Content-Type": "text/html; charset=UTF-8" }, body: html,
    });
    const file = response.ok ? await response.json() : null;
    if (file && !file.trashed) return { id: file.id, link: file.webViewLink };
  }
  const boundary = `deal-desk-${randomBytes(8).toString("hex")}`;
  const body = [
    `--${boundary}`, "Content-Type: application/json; charset=UTF-8", "", JSON.stringify({ name, mimeType: GOOGLE_DOC, parents: [folderId] }),
    `--${boundary}`, "Content-Type: text/html; charset=UTF-8", "", html, `--${boundary}--`, "",
  ].join("\r\n");
  const response = await fetch(`https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&${fields}`, {
    method: "POST", cache: "no-store", headers: { ...auth, "Content-Type": `multipart/related; boundary=${boundary}` }, body,
  });
  if (!response.ok) throw new Error(`Google Drive didn't save it (HTTP ${response.status}).`);
  const file = await response.json();
  return { id: file.id, link: file.webViewLink };
}
