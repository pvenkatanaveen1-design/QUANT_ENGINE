window.addEventListener("unhandledrejection", function (event) {
  console.warn("Unhandled promise rejection", event.reason || event);
});

document.addEventListener("htmx:responseError", function (event) {
  var source = event.detail && event.detail.elt;
  var selector = source && source.getAttribute && source.getAttribute("hx-target");
  var target = selector ? document.querySelector(selector) : source;
  if (!target) return;
  target.innerHTML =
    '<section class="panel border-amber-300"><div class="label">Request Failed</div><div class="mt-2 text-sm text-amber-300">The snapshot request failed. Check MT5 connection, symbol, timeframe, and server logs.</div></section>';
});

function confirmDangerousAction(message) {
  return window.confirm(message || "This action changes system state. Continue?");
}

function showToast(message, type) {
  var toast = document.createElement("div");
  toast.className = "fixed right-4 top-4 z-50 rounded border bg-white px-4 py-3 text-sm shadow";
  toast.textContent = message || "Done";
  if (type === "error") {
    toast.className += " border-red-200 text-red-700";
  } else {
    toast.className += " border-zinc-200 text-zinc-800";
  }
  document.body.appendChild(toast);
  window.setTimeout(function () {
    toast.remove();
  }, 3000);
}

function connectSocket(url, onMessage, statusElement) {
  var retry = 1000;
  var socket;

  function setStatus(text, state) {
    if (!statusElement) return;
    statusElement.textContent = text;
    statusElement.classList.remove("status-green", "status-amber", "status-red", "status-gray");
    statusElement.classList.add(state || "status-gray");
  }

  function open() {
    socket = new WebSocket(url);
    socket.onopen = function () {
      retry = 1000;
      setStatus("live connected", "status-green");
    };
    socket.onmessage = function (event) {
      try {
        onMessage(JSON.parse(event.data));
      } catch (error) {
        console.warn("Bad WebSocket payload", error);
      }
    };
    socket.onclose = function () {
      setStatus("reconnecting", "status-amber");
      window.setTimeout(open, retry);
      retry = Math.min(retry * 1.8, 10000);
    };
    socket.onerror = function () {
      setStatus("socket error", "status-red");
      socket.close();
    };
  }

  open();
  return function closeSocket() {
    if (socket) socket.close();
  };
}

function setLiveField(name, value) {
  document.querySelectorAll('[data-live-field="' + name + '"]').forEach(function (node) {
    node.textContent = value === null || value === undefined ? "-" : value;
  });
}

function initTableFilters(root) {
  (root || document).querySelectorAll("[data-table-filter]").forEach(function (input) {
    if (input.dataset.bound === "true") return;
    input.dataset.bound = "true";
    input.addEventListener("input", function () {
      var table = document.querySelector(input.getAttribute("data-table-filter"));
      if (!table) return;
      var query = input.value.trim().toLowerCase();
      table.querySelectorAll("tbody tr").forEach(function (row) {
        var text = (row.getAttribute("data-filter-text") || row.textContent || "").toLowerCase();
        row.hidden = query && text.indexOf(query) === -1;
      });
    });
  });
}

function initSymbolFilters(root) {
  (root || document).querySelectorAll("[data-symbol-filter]").forEach(function (input) {
    if (input.dataset.bound === "true") return;
    input.dataset.bound = "true";
    input.addEventListener("input", function () {
      var select = document.querySelector(input.getAttribute("data-symbol-filter"));
      if (!select) return;
      var query = input.value.trim().toLowerCase();
      Array.prototype.forEach.call(select.options, function (option) {
        var text = (option.getAttribute("data-filter-text") || option.textContent || "").toLowerCase();
        option.hidden = query && text.indexOf(query) === -1;
      });
      var firstVisible = Array.prototype.find.call(select.options, function (option) {
        return !option.hidden;
      });
      if (firstVisible) select.value = firstVisible.value;
    });
  });
}

function initActiveNav() {
  var path = window.location.pathname;
  document.querySelectorAll(".nav-link").forEach(function (link) {
    if (link.getAttribute("href") === path) {
      link.classList.add("nav-link-active");
    }
  });
}

