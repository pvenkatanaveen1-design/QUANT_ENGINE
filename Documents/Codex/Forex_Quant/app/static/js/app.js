document.addEventListener("htmx:responseError", function () {
  console.warn("HTMX request failed");
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
