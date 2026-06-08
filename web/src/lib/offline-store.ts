"use client";

// Offline-first persistence backed by the browser's native IndexedDB — no
// third-party dependency. Two concerns live here:
//
//   1. Composer DRAFTS, keyed by conversationId, so an in-progress message
//      survives a reload, a tab crash, or navigating between conversations.
//      A brand-new chat (no conversation row yet) uses the NEW_CHAT_DRAFT_KEY
//      sentinel.
//   2. An UNSENT QUEUE of turns the user tried to send while offline / mid
//      failure, so a future flush can retry them.
//
// All access is feature-detected and best-effort: if IndexedDB is unavailable
// (private mode in some browsers, SSR, disabled storage) every call resolves to
// a safe no-op / empty result rather than throwing, so the UI path never breaks
// on a storage failure.

const DB_NAME = "olune-offline";
const DB_VERSION = 1;
const DRAFTS_STORE = "drafts";
const QUEUE_STORE = "queue";

// Draft key used for the composer before a conversation row exists (the very
// first message of a new chat). Once the conversation is created the draft is
// cleared on send, so this never lingers across real conversations.
export const NEW_CHAT_DRAFT_KEY = "__new_chat__";

export interface UnsentTurn {
  // Stable client-minted id (also used to dedupe on flush).
  id: string;
  conversationId: string | null;
  text: string;
  tierId: string;
  providerId?: string;
  createdAt: string;
}

function hasIndexedDb(): boolean {
  return typeof window !== "undefined" && "indexedDB" in window && window.indexedDB !== null;
}

let dbPromise: Promise<IDBDatabase | null> | null = null;

function openDb(): Promise<IDBDatabase | null> {
  if (!hasIndexedDb()) return Promise.resolve(null);
  if (dbPromise) return dbPromise;

  dbPromise = new Promise<IDBDatabase | null>((resolve) => {
    let request: IDBOpenDBRequest;
    try {
      request = window.indexedDB.open(DB_NAME, DB_VERSION);
    } catch {
      resolve(null);
      return;
    }
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(DRAFTS_STORE)) {
        // Drafts are keyed explicitly by conversationId (out-of-line keys).
        db.createObjectStore(DRAFTS_STORE);
      }
      if (!db.objectStoreNames.contains(QUEUE_STORE)) {
        // Queue rows carry their own `id` as the in-line key.
        db.createObjectStore(QUEUE_STORE, { keyPath: "id" });
      }
    };
    request.onsuccess = () => {
      const db = request.result;
      // If another tab triggers a version change, close so it isn't blocked.
      db.onversionchange = () => db.close();
      resolve(db);
    };
    request.onerror = () => resolve(null);
    request.onblocked = () => resolve(null);
  });

  return dbPromise;
}

function runTransaction<T>(
  storeName: string,
  mode: IDBTransactionMode,
  work: (store: IDBObjectStore) => IDBRequest<T> | null,
): Promise<T | null> {
  return openDb().then(
    (db) =>
      new Promise<T | null>((resolve) => {
        if (!db) {
          resolve(null);
          return;
        }
        let tx: IDBTransaction;
        try {
          tx = db.transaction(storeName, mode);
        } catch {
          resolve(null);
          return;
        }
        let request: IDBRequest<T> | null = null;
        try {
          request = work(tx.objectStore(storeName));
        } catch {
          resolve(null);
          return;
        }
        if (!request) {
          tx.oncomplete = () => resolve(null);
          tx.onabort = () => resolve(null);
          tx.onerror = () => resolve(null);
          return;
        }
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => resolve(null);
        tx.onabort = () => resolve(null);
      }),
  );
}

// --- Drafts ----------------------------------------------------------------

function draftKey(conversationId: string | null | undefined): string {
  return conversationId ?? NEW_CHAT_DRAFT_KEY;
}

export async function saveDraft(
  conversationId: string | null | undefined,
  text: string,
): Promise<void> {
  const key = draftKey(conversationId);
  // An empty draft is the same as no draft — delete so a cleared composer
  // doesn't leave a stale row that would re-populate on the next mount.
  if (text.trim().length === 0) {
    await deleteDraft(conversationId);
    return;
  }
  await runTransaction<IDBValidKey>(DRAFTS_STORE, "readwrite", (store) =>
    store.put(text, key),
  );
}

export async function loadDraft(
  conversationId: string | null | undefined,
): Promise<string | null> {
  const key = draftKey(conversationId);
  const value = await runTransaction<unknown>(DRAFTS_STORE, "readonly", (store) =>
    store.get(key) as IDBRequest<unknown>,
  );
  return typeof value === "string" ? value : null;
}

export async function deleteDraft(
  conversationId: string | null | undefined,
): Promise<void> {
  const key = draftKey(conversationId);
  await runTransaction<undefined>(DRAFTS_STORE, "readwrite", (store) =>
    store.delete(key) as IDBRequest<undefined>,
  );
}

// --- Unsent queue ----------------------------------------------------------

export async function enqueueUnsent(turn: UnsentTurn): Promise<void> {
  await runTransaction<IDBValidKey>(QUEUE_STORE, "readwrite", (store) =>
    store.put(turn),
  );
}

export async function getUnsentQueue(): Promise<UnsentTurn[]> {
  const rows = await runTransaction<unknown>(QUEUE_STORE, "readonly", (store) =>
    store.getAll() as IDBRequest<unknown>,
  );
  if (!Array.isArray(rows)) return [];
  return rows.filter((row): row is UnsentTurn => {
    return (
      typeof row === "object" &&
      row !== null &&
      typeof (row as UnsentTurn).id === "string" &&
      typeof (row as UnsentTurn).text === "string"
    );
  });
}

export async function removeFromQueue(id: string): Promise<void> {
  await runTransaction<undefined>(QUEUE_STORE, "readwrite", (store) =>
    store.delete(id) as IDBRequest<undefined>,
  );
}

// --- Persistent storage ----------------------------------------------------

// Ask the browser to mark our origin's storage as persistent so the offline
// drafts/queue aren't silently evicted under storage pressure. Best-effort and
// idempotent — browsers may grant silently, prompt, or ignore. Returns whether
// storage is (now) persisted; resolves false when the API is unavailable.
export async function requestPersistentStorage(): Promise<boolean> {
  if (
    typeof navigator === "undefined" ||
    !navigator.storage ||
    typeof navigator.storage.persist !== "function"
  ) {
    return false;
  }
  try {
    if (typeof navigator.storage.persisted === "function") {
      const already = await navigator.storage.persisted();
      if (already) return true;
    }
    return await navigator.storage.persist();
  } catch {
    return false;
  }
}
