/**
 * Save to sheet: saves the SEEK Business listings you are looking at into this Google Sheet.
 *
 * You browse SEEK Business as normal. On a search results page, or on a single listing, click the
 * "Save to sheet" bookmark. It reads the listings on that page and sends them here. Each listing is
 * added once to the "SEEK listings" tab and updated when you see it again; new listings and changes
 * (price, title, under offer) are written to the "Changes" tab. Nothing visits SEEK on its own.
 *
 * Setup (once): see seek/README.md. In short: paste this file into Extensions > Apps Script,
 * deploy it as a web app, open the web app link and drag the "Save to sheet" button to your
 * bookmarks bar.
 */

var TAB = "SEEK listings";
var CHANGES_TAB = "Changes";
var TIMEZONE = "Australia/Perth";

// [field, column header]. The script owns these columns; add your own to the right of "Key".
var COLUMNS = [
  ["status", "Status"],
  ["title", "Title"],
  ["price_text", "Asking price"],
  ["price_aud", "Price (AUD)"],
  ["price_basis", "Price basis"],
  ["opportunity_type", "Type"],
  ["industry", "Industry"],
  ["location", "Location"],
  ["advertiser", "Advertiser"],
  ["advertiser_type", "Advertiser type"],
  ["turnover_aud", "Turnover (AUD/yr)"],
  ["profit_aud", "Profit (AUD/yr)"],
  ["phones", "Phones in listing"],
  ["summary", "Summary"],
  ["description", "Description"],
  ["url", "URL"],
  ["listing_id", "Listing ID"],
  ["seek_updated", "SEEK updated"],
  ["first_seen", "First seen"],
  ["last_seen", "Last seen"],
  ["last_changed", "Last changed"],
  ["key", "Key"],
];
// Changes to these fields are written to the Changes tab.
var WATCHED = { status: "Status", title: "Title", price_text: "Asking price", opportunity_type: "Type" };
// Food businesses are skipped, the same as in the other bots (config.toml exclude_categories).
var EXCLUDE = /\b(food|cafes?|coffee|restaurants?|takeaway|take-away|bakery|bakeries|butcher|deli|catering|juice|bubble tea|ice cream|gelato|donuts?|pizza|pubs?|bars?|tavern|brewery|liquor|alcohol|hospitality|function centre|fruit shop|supermarkets?|grocery|convenience|vending)\b/i;
// Columns kept as plain text so Sheets doesn't turn them into dates or numbers.
var TEXT_FIELDS = ["listing_id", "seek_updated", "first_seen", "last_seen", "last_changed"];
var CHANGE_HEADERS = ["When", "Source", "Listing ID", "Title", "What changed", "Old", "New", "URL"];

// ---------------------------------------------------------------------------------------------
// Web app: GET shows the install page with the bookmark; POST receives listings from the bookmark.
// ---------------------------------------------------------------------------------------------

function doGet() {
  var url = ScriptApp.getService().getUrl();
  var bookmark = "javascript:" + encodeURIComponent("(" + seekBookmarklet.toString() + ")(" + JSON.stringify(url) + ")");
  var html =
    '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' +
    "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px;color:#1f2937}" +
    "a.btn{display:inline-block;background:#0d6efd;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:600}" +
    "textarea{width:100%;height:90px;font:12px monospace}</style></head><body>" +
    "<h1>Save to sheet</h1>" +
    "<p><b>1.</b> Show your bookmarks bar (Cmd+Shift+B in Chrome).</p>" +
    '<p><b>2.</b> Drag this button onto the bookmarks bar: <a class="btn" href="' + escapeHtml(bookmark) + '">Save to sheet</a></p>' +
    "<p><b>3.</b> Open SEEK Business, search (for example WA, sorted by date) and click the bookmark on each results page " +
    "or listing you want saved. A tab opens saying what was saved.</p>" +
    "<p>If dragging doesn't work: create a new bookmark named <i>Save to sheet</i> and paste this as its URL:</p>" +
    "<textarea readonly onclick=\"this.select()\">" + escapeHtml(bookmark) + "</textarea>" +
    "<p>Keep this page's link private: anyone with it can add rows to your sheet.</p></body></html>";
  return HtmlService.createHtmlOutput(html).setTitle("Save to sheet");
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var payload = JSON.parse((e && e.parameter && e.parameter.payload) || "{}");
    var result = saveListings(SpreadsheetApp.getActiveSpreadsheet(), payload.listings || [], nowStamp());
    return resultPage(
      "Saved " + result.saved + " listing" + (result.saved === 1 ? "" : "s"),
      result.added + " new, " + result.updated + " changed, " + result.unchanged + " already up to date" +
        (result.skipped ? ", " + result.skipped + " food listing" + (result.skipped === 1 ? "" : "s") + " skipped." : "."),
      payload.page
    );
  } catch (err) {
    return resultPage("Couldn't save", String(err && err.message ? err.message : err), "");
  } finally {
    lock.releaseLock();
  }
}

