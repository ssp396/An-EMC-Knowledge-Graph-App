import streamlit as st
from neo4j import GraphDatabase
from pyvis.network import Network
import streamlit.components.v1 as components
import os

# ================= 1. 页面配置 =================
st.set_page_config(
    page_title="EMC 智能知识图谱系统",
    layout="wide",
    initial_sidebar_state="expanded"
)

if "message" not in st.session_state:
    st.session_state.message = None
if "msg_type" not in st.session_state:
    st.session_state.msg_type = None

# ================= 2. Neo4j & 数据查询 =================
@st.cache_resource
def init_driver(uri, username, password):
    try:
        driver = GraphDatabase.driver(uri, auth=(username, password))
        driver.verify_connectivity()
        return driver
    except Exception:
        return None

def get_data(driver, query_str, limit=50):
    cql = """
    MATCH (n) 
    WHERE n.name CONTAINS $name
    OPTIONAL MATCH (n)-[r]-(m)
    RETURN n, r, m LIMIT $limit
    """
    try:
        with driver.session() as session:
            result = session.run(cql, name=query_str, limit=limit)
            return [record for record in result]
    except Exception:
        return []

def get_full_data(driver, limit=300):
    cql = """
    MATCH (n) 
    OPTIONAL MATCH (n)-[r]->(m) 
    RETURN n, r, m LIMIT $limit
    """
    try:
        with driver.session() as session:
            result = session.run(cql, limit=limit)
            return [record for record in result]
    except Exception:
        return []

def get_shortest_path(driver, start_name, end_name):
    cql = """
    MATCH (p1 {name: $start}), (p2 {name: $end}),
    path = shortestPath((p1)-[*]-(p2))
    RETURN path
    """
    try:
        with driver.session() as session:
            result = session.run(cql, start=start_name, end=end_name)
            paths = [record["path"] for record in result]
            data = []
            for p in paths:
                for rel in p.relationships:
                    data.append({"n": rel.start_node, "r": rel, "m": rel.end_node})
            return data
    except Exception:
        return []

