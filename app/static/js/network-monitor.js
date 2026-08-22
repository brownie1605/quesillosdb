/* ==========================================================================
   network-monitor.js — indicador de conectividad y avisos de modo offline
   ========================================================================== */
(function () {
  "use strict";

  const NetworkMonitor = {
    online: null,
    pendientes: 0,

    elementos() {
      return {
        punto: document.getElementById("sync-indicator"),
        etiqueta: document.getElementById("sync-label"),
        badge: document.getElementById("sync-pending"),
        banner: document.getElementById("offline-banner"),
      };
    },

    pintar(estado, texto) {
      const el = this.elementos();
      if (!el.punto) return;
      el.punto.className = "sync-dot " + estado;
      if (el.etiqueta) el.etiqueta.textContent = texto;
    },

    actualizar(datos) {
      const el = this.elementos();
      const online = !!datos.online;
      this.pendientes = datos.pendientes || 0;

      if (online) {
        this.pintar("sync-online", this.pendientes ? "En línea · sincronizando" : "En línea");
      } else {
        this.pintar("sync-offline", "Sin conexión · modo local");
      }

      if (el.badge) {
        if (this.pendientes > 0) {
          el.badge.style.display = "inline-block";
          el.badge.textContent = this.pendientes;
          el.badge.title = this.pendientes + " operación(es) pendiente(s) de subir a la nube";
        } else {
          el.badge.style.display = "none";
        }
      }

      if (el.banner) {
        el.banner.classList.toggle("visible", !online);
        el.banner.innerHTML =
          "📡 Sin conexión a internet — el sistema sigue funcionando localmente. " +
          (this.pendientes
            ? "<strong>" + this.pendientes + "</strong> operación(es) se subirán al recuperar la señal."
            : "Los datos se subirán al recuperar la señal.");
      }

      if (this.online !== null && this.online !== online) {
        if (online) {
          Q.toast("success", "Conexión restaurada", "Sincronizando con la nube…");
        } else {
          Q.toast("warning", "Sin conexión", "El sistema continúa funcionando en modo local.");
        }
      }
      this.online = online;
    },

    sincronizando(activo) {
      const el = this.elementos();
      const boton = document.getElementById("btn-sync-now");
      if (boton) boton.classList.toggle("girando", activo);
      if (activo) this.pintar("sync-syncing", "Sincronizando…");
    },
  };

  /* ---------------------------------------------------------------- toasts */
  const Q = {
    stack: null,

    _stack() {
      if (!this.stack) {
        this.stack = document.createElement("div");
        this.stack.className = "q-toast-stack";
        document.body.appendChild(this.stack);
      }
      return this.stack;
    },

    toast(tipo, titulo, mensaje, duracion) {
      const iconos = { info: "ℹ️", success: "✅", warning: "⚠️", error: "❌" };
      const nodo = document.createElement("div");
      nodo.className = "q-toast " + (tipo || "info");
      nodo.innerHTML =
        "<div>" + (iconos[tipo] || "ℹ️") + "</div>" +
        "<div><strong>" + titulo + "</strong><p>" + (mensaje || "") + "</p></div>";
      this._stack().appendChild(nodo);
      setTimeout(function () {
        nodo.style.opacity = "0";
        nodo.style.transform = "translateX(28px)";
        nodo.style.transition = "all .25s";
        setTimeout(function () { nodo.remove(); }, 260);
      }, duracion || 5200);
      return nodo;
    },
  };

  window.Q = Q;
  window.NetworkMonitor = NetworkMonitor;

  /* --------------------------------------- banner de offline en cada página */
  document.addEventListener("DOMContentLoaded", function () {
    if (!document.getElementById("offline-banner")) {
      const b = document.createElement("div");
      b.id = "offline-banner";
      document.body.appendChild(b);
    }
  });

  /* ------------------------------- eventos nativos del navegador */
  window.addEventListener("offline", function () {
    NetworkMonitor.actualizar({ online: false, pendientes: NetworkMonitor.pendientes });
  });

  window.addEventListener("online", function () {
    if (window.SyncManager) window.SyncManager.sincronizar(true);
  });
})();