function saveListings(book, listings, stamp) {
  var sheet = book.getSheetByName(TAB) || createTab(book);
  var headers = COLUMNS.map(function (c) { return c[1]; });
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  var values = sheet.getDataRange().getValues();
  var plan = planChanges(values, listings, stamp);

  plan.updates.forEach(function (u) {
    sheet.getRange(u.row, 1, 1, headers.length).setValues([u.values]);
  });
  if (plan.appends.length) {
    // New listings go on top. Whole rows are inserted, so your own columns stay with their listing.
    sheet.insertRowsBefore(2, plan.appends.length);
    textFormat(sheet.getRange(2, 1, plan.appends.length, headers.length));
    sheet.getRange(2, 1, plan.appends.length, headers.length).setValues(plan.appends);
  }
  if (plan.changes.length) {
    var log = book.getSheetByName(CHANGES_TAB);
    if (!log) {
      log = book.insertSheet(CHANGES_TAB);
      log.appendRow(CHANGE_HEADERS);
      log.setFrozenRows(1);
    }
    log.getRange(log.getLastRow() + 1, 1, plan.changes.length, CHANGE_HEADERS.length).setValues(plan.changes);
  }
  return plan.counts;
}

function createTab(book) {
  var sheet = book.insertSheet(TAB);
  sheet.setFrozenRows(1);
  return sheet;
}

function textFormat(range) {
  TEXT_FIELDS.forEach(function (field) {
    var col = fieldIndex(field) + 1;
    range.getSheet().getRange(range.getRow(), col, range.getNumRows(), 1).setNumberFormat("@");
  });
}

function resultPage(heading, detail, backTo) {
  var html =
    '<!doctype html><html><head><meta charset="utf-8"><style>body{font:16px/1.5 system-ui,sans-serif;max-width:560px;margin:60px auto;padding:0 16px}</style></head><body>' +
    "<h2>" + escapeHtml(heading) + "</h2><p>" + escapeHtml(detail) + "</p>" +
    '<p>See the <b>' + TAB + "</b> tab in your sheet. You can close this tab.</p></body></html>";
  return HtmlService.createHtmlOutput(html).setTitle(heading);
}

// ---------------------------------------------------------------------------------------------
// Deciding what to write. Pure functions, so they can be tested outside Google (seek/test.js).
// ---------------------------------------------------------------------------------------------

