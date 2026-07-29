// Jacket widget: drop a file or paste an image URL; it uploads to
// assets/jackets/<stem>.webp and points the field at that stem. The stem is the
// field's current value, or the widget's data-default (song_id / song_id_DIFF).
(function () {
  function bust(src) {
    return src + (src.includes("?") ? "&" : "?") + "t=" + Date.now();
  }

  function init(root) {
    const input = root.querySelector(".jacket-input");
    const thumb = root.querySelector(".jacket-thumb");
    const file = root.querySelector(".jacket-file");
    const drop = root.querySelector(".jacket-drop");
    const urlInput = root.querySelector(".jacket-url-input");
    const urlBtn = root.querySelector(".jacket-url-btn");
    const status = root.querySelector(".jacket-status");

    function stem() {
      return (input.value.trim() || root.dataset.default || "").trim();
    }

    async function send(form) {
      const target = stem();
      if (!target) {
        status.textContent = "Set a name first.";
        return;
      }
      form.set("stem", target);
      status.textContent = "Downloading…";
      try {
        const res = await fetch("/jackets/upload", { method: "POST", body: form });
        const data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.detail || "upload failed");
        input.value = data.stem;
        thumb.src = bust(data.src);
        thumb.style.display = "";
        status.textContent = "Saved " + data.stem + ".webp";
      } catch (e) {
        status.textContent = "✕ " + e.message;
      }
    }

    function sendFile(f) {
      const form = new FormData();
      form.append("file", f);
      send(form);
    }

    drop.addEventListener("click", () => file.click());
    drop.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); file.click(); }
    });
    file.addEventListener("change", () => { if (file.files[0]) sendFile(file.files[0]); });

    ["dragover", "dragenter"].forEach((ev) =>
      drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); })
    );
    ["dragleave", "drop"].forEach((ev) =>
      drop.addEventListener(ev, () => drop.classList.remove("over"))
    );
    drop.addEventListener("drop", (e) => {
      e.preventDefault();
      const f = e.dataTransfer.files[0];
      const uri = e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain");
      if (f) sendFile(f);
      else if (uri) { const fd = new FormData(); fd.append("url", uri.trim()); send(fd); }
    });

    if (urlBtn) {
      urlBtn.addEventListener("click", () => {
        const u = urlInput.value.trim();
        if (!u) return;
        const fd = new FormData();
        fd.append("url", u);
        send(fd);
      });
    }

    // Live-refresh preview when the stem is typed/changed.
    input.addEventListener("change", () => {
      if (input.value.trim()) { thumb.src = bust("/jacket-img/" + input.value.trim() + ".webp"); thumb.style.display = ""; }
    });
    thumb.addEventListener("error", () => { thumb.style.display = "none"; });
  }

  function boot(scope) {
    (scope || document).querySelectorAll(".jacket:not([data-init])").forEach((el) => {
      el.dataset.init = "1";
      init(el);
    });
  }
  document.addEventListener("DOMContentLoaded", () => boot());
  // Re-init after htmx swaps, if any region containing widgets is replaced.
  document.body && document.addEventListener("htmx:afterSwap", (e) => boot(e.target));
})();
