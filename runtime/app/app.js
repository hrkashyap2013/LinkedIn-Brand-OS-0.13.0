"use strict";
// All text from the server or the AI is inserted as plain text nodes, never as markup.
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var S = { meta: null, post: null, data: null, posts: [], busy: false, history: [], lastReply: null };

  function h(tag, attrs) {
    var el = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      if (k === "class") el.className = attrs[k];
      else if (k === "text") el.textContent = attrs[k];
      else if (k === "onclick") el.addEventListener("click", attrs[k]);
      else if (k === "value") el.value = attrs[k];
      else if (attrs[k] === true) el.setAttribute(k, "");
      else if (attrs[k] !== false && attrs[k] != null) el.setAttribute(k, attrs[k]);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null || c === false) continue;
      el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return el;
  }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  function api(method, path, body) {
    var opt = { method: method, credentials: "same-origin", headers: { "X-LBA": "1" } };
    if (method === "POST") { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body || {}); }
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return { error: "The app returned something unexpected." }; }).then(function (j) {
        if (!r.ok || j.error) throw new Error(j.error || ("Request failed (" + r.status + ")"));
        return j;
      });
    });
  }

  function banner(msg, bad) {
    var b = $("banner");
    if (!msg) { b.hidden = true; return; }
    b.hidden = false; b.className = "banner" + (bad ? " bad" : ""); b.textContent = msg;
  }

  // ---- background jobs (the AI steps are slow, so the browser polls)
  function runJob(path, body, label) {
    if (S.busy) { banner("Another step is still running. Please wait for it to finish.", true); return Promise.resolve(); }
    S.busy = true; banner("");
    var t0 = Date.now(), p = $("progress");
    p.hidden = false;
    var tick = setInterval(function () { $("progress-text").textContent = (label || "Working") + "... " + Math.round((Date.now() - t0) / 1000) + "s (your AI tool can take a minute or two)"; }, 500);
    function finish() { clearInterval(tick); p.hidden = true; S.busy = false; }
    return api("POST", path, body).then(function (r) {
      return new Promise(function (resolve, reject) {
        (function poll() {
          api("GET", "/api/job/" + r.job).then(function (j) {
            if (j.state === "running") return setTimeout(poll, 1000);
            finish();
            if (j.state === "error") reject(new Error(j.error)); else resolve(j.result);
          }).catch(function (e) { finish(); reject(e); });
        })();
      });
    }).catch(function (e) { finish(); banner(e.message, true); throw e; });
  }

  function act(promise) { return promise.then(refreshPost).catch(function () {}); }

  // ---- tabs
  var tabs = document.querySelectorAll("#tabs button");
  Array.prototype.forEach.call(tabs, function (b) {
    b.addEventListener("click", function () { showTab(b.getAttribute("data-tab")); });
  });
  function showTab(name) {
    Array.prototype.forEach.call(tabs, function (b) { b.className = b.getAttribute("data-tab") === name ? "active" : ""; });
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (t) { t.hidden = t.id !== "tab-" + name; });
    if (name === "runs") loadRuns(); else if (name === "metrics") loadMetrics(); else if (name === "help") renderHelp(); else if (name === "chat") loadChat();
  }

  // ---- posts and pipeline
  function loadPosts(select) {
    return api("GET", "/api/posts").then(function (r) {
      S.posts = r.posts;
      var sel = $("post-select");
      clear(sel);
      if (!r.posts.length) sel.appendChild(h("option", { value: "", text: "(no posts yet)" }));
      r.posts.forEach(function (p) {
        sel.appendChild(h("option", { value: p.post_id, text: p.post_id + "  " + (p.title || "untitled") + "  (" + p.done + "/" + p.total + ")" }));
      });
      var want = select || S.post || (r.posts.length ? r.posts[r.posts.length - 1].post_id : null);
      if (want) { sel.value = want; S.post = want; return refreshPost(); }
      S.post = null; renderStage();
    });
  }
  $("post-select").addEventListener("change", function () { S.post = this.value || null; refreshPost(); });
  $("btn-newpost").addEventListener("click", function () {
    api("POST", "/api/post/new", { title: "", role: "" }).then(function (r) { return loadPosts(r.post_id); }).catch(function (e) { banner(e.message, true); });
  });
  function refreshPost() {
    if (!S.post) { S.data = null; renderStage(); return Promise.resolve(); }
    return api("GET", "/api/post/" + S.post).then(function (d) { S.data = d; renderStage(); }).catch(function (e) { banner(e.message, true); });
  }

  function stepsList() {
    var ol = $("steps"); clear(ol);
    if (!S.data) return;
    S.data.steps.forEach(function (s) {
      ol.appendChild(h("li", { class: s.done ? "done" : (s.available ? "" : "off"), title: s.why_not || "" }, h("span", { class: "dot", text: s.done ? "\u2713" : "\u2022" }), s.label));
    });
  }

  function strip(d) {
    var names = { 1: "idea", 2: "visual", 3: "post and visual", 4: "package" };
    var box = h("div", { class: "strip" });
    [1, 2, 3, 4].forEach(function (n) {
      var x = d.decisions[n];
      var cls = x.current ? "pill ok" : (x.approved ? "pill stale" : "pill");
      var txt = "Decision " + n + ": " + names[n] + " \u2014 " + (x.current ? "approved" : (x.approved ? "changed, approve again" : "not yet"));
      box.appendChild(h("span", { class: cls, text: txt }));
    });
    return box;
  }

  function stepOf(key) { return S.data.steps.filter(function (s) { return s.key === key; })[0]; }
  function card(title, key, body, extraClass) {
    var st = key ? stepOf(key) : null;
    var off = st && !st.available;
    var c = h("div", { class: "card" + (off ? " off" : "") + (extraClass ? " " + extraClass : "") }, h("h2", { text: title }));
    if (off) c.appendChild(h("div", { class: "why", text: st.why_not }));
    else body.forEach(function (b) { if (b) c.appendChild(b); });
    return c;
  }
  function feedbackBox(id, placeholder) { return h("textarea", { id: id, rows: "2", placeholder: placeholder || "Optional: tell the agents what to change" }); }
  function val(id) { var e = $(id); return e ? e.value : ""; }
  function runBtn(label, step, extra, fbId, cls) {
    return h("button", { class: cls || "primary", text: label, onclick: function () {
      var body = { step: step, feedback: fbId ? val(fbId) : "" };
      Object.keys(extra || {}).forEach(function (k) { body[k] = typeof extra[k] === "function" ? extra[k]() : extra[k]; });
      act(runJob("/api/post/" + S.post + "/step", body, label));
    } });
  }
  function decide(n, choice, label, extra) {
    return h("button", { class: "go", text: label, onclick: function () {
      var body = { decision: n }; if (choice) body.choice = choice;
      Object.keys(extra || {}).forEach(function (k) { body[k] = typeof extra[k] === "function" ? extra[k]() : extra[k]; });
      banner("");
      act(api("POST", "/api/post/" + S.post + "/decision", body));
    } });
  }
  function img(path, alt) { return h("img", { src: path, alt: alt || "" }); }
  function fileUrl(area, name) { return "/files/" + S.post + "/" + area + "/" + name; }
  function copyBox(title, text) {
    var pre = h("pre", { text: text || "(empty)" });
    var btn = h("button", { class: "small", text: "Copy", onclick: function () {
      var done = function () { btn.textContent = "Copied"; setTimeout(function () { btn.textContent = "Copy"; }, 1500); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text || "").then(done, function () { selectText(pre); });
      else selectText(pre);
    } });
    return h("div", { class: "copybox" }, h("div", { class: "bar" }, h("span", { text: title }), btn), pre);
  }
  function selectText(el) { var r = document.createRange(); r.selectNodeContents(el); var s = window.getSelection(); s.removeAllRanges(); s.addRange(r); }

  function renderStage() {
    stepsList();
    var st = $("stage"); clear(st);
    if (!S.data) { st.appendChild(h("div", { class: "card" }, h("h2", { text: "Start here" }), h("p", { text: "Click New post, then follow the cards from top to bottom. You make four decisions; nothing is posted for you." }))); return; }
    var d = S.data, s = d.state;
    st.appendChild(strip(d));

    // 1 ideas
    var ideaNodes = [h("p", { class: "muted", text: "The agents check your profile and memory, then propose 3 ideas. You pick one: that is Decision 1." }), feedbackBox("fb-ideas", "Optional: a theme or angle you want"),
      h("div", { class: "row" }, runBtn(s.ideas.length ? "Get 3 new ideas" : "Get 3 ideas", "ideas", {}, "fb-ideas"))];
    if (s.freshness_note) ideaNodes.push(h("p", { class: "muted", text: s.freshness_note }));
    s.ideas.forEach(function (it, i) {
      var chosen = s.chosen_idea === i + 1 && d.decisions[1].current;
      ideaNodes.push(h("div", { class: "idea" + (chosen ? " chosen" : "") }, h("h3", { text: (i + 1) + ". " + it.title }), h("div", { text: it.angle }),
        it.why_it_fits ? h("div", { class: "muted", text: "Why it fits: " + it.why_it_fits }) : null, it.proof_needed ? h("div", { class: "muted", text: "Proof you will need: " + it.proof_needed }) : null,
        chosen ? h("div", { class: "ok", text: "\u2713 Chosen (Decision 1)" }) : h("div", { class: "row" }, decide(1, i + 1, "Choose this idea (Decision 1)"))));
    });
    st.appendChild(card("1. Ideas and Decision 1", "ideas", ideaNodes));

    // 2 draft
    var dn = [];
    if (s.evidence_status === "INSUFFICIENT EVIDENCE") {
      dn.push(h("div", { class: "banner bad" }, "The agents need real support before they can write this. ", h("br"), (s.evidence_gaps || []).join(" ")));
      dn.push(h("textarea", { id: "support", rows: "4", placeholder: "Paste your real example, experience or source here. The agents will use only this as evidence." }));
    }
    dn.push(feedbackBox("fb-draft", "Optional: what to change (tone, length, focus)"));
    dn.push(h("div", { class: "row" }, runBtn(d.post_text ? "Rewrite the post" : "Write the post", "draft", { support: function () { return val("support"); } }, "fb-draft")));
    if (d.post_text) {
      dn.push(h("label", { class: "muted", text: "Post text (you can edit it; any edit means the later decisions must be approved again)" }));
      dn.push(h("textarea", { id: "ed-text", rows: "10", value: d.post_text }));
      dn.push(h("label", { class: "muted", text: "First comment" })); dn.push(h("textarea", { id: "ed-first", rows: "2", value: d.package.first_comment || "" }));
      dn.push(h("label", { class: "muted", text: "Comment to pin" })); dn.push(h("textarea", { id: "ed-pin", rows: "2", value: d.package.pin_comment || "" }));
      dn.push(h("label", { class: "muted", text: "Hashtags (separate with commas)" })); dn.push(h("input", { type: "text", id: "ed-tags", value: (d.package.hashtags || []).join(", ") }));
      var wc = d.writing_checks;
      if (wc) {
        var issues = wc.lint.filter(function (f) { return f.level !== "NOTE"; });
        dn.push(h("div", { class: "muted", text: "Writing checks (tier: " + wc.tier + "). Machine-like patterns: " + wc.tells_score + "/100, " + wc.tells_label + "." }));
        issues.forEach(function (f) { dn.push(h("div", { class: f.level === "ERROR" ? "bad" : "warn", text: (f.level === "ERROR" ? "\u2716 " : "\u26A0 ") + f.message })); });
        wc.tells.forEach(function (f) { dn.push(h("div", { class: "warn", text: "\u26A0 " + f.message + (f.examples.length ? " (e.g. " + f.examples.join("; ") + ")" : "") })); });
        wc.lint.filter(function (f) { return f.level === "NOTE"; }).forEach(function (f) { dn.push(h("div", { class: "muted", text: "\u2022 " + f.message })); });
        if (issues.length || wc.tells.length) {
          dn.push(h("div", { class: "row" }, h("button", { text: "Ask the AI to fix these", onclick: function () {
            var msg = "Fix these problems without changing any claim, figure, quotation or link, and keep my voice: " + issues.map(function (f) { return f.message; }).concat(wc.tells.map(function (f) { return f.message; })).join(" ");
            act(runJob("/api/post/" + S.post + "/step", { step: "draft", feedback: msg, support: "" }, "Fixing the writing"));
          } })));
        }
      }
      dn.push(h("div", { class: "row" }, h("button", { text: "Save my edits", onclick: function () {
        act(api("POST", "/api/post/" + S.post + "/fields", { post_text: val("ed-text"), fields: { first_comment: val("ed-first"), pin_comment: val("ed-pin"), hashtags: val("ed-tags") } }));
      } })));
    }
    st.appendChild(card("2. Write the post", "draft", dn));

    // 3 visual previews
    var vn = [h("p", { class: "muted", text: "3 previews of 3 different diagram types, using only the words of your post. You pick one: Decision 2." }), feedbackBox("fb-vis"),
      h("div", { class: "row" }, runBtn(d.previews.length ? "Get 3 new previews" : "Get 3 previews", "visuals", {}, "fb-vis"))];
    if (s.blueprint) vn.push(h("p", { class: "muted", text: s.blueprint }));
    if (d.previews.length) {
      var grid = h("div", { class: "previews" });
      d.previews.forEach(function (p) {
        var chosen = d.decisions[2].current && d.fingerprints.visual === p.spec_fingerprint;
        grid.appendChild(h("div", { class: "preview" + (chosen ? " chosen" : "") }, img(fileUrl("previews", p.png || p.svg), p.alt_short), h("div", { text: p.number + ". " + p.type.replace(/_/g, " ") }),
          h("div", { class: "muted", text: p.reason }), (p.warnings || []).map(function (w) { return h("div", { class: "warn", text: "\u26A0 " + w.message }); }),
          chosen ? h("div", { class: "ok", text: "\u2713 Picked (Decision 2)" }) : h("div", { class: "row" }, decide(2, p.number, "Pick this one (Decision 2)"))));
      });
      vn.push(grid);
    }
    st.appendChild(card("3. Visual previews and Decision 2", "visuals", vn));

    // 4 final visual
    var fn = [h("div", { class: "row" }, h("select", { id: "fmt" }, h("option", { value: "portrait", text: "Portrait 1080x1350 (recommended)" }), h("option", { value: "square", text: "Square 1080x1080" })),
      runBtn("Render the final visual", "render", { format: function () { return val("fmt"); } }, null),
      runBtn("Make a carousel (PDF) instead", "carousel", {}, "fb-car", "")), feedbackBox("fb-car", "Optional: what the carousel should cover")];
    if (d.final.files.length) {
      var png = d.final.files.filter(function (f) { return /\.png$/.test(f); })[0], svg = d.final.files.filter(function (f) { return /\.svg$/.test(f); })[0];
      var pdf = d.final.files.filter(function (f) { return /\.pdf$/.test(f); })[0];
      fn.push(h("div", { class: "final" }, img(fileUrl("final", png || svg), d.final.alt_short)));
      if (pdf) fn.push(h("p", {}, h("a", { href: fileUrl("final", pdf), target: "_blank", rel: "noopener", text: "Open the carousel PDF" })));
      fn.push(h("p", { class: "muted", text: "Alt text: " + d.final.alt_short }));
      d.final.messages.forEach(function (m) { fn.push(h("div", { class: "warn", text: m })); });
      d.final.warnings.forEach(function (w) { fn.push(h("div", { class: "warn", text: "\u26A0 " + w.message })); });
      if (!d.decisions[2].current && d.visual_type === "carousel") fn.push(h("div", { class: "row" }, decide(2, null, "Approve this carousel as my visual (Decision 2)")));
    }
    st.appendChild(card("4. Final visual", "render", fn));

    // 5 checks
    var cn = [feedbackBox("fb-chk", "Optional: something specific to check"), h("div", { class: "row" }, runBtn(s.check ? "Run the checks again" : "Run quality checks", "check", {}, "fb-chk"))];
    var chk = s.check;
    if (chk) {
      cn.push(h("p", {}, h("b", { text: "Visual quality: " + chk.qa.score + "/100 " }), h("span", { class: chk.qa.pass ? "ok" : "bad", text: chk.qa.pass ? "(passes the gate)" : "(below the gate)" })));
      cn.push(h("p", {}, h("b", { text: "Governance: " + chk.governance.status })));
      chk.governance.notes.forEach(function (n) { cn.push(h("div", { class: "muted", text: "\u2022 " + n })); });
      chk.qa.defects.forEach(function (n) { cn.push(h("div", { class: "warn", text: "\u2022 " + n })); });
      cn.push(h("p", { class: "muted", text: "Automatic checks: smallest text " + chk.engine.min_font_px + " px, about " + chk.engine.words + " words." }));
      chk.engine.warnings.forEach(function (w) { cn.push(h("div", { class: "warn", text: "\u26A0 " + w.message })); });
      chk.engine.errors.forEach(function (w) { cn.push(h("div", { class: "bad", text: "\u2716 " + w })); });
    }
    st.appendChild(card("5. Quality checks", "check", cn));

    // 6 approve content
    var an = [h("p", { class: "muted", text: "You are approving exactly this post text and this visual. If you change either later, this approval stops matching." }), copyBox("Post text", d.post_text)];
    an.push(h("label", { class: "chk" }, h("input", { type: "checkbox", id: "accept" }), h("span", { text: "I have read any open findings above and I accept them." })));
    an.push(h("div", { class: "row" }, decide(3, null, "Approve post and visual (Decision 3)", { accept_findings: function () { return $("accept").checked; } })));
    st.appendChild(card("6. Decision 3: approve the post and visual", "decision3", an));

    // 7 package
    var pk = d.package, fields = [["suggested_time", "Suggested time to post"], ["audience", "Audience"], ["objective", "Objective"], ["cta_type", "Call to action"], ["expected_takeaway", "Expected takeaway"]];
    var pn = [h("p", { class: "muted", text: "Check the package details. A suggested time is required." })];
    fields.forEach(function (f) { pn.push(h("label", { class: "muted", text: f[1] })); pn.push(h("input", { type: "text", id: "pk-" + f[0], value: pk[f[0]] || "" })); });
    pn.push(h("div", { class: "row" }, h("button", { text: "Save package details", onclick: function () {
      var u = {}; fields.forEach(function (f) { u[f[0]] = val("pk-" + f[0]); });
      act(api("POST", "/api/post/" + S.post + "/fields", { fields: u }));
    } }), decide(4, null, "Approve the package (Decision 4)")));
    st.appendChild(card("7. Decision 4: approve the package", "decision4", pn));

    // 8 build
    var bn = [h("p", { class: "muted", text: "Builds the folder you will copy from. It refuses if any of the four decisions no longer matches." }),
      h("div", { class: "row" }, h("button", { class: "primary", text: d.built ? "Rebuild the package" : "Build the ready-to-paste package", onclick: function () {
        banner(""); act(api("POST", "/api/post/" + S.post + "/build", {}));
      } }))];
    if (d.approval_problems.length && !d.built) d.approval_problems.forEach(function (p) { bn.push(h("div", { class: "warn", text: p })); });
    if (d.built) {
      bn.push(h("p", { class: "ok", text: "Package folder: " + d.built.folder }));
      bn.push(h("div", { id: "parts" }));
      loadParts();
    }
    st.appendChild(card("8. Ready-to-paste package", "build", bn));

    // 9 live
    var ln = [h("p", { class: "muted", text: "After you have posted it yourself, paste the post link and choose when you want results-check reminders." }), h("input", { type: "text", id: "live-url", placeholder: "https://www.linkedin.com/..." })];
    var wrap = h("div", { class: "row" });
    (S.meta.windows || []).forEach(function (w) {
      var on = (d.package.measurement_windows || []).indexOf(w) >= 0;
      var cb = h("input", { type: "checkbox", value: w, class: "win" }); cb.checked = on;
      wrap.appendChild(h("label", { class: "chk" }, cb, h("span", { text: w })));
    });
    ln.push(wrap);
    ln.push(h("div", { class: "muted", text: "Also remind me to read and answer the comments (you choose when):" }));
    var rwrap = h("div", { class: "row" });
    (S.meta.reply_windows || []).forEach(function (w) {
      var cb2 = h("input", { type: "checkbox", value: w, class: "rwin" });
      rwrap.appendChild(h("label", { class: "chk" }, cb2, h("span", { text: w + " after posting" })));
    });
    ln.push(rwrap);
    ln.push(h("div", { class: "row" }, h("button", { class: "primary", text: "Mark as live and start reminders", onclick: function () {
      var wins = Array.prototype.map.call(document.querySelectorAll("input.win:checked"), function (x) { return x.value; });
      var rwins = Array.prototype.map.call(document.querySelectorAll("input.rwin:checked"), function (x) { return x.value; });
      act(api("POST", "/api/post/" + S.post + "/live", { url: val("live-url"), windows: wins, reply_windows: rwins }).then(function (r) { banner("Marked live. " + r.reminders_added + " reminder(s) set.", false); }));
    } })));
    if (d.reminders.length) ln.push(h("p", { class: "muted", text: "Reminders: " + d.reminders.map(function (r) { return r.window + " (" + r.status + ")"; }).join(", ") }));
    st.appendChild(card("9. Mark as live", "build", ln));

    // 10 optional auto-post (only when you switched it on in docs/settings.json)
    if (S.meta.auto_post) {
      var an2 = [h("p", { class: "warn", text: "Optional add-on. It creates a Publora draft, or a post scheduled at least 5 minutes ahead. It never posts right now, and it does not send your first or pinned comment." }),
        h("div", { class: "row" }, h("select", { id: "ap-mode" }, h("option", { value: "draft", text: "Create a draft in Publora" }), h("option", { value: "schedule", text: "Schedule it" })),
          h("input", { type: "text", id: "ap-at", placeholder: "When (schedule only), e.g. 2026-11-03T08:00:00+05:30" })),
        h("input", { type: "text", id: "ap-media", placeholder: "Public https link to the image (optional; the service cannot take files)" }),
        h("label", { class: "chk" }, h("input", { type: "checkbox", id: "ap-textonly" }), h("span", { text: "Send the words only; I will add the image by hand." })),
        h("div", { class: "row" }, h("button", { text: "Preview what would be sent", onclick: function () { autopost("preview"); } })),
        h("div", { id: "ap-out" }),
        h("label", { class: "muted", text: "To send for real, type PUBLISH:" }), h("input", { type: "text", id: "ap-confirm" }),
        h("div", { class: "row" }, h("button", { class: "go", text: "Send to Publora", onclick: function () { autopost("send"); } }))];
      st.appendChild(card("10. Optional: send to Publora", "build", an2));
    }
  }

  function autopost(action) {
    var body = { action: action, mode: val("ap-mode"), at: val("ap-at"), media_url: val("ap-media"), text_only: $("ap-textonly").checked, confirm: val("ap-confirm") };
    api("POST", "/api/post/" + S.post + "/autopost", body).then(function (r) {
      var out = $("ap-out"); clear(out);
      if (action === "send") { banner("Done: " + r.record.status + (r.record.remote_id ? " (Publora id " + r.record.remote_id + ")" : "") + ". Post the first comment by hand.", false); return; }
      out.appendChild(h("p", { class: r.ok ? "ok" : "bad", text: r.summary }));
      r.problems.forEach(function (p) { out.appendChild(h("div", { class: "bad", text: "\u2716 " + p })); });
      r.warnings.forEach(function (p) { out.appendChild(h("div", { class: "warn", text: "\u26A0 " + p })); });
    }).catch(function (e) { banner(e.message, true); });
  }

  function loadParts() {
    var parts = [["PACKAGE.md", "Everything in order"], ["post.txt", "Post text"], ["suggested-time.txt", "Suggested time"], ["first-comment.txt", "First comment"], ["pin-comment.txt", "Comment to pin"],
      ["alt-text.txt", "Alt text"], ["visual-prompt.txt", "Visual prompt"]];
    var host = $("parts"); if (!host) return;
    parts.forEach(function (p) {
      fetch(fileUrl("package", p[0]), { credentials: "same-origin" }).then(function (r) { return r.ok ? r.text() : ""; }).then(function (t) { if (t && $("parts") === host) host.appendChild(copyBox(p[1] + "  (" + p[0] + ")", t)); });
    });
    var vis = S.data.built.files.filter(function (f) { return /^visual.*\.(png|pdf|svg)$/.test(f); });
    host.appendChild(h("p", {}, "Visual files to upload: ", vis.map(function (f) { return h("a", { href: fileUrl("package", f), target: "_blank", rel: "noopener", text: f + "  " }); })));
  }

  // ---- chat with the live @ and / menus
  var menuItems = [], menuSel = 0;
  function loadChat() {
    api("GET", "/api/chat/history").then(function (r) { S.history = r.history; drawChat(); });
  }
  function drawChat() {
    var log = $("chatlog"); clear(log);
    if (!S.history.length) log.appendChild(h("div", { class: "hint", text: "Nothing here yet. Try: @governance is this idea safe to post? (type @ to see all 21 agents)" }));
    S.history.forEach(function (m) { log.appendChild(h("div", { class: "msg " + m.role, text: m.text })); });
    if (S.lastReply && S.lastReply.has_entries) {
      var sel = h("select", { id: "apply-agent" });
      S.meta.agents.forEach(function (a) { sel.appendChild(h("option", { value: a.name, text: a.name })); });
      if (S.lastReply.mentions[0]) sel.value = S.lastReply.mentions[0];
      log.appendChild(h("div", { class: "row" }, h("span", { class: "muted", text: "This reply contains proposed memory entries. Save them as:" }), sel, h("button", { class: "small", text: "Save to memory", onclick: function () {
        var last = S.history[S.history.length - 1];
        api("POST", "/api/memory/apply", { text: last.text, agent: sel.value }).then(function (r) { banner(r.message, false); }).catch(function (e) { banner(e.message, true); });
      } })));
    }
    log.scrollTop = log.scrollHeight;
  }
  function currentToken() {
    var ta = $("chatin"), before = ta.value.slice(0, ta.selectionStart);
    var m = /(^|\s)@([a-z-]*)$/.exec(before);
    if (m) return { kind: "@", q: m[2], start: ta.selectionStart - m[2].length - 1 };
    m = /^\/([a-z-]*)$/.exec(before.split("\n").pop());
    if (m && before.lastIndexOf("\n") + 1 === before.length - m[0].length) return { kind: "/", q: m[1], start: before.length - m[0].length };
    return null;
  }
  function updateMenu() {
    var t = currentToken(), menu = $("menu");
    if (!t) { menu.hidden = true; return; }
    var src = t.kind === "@" ? S.meta.agents : S.meta.commands;
    menuItems = src.filter(function (a) { return a.name.indexOf(t.q) === 0 || (t.q.length > 1 && a.name.indexOf(t.q) >= 0); }).slice(0, 60);
    menuSel = 0; clear(menu);
    if (!menuItems.length) { menu.hidden = true; return; }
    menuItems.forEach(function (a, i) {
      var row = h("div", { class: i === 0 ? "sel" : "" }, h("b", { text: t.kind + a.name }), "  ", a.description || "");
      row.addEventListener("mousedown", function (ev) { ev.preventDefault(); pick(i); });
      menu.appendChild(row);
    });
    menu.hidden = false;
  }
  function pick(i) {
    var t = currentToken(), ta = $("chatin"); if (!t || !menuItems[i]) return;
    var after = ta.value.slice(ta.selectionStart);
    var ins = t.kind + menuItems[i].name + " ";
    ta.value = ta.value.slice(0, t.start) + ins + after;
    ta.selectionStart = ta.selectionEnd = t.start + ins.length;
    $("menu").hidden = true; ta.focus();
  }
  $("chatin").addEventListener("input", updateMenu);
  $("chatin").addEventListener("keydown", function (e) {
    var menu = $("menu");
    if (!menu.hidden) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault(); menuSel = (menuSel + (e.key === "ArrowDown" ? 1 : -1) + menuItems.length) % menuItems.length;
        Array.prototype.forEach.call(menu.children, function (c, i) { c.className = i === menuSel ? "sel" : ""; });
        menu.children[menuSel].scrollIntoView({ block: "nearest" }); return;
      }
      if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); pick(menuSel); return; }
      if (e.key === "Escape") { menu.hidden = true; return; }
    }
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); sendChat(); }
  });
  $("chatin").addEventListener("blur", function () { setTimeout(function () { $("menu").hidden = true; }, 150); });
  function sendChat() {
    var ta = $("chatin"), msg = ta.value.trim(); if (!msg) return;
    S.history.push({ role: "owner", text: msg }); drawChat(); ta.value = "";
    runJob("/api/chat", { message: msg }, "Asking your agents").then(function (r) { S.lastReply = r; return api("GET", "/api/chat/history"); })
      .then(function (r) { S.history = r.history; drawChat(); }).catch(function () { loadChat(); });
  }
  $("chatsend").addEventListener("click", sendChat);
  $("chatnew").addEventListener("click", function () { api("POST", "/api/chat/new", {}).then(function () { S.history = []; S.lastReply = null; drawChat(); }); });

  // ---- runs, metrics, help
  function loadRuns() {
    var t = $("tab-runs"); clear(t);
    api("GET", "/api/runs").then(function (r) {
      t.appendChild(h("div", { class: "card" }, h("h2", { text: "Results checks waiting for you" }),
        r.due.length ? r.due.map(function (i) {
          var isReply = i.kind === "reply";
          return h("div", { class: "row" }, h("span", { text: i.post_id + " \u2014 " + (isReply ? "answer the comments" : i.window + " results check") + " (was due " + i.due_at + ")" }),
            h("button", { class: "small", text: isReply ? "I answered them (mark done)" : "I entered the numbers (mark done)", onclick: function () { api("POST", "/api/reminders/done", { post_id: i.post_id, window: i.window, kind: i.kind || "results" }).then(loadRuns); } }));
        }) : h("div", { class: "muted", text: "None. When a post is live, reminders appear here (and as pop-ups if you turned notifications on)." }),
        h("p", { class: "muted", text: "To enter the numbers, ask in Chat: /metrics, or put your LinkedIn analytics CSV in the inbox folder and use the Metrics tab." })));
      t.appendChild(h("div", { class: "card" }, h("h2", { text: "Scheduled preparation runs" }),
        r.runs.length ? r.runs.map(function (x) { return h("details", {}, h("summary", { class: x.failed ? "bad" : "", text: x.file + (x.failed ? "  (FAILED)" : "") }), h("pre", { class: "plain", text: x.preview })); })
          : h("div", { class: "muted", text: "No scheduled runs yet." })));
      t.appendChild(h("div", { class: "card" }, h("h2", { text: "Scheduler log (last lines)" }), h("pre", { class: "plain", text: r.log_tail.join("\n") || "(empty)" })));
    }).catch(function (e) { banner(e.message, true); });
  }
  function loadMetrics() {
    var t = $("tab-metrics"); clear(t);
    api("GET", "/api/metrics").then(function (r) {
      var sel = h("select", { id: "csv" }); r.csv_files.forEach(function (f) { sel.appendChild(h("option", { value: f, text: f })); });
      t.appendChild(h("div", { class: "card" }, h("h2", { text: "Build your dashboard" }),
        h("p", { class: "muted", text: "Export your analytics from LinkedIn as CSV and save it in this workspace's inbox folder. Only the numbers in your file are used; nothing is estimated." }),
        r.csv_files.length ? h("div", { class: "row" }, sel, h("button", { class: "primary", text: "Build dashboard", onclick: function () {
          api("POST", "/api/metrics/run", { file: sel.value }).then(function () { loadMetrics(); }).catch(function (e) { banner(e.message, true); });
        } })) : h("div", { class: "warn", text: "No CSV file found in the inbox folder yet." })));
      if (r.dashboard) t.appendChild(h("div", { class: "card" }, h("h2", { text: r.dashboard_name }), h("pre", { class: "plain", text: r.dashboard })));
    }).catch(function (e) { banner(e.message, true); });
  }
  function renderHelp() {
    var t = $("tab-help"); clear(t);
    var lines = ["Pipeline: follow the cards from top to bottom. The AI only writes text; this program renders the visual, runs the checks and records your decisions when you click.",
      "The four decisions: 1 the idea, 2 the visual, 3 the post and rendered visual, 4 the package. If you change anything after approving, the matching decision turns red and must be approved again.",
      "Nothing is ever posted for you. The last step builds a folder you copy from; you post it yourself, then click Mark as live to start reminders.",
      "Chat: type @ for the agent menu or / for commands. Chat is for questions and single jobs; it cannot change your files.",
      "No Chrome or Edge? You still get SVG visuals. Install Chrome or Edge to also get PNG and PDF files.",
      "Your AI tool: this app runs the Claude Code or Codex already installed on this computer (chosen in your setup). Use 'Test my AI tool' at the top if something does not respond.",
      "Everything stays on this computer. Stop the app with Ctrl+C in the terminal window."];
    t.appendChild(h("div", { class: "card" }, h("h2", { text: "How this works" }), lines.map(function (l) { return h("p", { text: l }); })));
  }

  $("btn-testai").addEventListener("click", function () {
    runJob("/api/test-ai", {}, "Testing your AI tool").then(function (r) { banner("Your AI tool answered: " + r, false); }).catch(function () {});
  });

  // ---- start
  api("GET", "/api/meta").then(function (m) {
    S.meta = m;
    $("badge-tool").textContent = "AI: " + m.tool;
    $("badge-demo").hidden = !m.demo;
    if (!m.setup_completed && !m.demo) banner("Setup has not been run yet. In a terminal run: python3 scripts/setup_wizard.py (your language, tool and notifications). You can still look around.", false);
    if (!m.browser) banner((document.getElementById("banner").hidden ? "" : document.getElementById("banner").textContent + " ") + "No Chrome or Edge found: visuals will be SVG only. Install Chrome or Edge for PNG and PDF files.", false);
    return loadPosts();
  }).catch(function (e) { banner(e.message, true); });
})();