# ================= 3. HTML 注入：hover/click 弹窗 + 拖拽/固定 + 全屏按钮 =================
def inject_hover_click_popup(html_str: str) -> str:
    injected = r"""
<style>
  body { margin: 0; }
  #mynetwork { width: 100% !important; height: 100% !important; }

  #fsBtn {
    position: fixed;
    top: 18px;
    right: 18px;
    z-index: 100000;
    cursor: pointer;
    border: none;
    background: #111;
    color: #fff;
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 13px;
    box-shadow: 0 8px 20px rgba(0,0,0,0.18);
  }

  #infoBox {
    position: fixed;
    top: 78px;
    right: 20px;
    width: 420px;
    max-height: 72vh;
    overflow: auto;
    background: rgba(255,255,255,0.98);
    border: 2px solid #222;
    border-radius: 12px;
    box-shadow: 0 10px 28px rgba(0,0,0,0.18);
    padding: 12px 12px 10px 12px;
    z-index: 99999;
    display: none;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans",
                 "PingFang SC", "Microsoft YaHei", sans-serif;
    line-height: 1.35;
  }

  #infoBox .hdr {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:10px;
    margin-bottom: 8px;
    cursor: move;
    user-select: none;
  }

  #infoBox .hdr .titleWrap { display:flex; align-items:center; gap:8px; }
  #infoBox .hdr .title { font-weight: 900; font-size: 15px; }
  #infoBox .hdr .badge {
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 999px;
    background: #f0f0f0;
  }

  #infoBox .hdr .btns { display:flex; gap:6px; align-items:center; }
  #infoBox button {
    cursor:pointer;
    border:none;
    background:#111;
    color:#fff;
    border-radius: 9px;
    padding: 6px 10px;
    font-size: 12px;
  }
  #infoBox button.secondary { background:#4b5563; }

  #infoBox .sec { margin-top: 10px; padding-top: 8px; border-top: 1px dashed #ddd; }
  #infoBox .kv { margin: 6px 0; font-size: 13px; }

  #infoBox pre {
    white-space: pre-wrap;
    word-break: break-word;
    background: #f6f6f6;
    border-radius: 10px;
    padding: 10px;
    display:block;
    font-size: 12px;
  }

  #infoBox .pill {
    display:inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    background: #f0f0f0;
    font-size: 12px;
    margin-left: 6px;
  }

  #infoBox .relItem {
    margin: 8px 0;
    padding: 9px;
    background: #fafafa;
    border: 1px solid #eee;
    border-radius: 12px;
  }
  #infoBox .relType { font-weight: 800; }
  #infoBox .muted { color: #666; font-size: 12px; }
</style>

<button id="fsBtn" onclick="toggleFullscreen()">全屏</button>

<div id="infoBox">
  <div class="hdr" id="infoBoxHeader">
    <div class="titleWrap">
      <div class="title" id="infoTitle">详情</div>
      <span class="badge" id="infoBadge">Hover</span>
    </div>
    <div class="btns">
      <button class="secondary" id="pinBtn" onclick="togglePin()">固定</button>
      <button class="secondary" onclick="copyInfo()">复制</button>
      <button onclick="closeInfo()">关闭</button>
    </div>
  </div>
  <div id="infoContent"></div>
</div>

<script>
  function toggleFullscreen(){
    const target = document.documentElement;
    if (!document.fullscreenElement) {
      target.requestFullscreen().then(()=>{}).catch(()=>{});
    } else {
      document.exitFullscreen().then(()=>{}).catch(()=>{});
    }
  }
  document.addEventListener("fullscreenchange", ()=>{
    const b = document.getElementById("fsBtn");
    if (!b) return;
    b.textContent = document.fullscreenElement ? "退出全屏" : "全屏";
    try { if (typeof network !== "undefined") network.fit({animation:false}); } catch(e){}
  });

  let pinned = false;
  let lastMode = "hover";
  let hideTimer = null;

  let dragging = false;
  let dragOffsetX = 0;
  let dragOffsetY = 0;

  function $(id){ return document.getElementById(id); }

  function escapeHtml(s) {
    if (s === undefined || s === null) return "";
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function setBadge(mode){
    lastMode = mode;
    const b = $("infoBadge");
    if (!b) return;
    b.textContent = pinned ? "Pinned" : (mode === "click" ? "Click" : "Hover");
  }

  function openInfo(html, mode="hover"){
    const box = $("infoBox");
    const cont = $("infoContent");
    if (!box || !cont) return;
    cont.innerHTML = html;
    box.style.display = "block";
    setBadge(mode);
  }

  function closeInfo(){
    if (pinned) return;
    const box = $("infoBox");
    if (box) box.style.display = "none";
  }

  function forceClose(){
    const box = $("infoBox");
    if (box) box.style.display = "none";
  }

  function togglePin(){
    pinned = !pinned;
    const btn = $("pinBtn");
    if (btn) btn.textContent = pinned ? "取消固定" : "固定";
    setBadge(lastMode);
  }

  function copyInfo(){
    const cont = $("infoContent");
    if (!cont) return;
    const text = cont.innerText || "";
    navigator.clipboard.writeText(text).then(()=>{
      const b = $("infoBadge");
      if (!b) return;
      b.textContent = "Copied!";
      setTimeout(()=>{ b.textContent = pinned ? "Pinned" : (lastMode==="click"?"Click":"Hover"); }, 800);
    }).catch(()=>{});
  }

  function fmtNodeBlock(n, headerText) {
    if (!n) return "";
    const name = escapeHtml(n.label || n.name || "");
    const nid  = escapeHtml(n.node_id || n.id || "");
    const nlb  = escapeHtml(n.neo_label || "");
    const et   = escapeHtml(n.entity_type || "");
    const ca   = escapeHtml(n.core_attr || "");

    const hdr = headerText ? ("<div class='kv'><b>" + escapeHtml(headerText) + "</b></div>") : "";
    let html = ""
      + hdr
      + "<div class='kv'><b>名称</b>: " + name + (nlb ? ("<span class='pill'>" + nlb + "</span>") : "") + "</div>"
      + (nid ? ("<div class='kv'><b>ID</b>: " + nid + "</div>") : "")
      + (et ?  ("<div class='kv'><b>实体类型</b>: " + et + "</div>") : "")
      + (ca ?  ("<div class='kv'><b>核心属性</b>:</div><pre>" + ca + "</pre>") : "");
    return html;
  }

  function fmtEdgeBlock(e) {
    if (!e) return "";
    const rt = escapeHtml(e.rel_type || e.label || e.title || "");
    const desc = escapeHtml(e.description || "");
    const html = ""
      + "<div class='kv'><b>关系类型</b>: <span class='relType'>" + rt + "</span></div>"
      + (desc ? ("<div class='kv'><b>关系描述</b>:</div><pre>" + desc + "</pre>") : "<div class='muted'>（该关系未提供 description）</div>");
    return html;
  }

  function listNodeRels(nodeId) {
    const res = [];
    const allEdges = edges.get();
    for (let i=0;i<allEdges.length;i++){
      const e = allEdges[i];
      if (e.from === nodeId || e.to === nodeId) res.push(e);
    }
    if (res.length === 0) return "<div class='muted'>当前视图中该节点暂无关联边（或为孤立节点）。</div>";

    let html = "";
    for (let j=0;j<res.length;j++){
      const e = res[j];
      const otherId = (e.from === nodeId) ? e.to : e.from;
      const other = nodes.get(otherId);
      const otherName = escapeHtml((other && (other.label || other.name)) || otherId);
      const rt = escapeHtml(e.rel_type || e.label || e.title || "");
      const desc = escapeHtml(e.description || "");
      html += "<div class='relItem'>"
           +  "<div><span class='relType'>" + rt + "</span> <span class='muted'>→</span> <b>" + otherName + "</b></div>"
           +  (desc ? ("<div class='muted' style='margin-top:6px;'><b>描述</b>: " + desc + "</div>") : "<div class='muted' style='margin-top:6px;'>（无描述）</div>")
           + "</div>";
    }
    return html;
  }

  function scheduleHide(){
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(()=>{
      if (!pinned) forceClose();
    }, 180);
  }

  function cancelHide(){
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = null;
  }

  function showNode(nodeId, mode="hover"){
    const n = nodes.get(nodeId);
    const html = ""
      + "<div class='kv'><b>点击对象</b>: 节点</div>"
      + "<div class='sec'>" + fmtNodeBlock(n, "节点信息") + "</div>"
      + "<div class='sec'><div class='kv'><b>相关关系（当前视图）</b>:</div>"
      + listNodeRels(nodeId)
      + "</div>";
    openInfo(html, mode);
    try { network.selectNodes([nodeId], true); } catch(e){}
  }

  function showEdge(edgeId, mode="hover"){
    const e = edges.get(edgeId);
    const s = nodes.get(e.from);
    const t = nodes.get(e.to);
    const html = ""
      + "<div class='kv'><b>点击对象</b>: 关系（连线）</div>"
      + "<div class='sec'>" + fmtEdgeBlock(e) + "</div>"
      + "<div class='sec'>" + fmtNodeBlock(s, "起点节点信息") + "</div>"
      + "<div class='sec'>" + fmtNodeBlock(t, "终点节点信息") + "</div>";
    openInfo(html, mode);
    try { network.selectEdges([edgeId]); } catch(e){}
  }

  function clamp(v, min, max){ return Math.max(min, Math.min(max, v)); }

  function enableDragging(){
    const header = $("infoBoxHeader");
    const box = $("infoBox");
    if (!header || !box) return;

    header.addEventListener("mousedown", (ev)=>{
      const tag = (ev.target && ev.target.tagName) ? ev.target.tagName.toLowerCase() : "";
      if (tag === "button") return;

      dragging = true;
      cancelHide();

      const rect = box.getBoundingClientRect();
      box.style.right = "auto";
      box.style.left = rect.left + "px";
      box.style.top  = rect.top + "px";

      dragOffsetX = ev.clientX - rect.left;
      dragOffsetY = ev.clientY - rect.top;
      ev.preventDefault();
    });

    document.addEventListener("mousemove", (ev)=>{
      if (!dragging) return;
      const box = $("infoBox");
      if (!box) return;

      const w = box.offsetWidth;
      const h = box.offsetHeight;
      const maxX = window.innerWidth - w - 8;
      const maxY = window.innerHeight - h - 8;

      const x = clamp(ev.clientX - dragOffsetX, 8, Math.max(8, maxX));
      const y = clamp(ev.clientY - dragOffsetY, 8, Math.max(8, maxY));

      box.style.left = x + "px";
      box.style.top  = y + "px";
    });

    document.addEventListener("mouseup", ()=>{ dragging = false; });

    box.addEventListener("mouseenter", cancelHide);
    box.addEventListener("mouseleave", ()=>{ if (!pinned) scheduleHide(); });
  }

  if (typeof network !== "undefined" && typeof nodes !== "undefined" && typeof edges !== "undefined") {
    try {
      network.setOptions({
        interaction: {
          hover: true,
          hoverConnectedEdges: true,
          multiselect: true,
          navigationButtons: true,
          keyboard: { enabled: true }
        }
      });
    } catch(e){}

    enableDragging();

    network.on("hoverNode", function(params){
      if (pinned) return;
      cancelHide();
      showNode(params.node, "hover");
    });
    network.on("blurNode", function(params){
      if (pinned) return;
      scheduleHide();
    });

    network.on("hoverEdge", function(params){
      if (pinned) return;
      cancelHide();
      showEdge(params.edge, "hover");
    });
    network.on("blurEdge", function(params){
      if (pinned) return;
      scheduleHide();
    });

    network.on("click", function(params){
      cancelHide();

      const hasNode = params.nodes && params.nodes.length > 0;
      const hasEdge = params.edges && params.edges.length > 0;

      if (!hasNode && !hasEdge) {
        if (!pinned) forceClose();
        return;
      }

      if (hasNode) {
        showNode(params.nodes[0], "click");
        if (!pinned) togglePin();
        return;
      }

      if (hasEdge) {
        showEdge(params.edges[0], "click");
        if (!pinned) togglePin();
        return;
      }
    });

    document.addEventListener("keydown", function(ev){
      if (ev.key === "Escape") {
        if (!pinned) forceClose();
      }
      if (ev.key === "p" || ev.key === "P") {
        togglePin();
      }
      if (ev.key === "f" || ev.key === "F") {
        toggleFullscreen();
      }
    });
  }
</script>
"""
    if "</body>" in html_str:
        return html_str.replace("</body>", injected + "\n</body>")
    return html_str + injected