/** values: the tab's current cells (header row first). Returns rows to update, rows to add, change-log rows. */
function planChanges(values, listings, stamp) {
  var keyCol = fieldIndex("key");
  var rowOf = {};
  for (var r = 1; r < values.length; r++) {
    if (values[r][keyCol]) rowOf[values[r][keyCol]] = r;
  }
  var updates = [];
  var appends = [];
  var changes = [];
  var counts = { saved: 0, added: 0, updated: 0, unchanged: 0, skipped: 0 };
  var done = {};
  listings.forEach(function (raw) {
    var record = normalise(raw, stamp);
    if (!record.listing_id || done[record.key]) return;
    done[record.key] = true;
    if (EXCLUDE.test(record.industry)) {
      counts.skipped++;
      return;
    }
    var r = rowOf[record.key];
    counts.saved++;
    if (r === undefined) {
      record.first_seen = record.last_changed = stamp;
      appends.push(toRow(record));
      changes.push(changeRow(stamp, record, "New listing", "", record.price_text));
      counts.added++;
      return;
    }
    var old = fromRow(values[r]);
    var merged = {};
    COLUMNS.forEach(function (c) {
      var f = c[0];
      var fresh = record[f];
      merged[f] = fresh !== undefined && fresh !== null && fresh !== "" ? fresh : old[f];
    });
    merged.first_seen = old.first_seen || stamp;
    merged.last_seen = stamp;
    var diffs = Object.keys(WATCHED).filter(function (f) {
      return String(old[f] || "") !== String(merged[f] || "");
    });
    merged.last_changed = diffs.length ? stamp : old.last_changed;
    diffs.forEach(function (f) {
      changes.push(changeRow(stamp, merged, WATCHED[f], old[f] || "", merged[f] || ""));
    });
    updates.push({ row: r + 1, values: toRow(merged) });
    if (diffs.length) counts.updated++;
    else counts.unchanged++;
  });
  return { updates: updates, appends: appends, changes: changes, counts: counts };
}

/** One listing as sent by the bookmark -> the fields of its row. */
function normalise(raw, stamp) {
  var id = String(raw.id || "").replace(/\D/g, "");
  var title = clean(raw.title);
  var priceText = clean(raw.price_text) || priceFromParts(raw);
  var text = [title, raw.summary, raw.description].filter(Boolean).join("\n");
  var basis = priceBasis(priceText);
  if (raw.sav && basis.indexOf("SAV") < 0) basis.push("+ stock (SAV)");
  if (raw.negotiable && basis.indexOf("Negotiable / offers") < 0) basis.push("Negotiable / offers");
  return {
    key: "seek:" + id,
    listing_id: id,
    status: listingStatus(title + " " + priceText),
    title: title,
    price_text: priceText,
    price_aud: raw.price_min ? Number(raw.price_min) : money(priceText),
    price_basis: basis.join(", "),
    opportunity_type: clean(raw.opportunity_type),
    industry: clean(raw.industry),
    location: clean(raw.location),
    advertiser: clean(raw.advertiser),
    advertiser_type: clean(raw.advertiser_type),
    turnover_aud: turnover(text),
    profit_aud: profit(text),
    phones: phones(text).join("; "),
    summary: clean(raw.summary),
    description: String(raw.description || "").trim().slice(0, 5000),
    url: raw.url || "",
    seek_updated: raw.refreshed ? formatStamp(new Date(raw.refreshed)) : "",
    last_seen: stamp,
  };
}

function priceFromParts(raw) {
  if (raw.poa) return "P.O.A";
  var min = Number(raw.price_min || 0);
  var max = Number(raw.price_max || 0);
  if (!min && !max) return "";
  var text = min && max && min !== max ? "$" + min.toLocaleString("en-AU") + " - $" + max.toLocaleString("en-AU") : "$" + (min || max).toLocaleString("en-AU");
  return text + (raw.sav ? " + SAV" : "");
}

function listingStatus(text) {
  if (/under offer|under contract/i.test(text)) return "Under offer";
  if (/\bsold\b/i.test(text)) return "Sold";
  return "Active";
}

var MONEY = /\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s?(k|m|mil|million)\b)?(?![A-Za-z0-9])/gi;
var PER_WEEK = /^\s*(?:(?:per|a|\/|p\.?)\s*(?:week|wk)\b|pw\b|p\/w\b|weekly\b)/i;
var PER_MONTH = /^\s*(?:(?:per|a|\/|p\.?)\s*(?:month|mth)\b|pm\b|p\/m\b|monthly\b)/i;
var PRICE_WORDS = /asking|price|priced|offers|\bsav\b|stock|rent|lease/i;
var TURNOVER = "turnover|revenue|gross sales|annual sales|sales|takings";
var PROFIT = "adjusted net profit|net profit|ebitda|ebit|profit|net income|owner'?s? (?:earnings|benefit|income|return)|return to (?:the )?owners?";

