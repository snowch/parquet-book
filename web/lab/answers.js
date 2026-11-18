// A workbench stores the active draft and the recoverable draft in one browser storage entry.
// Older workbenches stored the active draft as plain text under `problems:<chapter>`.
const legacyPrefix = "problems:";
const draftsPrefix = "problem-drafts:";

export function loadDrafts(chapter) {
  try {
    const drafts = localStorage.getItem(draftsPrefix + chapter);
    if (drafts !== null) {
      try {
        const parsed = JSON.parse(drafts);
        if (parsed && [parsed.draft, parsed.previous].every((value) => value === null || typeof value === "string")) {
          return { ...parsed, storageReadable: true };
        }
      } catch {
        // A previous browser version may still have its plain-text draft.
      }
    }
    return { draft: localStorage.getItem(legacyPrefix + chapter), previous: null, storageReadable: true };
  } catch {
    return { draft: null, previous: null, storageReadable: false };
  }
}

export function saveDrafts(chapter, { draft, previous }) {
  try {
    localStorage.setItem(draftsPrefix + chapter, JSON.stringify({ draft, previous }));
  } catch {
    return false;
  }
  try {
    localStorage.removeItem(legacyPrefix + chapter);
  } catch {
    // The new entry takes precedence even if the browser keeps the legacy key.
  }
  return true;
}

// Standalone pytest commands also use learners' active drafts. A null draft uses the book's stub.
export function savedAnswers() {
  const out = {};
  try {
    const chapters = new Set();
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith(legacyPrefix)) chapters.add(key.slice(legacyPrefix.length));
      if (key?.startsWith(draftsPrefix)) chapters.add(key.slice(draftsPrefix.length));
    }
    for (const chapter of chapters) {
      const { draft } = loadDrafts(chapter);
      if (draft !== null) out[chapter] = draft;
    }
  } catch {}
  return out;
}
