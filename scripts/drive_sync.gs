/**
 * Google Apps Script: sync newest Drive backups into GitHub.
 *
 * Drive layout:
 *   Kennzeichensammler/<NAME>/<backup files...>
 *
 * GitHub layout:
 *   backups/<NAME>/<same filename>
 *
 * Same filenames across friends are fine; the NAME folder keeps them apart.
 * For each friend, only the newest backup is uploaded. "Newest" is chosen from
 * the DD.MM.YYYY date embedded in the filename (not Drive lastUpdated), because
 * shared-folder syncs often give every file the same move timestamp.
 * Older files already present under that friend's GitHub folder are removed.
 *
 * Script Properties (Project Settings -> Script Properties):
 *   GITHUB_TOKEN   required  fine-grained PAT
 *   GITHUB_REPO    optional  default: lluten/kennzeichensammler-scoreboard
 *   DRIVE_FOLDER_ID optional  default: shared Kennzeichensammler folder id
 *   TRASH_AFTER_SYNC optional  "true" to trash Drive file after successful upload
 *
 * After a successful Contents API commit under backups/, the repo workflow
 * rebuilds data/ + profiles/ for GitHub Pages. You do not need extra
 * "Actions" permissions on the PAT for that — the commit event triggers CI.
 */

var DEFAULT_GITHUB_REPO = "lluten/kennzeichensammler-scoreboard";
var DEFAULT_DRIVE_FOLDER_ID = "1piXwu5-9sUS5VkB0PAuQqp9UAV_Rfpl9";

function pushSharedFoldersToGithub() {
  var props = PropertiesService.getScriptProperties();
  var githubToken = props.getProperty("GITHUB_TOKEN");
  var repoPath = props.getProperty("GITHUB_REPO") || DEFAULT_GITHUB_REPO;
  var mainSharedFolderId = props.getProperty("DRIVE_FOLDER_ID") || DEFAULT_DRIVE_FOLDER_ID;
  var trashAfterSync = String(props.getProperty("TRASH_AFTER_SYNC") || "").toLowerCase() === "true";

  if (!githubToken) {
    throw new Error("Missing GITHUB_TOKEN in Script Properties");
  }

  var mainFolder = DriveApp.getFolderById(mainSharedFolderId);
  var subfolders = mainFolder.getFolders();
  var summary = [];

  while (subfolders.hasNext()) {
    var friendFolder = subfolders.next();
    var friendName = friendFolder.getName();
    var latest = getLatestBackupFile(friendFolder);

    if (!latest) {
      summary.push(friendName + ": no files");
      continue;
    }

    var fileName = latest.getName();
    var result = upsertGithubFile(
      repoPath,
      githubToken,
      "backups/" + friendName + "/" + fileName,
      latest.getBlob().getBytes(),
      "Auto-upload latest backup for " + friendName
    );

    if (!result.ok) {
      summary.push(friendName + ": upload failed (" + result.code + ") " + result.body);
      continue;
    }

    var cleanup = deleteOtherGithubFilesInFolder(
      repoPath,
      githubToken,
      "backups/" + friendName,
      fileName,
      "Remove older backup for " + friendName
    );

    if (trashAfterSync) {
      latest.setTrashed(true);
    }

    summary.push(
      friendName +
        ": uploaded " +
        fileName +
        (cleanup.deleted ? ", removed " + cleanup.deleted + " older GitHub file(s)" : "")
    );
  }

  Logger.log(summary.join("\n"));
  return summary;
}

function parseBackupDateFromName(fileName) {
  // Matches ...-15.07.2026 or ..._15.07.2026 anywhere in the name.
  var match = String(fileName).match(/(\d{2})\.(\d{2})\.(\d{4})/);
  if (!match) {
    return null;
  }
  var day = Number(match[1]);
  var month = Number(match[2]);
  var year = Number(match[3]);
  var date = new Date(year, month - 1, day);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return null;
  }
  return date;
}