def write_graph_html(net: Network, out_path: str):
    net.save_graph(out_path)
    with open(out_path, "r", encoding="utf-8") as f:
        html = f.read()
    html = inject_hover_click_popup(html)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

# ================= 4. 侧边栏 =================
with st.sidebar:
    st.title("系统配置")
    with st.expander("数据库连接", expanded=True):
        uri = st.text_input("URI", "neo4j+s://e1d3d7ac.databases.neo4j.io")
        user = st.text_input("用户名", "neo4j")
        password = st.text_input("密码", "vKH48VG_a8kCpvDj9sCzzKqlSVfBRkUKTM_geelU5Y4", type="password")

    driver = init_driver(uri, user, password)

    if not driver:
        st.error("数据库未连接")
        st.stop()
    else:
        st.success("数据库已连接")

    st.markdown("---")

    # ✅ 修改 2：路径分析 -> 显示节点关联路径
    mode = st.radio("功能模式", ["显示相关节点", "显示节点关联路径"])

    search_query = ""
    path_start = ""
    path_end = ""

    # ✅ 默认开启物理引力，不再提供开关
    use_physics = True

    if mode == "显示相关节点":
        # ✅ 修改 1：显示全量图谱 -> 显示完整知识图谱
        show_all_graph = st.checkbox("显示完整知识图谱", value=True)

        if not show_all_graph:
            search_query = st.text_input("搜索关键词", placeholder="例如: 辐射")

        node_limit = st.number_input(
            "最大节点数",
            min_value=1,
            max_value=1000,
            value=1000,
            step=50
        )

    else:
        c1, c2 = st.columns(2)
        path_start = c1.text_input("起点", "电源")
        path_end = c2.text_input("终点", "干扰")
        node_limit = st.number_input(
            "最大节点数",
            min_value=1,
            max_value=1000,
            value=300,
            step=50
        )

