import { createDriveFolder, linkFolder } from "@/lib/actions";
import { Business, nameOf, Tracking, when } from "@/lib/db";
import { businessFolders, driveReady, DriveFile, DriveFolder, filesIn, folderLink, kindOf } from "@/lib/drive";
import { connection } from "@/lib/google";
import { DriveUpload } from "./drive-upload";

/** The business's folder in Acquisitions: its files and a place to drop more, or a choice of folder to link. */
export async function DriveCard({ business, tracking }: { business: Business; tracking: Tracking | null }) {
  if (!tracking || !driveReady()) return null;
  let files: DriveFile[] = [], folders: DriveFolder[] = [], problem = "";
  try {
    if (tracking.drive_folder_id) files = await filesIn(tracking.drive_folder_id);
    else folders = await businessFolders();
  } catch (e) {
    problem = e instanceof Error ? e.message : "Google Drive didn't answer.";
  }
  const connected = Boolean(await connection());

  return (
    <section className="card"><h2>Drive folder</h2>
      {problem ? <p className="note warn">{problem}</p> : null}
      {tracking.drive_folder_id ? (
        <>
          <p><a className="btn" href={folderLink(tracking.drive_folder_id)} target="_blank" rel="noreferrer">Open the folder in Drive</a></p>
          {connected ? <DriveUpload id={business.id} /> : <p className="lsub">Connect Google Drive on the Sources page to add files from here.</p>}
          {files.length ? files.map((file) => (
            <a className="item" key={file.id} href={file.webViewLink} target="_blank" rel="noreferrer">
              <span className="ltitle">{file.name}</span>
              <span className="lsub">{kindOf(file)} · changed {when(file.modifiedTime)}</span>
            </a>
          )) : problem ? null : <p className="lsub">The folder is empty.</p>}
          <form action={linkFolder}>
            <input type="hidden" name="id" value={business.id} />
            <button type="submit" className="plain dark">Unlink this folder</button>
          </form>
        </>
      ) : (
        <>
          {folders.length ? (
            <form action={linkFolder} className="actions">
              <input type="hidden" name="id" value={business.id} />
              <select name="folder" aria-label="Drive folder" defaultValue="">
                <option value="" disabled>Choose its folder in Acquisitions</option>
                {folders.map((f) => <option key={f.id} value={f.id}>{f.name}{f.passed ? " (Passed)" : ""}</option>)}
              </select>
              <button type="submit" className="btn">Link</button>
            </form>
          ) : problem ? null : <p className="lsub">No folders in Acquisitions yet.</p>}
          {connected ? (<>
            <form action={createDriveFolder} className="actions folderrow" style={{ marginTop: 8 }}>
              <input type="hidden" name="id" value={business.id} />
              <input className="input" name="name" aria-label="Name of the new folder" defaultValue={nameOf(business, tracking)} style={{ flex: "1 1 200px" }} />
              <button type="submit" className="btn">Make a new folder for it</button>
            </form>
            <p className="lsub">The folder's name becomes the business's name on the website.</p>
          </>) : null}
        </>
      )}
    </section>
  );
}
