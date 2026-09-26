// Cross-origin isolation for the Rust trial page, which GitHub Pages cannot give by headers.
//
// rustc runs with threads, which need SharedArrayBuffer, which a browser allows only on a
// cross-origin isolated page: one served with COOP and COEP headers. This service worker adds
// them to every response in its scope (this directory only; the book's own pages are untouched).
// The page registers it and reloads once, so its second load is isolated.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
  const request = event.request;
  // Everything the page loads is on this origin; anything else passes through untouched.
  if (new URL(request.url).origin !== self.location.origin) return;
  if (request.cache === "only-if-cached" && request.mode !== "same-origin") return;
  event.respondWith(
    fetch(request).then((response) => {
      if (response.status === 0) return response;
      const headers = new Headers(response.headers);
      headers.set("Cross-Origin-Opener-Policy", "same-origin");
      headers.set("Cross-Origin-Embedder-Policy", "require-corp");
      headers.set("Cross-Origin-Resource-Policy", "same-origin");
      return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
    }),
  );
});
