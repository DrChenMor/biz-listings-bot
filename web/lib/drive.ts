/**
 * Reads the Acquisitions folder in Google Drive as the bots' robot account, which Tom shared it with. Server only.
 * The key comes from GOOGLE_SERVICE_ACCOUNT_JSON (on Vercel) or GOOGLE_SERVICE_ACCOUNT_FILE (on a Mac). Read only.
 */
import { createSign } from "node:crypto";
import { readFileSync } from "node:fs";

export type DriveFile = { id: string; name: string; mimeType: string; modifiedTime: string; webViewLink: string };
export type DriveFolder = { id: string; name: string; passed: boolean };

const FOLDER = "application/vnd.google-apps.folder";
let token: { value: string; until: number } | null = null;

export function driveReady(): boolean {
  return Boolean(process.env.GOOGLE_SERVICE_ACCOUNT_JSON || process.env.GOOGLE_SERVICE_ACCOUNT_FILE);
}

function robotKey(): { client_email: string; private_key: string } {
  const path = process.env.GOOGLE_SERVICE_ACCOUNT_FILE;
  return JSON.parse(process.env.GOOGLE_SERVICE_ACCOUNT_JSON || (path ? readFileSync(path, "utf8") : "{}"));
}

async function accessToken(): Promise<string> {
  if (token && token.until > Date.now() + 60_000) return token.value;
  const key = robotKey();
  const now = Math.floor(Date.now() / 1000);
  const part = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  const unsigned = `${part({ alg: "RS256", typ: "JWT" })}.${part({
    iss: key.client_email, scope: "https://www.googleapis.com/auth/drive.readonly", aud: "https://oauth2.googleapis.com/token", iat: now, exp: now + 3600,
  })}`;
  const signature = createSign("RSA-SHA256").update(unsigned).sign(key.private_key).toString("base64url");
  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST", cache: "no-store", headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion: `${unsigned}.${signature}` }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(`Google refused the robot account: ${data.error_description ?? data.error}`);
  token = { value: data.access_token, until: Date.now() + data.expires_in * 1000 };
  return token.value;
}

async function list(q: string): Promise<DriveFile[]> {
  const params = new URLSearchParams({ q, fields: "files(id,name,mimeType,modifiedTime,webViewLink)", pageSize: "200", orderBy: "folder,name" });
  const response = await fetch(`https://www.googleapis.com/drive/v3/files?${params}`, {
    headers: { Authorization: `Bearer ${await accessToken()}` }, cache: "no-store",
  });
  if (!response.ok) throw new Error(`Google Drive refused (HTTP ${response.status})`);
  return (await response.json()).files;
}

const inside = (id: string) => `'${id.replace(/[^\w-]/g, "")}' in parents and trashed = false`;
const folders = (files: DriveFile[]) => files.filter((f) => f.mimeType === FOLDER);

export function filesIn(folderId: string): Promise<DriveFile[]> {
  return list(inside(folderId));
}

/** The Acquisitions folder's ID, or null when it isn't shared with the robot account. */
export async function acquisitionsId(): Promise<string | null> {
  const [root] = await list(`name = 'Acquisitions' and mimeType = '${FOLDER}' and trashed = false`);
  return root?.id ?? null;
}

/** Every business's folder in Acquisitions, including the ones moved into Acquisitions/Passed. */
export async function businessFolders(): Promise<DriveFolder[]> {
  const rootId = await acquisitionsId();
  if (!rootId) return [];
  const root = { id: rootId };
  const top = folders(await list(inside(root.id)));
  const passed = top.find((f) => f.name.trim().toLowerCase() === "passed");
  const gone = passed ? folders(await list(inside(passed.id))) : [];
  return [...top.filter((f) => f !== passed).map((f) => ({ id: f.id, name: f.name, passed: false })),
    ...gone.map((f) => ({ id: f.id, name: f.name, passed: true }))];
}

export function folderLink(id: string): string {
  return `https://drive.google.com/drive/folders/${id}`;
}

export function kindOf(file: DriveFile): string {
  if (file.mimeType === FOLDER) return "Folder";
  if (file.mimeType.includes("pdf")) return "PDF";
  if (file.mimeType.includes("word") || file.mimeType.endsWith("document")) return "Document";
  if (file.mimeType.includes("sheet") || file.mimeType.includes("excel")) return "Spreadsheet";
  if (file.mimeType.startsWith("video")) return "Video";
  if (file.mimeType.startsWith("image")) return "Picture";
  return "File";
}
