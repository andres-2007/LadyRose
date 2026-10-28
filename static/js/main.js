/* Ladyrose: interacciones de la página (sin librerías) */
document.addEventListener("DOMContentLoaded", function () {
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* HU 23: menú tipo hamburguesa en celular */
  var boton = $(".menu-boton"), menu = $("#menu-principal"), velo = $("[data-velo]");
  function cerrarMenu() {
    if (!menu) return;
    menu.classList.remove("abierto");
    if (velo) velo.classList.remove("visible");
    if (boton) boton.setAttribute("aria-expanded", "false");
    document.body.style.overflow = "";
  }
  if (boton && menu) {
    boton.addEventListener("click", function () {
      var abierto = menu.classList.toggle("abierto");
      boton.setAttribute("aria-expanded", abierto ? "true" : "false");
      if (velo) velo.classList.toggle("visible", abierto);
      document.body.style.overflow = abierto ? "hidden" : "";
    });
    if (velo) velo.addEventListener("click", cerrarMenu);
    $$("[data-cerrar-menu]").forEach(function (c) { c.addEventListener("click", cerrarMenu); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") cerrarMenu(); });
  }

  /* Los mensajes se van solos */
  $$(".mensajes .alerta").forEach(function (a, i) {
    setTimeout(function () { a.style.transition = "opacity .4s"; a.style.opacity = "0"; }, 5000 + i * 400);
    setTimeout(function () { a.remove(); }, 5600 + i * 400);
  });

  /* HU 31: copiar el enlace del producto o curso */
  $$("[data-copiar]").forEach(function (b) {
    b.addEventListener("click", function () {
      var texto = b.getAttribute("data-copiar"), original = b.innerHTML;
      var listo = function () {
        b.textContent = "¡Enlace copiado!";
        setTimeout(function () { b.innerHTML = original; }, 2000);
      };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(texto).then(listo);
      } else {
        var t = document.createElement("textarea");
        t.value = texto; document.body.appendChild(t); t.select();
        document.execCommand("copy"); document.body.removeChild(t); listo();
      }
    });
  });

  /* Galería de la ficha: cambiar la foto principal */
  var principal = $("[data-foto-principal]");
  $$("[data-miniatura]").forEach(function (m) {
    m.addEventListener("click", function () {
      principal.src = m.getAttribute("data-miniatura");
      $$("[data-miniatura]").forEach(function (o) { o.classList.remove("activa"); });
      m.classList.add("activa");
    });
  });

  /* Botones + y - de cantidad */
  $$("[data-cantidad]").forEach(function (caja) {
    var input = $("input", caja);
    $$("button", caja).forEach(function (b) {
      b.addEventListener("click", function () {
        var max = parseInt(input.max || "20", 10), min = parseInt(input.min || "1", 10);
        var v = (parseInt(input.value, 10) || 1) + parseInt(b.getAttribute("data-paso"), 10);
        input.value = Math.max(min, Math.min(max, v));
        if (caja.hasAttribute("data-enviar")) caja.closest("form").submit();
      });
    });
  });

  /* HU 19: no se puede agregar al carrito sin elegir talla */
  var formCompra = $("[data-form-compra]");
  if (formCompra) {
    formCompra.addEventListener("submit", function (e) {
      var grupos = $$("[data-requerido]", formCompra);
      for (var i = 0; i < grupos.length; i++) {
        if (!$("input:checked", grupos[i])) {
          e.preventDefault();
          var aviso = $("[data-aviso]", grupos[i]);
          if (aviso) aviso.classList.remove("oculto");
          grupos[i].scrollIntoView({ behavior: "smooth", block: "center" });
          return;
        }
      }
    });
    $$("[data-requerido] input", formCompra).forEach(function (r) {
      r.addEventListener("change", function () {
        var aviso = $("[data-aviso]", r.closest("[data-requerido]"));
        if (aviso) aviso.classList.add("oculto");
        var elegido = $("[data-elegido]", r.closest("[data-requerido]"));
        if (elegido) elegido.textContent = r.getAttribute("data-texto") || r.value;
      });
    });
  }

  /* HU 11: contador de caracteres de la nota */
  $$("[data-contador]").forEach(function (t) {
    var max = parseInt(t.getAttribute("data-contador"), 10);
    var c = document.createElement("div");
    c.className = "contador";
    t.insertAdjacentElement("afterend", c);
    var pintar = function () { c.textContent = t.value.length + " / " + max + " caracteres"; };
    t.addEventListener("input", pintar); pintar();
  });

  /* Mostrar u ocultar partes del formulario según una casilla o un radio */
  $$("[data-mostrar-si]").forEach(function (bloque) {
    var regla = bloque.getAttribute("data-mostrar-si").split("=");
    var campos = $$('[name="' + regla[0] + '"]');
    var revisar = function () {
      var visible;
      if (campos[0] && campos[0].type === "checkbox") {
        visible = regla[1] === "no" ? !campos[0].checked : campos[0].checked;
      } else {
        visible = campos.some(function (c) { return c.checked && c.value === regla[1]; });
      }
      bloque.classList.toggle("oculto", !visible);
    };
    campos.forEach(function (c) { c.addEventListener("change", revisar); });
    revisar();
  });

  /* Resumen del pago: sumar el empaque elegido (HU 11) */
  var totalPago = $("[data-total]");
  if (totalPago) {
    var base = parseInt(totalPago.getAttribute("data-subtotal"), 10);
    var filaEmpaque = $("[data-fila-empaque]");
    var formato = function (n) { return "$" + n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, "."); };
    var recalcular = function () {
      var elegido = $('input[name="empaque"]:checked');
      var costo = elegido ? parseInt(elegido.getAttribute("data-costo") || "0", 10) : 0;
      totalPago.textContent = formato(base + costo);
      if (filaEmpaque) {
        filaEmpaque.classList.toggle("oculto", !costo);
        $("span:last-child", filaEmpaque).textContent = formato(costo);
      }
    };
    $$('input[name="empaque"]').forEach(function (r) { r.addEventListener("change", recalcular); });
    recalcular();
  }

  /* HU 04: cambiar el estado del pedido sin salir del panel */
  $$("[data-estado-pedido]").forEach(function (form) {
    var select = $("select", form), aviso = $(".guardado", form);
    var boton = $("button", form);
    if (boton) boton.classList.add("oculto");
    select.addEventListener("change", function () {
      var datos = new FormData(form);
      fetch(form.action, { method: "POST", body: datos, headers: { "x-requested-with": "fetch" } })
        .then(function (r) { return r.json(); })
        .then(function (r) {
          aviso.style.color = r.ok ? "" : "var(--error)";
          aviso.textContent = r.ok ? "Guardado" : (r.error || "No se pudo guardar");
          aviso.classList.add("visible");
          if (!r.ok) return;
          setTimeout(function () { aviso.classList.remove("visible"); }, 1800);
          var tarjeta = form.closest("[data-pedido]");
          if (tarjeta) {
            var insignia = $("[data-insignia]", tarjeta);
            if (insignia) { insignia.className = "insignia insignia--" + r.estado; insignia.textContent = r.etiqueta; }
            if (r.terminado && tarjeta.closest("[data-lista-pendientes]")) {
              tarjeta.style.opacity = ".3";
              setTimeout(function () { window.location.reload(); }, 700);
            }
          }
        })
        .catch(function () { form.submit(); });
    });
  });
});