function money(text) {
  MONEY.lastIndex = 0;
  var m = MONEY.exec(text || "");
  return m ? amountOf(m) : "";
}

function turnover(text) {
  return yearly(text, TURNOVER, "averaging");
}

function profit(text) {
  return yearly(text, PROFIT, "");
}

/** A yearly amount tied to a keyword: "Turnover: $281,700", "$13K weekly sales", "~$160K net profit". */
function yearly(text, keywords, extraBefore) {
  text = String(text || "");
  // Amount then keyword first, as it's the tighter pairing: "$13K weekly sales", "~$160K net profit".
  var after = new RegExp("^\\s*((?:(?:weekly|per week|a week|monthly|per month|annual|yearly|approx\\.?|approximately|in|of)\\s+)*)(?:net\\s+)?(?:" + keywords + ")\\b", "i");
  var a;
  MONEY.lastIndex = 0;
  while ((a = MONEY.exec(text))) {
    var rest = text.slice(a.index + a[0].length, a.index + a[0].length + 40);
    var hit = after.exec(rest);
    if (!hit) continue;
    var amount = amountOf(a);
    if (/week/i.test(hit[1])) amount *= 52;
    else if (/month/i.test(hit[1])) amount *= 12;
    if (amount >= 1000) return amount;
  }
  // Then keyword then amount, in the same clause: "Turnover: approx $281,700".
  var before = new RegExp("\\b(?:" + keywords + (extraBefore ? "|" + extraBefore : "") + ")\\b", "gi");
  var k;
  while ((k = before.exec(text))) {
    var tail = text.slice(k.index + k[0].length, k.index + k[0].length + 80).split("\n")[0];
    MONEY.lastIndex = 0;
    var m;
    while ((m = MONEY.exec(tail))) {
      if (/^(?:19|20)\d{2}$/.test(m[1]) && !m[2]) continue; // "$2026 – $329,300": a year, not money
      var between = tail.slice(0, m.index);
      if (PRICE_WORDS.test(between) || /[,;]\s|\.\s+(?=[A-Z])/.test(between)) break;
      var value = annualise(amountOf(m), tail.slice(m.index + m[0].length));
      if (value >= 1000) return value;
      break;
    }
  }
  return "";
}

function annualise(value, following) {
  if (PER_WEEK.test(following)) return value * 52;
  if (PER_MONTH.test(following)) return value * 12;
  return value;
}

function amountOf(m) {
  var value = parseFloat(m[1].replace(/,/g, ""));
  var suffix = (m[2] || "").toLowerCase();
  if (suffix === "k") value *= 1000;
  else if (suffix) value *= 1000000;
  return Math.round(value);
}

function priceBasis(text) {
  var rules = [
    [/\+\s*s\.?a\.?v\.?|plus\s+(?:stock|sav)/i, "+ stock (SAV)"],
    [/\bwiwo\b|walk[\s-]*in[\s,-]*walk[\s-]*out/i, "Walk in walk out"],
    [/\binc(?:l|luding)?\.?\s*(?:stock|sav)/i, "Incl. stock"],
    [/\+\s*gst|plus gst/i, "+ GST"],
    [/\bneg(?:otiable)?\b|\bo\.?n\.?o\.?\b|\boffers?\b/i, "Negotiable / offers"],
    [/\bp\.?o\.?a\.?\b|contact|enquire|on application/i, "Price on application"],
  ];
  return rules.filter(function (r) { return r[0].test(text || ""); }).map(function (r) { return r[1]; });
}

/** Australian phone numbers written in the listing (usually the broker's). */
function phones(text) {
  var found = String(text || "").match(/(?:\+?61\s?|\b0)[2-478](?:[ -]?\d){8}\b|\b1[38]00(?:[ -]?\d){6}\b|\b13(?:[ -]?\d){4}\b/g) || [];
  var seen = {};
  return found.map(function (p) { return p.trim(); }).filter(function (p) {
    var digits = p.replace(/\D/g, "").replace(/^61/, "0");
    if (seen[digits]) return false;
    seen[digits] = true;
    return true;
  });
}

