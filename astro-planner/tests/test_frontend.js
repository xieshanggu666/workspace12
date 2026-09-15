/* jsdom 冒烟测试: 加载页面 + 真实后端, 验证初始化渲染与手工拖拽重排 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("/tmp/node_modules/jsdom");

const HTML = fs.readFileSync(path.join(__dirname, "../webapp/static/index.html"), "utf8");
const JS = fs.readFileSync(path.join(__dirname, "../webapp/static/app.js"), "utf8");

function makeCtx() {
  return new Proxy({}, { get: (t, p) => {
    if (p === "canvas") return { clientWidth: 900 };
    if (p === "measureText") return () => ({ width: 10 });
    return (...a) => undefined;
  }, set: () => true });
}

const dom = new JSDOM(HTML, {
  url: "http://127.0.0.1:8000/",
  runScripts: "outside-only",
  pretendToBeVisual: true,
});
const { window } = dom;
window.HTMLCanvasElement.prototype.getContext = function () { return makeCtx(); };
Object.defineProperty(window.HTMLCanvasElement.prototype, "clientWidth",
  { value: 900, configurable: true });
window.HTMLCanvasElement.prototype.getAttribute = function () { return 400; };

window.fetch = async (url, opts) => {
  const u = url.replace("http://127.0.0.1:8000", "");
  if (u === "/api/sites") {
    const payload = JSON.stringify({
      sites: ["兴隆观测站", "冷湖观测基地"],
      catalog: JSON.parse(require("child_process")
        .execSync("curl -s http://127.0.0.1:8000/api/sites")).catalog,
    });
    return { ok: true, json: async () => JSON.parse(payload) };
  }
  if (u === "/api/plan") {
    const out = require("child_process")
      .execSync(`curl -s -X POST http://127.0.0.1:8000/api/plan -H 'Content-Type: application/json' -d ${JSON.stringify(opts.body)}`);
    return { ok: true, json: async () => JSON.parse(out) };
  }
  throw new Error("unexpected " + u);
};

window.eval(JS);

setTimeout(async () => {
  const doc = window.document;
  const assert = (c, m) => { if (!c) { console.error("FAIL:", m); process.exit(1); } };

  await new Promise(r => setTimeout(r, 800));
  const g = { get DATA(){return window.__planner.getData()} };
  assert(window.__planner.getData(), "DATA 应已填充");
  assert(doc.querySelectorAll("#planTable tbody tr").length > 5, "计划表应有多行");
  assert(doc.querySelectorAll("#targetTable tbody tr").length === 16, "目标表 16 行");
  assert(doc.getElementById("nightinfo").textContent.includes("天文暗夜"), "夜间信息已渲染");
  assert(doc.getElementById("planMeta").textContent.includes("利用率"), "计划汇总已渲染");
  const nRowsBefore = doc.querySelectorAll("#planTable tbody tr").length;

  // 模拟把第二个 griprow 拖到第一个之前
  const grips = [...doc.querySelectorAll(".griprow")];
  assert(grips.length >= 3, "至少 3 个可拖拽目标块");
  const dragged = grips[2].dataset.name, target = grips[0].dataset.name;
  const beforeOrder = [...window.__planner.getData().plan.order];
  const dt = { effectAllowed: "" };
  const drag = (type, target) => {
    const ev = new window.Event(type, { bubbles: true, cancelable: true });
    ev.dataTransfer = dt;
    if (type === "dragover" || type === "drop") { ev.clientY = 10; }
    target.dispatchEvent(ev);
  };
  drag("dragstart", grips[2]);
  grips[0].getBoundingClientRect = () => ({ top: 0, height: 40 });
  drag("dragover", grips[0]);
  drag("drop", grips[0]);
  drag("dragend", grips[2]);

  await new Promise(r => setTimeout(r, 1200));
  const afterOrder = [...window.__planner.getData().plan.order];
  assert(afterOrder.join() !== beforeOrder.join(), "拖拽后顺序应改变");
  const di = afterOrder.indexOf(dragged), ti = afterOrder.indexOf(target);
  assert(di < ti, `${dragged} 应排到 ${target} 之前 (${di} vs ${ti})`);
  assert(doc.querySelectorAll("#planTable tbody tr").length > 0, "拖拽后仍有计划行");

  // 恢复自动排序
  doc.getElementById("autoOrder").click();
  await new Promise(r => setTimeout(r, 1000));
  assert(window.__planner.getData().plan.order.join() === window.__planner.getData().plan.auto_order.join(), "自动顺序已恢复");

  console.log("PASS 前端冒烟: 初始化/渲染/拖拽重排/自动排序 全部通过");
  console.log(`     计划行 ${nRowsBefore}, 拖拽: ${dragged} → 队首方向`);
  process.exit(0);
}, 300);
