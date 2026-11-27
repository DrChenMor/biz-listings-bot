/**
 * The email copier that runs inside Tom's deals Google account, as Google Apps Script. The website serves it on the
 * Sources page so Tom can paste it in. It reads Gmail through the Gmail API with the read-only scope, so it can't send,
 * delete or change any email; it writes only into the Communication doc and the business's Drive folder.
 */

export const MANIFEST = JSON.stringify({
  timeZone: "Australia/Perth",
  runtimeVersion: "V8",
  exceptionLogging: "STACKDRIVER",
  dependencies: { enabledAdvancedServices: [{ userSymbol: "Gmail", serviceId: "gmail", version: "v1" }] },
  oauthScopes: [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/script.external_request",
    "https://www.googleapis.com/auth/script.scriptapp",
    "https://www.googleapis.com/auth/script.send_mail",
  ],
}, null, 2);

export const SCRIPT = String.raw`/**
 * Deal desk email copier.
 * Copies emails to and from each business's contacts into the business's Communication doc in Drive, saves their
 * attachments into the business's folder, and sends a copy to the Deal desk website for its Communication timeline.
 * It only READS Gmail (read-only permission): it never deletes, labels or marks anything. The one email it sends is
 * the Deal desk morning update, to Tom himself.
 *
 * Setup, once: Project Settings > Script properties > add DEAL_DESK_URL and DEAL_DESK_KEY, then run setup().
 */

function setup() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'copyEmails') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('copyEmails').timeBased().everyDays(1).atHour(7).create();
  copyEmails();
}

function copyEmails() {
  var copied = 0, unmatched = 0, skipped = 0, problem = '';
  try {
    var info = api_('get', '/api/mail');
    var ids = {};
    var queries = [];
    for (var i = 0; i < info.contacts.length; i += 15) {
      var chunk = info.contacts.slice(i, i + 15).map(function (a) { return 'from:' + a + ' to:' + a + ' cc:' + a; });
      queries.push('{' + chunk.join(' ') + '} newer_than:' + info.lookbackDays + 'd');
    }
    queries.push('in:inbox category:primary -from:me newer_than:' + info.unmatchedDays + 'd');
    queries.forEach(function (q) {
      var page;
      do {
        var found = Gmail.Users.Messages.list('me', { q: q, maxResults: 100, pageToken: page });
        (found.messages || []).forEach(function (m) { ids[m.id] = true; });
        page = found.nextPageToken;
      } while (page && Object.keys(ids).length < 500);
    });

    var all = Object.keys(ids);
    for (var start = 0; start < all.length; start += 20) {
      // One email Google can't hand over cleanly is skipped and counted, rather than stopping the whole run.
      var batch = all.slice(start, start + 20).map(function (id) {
        try { return read_(id); } catch (e) { skipped++; console.log('Skipped email ' + id + ': ' + e); return null; }
      }).filter(function (m) { return m; });
      if (!batch.length) continue;
      var reply = api_('post', '/api/mail', { messages: batch.map(function (m) { return m.summary; }) });
      reply.results.forEach(function (result) {
        if (result.unmatched) unmatched++;
        var message = batch.filter(function (m) { return m.summary.id === result.id; })[0];
        result.targets.forEach(function (target) {
          if (target.folder_id) {
            var folder = DriveApp.getFolderById(target.folder_id);
            appendToDoc_(folder, target.text);
            saveAttachments_(folder, message);
          }
          copied++;
        });
      });
    }
  } catch (e) {
    problem = String(e && e.message || e);
  }
  try { api_('post', '/api/mail/done', { copied: copied, unmatched: unmatched, skipped: skipped, error: problem }); } catch (ignored) {}
  try { sendMorningEmail(); } catch (e) { console.log('Morning email not sent: ' + e); }
  if (problem) throw new Error(problem);
}

/** The Deal desk morning update, sent to Tom himself, and only when there's something new. Run it to see one now. */
function sendMorningEmail() {
  var digest = api_('get', '/api/digest');
  if (!digest.send) return;
  var me = Gmail.Users.getProfile('me').emailAddress;
  MailApp.sendEmail({ to: me, subject: digest.subject, htmlBody: digest.html, body: digest.text, name: 'Deal desk' });
}

/** One email, read through the Gmail API: its headers, plain text and attachment list. */
function read_(id) {
  var m = Gmail.Users.Messages.get('me', id, { format: 'full' });
  var headers = {};
  (m.payload.headers || []).forEach(function (h) { headers[h.name.toLowerCase()] = h.value; });
  var plain = [], html = [], files = [];
  walk_(m.payload, plain, html, files);
  var body = plain.length ? plain.join('\n') : html.join('\n').replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<br\s*\/?>/gi, '\n').replace(/<\/(p|div|li|tr)>/gi, '\n').replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#39;/g, "'").replace(/&quot;/g, '"');
  return {
    id: m.id,
    files: files,
    summary: {
      id: m.id, threadId: m.threadId, date: new Date(Number(m.internalDate)).toISOString(),
      from: headers['from'] || '', to: headers['to'] || '', cc: headers['cc'] || '', subject: headers['subject'] || '',
      body: body, attachments: files.map(function (f) { return f.name; })
    }
  };
}

function walk_(part, plain, html, files) {
  if (part.filename && part.body && part.body.attachmentId) {
    files.push({ name: part.filename, type: part.mimeType, attachmentId: part.body.attachmentId });
  } else if (part.mimeType === 'text/plain' && part.body && part.body.data) {
    plain.push(decode_(part.body.data));
  } else if (part.mimeType === 'text/html' && part.body && part.body.data) {
    html.push(decode_(part.body.data));
  }
  (part.parts || []).forEach(function (p) { walk_(p, plain, html, files); });
}

/** Gmail API content arrives as web-safe base64, sometimes without its padding, or already as a list of bytes. */
function bytes_(data) {
  if (Array.isArray(data)) return data;
  var text = String(data || '').replace(/-/g, '+').replace(/_/g, '/').replace(/\s/g, '');
  while (text.length % 4) text += '=';
  return Utilities.base64Decode(text);
}

function decode_(data) {
  return Utilities.newBlob(bytes_(data)).getDataAsString('UTF-8');
}

/** Adds the email to the bottom of the folder's Communication doc, making the doc if there isn't one. */
function appendToDoc_(folder, text) {
  var docs = folder.getFilesByName('Communication');
  var doc = null;
  while (docs.hasNext()) {
    var file = docs.next();
    if (file.getMimeType() === MimeType.GOOGLE_DOCS) { doc = DocumentApp.openById(file.getId()); break; }
  }
  if (!doc) {
    doc = DocumentApp.create('Communication');
    DriveApp.getFileById(doc.getId()).moveTo(folder);
  }
  var body = doc.getBody();
  var lines = text.split('\n');
  body.appendParagraph('');
  body.appendParagraph(lines[0]).setBold(true);
  body.appendParagraph(lines[1] || '').setItalic(true).setBold(false);
  lines.slice(2).forEach(function (line) { body.appendParagraph(line).setBold(false).setItalic(false); });
  doc.saveAndClose();
}

/** Saves the email's attachments into the folder, skipping any file name already there. */
function saveAttachments_(folder, message) {
  message.files.forEach(function (f) {
    if (folder.getFilesByName(f.name).hasNext()) return;
    var data = Gmail.Users.Messages.Attachments.get('me', message.id, f.attachmentId).data;
    folder.createFile(Utilities.newBlob(bytes_(data), f.type, f.name));
  });
}

function api_(method, path, payload) {
  var props = PropertiesService.getScriptProperties();
  var url = (props.getProperty('DEAL_DESK_URL') || '').replace(/\/$/, '');
  var key = props.getProperty('DEAL_DESK_KEY') || '';
  if (!url || !key) throw new Error('Add DEAL_DESK_URL and DEAL_DESK_KEY under Project Settings > Script properties.');
  var options = { method: method, headers: { 'x-deal-desk-key': key }, muteHttpExceptions: true };
  if (payload) { options.contentType = 'application/json'; options.payload = JSON.stringify(payload); }
  var response = UrlFetchApp.fetch(url + path, options);
  if (response.getResponseCode() >= 300) {
    throw new Error('Deal desk said ' + response.getResponseCode() + ': ' + response.getContentText().slice(0, 200));
  }
  return JSON.parse(response.getContentText());
}
`;