function toRow(record) {
  return COLUMNS.map(function (c) {
    var v = record[c[0]];
    return v === undefined || v === null ? "" : v;
  });
}

function fromRow(row) {
  var record = {};
  COLUMNS.forEach(function (c, i) { record[c[0]] = row[i] instanceof Date ? formatStamp(row[i]) : row[i]; });
  return record;
}

function changeRow(stamp, record, what, oldValue, newValue) {
  return [stamp, "seek", record.listing_id, record.title, what, oldValue, newValue, record.url];
}

function fieldIndex(field) {
  for (var i = 0; i < COLUMNS.length; i++) if (COLUMNS[i][0] === field) return i;
  return -1;
}

function nowStamp() {
  return formatStamp(new Date());
}

function formatStamp(date) {
  if (typeof Utilities !== "undefined") return Utilities.formatDate(date, TIMEZONE, "yyyy-MM-dd HH:mm");
  var parts = new Intl.DateTimeFormat("en-CA", { timeZone: TIMEZONE, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(date);
  var get = function (type) { return parts.filter(function (p) { return p.type === type; })[0].value; };
  return get("year") + "-" + get("month") + "-" + get("day") + " " + get("hour").replace(/^24$/, "00") + ":" + get("minute");
}

function clean(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function escapeHtml(text) {
  return String(text).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ---------------------------------------------------------------------------------------------
// The bookmark. This function runs in your browser on the SEEK page you're looking at (it is
// turned into the bookmark by doGet above). It reads that page only, then posts to this script.
// ---------------------------------------------------------------------------------------------

function seekBookmarklet(webAppUrl, dryRun) {
  var text = function (el) { return el ? el.innerText.replace(/\s+/g, " ").trim() : ""; };
  var idFrom = function (href) { var m = /-listing\/[^\/?#]+\/(\d+)/.exec(href || ""); return m ? m[1] : ""; };
  if (location.hostname.indexOf("seekbusiness.com.au") < 0) {
    alert("Open a SEEK Business search results page or listing first.");
    return;
  }
  var apollo = {};
  try {
    apollo = JSON.parse(document.getElementById("__NEXT_DATA__").textContent).props.pageProps.__APOLLO_STATE__ || {};
  } catch (e) {}
  var listings = [];
  var pageId = idFrom(location.pathname);

  if (pageId) {
    // One listing: also take the full description, which usually names the broker and their phone.
    var product = {};
    Array.prototype.forEach.call(document.querySelectorAll('script[type="application/ld+json"]'), function (s) {
      try { var d = JSON.parse(s.textContent); if (d["@type"] === "Product") product = d; } catch (e) {}
    });
    var offer = product.offers || {};
    var lines = document.body.innerText.split("\n").map(function (l) { return l.trim(); }).filter(Boolean);
    var title = text(document.querySelector("h1"));
    var start = Math.max(0, lines.indexOf(title));
    var head = lines.slice(start, start + 20);
    // Franchise pages label their facts ("Type:" then the value on the next line); business pages
    // put them inline ("Type: Business") or unlabelled.
    var labelled = function (label) {
      for (var i = 0; i < head.length; i++) {
        if (head[i].toLowerCase() === label.toLowerCase() + ":") return head[i + 1] || "";
        if (head[i].toLowerCase().indexOf(label.toLowerCase() + ": ") === 0) return head[i].slice(label.length + 1).trim();
      }
      return "";
    };
    var typeAt = -1;
    for (var i = 0; i < head.length; i++) if (/^Type:/i.test(head[i])) typeAt = i;
    var pick = function (from, to, test) { for (var j = from; j < to; j++) if (head[j] && test(head[j])) return head[j]; return ""; };
    var beforeType = typeAt < 0 ? head.length : typeAt;
    // The description: every section from "Summary" down to the enquiry form.
    var from = lines.indexOf("Summary");
    var to = lines.length;
    for (var k = from + 1; k < lines.length; k++) {
      if (/^(Send an enquiry|Share this business|You might also like|Enquiry sent|Find out more at )/.test(lines[k])) {
        to = k;
        break;
      }
    }
    listings.push({
      id: pageId,
      url: location.origin + location.pathname,
      title: title,
      location: labelled("Location") || pick(1, beforeType, function (l) { return / > /.test(l); }),
      price_text: labelled("Investment level") || pick(1, beforeType, function (l) { return /^(\$|P\.?O\.?A|Price|Negotiable|Contact)/i.test(l); }),
      price_min: offer.price || "",
      opportunity_type: labelled("Type"),
      industry: labelled("Industry") || (typeAt >= 0 ? pick(typeAt + 1, head.length, function (l) { return / > /.test(l); }) : ""),
      advertiser: (offer.seller || {}).name || "",
      summary: product.description || "",
      description: from >= 0 ? lines.slice(from + 1, to).join("\n") : "",
    });
  } else {
    // A results page: every listing card on it.
    var seen = {};
    Array.prototype.forEach.call(document.querySelectorAll('h2 a[href*="-listing/"]'), function (a) {
      var id = idFrom(a.href);
      if (!id || seen[id]) return;
      seen[id] = true;
      var card = a;
      while (card && !card.querySelector('[data-testid="search-result-item-location-breadcrumbs"]')) card = card.parentElement;
      if (!card) return;
      var s = apollo["SearchListing:" + id] || {};
      var investment = s.investment || {};
      var range = investment.range || {};
      var client = s.client && s.client.__ref ? apollo[s.client.__ref] : s.client || {};
      var leaves = Array.prototype.filter.call(card.querySelectorAll("span"), function (el) { return !el.children.length; }).map(function (el) { return el.innerText.trim(); });
      var readMore = card.querySelector('[data-testid="serp-listing-item-read-more-link"]');
      listings.push({
        id: id,
        url: a.href.split("?")[0],
        title: text(a),
        advertiser: text(card.querySelector('[data-testid="serp-listing-business-name"]')),
        advertiser_type: client.type || "",
        location: text(card.querySelector('[data-testid="search-result-item-location-breadcrumbs"]')),
        industry: text(card.querySelector('[data-testid="search-result-item-industry-breadcrumbs"]')),
        price_text: leaves.filter(function (l) { return /^(\$|P\.?O\.?A|Price|Negotiable|Contact)/i.test(l); })[0] || "",
        price_min: range.min || "",
        price_max: range.max || "",
        poa: !!investment.isPoa,
        negotiable: !!investment.isNegotiable,
        sav: !!investment.hasInventorySav,
        opportunity_type: s.opportunityType || leaves.filter(function (l) { return /^(Business|Franchise|Licen|Distribution|Dealership|Home)/i.test(l); })[0] || "",
        summary: s.summary || (readMore ? text(readMore.parentElement).replace(/\s*more\s*››\s*$/, "") : ""),
        refreshed: s.refreshDate || "",
      });
    });
  }

  if (!listings.length) {
    alert("No SEEK Business listings found on this page.");
    return;
  }
  var payload = { source: "seek", page: location.href, listings: listings };
  if (dryRun) return payload;
  var form = document.createElement("form");
  form.method = "POST";
  form.action = webAppUrl;
  form.target = "_blank";
  form.acceptCharset = "UTF-8";
  var input = document.createElement("input");
  input.type = "hidden";
  input.name = "payload";
  input.value = JSON.stringify(payload);
  form.appendChild(input);
  document.body.appendChild(form);
  form.submit();
  form.remove();
}

// Lets seek/test.js load this file in Node. Google Apps Script has no `module`, so this is skipped there.
if (typeof module !== "undefined") {
  module.exports = { planChanges: planChanges, normalise: normalise, turnover: turnover, profit: profit, phones: phones, priceFromParts: priceFromParts, COLUMNS: COLUMNS, seekBookmarklet: seekBookmarklet };
}
