// Runs runtime/app/app.js against a live app server with a tiny stand-in DOM and clicks through the pipeline.
// Usage: node tests/ui_smoke.js <base-url-with-port> <token>
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const base = process.argv[2], token = process.argv[3];
const root = path.join(__dirname, "..", "runtime", "app");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const code = fs.readFileSync(path.join(root, "app.js"), "utf8");
let cookie = "";

class El {
  constructor(tag) { this.tagName = (tag || "div").toUpperCase(); this.children = []; this.attrs = {}; this.handlers = {}; this._text = ""; this.value = ""; this.checked = false;
    this.hidden = false; this.className = ""; this.selectionStart = 0; this.scrollTop = 0; this.scrollHeight = 0; this.style = {}; }
  appendChild(c) { this.children.push(c); c.parent = this; if (this.tagName === "SELECT" && c.tagName === "OPTION" && !this.value) this.value = c.value; return c; }
  removeChild(c) { this.children = this.children.filter(x => x !== c); }
  get firstChild() { return this.children[0] || null; }
  setAttribute(k, v) { this.attrs[k] = v; if (k === "id") reg[v] = this; }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(t, f) { (this.handlers[t] = this.handlers[t] || []).push(f); }
  fire(t, ev) { (this.handlers[t] || []).forEach(f => f.call(this, ev || { preventDefault() {}, key: "" })); }
  set textContent(v) { this.children = []; this._text = String(v); }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(""); }
  focus() {} scrollIntoView() {}
  all() { return [this].concat(...this.children.map(c => c.all ? c.all() : [])); }
}
class Txt { constructor(t) { this._t = String(t); } get textContent() { return this._t; } }
const reg = {};
function mk(tag, attrs) { const e = new El(tag); Object.keys(attrs || {}).forEach(k => { if (k === "class") e.className = attrs[k]; else if (k === "hidden") e.hidden = true; else e.setAttribute(k, attrs[k]); }); return e; }
// static elements from index.html
const tabButtons = [], tabSections = [];
(html.match(/<(button|section|div|span|nav|textarea|select|ol|header|aside)\b[^>]*>/g) || []).forEach(tag => {
  const get = n => { const m = new RegExp(n + '="([^"]*)"').exec(tag); return m ? m[1] : null; };
  const t = /^<(\w+)/.exec(tag)[1], id = get("id"), cls = get("class");
  const e = mk(t, {}); if (cls) e.className = cls; if (/\bhidden\b/.test(tag)) e.hidden = true; if (get("data-tab")) e.attrs["data-tab"] = get("data-tab");
  if (id) { e.attrs.id = id; reg[id] = e; }
  if (get("data-tab")) tabButtons.push(e);
  if (cls && /\btab\b/.test(cls) && id) tabSections.push(e);
});
const document = {
  getElementById: id => reg[id] || null, createElement: t => new El(t), createTextNode: t => new Txt(t),
  querySelectorAll: sel => sel === "#tabs button" ? tabButtons : sel === ".tab" ? tabSections : sel === "input.win:checked" ? Object.values(reg).concat(allCreated).filter(e => e.className === "win" && e.checked) : [],
  createRange: () => ({ selectNodeContents() {} }),
};
const allCreated = [];
const origCreate = document.createElement; document.createElement = t => { const e = origCreate(t); allCreated.push(e); return e; };
const errors = [];
const sandbox = {
  document, window: { getSelection: () => ({ removeAllRanges() {}, addRange() {} }) }, navigator: {}, console, setTimeout, setInterval, clearInterval, Promise,
  fetch: (p, o) => { o = o || {}; o.headers = Object.assign({}, o.headers, { Cookie: cookie }); return fetch(base + p, o); },
};
sandbox.window.document = document;
process.on("unhandledRejection", e => { errors.push("unhandled: " + e); });
const sleep = ms => new Promise(r => setTimeout(r, ms));
function texts(el) { return el.all().filter(e => e.tagName === "BUTTON").map(b => b.textContent); }
function findBtn(label) { return reg.stage.all().find(e => e.tagName === "BUTTON" && e.textContent.indexOf(label) === 0); }
async function click(label, wait) {
  const b = findBtn(label);
  if (!b) throw new Error("button not found: " + label + " | have: " + texts(reg.stage).join(" | "));
  b.fire("click"); await sleep(wait || 700);
  for (let i = 0; i < 60 && !reg.progress.hidden; i++) await sleep(250);
  await sleep(400);
}
(async () => {
  const r0 = await fetch(base + "/?t=" + token, { redirect: "manual" });
  cookie = r0.headers.get("set-cookie").split(";")[0];
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  await sleep(1200);
  const out = {};
  if (!reg["badge-demo"] || reg["badge-demo"].hidden) throw new Error("demo badge should be visible");
  reg["btn-newpost"].fire("click"); await sleep(900);
  if (reg["post-select"].children.length < 1) throw new Error("no post in the selector");
  const labels = ["Get 3 ideas", "Choose this idea (Decision 1)", "Write the post", "Get 3 previews", "Pick this one (Decision 2)", "Render the final visual", "Run quality checks",
    "Approve post and visual (Decision 3)", "Approve the package (Decision 4)", "Build the ready-to-paste package"];
  for (const l of labels) { await click(l); if (!reg.banner.hidden && /bad/.test(reg.banner.className)) throw new Error("error banner after '" + l + "': " + reg.banner.textContent); }
  const steps = reg.steps.children.map(li => li.className);
  out.stepsDone = steps.filter(c => /done/.test(c)).length; out.stepsTotal = steps.length;
  out.copyBoxes = reg.stage.all().filter(e => /copybox/.test(e.className)).length;
  out.pills = reg.stage.all().filter(e => /pill ok/.test(e.className)).length;
  // chat menu
  const ta = reg.chatin; ta.value = "@gov"; ta.selectionStart = 4; ta.fire("input");
  out.agentMenu = reg.menu.hidden ? 0 : reg.menu.children.length;
  ta.fire("keydown", { key: "Enter", preventDefault() {} }); out.afterPick = ta.value;
  ta.value = "/ne"; ta.selectionStart = 3; ta.fire("input"); out.commandMenu = reg.menu.hidden ? 0 : reg.menu.children.length;
  ta.value = "@"; ta.selectionStart = 1; ta.fire("input"); out.allAgents = reg.menu.children.length;
  ta.value = "email me@example.com"; ta.selectionStart = ta.value.length; ta.fire("input"); out.emailMenuHidden = reg.menu.hidden;
  // other tabs render without errors
  for (const t of ["runs", "metrics", "help", "chat", "pipeline"]) { tabButtons.find(b => b.attrs["data-tab"] === t).fire("click"); await sleep(400); }
  out.errors = errors;
  console.log(JSON.stringify(out));
})().catch(e => { console.log(JSON.stringify({ fatal: String(e && e.stack || e) })); process.exit(1); });
