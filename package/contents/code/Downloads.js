.pragma library

// The Downloads stack, as in the macOS dock: the newest files first, without
// downloads that are still running. Plain JavaScript; DownloadsTile feeds it
// rows from a FolderListModel sorted by time.

var limit = 12;
// Suffixes browsers and download managers use while a file is incomplete.
var partial = ["part", "crdownload", "download", "partial", "opdownload", "tmp"];
var images = ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "avif"];
var kinds = {
    pdf: "application-pdf",
    zip: "package-x-generic", gz: "package-x-generic", xz: "package-x-generic", bz2: "package-x-generic",
    zst: "package-x-generic", "7z": "package-x-generic", rar: "package-x-generic", tar: "package-x-generic",
    rpm: "package-x-generic", deb: "package-x-generic", flatpakref: "package-x-generic", appimage: "package-x-generic",
    iso: "media-optical", img: "media-optical",
    mp3: "audio-x-generic", flac: "audio-x-generic", ogg: "audio-x-generic", wav: "audio-x-generic", m4a: "audio-x-generic",
    mp4: "video-x-generic", mkv: "video-x-generic", webm: "video-x-generic", mov: "video-x-generic", avi: "video-x-generic",
    doc: "x-office-document", docx: "x-office-document", odt: "x-office-document", rtf: "x-office-document",
    xls: "x-office-spreadsheet", xlsx: "x-office-spreadsheet", ods: "x-office-spreadsheet", csv: "x-office-spreadsheet",
    ppt: "x-office-presentation", pptx: "x-office-presentation", odp: "x-office-presentation",
    txt: "text-x-generic", md: "text-x-generic", json: "text-x-generic", log: "text-x-generic"
};

function suffixOf(name) {
    const text = String(name || "");
    const dot = text.lastIndexOf(".");
    return dot > 0 ? text.slice(dot + 1).toLowerCase() : "";
}
function isPartial(name) { return partial.indexOf(suffixOf(name)) >= 0; }
function isImage(name) { return images.indexOf(suffixOf(name)) >= 0; }
function iconFor(name, isDir) {
    if (isDir) return "folder";
    if (isImage(name)) return "image-x-generic";
    return kinds[suffixOf(name)] || "text-x-generic";
}

// rows: [{name, url, isDir}] newest first. Returns at most `max` finished
// entries, each with its icon and whether it can show as a thumbnail.
function entries(rows, max) {
    const list = [];
    for (const row of rows || []) {
        if (list.length >= (max || limit)) break;
        if (!row || typeof row.name !== "string" || !row.name.length || row.name[0] === "." || isPartial(row.name)) continue;
        list.push({name: row.name, url: String(row.url), isDir: Boolean(row.isDir),
            icon: iconFor(row.name, row.isDir), thumbnail: !row.isDir && isImage(row.name)});
    }
    return list;
}
