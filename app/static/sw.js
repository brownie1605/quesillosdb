// Service worker de Quesillos POS.
//
// Alcance deliberadamente chico: solo cachea los archivos estaticos
// (CSS/JS/iconos) para que la app cargue rapido y sobreviva baches de red.
// Nunca cachea HTML ni /api/*: el sistema ya tiene su propia arquitectura
// local-first en el servidor (base de datos local + cola de sincronizacion
// hacia la nube), y meter cache del navegador ahi arriba arriesgaria
// mostrar ventas/inventario desactualizados sobre un sistema que ya
// resuelve eso de otra forma.
//
// Estrategia: red primero, cache como respaldo (no cache-first). Con
// cache-first, cada vez que se corrige un bug en un .js/.css el navegador
// seguia sirviendo la version vieja cacheada indefinidamente -- aqui, con
// internet disponible siempre se pide la version mas nueva al servidor (y
// de paso se actualiza el cache); el cache solo se usa si de verdad no hay
// internet en ese momento.

const CACHE_NAME = "quesillos-pos-shell-v2";
const APP_SHELL = [
  "/static/css/dashboard.css",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (!url.pathname.startsWith("/static/")) return; // nada de HTML ni /api/*

  event.respondWith(
    fetch(req)
      .then((resp) => {
        if (resp && resp.ok) {
          const copia = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copia));
        }
        return resp;
      })
      .catch(() => caches.match(req)) // sin internet: lo ultimo que se cacheo
  );
});