function initLiveData() {
  var config = window.QuantaLiveData;
  if (!config || !config.symbol) return;
  var status = document.querySelector("[data-live-status]");
  var symbolSelect = document.querySelector("[data-live-symbol]");
  function openForSymbol(symbol) {
    var wsScheme = window.location.protocol === "https:" ? "wss://" : "ws://";
    return connectSocket(wsScheme + window.location.host + "/ws/data/live?symbol=" + encodeURIComponent(symbol), function (payload) {
      if (!payload.ok) {
        if (status) {
          status.textContent = payload.error || "live unavailable";
          status.classList.remove("status-green", "status-gray");
          status.classList.add("status-amber");
        }
        return;
      }
      setLiveField("bid", payload.bid);
      setLiveField("ask", payload.ask);
      setLiveField("spread", payload.spread);
    }, status);
  }
  var close = openForSymbol(config.symbol);
  if (symbolSelect) {
    symbolSelect.addEventListener("change", function () {
      close();
      close = openForSymbol(symbolSelect.value);
    });
  }
}

function initLiveRegime() {
  var config = window.QuantaLiveRegime;
  if (!config || !config.symbol) return;
  var status = document.querySelector("[data-live-status]");
  var wsScheme = window.location.protocol === "https:" ? "wss://" : "ws://";
  connectSocket(
    wsScheme + window.location.host + "/ws/regime/live?symbol=" + encodeURIComponent(config.symbol) + "&timeframe=" + encodeURIComponent(config.timeframe || "M15") + "&tf_minutes=" + encodeURIComponent(config.tfMinutes || 15),
    function (payload) {
      if (payload.ok && payload.current_regime) {
        setLiveField("regime", payload.current_regime.regime_id);
        setLiveField("active-duration", payload.active_duration_minutes);
      }
    },
    status
  );
}

function initHtmxLite(root) {
  if (window.htmx) return;
  var scope = root || document;

  function targetFor(source) {
    var selector = source.getAttribute("hx-target");
    if (!selector) return source;
    return document.querySelector(selector) || source;
  }

  function swap(target, html, mode) {
    if ((mode || "innerHTML").toLowerCase() === "outerhtml") {
      target.outerHTML = html;
      initAfterSwap(document);
      return;
    }
    target.innerHTML = html;
    initAfterSwap(target);
  }

  function showLoading(target) {
    if (!target) return;
    target.innerHTML = '<section class="panel"><div class="text-sm text-zinc-500">Loading...</div></section>';
  }

  function showError(target, error) {
    if (!target) return;
    var message = error && error.message ? error.message : "Request failed.";
    target.innerHTML =
      '<section class="panel border-amber-300"><div class="label">Request Failed</div><div class="mt-2 text-sm text-amber-300">' +
      message +
      "</div></section>";
  }

  function formDataFor(source) {
    var form = source.tagName === "FORM" ? source : source.closest("form");
    return form ? new FormData(form) : new FormData();
  }

  function request(source, method, url) {
    var target = targetFor(source);
    var options = { method: method };
    if (method === "POST") {
      options.body = formDataFor(source);
    }
    showLoading(target);
    fetch(url, options)
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.text();
      })
      .then(function (html) {
        swap(target, html, source.getAttribute("hx-swap"));
      })
      .catch(function (error) {
        showError(target, error);
      });
  }

  scope.querySelectorAll("[hx-get]").forEach(function (node) {
    if (node.dataset.htmxLiteBound === "true") return;
    node.dataset.htmxLiteBound = "true";
    var trigger = node.getAttribute("hx-trigger") || "";
    if (trigger.indexOf("load") !== -1) {
      request(node, "GET", node.getAttribute("hx-get"));
    }
  });

  scope.querySelectorAll("form[hx-post], form[hx-get]").forEach(function (form) {
    if (form.dataset.htmxLiteBound === "true") return;
    form.dataset.htmxLiteBound = "true";
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var method = form.hasAttribute("hx-post") ? "POST" : "GET";
      request(form, method, form.getAttribute("hx-post") || form.getAttribute("hx-get"));
    });
  });

  scope.querySelectorAll("select[hx-post], select[hx-get], button[hx-post], button[hx-get]").forEach(function (node) {
    if (node.dataset.htmxLiteBound === "true") return;
    node.dataset.htmxLiteBound = "true";
    var eventName = node.tagName === "SELECT" ? "change" : "click";
    node.addEventListener(eventName, function (event) {
      event.preventDefault();
      var method = node.hasAttribute("hx-post") ? "POST" : "GET";
      request(node, method, node.getAttribute("hx-post") || node.getAttribute("hx-get"));
    });
  });
}

function initAfterSwap(root) {
  initTableFilters(root);
  initSymbolFilters(root);
  initHtmxLite(root);
}

document.addEventListener("DOMContentLoaded", function () {
  initActiveNav();
  initAfterSwap(document);
  initLiveData();
  initLiveRegime();
});

document.addEventListener("htmx:afterSwap", function (event) {
  initAfterSwap(event.target);
});
