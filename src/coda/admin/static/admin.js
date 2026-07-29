// Editor conveniences for the song create/detail forms. All prefills are
// "fill only when empty / not manually touched" — they never clobber a value
// the user typed. Pure client-side; the server stays the source of truth.
(function () {
  "use strict";

  // Boosted forms still hit validation-error responses (e.g. song create, 400).
  // htmx's default responseHandling skips the swap on non-2xx/3xx, which would
  // silently drop those error pages. Swap on 4xx too; keep 5xx as a hard error.
  if (window.htmx) {
    htmx.config.responseHandling = [
      { code: "204", swap: false },
      { code: "[23]..", swap: true },
      { code: "[4]..", swap: true },
      { code: "[5]..", swap: false, error: true },
    ];
  }

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  // --- unified auto-fill --------------------------------------------------
  // target mirrors derive() on every source change, UNLESS the user has typed
  // into target (manual). Clearing target (emptying it) resumes auto-fill.
  // A pre-populated target (edit forms) starts as manual so it isn't clobbered.
  function autoBind(target, derive, sources, onApply) {
    if (!target) return;
    let manual = target.value.trim() !== "";
    target.addEventListener("input", () => { manual = target.value.trim() !== ""; });
    const apply = () => {
      if (manual) return;
      const v = derive();
      if (v != null) target.value = v;
      if (onApply) onApply(target.value);
    };
    sources.forEach((s) => s.el && s.el.addEventListener(s.ev, apply));
    apply(); // initial pass (e.g. default-pack name on a fresh create form)
  }

  // "fractureray" from "Fracture Ray": lowercase, keep a-z0-9, drop the rest.
  function slug(s) { return s.toLowerCase().replace(/[^a-z0-9]/g, ""); }
  function firstNumber(s) { const m = String(s).match(/\d+(\.\d+)?/); return m ? m[0] : ""; }

  function wireAutofills(form) {
    const idEl = $("[data-songid]", form);
    const nameEl = $("[data-namesrc]", form);
    const packSel = $("[data-pack]", form);
    const packName = $("[data-packname]", form);
    const bpm = $("[data-bpm]", form);
    const base = $("[data-bpmbase]", form);
    const jacket = $(".jacket", form);
    const stemEl = jacket && $(".jacket-input", jacket);

    // The jacket's default stem mirrors song_id live (placeholder + data-default),
    // UNTIL the stem field is manually named. Clearing the stem resumes the mirror.
    const syncStem = () => {
      if (!jacket || !idEl || stemEl.value.trim() !== "") return;
      jacket.dataset.default = idEl.value;
      stemEl.placeholder = idEl.value;
    };

    // song_id <- slug(name_en); keep the jacket's default stem in step.
    autoBind(
      idEl,
      () => (nameEl ? slug(nameEl.value) : null),
      nameEl ? [{ el: nameEl, ev: "input" }] : [],
      syncStem // name->id autofill writes value programmatically (no input event)
    );
    if (idEl) idEl.addEventListener("input", syncStem);  // manual song_id edits
    if (stemEl) stemEl.addEventListener("input", syncStem); // clearing name resumes
    syncStem();
    // pack_name <- selected pack option's display name.
    autoBind(
      packName,
      () => {
        const opt = packSel && packSel.options[packSel.selectedIndex];
        return opt ? opt.dataset.name : null;
      },
      packSel ? [{ el: packSel, ev: "change" }] : []
    );
    // bpm_base <- first number in the bpm string.
    autoBind(
      base,
      () => (bpm ? firstNumber(bpm.value) : null),
      bpm ? [{ el: bpm, ev: "input" }] : []
    );
  }

  // --- rating -> level prefill (add-chart form) ---------------------------
  // x.0–x.6 -> "x"; x.7–x.9 -> "x+" (no "+" when x < 7). PREFILL only.
  function levelFromRating(raw) {
    const r = parseFloat(raw);
    if (!isFinite(r)) return "";
    const x = Math.floor(r + 1e-9);
    const frac = r - x;
    if (frac <= 0.6 + 1e-9) return String(x);
    return x >= 7 ? x + "+" : String(x);
  }
  function wireLevelPrefill(form) {
    const rating = $("[data-rating-src]", form);
    const level = $("[data-level-prefill]", form);
    if (!rating || !level) return;
    autoBind(level, () => levelFromRating(rating.value) || null,
             [{ el: rating, ev: "input" }]);
  }

  // --- chart_designer carryover across adds (per song, this tab) ----------
  function wireDesignerCarryover(form) {
    const el = $("[data-designer]", form);
    if (!el) return;
    const m = (form.getAttribute("action") || "").match(/\/songs\/([^/]+)\//);
    const key = "designer:" + (m ? m[1] : "?");
    if (!el.value.trim()) {
      const saved = sessionStorage.getItem(key);
      if (saved) el.value = saved;
    }
    form.addEventListener("submit", () => {
      if (el.value.trim()) sessionStorage.setItem(key, el.value.trim());
    });
  }

  // --- date field is raw unix-SECONDS; hover shows the parsed UTC datetime -
  // Accepts a pasted/typed seconds value directly, or a pasted ISO date which
  // it converts to seconds. The title (hover) always reflects the current value.
  function secToText(sec) {
    if (!isFinite(sec)) return "";
    return new Date(sec * 1000).toISOString().replace("T", " ").slice(0, 19) + " UTC";
  }
  function isoToSeconds(txt) {
    const m = txt.match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) / 1000 : null;
  }
  function wireSecDate(el) {
    const lbl = el.closest("label");
    const refresh = () => {
      const v = el.value.trim();
      const t = /^-?\d+$/.test(v) ? secToText(parseInt(v, 10)) : "";
      el.title = t; // native fallback
      if (lbl) { lbl.title = t; lbl.dataset.tip = t; } // styled tooltip
    };
    el.addEventListener("input", refresh);
    // On unfocus, convert a typed ISO date to seconds.
    el.addEventListener("change", () => {
      const v = el.value.trim();
      if (/^-?\d+$/.test(v)) return; // already seconds
      const sec = isoToSeconds(v);
      if (sec != null) { el.value = String(sec); refresh(); }
    });
    el.addEventListener("paste", (e) => {
      const txt = (e.clipboardData || window.clipboardData).getData("text").trim();
      if (/^-?\d+$/.test(txt)) return; // pure seconds: let the default paste through
      const sec = isoToSeconds(txt);
      if (sec != null) { e.preventDefault(); el.value = String(sec); refresh(); }
    });
    refresh();
  }

  // --- artist/charter link picker: parse "(id)" tail, auto-link -----------
  function wireLinkPicker(form) {
    const pick = $("[data-linkpick]", form);
    const hid = $("[data-linkid]", form);
    if (!pick || !hid) return;
    const idOf = (v) => { const m = v.match(/\(([^)]+)\)\s*$/); return m ? m[1] : ""; };
    pick.addEventListener("input", () => {
      const id = idOf(pick.value);
      if (id) { hid.value = id; form.requestSubmit ? form.requestSubmit() : form.submit(); }
    });
    form.addEventListener("submit", (e) => {
      const id = idOf(pick.value) || pick.value.trim();
      if (!id) { e.preventDefault(); return; }
      hid.value = id;
    });
  }

  // --- tag add picker (floating panel) ------------------------------------
  // The tag field opens a single reused panel listing the whole vocabulary
  // grouped by category (collapsible headers), tinted by category color and
  // live-filtered by what you type. Picking a row links that existing tag and
  // submits. Typing a label that matches no tag reveals the category field so
  // the Add button creates it (a new category is auto-created server-side).
  // The panel is a body-level singleton (not per-form) so many chart sub-forms
  // don't each duplicate the full vocabulary DOM.
  const TagPicker = (() => {
    let vocab = null;       // [{label, style, tags:[{slug,label}]}]
    let labelSet = null;    // lowercased existing tag labels + slugs (exact match)
    let panel = null;       // the singleton panel element
    let active = null;      // { form, input, catWrap, catInput } currently open
    const COLLAPSE_KEY = "tagcat-collapsed";

    function loadVocab() {
      if (vocab) return vocab;
      const el = document.getElementById("tag-vocab");
      try { vocab = el ? JSON.parse(el.textContent) : []; } catch { vocab = []; }
      labelSet = new Set();
      vocab.forEach((g) => g.tags.forEach((t) => {
        labelSet.add(t.label.toLowerCase());
        labelSet.add(t.slug.toLowerCase());
      }));
      return vocab;
    }

    function collapsedSet() {
      try { return new Set(JSON.parse(sessionStorage.getItem(COLLAPSE_KEY)) || []); }
      catch { return new Set(); }
    }
    function saveCollapsed(set) {
      sessionStorage.setItem(COLLAPSE_KEY, JSON.stringify(Array.from(set)));
    }

    // Build the panel DOM once from the vocabulary; filtering only toggles
    // visibility afterwards (the vocab itself is static per page load).
    function build() {
      if (panel) return panel;
      loadVocab();
      panel = document.createElement("div");
      panel.className = "tag-panel";
      panel.hidden = true;
      const collapsed = collapsedSet();
      const empty = document.createElement("p");
      empty.className = "tag-panel-empty muted";
      empty.textContent = "No matching tags — type to create a new one.";
      empty.hidden = true;
      vocab.forEach((g) => {
        const grp = document.createElement("div");
        grp.className = "tag-grp";
        if (collapsed.has(g.label)) grp.classList.add("collapsed");
        const head = document.createElement("button");
        head.type = "button";
        head.className = "tag-grp-head";
        head.innerHTML = `<span class="caret">▸</span><span class="tag-grp-name">${g.label}</span>`;
        head.addEventListener("click", () => {
          grp.classList.toggle("collapsed");
          const set = collapsedSet();
          grp.classList.contains("collapsed") ? set.add(g.label) : set.delete(g.label);
          saveCollapsed(set);
        });
        grp.appendChild(head);
        const ul = document.createElement("ul");
        ul.className = "tag-grp-list";
        g.tags.forEach((t) => {
          const li = document.createElement("li");
          li.className = "tag-opt chip-tint";
          li.setAttribute("style", g.style);
          li.textContent = t.slug;
          li.dataset.label = t.label;
          li.dataset.hay = (t.slug + " " + t.label).toLowerCase();
          // mousedown (not click) so it fires before the input's blur closes us.
          li.addEventListener("mousedown", (e) => { e.preventDefault(); choose(t.label); });
          ul.appendChild(li);
        });
        grp.appendChild(ul);
        panel.appendChild(grp);
      });
      panel.appendChild(empty);
      document.body.appendChild(panel);
      return panel;
    }

    function filter(q) {
      const query = q.trim().toLowerCase();
      let any = false;
      $$(".tag-grp", panel).forEach((grp) => {
        let shown = 0;
        $$(".tag-opt", grp).forEach((li) => {
          const hit = !query || li.dataset.hay.includes(query);
          li.hidden = !hit;
          if (hit) shown++;
        });
        grp.hidden = shown === 0;
        // While searching, force groups open so matches are visible regardless
        // of their saved collapsed state.
        grp.classList.toggle("searching", Boolean(query));
        if (shown) any = true;
      });
      $(".tag-panel-empty", panel).hidden = any;
    }

    function position() {
      if (!active) return;
      const r = active.input.getBoundingClientRect();
      const M = 6; // viewport gutter
      panel.style.minWidth = r.width + "px";
      // measure after minWidth so width reflects content
      const pw = panel.offsetWidth, ph = panel.offsetHeight;
      const vw = document.documentElement.clientWidth;
      const vh = document.documentElement.clientHeight;
      // horizontal: align to input left, clamp into viewport
      let left = Math.min(r.left, vw - pw - M);
      left = Math.max(M, left);
      // vertical: below input, flip above if it would overflow and more room up
      const below = r.bottom + 4;
      let top = below;
      if (below + ph > vh - M && r.top - 4 - ph >= M) top = r.top - 4 - ph;
      top = Math.max(M, Math.min(top, vh - ph - M));
      panel.style.left = left + "px";
      panel.style.top = top + "px";
    }

    function open(ctx) {
      build();
      active = ctx;
      filter(ctx.input.value);
      panel.hidden = false;
      position();
    }
    function close() {
      if (panel) panel.hidden = true;
      active = null;
    }
    function choose(label) {
      if (!active) return;
      active.input.value = label;
      showCat(active, false); // existing tag → no category needed
      const f = active.form;
      close();
      f.requestSubmit ? f.requestSubmit() : f.submit();
    }
    function showCat(ctx, on) {
      ctx.catWrap.hidden = !on;
      if (ctx.catInput) ctx.catInput.required = on;
    }
    const isExisting = (v) => { loadVocab(); return labelSet.has(v.trim().toLowerCase()); };

    // global dismissers (wired once)
    document.addEventListener("mousedown", (e) => {
      if (!active || panel.hidden) return;
      if (panel.contains(e.target) || e.target === active.input) return;
      close();
    });
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);

    return { open, close, filter, isExisting, showCat };
  })();

  function wireTagPicker(form) {
    const input = $("[data-tagpick]", form);
    const catWrap = $("[data-tagcat]", form);
    const catInput = $("[data-tagcatinput]", form);
    if (!input || !catWrap) return;
    const ctx = { form, input, catWrap, catInput };
    input.addEventListener("focus", () => TagPicker.open(ctx));
    input.addEventListener("input", () => {
      TagPicker.open(ctx);          // (re)open + reposition as they type
      TagPicker.filter(input.value);
      // New label (no exact match) needs a category to create it on submit.
      TagPicker.showCat(ctx, Boolean(input.value.trim()) && !TagPicker.isExisting(input.value));
    });
    input.addEventListener("keydown", (e) => { if (e.key === "Escape") TagPicker.close(); });
  }

  // Override-toggle checkbox: submit its form on change.
  function wireOverrideToggle(el) {
    el.addEventListener("change", () => {
      const f = el.closest("form");
      if (f) f.requestSubmit ? f.requestSubmit() : f.submit();
    });
  }

  // --- add-chart: hide overrides when the picked difficulty is ftr --------
  // ftr IS the song default, so it has no per-chart overrides (mirrors the
  // edit form's `if != ftr`). Disabled inputs also drop out of the POST.
  function wireFtrOverrides(form) {
    const sel = $("[name=difficulty]", form);
    const overrides = $("details.overrides", form);
    if (!sel || !overrides) return;
    const sync = () => {
      const isFtr = sel.value === "ftr";
      overrides.hidden = isFtr;
      if (isFtr) overrides.open = false;
      $$("input, select, textarea", overrides).forEach((el) => { el.disabled = isFtr; });
    };
    sel.addEventListener("change", sync);
    sync();
  }

  // --- unsaved indicator --------------------------------------------------
  // Mark a tracked form dirty on the first genuine user input and reveal its
  // [data-dirty] badge. Scoped to opt-in forms only, so the auto-submitting
  // link picker / override toggle and jacket.js's programmatic value writes
  // never trip it. Cleared on submit (the page reloads on the server round-trip).
  function wireDirtyTracker(form) {
    const badge = $("[data-dirty]", form);
    let dirty = false;
    const mark = () => {
      if (dirty) return;
      dirty = true;
      form.classList.add("dirty");
      if (badge) badge.hidden = false;
    };
    form.addEventListener("input", mark);
    form.addEventListener("change", mark);
    form.addEventListener("submit", () => {
      dirty = false;
      form.classList.remove("dirty");
      if (badge) badge.hidden = true;
    });
  }

  // --- <details> open-state persistence -----------------------------------
  // Forms here POST and reload the whole page, which resets every <details> to
  // its default-closed state. Remember each panel's open/closed state (keyed by
  // a structural DOM path, scoped to the page URL) so a save doesn't collapse
  // the sections you were working in. sessionStorage = per-tab, clears on close.
  function detailsKey(el) {
    const parts = [];
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      let i = 1, s = n;
      while ((s = s.previousElementSibling)) if (s.tagName === n.tagName) i++;
      parts.push(n.tagName + i);
    }
    return "det:" + location.pathname + "#" + parts.reverse().join("/");
  }
  function wireDetailsPersist(el) {
    const key = detailsKey(el);
    const saved = sessionStorage.getItem(key);
    if (saved === "1") el.open = true;
    else if (saved === "0") el.open = false;
    el.addEventListener("toggle", () => {
      sessionStorage.setItem(key, el.open ? "1" : "0");
    });
  }

  // --- song-list sort toggle (entity detail) -----------------------------
  // Client-side reorder of the rendered <li>s by idx / name / date. Re-clicking
  // the active key flips direction. The server ships per-(song,date) rows so a
  // song whose charts span multiple release dates arrives pre-split; for the
  // idx/name views we merge those back into one row per song (data-merge lists),
  // and only the date view keeps them split.
  function wireSongSort(toggle) {
    const list = toggle.closest("section").querySelector("[data-sortable]");
    if (!list) return;
    const split = $$("li[data-idx]", list).map((li) => li.cloneNode(true));

    // Merged view: one row per song, chips unioned and re-ordered by difficulty.
    let merged = split;
    if (list.hasAttribute("data-merge")) {
      const bySong = new Map();
      split.forEach((li) => {
        const id = li.dataset.song;
        if (!bySong.has(id)) {
          bySong.set(id, li.cloneNode(true));
        } else {
          $$(".diff-chip", li).forEach((c) => bySong.get(id).appendChild(c.cloneNode(true)));
        }
      });
      merged = Array.from(bySong.values());
      merged.forEach((li) => {
        const chips = $$(".diff-chip", li);
        // Owns every chart of the song → badges add nothing in the merged view.
        if (chips.length >= Number(li.dataset.total)) {
          chips.forEach((c) => c.remove());
        } else {
          chips
            .sort((a, b) => Number(a.dataset.ord) - Number(b.dataset.ord))
            .forEach((c) => li.appendChild(c));  // moves to tail in difficulty order
        }
      });
    }

    // Chosen sort persists across entity pages (not per-id) so a picked
    // key/direction sticks while browsing. data-merge pages key separately
    // since their valid sorts (merged vs split) differ from plain lists.
    const SORT_KEY = "songsort:" + (list.hasAttribute("data-merge") ? "merged" : "plain");

    let dir = 1;
    function render(key) {
      const rows = (key === "date" ? split : merged).map((li) => li.cloneNode(true));
      rows.sort((a, b) => {
        const x = a.dataset[key], y = b.dataset[key];
        const cmp = key === "name" ? x.localeCompare(y) : Number(x) - Number(y);
        return cmp * dir;
      });
      list.replaceChildren(...rows);
    }
    function apply(key, save) {
      $$("button", toggle).forEach((b) => b.classList.toggle("active", b.dataset.key === key));
      render(key);
      if (save) localStorage.setItem(SORT_KEY, JSON.stringify({ key, dir }));
    }

    toggle.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-key]");
      if (!btn) return;
      dir = btn.classList.contains("active") ? -dir : 1;
      apply(btn.dataset.key, true);
    });

    // Restore saved choice; fall back to merged/idx (matches default toggle).
    let saved;
    try { saved = JSON.parse(localStorage.getItem(SORT_KEY)); } catch { saved = null; }
    const keys = $$("button[data-key]", toggle).map((b) => b.dataset.key);
    if (saved && keys.includes(saved.key)) {
      dir = saved.dir === -1 ? -1 : 1;
      apply(saved.key, false);
    } else {
      apply("idx", false);
    }
  }

  // --- tag vocabulary page -----------------------------------------------
  // One global "edit mode" toggle flips the page between browse (pills link to
  // their detail page) and edit (inline label/slug/color edits, ✕ delete, drag
  // to reorder categories or move a tag to another category). Every mutation
  // POSTs and reloads, so edit mode is persisted in localStorage and restored.
  function wireTagsPage(page) {
    const EDIT_KEY = "tags-edit-mode";
    // The toggle lives in .page-head, outside this container — query the document.
    const toggle = $("[data-tags-edit-toggle]");
    const setEdit = (on) => {
      page.classList.toggle("editing", on);
      if (toggle) toggle.setAttribute("aria-pressed", on ? "true" : "false");
      localStorage.setItem(EDIT_KEY, on ? "1" : "0");
    };
    setEdit(localStorage.getItem(EDIT_KEY) === "1");
    if (toggle) toggle.addEventListener("click", () => setEdit(!page.classList.contains("editing")));

    // Collapse/expand per category, keyed by category id (so state travels with
    // the card across a drag-reorder, unlike a DOM-position key). sessionStorage.
    const COLLAPSE_KEY = "tagcat-collapsed-cards";
    const collapsed = () => {
      try { return new Set(JSON.parse(sessionStorage.getItem(COLLAPSE_KEY)) || []); }
      catch { return new Set(); }
    };
    const saveCollapsed = (set) => sessionStorage.setItem(COLLAPSE_KEY, JSON.stringify([...set]));
    const initial = collapsed();
    $$(".cat-card", page).forEach((card) => {
      if (initial.has(card.dataset.cid)) card.classList.add("collapsed");
      const btn = $("[data-cat-toggle]", card);
      if (btn) btn.addEventListener("click", () => {
        card.classList.toggle("collapsed");
        const set = collapsed();
        card.classList.contains("collapsed") ? set.add(card.dataset.cid) : set.delete(card.dataset.cid);
        saveCollapsed(set);
      });
    });

    // Color pickers: post the chosen color on change (a bare input, so build a
    // throwaway form pointed at its data-action).
    $$("[data-color-submit]", page).forEach((inp) => {
      inp.addEventListener("change", () => {
        const f = document.createElement("form");
        f.method = "post";
        f.action = inp.dataset.action;
        const c = document.createElement("input");
        c.name = "color"; c.value = inp.value;
        f.appendChild(c);
        document.body.appendChild(f);
        // Freshly appended: htmx's mutation observer processes it asynchronously,
        // so force-process now or the boost wiring may lose the race with submit.
        if (window.htmx) htmx.process(f);
        f.requestSubmit ? f.requestSubmit() : f.submit();
      });
    });

    // Inline-edit single-field forms: Enter submits (native); Escape reverts and
    // blurs; blur submits only if the value actually changed (else: no reload).
    $$("[data-inline-edit]", page).forEach((form) => {
      const inp = $("input", form);
      if (!inp) return;
      const orig = inp.value;
      inp.addEventListener("keydown", (e) => {
        if (e.key === "Escape") { inp.value = orig; inp.blur(); }
      });
      inp.addEventListener("blur", (e) => {
        // Don't submit when leaving for the pill's own ✕ — let the delete win.
        if (e.relatedTarget && e.relatedTarget.closest(".pill-del")) { inp.value = orig; return; }
        if (inp.value.trim() && inp.value !== orig) {
          form.requestSubmit ? form.requestSubmit() : form.submit();
        } else {
          inp.value = orig; // discard whitespace-only / unchanged edits
        }
      });
    });

    // Hug content: `field-sizing:content` handles this in Chromium; the `size`
    // attribute is the cross-browser fallback (Safari has no field-sizing yet).
    $$(".cat-edit, .pill-edit-input, .tag-add-input", page).forEach((inp) => {
      const fit = () => { inp.size = Math.max(2, inp.value.length || inp.placeholder.length); };
      inp.addEventListener("input", fit);
      fit();
    });

    // Add-tag box → input on click; revert to the box if left empty.
    $$("[data-tag-add]", page).forEach((form) => {
      const btn = $("[data-tag-add-btn]", form);
      const inp = $(".tag-add-input", form);
      if (!btn || !inp) return;
      btn.addEventListener("click", () => {
        btn.hidden = true; inp.hidden = false; inp.focus();
      });
      inp.addEventListener("blur", () => {
        if (!inp.value.trim()) { inp.hidden = true; btn.hidden = false; }
      });
      inp.addEventListener("keydown", (e) => {
        if (e.key === "Escape") { inp.value = ""; inp.blur(); }
      });
    });

    wireCatReorder(page);
    wirePillMove(page);
  }

  // Drag category cards by their handle to reorder; on drop, POST the new id
  // order. Only submits when the order changed.
  function wireCatReorder(page) {
    const list = $("[data-cat-list]", page);
    const form = $("[data-reorder-form]", page);
    if (!list || !form) return;
    const order = () => $$(".cat-card", list).map((c) => c.dataset.cid);
    const before = order().join(",");
    let dragged = null;

    $$(".cat-handle", list).forEach((h) => {
      const card = h.closest(".cat-card");
      h.addEventListener("dragstart", (e) => {
        dragged = card; card.classList.add("dragging");
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", "cat");
      });
      h.addEventListener("dragend", () => {
        if (dragged) dragged.classList.remove("dragging");
        dragged = null;
        if (order().join(",") !== before) {
          $("[data-reorder-input]", form).value = order().join(",");
          form.requestSubmit ? form.requestSubmit() : form.submit();
        }
      });
    });

    list.addEventListener("dragover", (e) => {
      if (!dragged) return;
      e.preventDefault();
      const after = $$(".cat-card:not(.dragging)", list).find((c) => {
        const r = c.getBoundingClientRect();
        return e.clientY < r.top + r.height / 2;
      });
      if (after) list.insertBefore(dragged, after);
      else list.appendChild(dragged);
    });
  }

  // Drag a pill onto another category's pill area to recategorize the tag.
  function wirePillMove(page) {
    const moveForm = $("[data-move-form]", page);
    if (!moveForm) return;
    let tid = null, fromCid = null;

    $$(".pill-edit[draggable]", page).forEach((grip) => {
      const pill = grip.closest(".tag-pill");
      const pills = grip.closest("[data-tag-pills]");
      grip.addEventListener("dragstart", (e) => {
        tid = pill.dataset.tid; fromCid = pills.dataset.cid;
        pill.classList.add("dragging");
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", "pill");
      });
      grip.addEventListener("dragend", () => {
        pill.classList.remove("dragging");
        tid = null; fromCid = null;  // clear so a later category-handle drag isn't mistaken for a pill
      });
    });

    $$("[data-tag-pills]", page).forEach((zone) => {
      zone.addEventListener("dragover", (e) => {
        if (tid == null) return;          // not a pill drag
        e.preventDefault();
        if (zone.dataset.cid !== fromCid) zone.classList.add("drop-target");
      });
      zone.addEventListener("dragleave", () => zone.classList.remove("drop-target"));
      zone.addEventListener("drop", (e) => {
        zone.classList.remove("drop-target");
        if (tid == null || zone.dataset.cid === fromCid) return;
        e.preventDefault();
        moveForm.action = "/tags/items/" + tid + "/move";
        $("[data-move-cat]", moveForm).value = zone.dataset.cid;
        moveForm.requestSubmit ? moveForm.requestSubmit() : moveForm.submit();
      });
    });
  }

  function boot(scope) {
    $$("[data-tags-page]", scope).forEach(wireTagsPage);
    $$("[data-sort-songs]", scope).forEach(wireSongSort);
    $$("details", scope).forEach(wireDetailsPersist);
    $$("[data-overridetoggle]", scope).forEach(wireOverrideToggle);
    $$("[data-song-form]", scope).forEach(wireAutofills);
    $$("[data-addchart]", scope).forEach((f) => {
      wireLevelPrefill(f); wireDesignerCarryover(f); wireFtrOverrides(f);
    });
    $$("[data-linkform]", scope).forEach(wireLinkPicker);
    $$("[data-tagform]", scope).forEach(wireTagPicker);
    $$("[data-secdate]", scope).forEach(wireSecDate);
    $$("[data-dirty-track]", scope).forEach(wireDirtyTracker);
  }

  // After a save we redirect to #chart-<id>; open that chart and scroll to it so
  // the page doesn't jump back to the top.
  function revealHashChart() {
    if (!location.hash) return;
    const el = document.querySelector(location.hash);
    if (!el) return;
    if (el.tagName === "DETAILS") el.open = true;
    el.scrollIntoView({ block: "center" });
  }

  document.addEventListener("DOMContentLoaded", () => { boot(document); revealHashChart(); });
  document.body && document.addEventListener("htmx:afterSwap", (e) => { boot(e.target); revealHashChart(); });
})();
