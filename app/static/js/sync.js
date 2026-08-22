/* ==========================================================================
   sync.js — cliente de sincronización local <-> nube
   - Consulta el estado cada 15 s
   - Sincroniza automáticamente cada 2 min si hay conexión
   - Botón "Sincronizar ahora" (⟳ en la barra superior)
   - Avisa de conflictos resueltos (ventas anuladas)
   ========================================================================== */
(function () {
  "use strict";

  const INTERVALO_ESTADO = 15000;   // 15 s
  const INTERVALO_SYNC = 120000;    // 2 min

  const SyncManager = {
    enCurso: false,
    ultimoConteoConflictos: 0,

    async estado() {
      try {
        const res = await fetch("/api/sync/status", { headers: { Accept: "application/json" } });
        if (!res.ok) throw new Error("status " + res.status);
        const datos = await res.json();
        NetworkMonitor.actualizar(datos);
        this._revisarConflictos(datos);
        return datos;
      } catch (e) {
        NetworkMonitor.actualizar({ online: false, pendientes: NetworkMonitor.pendientes });
        return null;
      }
    },

    async sincronizar(automatico) {
      if (this.enCurso) return null;
      this.enCurso = true;
      NetworkMonitor.sincronizando(true);
      try {
        const res = await fetch("/api/sync/now", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });
        const datos = await res.json();

        if (!datos.ok) {
          if (!automatico) {
            Q.toast("warning", "Sin conexión", datos.mensaje || "No se pudo contactar la nube.");
          }
        } else {
          const subidos = (datos.push && datos.push.enviados) || 0;
          const bajados = (datos.pull && datos.pull.aplicados) || 0;
          const conflictos = (datos.conflictos && datos.conflictos.resueltos) || 0;

          if (!automatico || subidos || bajados || conflictos) {
            Q.toast(
              "success",
              "Sincronización completa",
              "Subidos: " + subidos + " · Bajados: " + bajados +
                (conflictos ? " · Conflictos resueltos: " + conflictos : "")
            );
          }
          if (conflictos > 0) this._avisarConflictos();
        }
        await this.estado();
        return datos;
      } catch (e) {
        if (!automatico) Q.toast("error", "Error de sincronización", e.message);
        return null;
      } finally {
        this.enCurso = false;
        NetworkMonitor.sincronizando(false);
      }
    },

    async _avisarConflictos() {
      try {
        const res = await fetch("/api/conflicts?estado=resuelto_auto");
        const lista = await res.json();
        lista.slice(0, 3).forEach(function (c) {
          const gano = c.datos_resueltos ? c.datos_resueltos.ganador : null;
          if (gano === "remoto") {
            Q.toast(
              "error",
              "El último producto ha sido vendido",
              "Tu venta fue anulada: otro punto de venta la registró primero.",
              9000
            );
          }
        });
      } catch (e) { /* silencioso */ }
    },

    _revisarConflictos(datos) {
      const n = datos.conflictos_pendientes || 0;
      if (n > this.ultimoConteoConflictos && n > 0) {
        Q.toast("warning", "Conflictos de sincronización", n + " conflicto(s) requieren revisión.");
      }
      this.ultimoConteoConflictos = n;
    },
  };

  window.SyncManager = SyncManager;

  /* ------------------------------------------------------------- arranque */
  document.addEventListener("DOMContentLoaded", function () {
    const boton = document.getElementById("btn-sync-now");
    if (boton) {
      boton.addEventListener("click", function (e) {
        e.preventDefault();
        SyncManager.sincronizar(false);
      });
    }

    SyncManager.estado();
    setInterval(function () { SyncManager.estado(); }, INTERVALO_ESTADO);
    setInterval(function () {
      if (navigator.onLine) SyncManager.sincronizar(true);
    }, INTERVALO_SYNC);
  });
})();