# ================= 5. 主界面 =================
st.title("EMC电磁兼容知识图谱系统")

if st.session_state.message:
    if st.session_state.msg_type == "success":
        st.success(st.session_state.message)
    else:
        st.error(st.session_state.message)
    st.session_state.message = None
    st.session_state.msg_type = None

data = []
if mode == "显示相关节点":
    if show_all_graph:
        data = get_full_data(driver, limit=int(node_limit))
    elif search_query:
        data = get_data(driver, search_query, int(node_limit))
elif mode == "显示节点关联路径" and path_start and path_end:
    data = get_shortest_path(driver, path_start, path_end)

if data:
    net = Network(height="900px", width="100%", bgcolor="#ffffff", font_color="black", notebook=False)

    net.barnes_hut(
        gravity=-2000,
        central_gravity=0.1,
        spring_length=150,
        spring_strength=0.04,
        damping=0.09,
        overlap=0
    )

    color_map = {
        "Theory": "#FF6B6B",
        "Element": "#4ECDC4",
        "TestProblem": "#FFE66D",
        "Solution": "#1A535C",
        "Case": "#FF9F1C",
        "Concept": "#C7C7C7"
    }

    node_ids = set()
    edge_counter = 0

    def node_vis_id(n):
        return n.get("id") if n.get("id") else n.element_id

    def node_label(n):
        return list(n.labels)[0] if n.labels else "Concept"

    for record in data:
        src = record["n"]
        s_vis_id = node_vis_id(src)
        s_name = src.get("name", "N/A")
        s_label = node_label(src)

        if s_vis_id not in node_ids:
            net.add_node(
                s_vis_id,
                label=s_name,
                title=s_name,
                color=color_map.get(s_label, "#97C2FC"),
                size=20,
                font={"size": 14},
                node_id=src.get("id", ""),
                neo_label=s_label,
                entity_type=src.get("entity_type", ""),
                core_attr=src.get("core_attr", "")
            )
            node_ids.add(s_vis_id)

        tgt = record.get("m")
        rel = record.get("r")

        if tgt is not None and rel is not None:
            t_vis_id = node_vis_id(tgt)
            t_name = tgt.get("name", "N/A")
            t_label = node_label(tgt)

            if t_vis_id not in node_ids:
                net.add_node(
                    t_vis_id,
                    label=t_name,
                    title=t_name,
                    color=color_map.get(t_label, "#97C2FC"),
                    size=20,
                    font={"size": 14},
                    node_id=tgt.get("id", ""),
                    neo_label=t_label,
                    entity_type=tgt.get("entity_type", ""),
                    core_attr=tgt.get("core_attr", "")
                )
                node_ids.add(t_vis_id)

            rel_type = rel.type
            try:
                rel_desc = rel.get("description", "")
            except Exception:
                rel_desc = ""

            edge_id = f"e_{edge_counter}"
            edge_counter += 1

            net.add_edge(
                s_vis_id,
                t_vis_id,
                id=edge_id,
                title=rel_type,
                label=rel_type,
                arrows="to",
                rel_type=rel_type,
                description=rel_desc
            )

    net.toggle_physics(use_physics)

    out_dir = "html_files"
    os.makedirs(out_dir, exist_ok=True)
    out_html = os.path.join(out_dir, "graph.html")

    write_graph_html(net, out_html)

    with open(out_html, "r", encoding="utf-8") as f:
        components.html(f.read(), height=980, scrolling=False)
else:
    st.info("暂无数据，请调整搜索条件。")