function getLatestBackupFile(folder) {
  var files = folder.getFiles();
  var latest = null;
  var latestDate = null;
  var latestName = "";

  while (files.hasNext()) {
    var file = files.next();
    var fileName = file.getName();
    var fileDate = parseBackupDateFromName(fileName);

    if (!latest) {
      latest = file;
      latestDate = fileDate;
      latestName = fileName;
      continue;
    }

    // Prefer a parseable filename date over files without one.
    if (fileDate && !latestDate) {
      latest = file;
      latestDate = fileDate;
      latestName = fileName;
      continue;
    }
    if (!fileDate && latestDate) {
      continue;
    }

    if (fileDate && latestDate) {
      if (fileDate.getTime() > latestDate.getTime()) {
        latest = file;
        latestDate = fileDate;
        latestName = fileName;
      } else if (fileDate.getTime() === latestDate.getTime() && fileName > latestName) {
        // Stable tie-break if two files share the same embedded date.
        latest = file;
        latestDate = fileDate;
        latestName = fileName;
      }
      continue;
    }

    // Neither filename has a date: fall back to lexicographic name.
    if (fileName > latestName) {
      latest = file;
      latestDate = fileDate;
      latestName = fileName;
    }
  }

  return latest;
}

function githubContentsUrl(repoPath, path) {
  var encoded = path
    .split("/")
    .map(function (part) {
      return encodeURIComponent(part);
    })
    .join("/");
  return "https://api.github.com/repos/" + repoPath + "/contents/" + encoded;
}

function githubHeaders(token) {
  return {
    Authorization: "Bearer " + token,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
  };
}

function getGithubFileMeta(repoPath, token, path) {
  var response = UrlFetchApp.fetch(githubContentsUrl(repoPath, path), {
    method: "get",
    headers: githubHeaders(token),
    muteHttpExceptions: true
  });
  var code = response.getResponseCode();
  if (code === 404) {
    return null;
  }
  if (code < 200 || code >= 300) {
    throw new Error("GET " + path + " failed (" + code + "): " + response.getContentText());
  }
  return JSON.parse(response.getContentText());
}

function upsertGithubFile(repoPath, token, path, bytes, message) {
  var existing = getGithubFileMeta(repoPath, token, path);
  var payload = {
    message: message,
    content: Utilities.base64Encode(bytes)
  };
  if (existing && existing.sha) {
    payload.sha = existing.sha;
  }

  var response = UrlFetchApp.fetch(githubContentsUrl(repoPath, path), {
    method: "put",
    headers: githubHeaders(token),
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  var code = response.getResponseCode();
  return {
    ok: code >= 200 && code < 300,
    code: code,
    body: response.getContentText()
  };
}

function listGithubFolder(repoPath, token, folderPath) {
  var response = UrlFetchApp.fetch(githubContentsUrl(repoPath, folderPath), {
    method: "get",
    headers: githubHeaders(token),
    muteHttpExceptions: true
  });
  var code = response.getResponseCode();
  if (code === 404) {
    return [];
  }
  if (code < 200 || code >= 300) {
    throw new Error("LIST " + folderPath + " failed (" + code + "): " + response.getContentText());
  }

  var payload = JSON.parse(response.getContentText());
  if (!Array.isArray(payload)) {
    return [];
  }
  return payload;
}

function deleteGithubFile(repoPath, token, path, sha, message) {
  var response = UrlFetchApp.fetch(githubContentsUrl(repoPath, path), {
    method: "delete",
    headers: githubHeaders(token),
    contentType: "application/json",
    payload: JSON.stringify({
      message: message,
      sha: sha
    }),
    muteHttpExceptions: true
  });
  var code = response.getResponseCode();
  return code >= 200 && code < 300;
}

function deleteOtherGithubFilesInFolder(repoPath, token, folderPath, keepFileName, message) {
  var entries = listGithubFolder(repoPath, token, folderPath);
  var deleted = 0;

  entries.forEach(function (entry) {
    if (entry.type !== "file") {
      return;
    }
    if (entry.name === keepFileName) {
      return;
    }
    if (deleteGithubFile(repoPath, token, folderPath + "/" + entry.name, entry.sha, message)) {
      deleted += 1;
    }
  });

  return { deleted: deleted };
}
