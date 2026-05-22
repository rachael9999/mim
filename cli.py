import sys
import os
import json
import time
from runtime.core import mems, index, cert_index, scope_graph, store, index_store, embed_provider, runtime, restore_all, save_certs, SNAPSHOT_DIR
from runtime.actor import MemoryActor
from runtime.visibility import VisibilityResolver
from runtime.extractor import DialogueMessage, MockExtractor

def remember(user, content, type_="project", tag="mim"):
    # 支持指定 ID (用于 demo 和确定性链接)
    if ":" in tag:
        tag_parts = tag.split(":")
        tag = tag_parts[0]
        mem_id = tag_parts[1]
    else:
        mem_id = f"mem_{int(time.time()*1000)}"

    mem = MemoryActor(id=mem_id, owner_id=user, content="", memory_type=type_, tags=[])
    mems[mem_id] = mem
    runtime.dispatch(mem, "update_content", {"content": content})
    runtime.dispatch(mem, "add_tag", {"tag": tag})
    index_store.save(index)
    print(f"[CREATE] {mem_id}: {content}")

def recall(user, tag=None):
    vis = VisibilityResolver(cert_index, scope_graph)
    ids = index.query(owner=user, tag=tag)
    found = False
    for mid in ids:
        mem = mems.get(mid)
        if mem and vis.object_visible(mem):
            print(f"[{mem.id}] ({mem.memory_type.value}) {mem.content.value} (clock:{mem._meta.get('clock')})")
            found = True
    if not found:
        print("No memories found.")

def search(user, query_text):
    print(f"[SEARCH] Searching for: '{query_text}' (User: {user})")
    results = index.hybrid_query(owner=user, query_text=query_text, provider=embed_provider)
    found = False
    for mid, score in results:
        mem = mems.get(mid)
        if mem:
            print(f"[{score:.4f}] [{mem.id}] ({mem.memory_type.value}) {mem.content.value}")
            found = True
    if not found:
        print("No matches found.")

def forget(mem_id):
    mem = mems.get(mem_id)
    if not mem:
        print(f"Memory {mem_id} not found.")
        return
    from runtime.core import NODE_ID
    cert = {"scope": mem_id, "delete_clock": {NODE_ID: 1}, "policy": "delete_wins"}
    runtime.dispatch(mem, "delete", {"certificate": cert})
    cert_index.add(cert)
    save_certs()
    print(f"[FORGET] {mem_id}")

def sync(source_node_dir):
    print(f"[SYNC] Syncing from {source_node_dir}...")
    remote_cert_file = os.path.join(source_node_dir, "certs.json")
    if os.path.exists(remote_cert_file):
        with open(remote_cert_file, "r", encoding="utf-8") as f:
            remote_certs = json.load(f)
            for scope, cert in remote_certs.items():
                cert_index.add(cert)
        save_certs()
    if os.path.exists(source_node_dir):
        for fn in os.listdir(source_node_dir):
            if fn.endswith(".json") and not (fn.startswith("index") or fn == "certs.json"):
                mid = fn[:-5]
                remote_path = os.path.join(source_node_dir, fn)
                with open(remote_path, "r", encoding="utf-8") as f:
                    remote_data = json.load(f)
                if mid in mems:
                    mems[mid].merge_state(remote_data, cert_index)
                else:
                    mems[mid] = MemoryActor(id=remote_data["id"], owner_id=remote_data["owner_id"], content="", memory_type=remote_data["memory_type"]["value"], tags=[])
                    mems[mid].merge_state(remote_data, cert_index)
                store.save(mems[mid])
                index.add_memory(mems[mid])
    index_store.save(index)
    print(f"[SYNC] Sync completed.")

def ingest(user, text):
    from runtime.core import llm_extractor
    if os.path.exists(text):
        with open(text, "r", encoding="utf-8") as f:
            data = json.load(f)
            messages = [DialogueMessage(**m) for m in data]
    else:
        messages = [DialogueMessage(role="user", content=text)]

    # 使用增强的 LLM 提取器
    extracted = runtime.ingest_dialogue(user, messages, llm_extractor)
    for mem in extracted:
        mems[mem.id] = mem
    index_store.save(index)
    print(f"[INGEST] Completed ingestion for {user}. Extracted {len(extracted)} memories via LLM.")

def link(from_id, to_id, rel_type, weight=1.0):
    if from_id not in mems:
        print(f"Error: {from_id} not found.")
        return
    actor = mems[from_id]
    runtime.dispatch(actor, "add_link", {"to_id": to_id, "type": rel_type, "weight": float(weight)})
    index_store.save(index)
    print(f"[LINK] {from_id} --({rel_type})--> {to_id}")

def graph_query(user, query_text):
    results = runtime.graph_query(user, query_text)
    print(f"\n[GRAPH RESULTS] Found {len(results)} associated nodes:")
    for res in results:
        print(f"  [{res['score']:.4f}] {res['id']}: {res['content']}")
        print(f"    Reason: {res['explanation']}")

def ingest_folder(user, path):
    from runtime.extractor import FolderCrawler
    crawler = FolderCrawler(runtime)
    mems_created = crawler.crawl(user, path)
    index_store.save(index)
    print(f"[CRAWL] Ingested folder {path}. Created {len(mems_created)} nodes.")

def maintain():
    runtime.maintain()
    save_certs()
    index_store.save(index)

def visualize(user_id, output_format="mermaid"):
    print(f"[VISUALIZE] Exporting graph for user {user_id} in {output_format} format...")
    vis = VisibilityResolver(cert_index, scope_graph)

    # 获取属于该用户的可见内存
    user_mems = []
    for mid, actor in mems.items():
        if actor.owner_id == user_id and vis.object_visible(actor):
            user_mems.append(actor)

    if output_format == "mermaid":
        print("\n```mermaid")
        print("graph TD")
        for actor in user_mems:
            # 节点定义
            content_snippet = actor.content.value[:30].replace('"', "'").replace("\n", " ")
            label = f"{actor.id}[{actor.memory_type.value}: {content_snippet}...]"
            print(f"    {label}")

            # 边定义
            for (to_id, rel_type, weight) in actor.links.elements():
                # 只有当目标节点也可见时才显示边
                to_actor = mems.get(to_id)
                if to_actor and vis.object_visible(to_actor):
                    print(f"    {actor.id} -- \"{rel_type} (w:{weight})\" --> {to_id}")
        print("```\n")
    elif output_format == "html":
        nodes = []
        edges = []
        for actor in user_mems:
            content_snippet = actor.content.value[:50].replace('"', "'").replace("\n", " ")
            nodes.append({
                "data": {
                    "id": actor.id,
                    "label": f"{actor.id}\n({actor.memory_type.value})",
                    "content": content_snippet,
                    "type": actor.memory_type.value
                }
            })
            for (to_id, rel_type, weight) in actor.links.elements():
                to_actor = mems.get(to_id)
                if to_actor and vis.object_visible(to_actor):
                    edges.append({
                        "data": {
                            "source": actor.id,
                            "target": to_id,
                            "label": rel_type,
                            "weight": weight
                        }
                    })

        html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <title>MIM Knowledge Graph</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.23.0/cytoscape.min.js"></script>
    <style>
        #cy {{ width: 100%; height: 90vh; display: block; background-color: #f9f9f9; }}
        body {{ font-family: sans-serif; margin: 0; }}
        .header {{ padding: 10px; background: #333; color: white; text-align: center; }}
    </style>
</head>
<body>
    <div class="header">MIM Knowledge Graph - User: {user_id}</div>
    <div id="cy"></div>
    <script>
        var cy = cytoscape({{
            container: document.getElementById('cy'),
            elements: {{
                nodes: {json.dumps(nodes)},
                edges: {json.dumps(edges)}
            }},
            style: [
                {{
                    selector: 'node',
                    style: {{
                        'background-color': '#666',
                        'label': 'data(label)',
                        'text-wrap': 'wrap',
                        'font-size': '10px',
                        'color': '#333'
                    }}
                }},
                {{
                    selector: 'node[type="directory"]',
                    style: {{ 'background-color': '#f1c40f', 'shape': 'rectangle' }}
                }},
                {{
                    selector: 'node[type="file"]',
                    style: {{ 'background-color': '#3498db', 'shape': 'round-rectangle' }}
                }},
                {{
                    selector: 'node[type="entity"]',
                    style: {{ 'background-color': '#e74c3c', 'shape': 'ellipse' }}
                }},
                {{
                    selector: 'edge',
                    style: {{
                        'width': 2,
                        'line-color': '#ccc',
                        'target-arrow-color': '#ccc',
                        'target-arrow-shape': 'triangle',
                        'curve-style': 'bezier',
                        'label': 'data(label)',
                        'font-size': '8px'
                    }}
                }}
            ],
            layout: {{ name: 'cose', animate: true }}
        }});
        cy.on('tap', 'node', function(evt){{
            alert(evt.target.data('content'));
        }});
    </script>
</body>
</html>
"""
        filename = f"mim_graph_{user_id}.html"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html_template)
        print(f"[VISUALIZE] HTML Graph saved to: {os.path.abspath(filename)}")
    else:
        print(f"Format {output_format} not supported yet.")

def remote_pull(remote_url, user_id):
    import requests
    from runtime.clocks import VersionVector
    from runtime.core import NODE_ID

    print(f"[PULL] Pulling updates from {remote_url} for user {user_id}...")

    # 1. 构建本地对该用户所有记忆的综合版本向量 (或简单全量对比)
    # 生产环境应存储每个 remote_node 的 last_seen_vector
    local_vector = {}
    for mid, actor in mems.items():
        if actor.owner_id == user_id:
            vv = actor._meta.get("version_vector", {})
            for nid, count in vv.items():
                local_vector[nid] = max(local_vector.get(nid, 0), count)

    try:
        response = requests.post(
            f"{remote_url}/v1/pull",
            json={"user_id": user_id, "vector": local_vector},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            updates = data.get("updates", [])
            certs = data.get("certs", {})

            # 2. 合并证书
            cert_index.from_dict(certs)
            save_certs()

            # 3. 合并 Actor 状态
            for remote_data in updates:
                mid = remote_data["id"]
                if mid in mems:
                    mems[mid].merge_state(remote_data, cert_index)
                else:
                    mems[mid] = MemoryActor(id=mid, owner_id=remote_data["owner_id"], content="", memory_type=remote_data["memory_type"]["value"], tags=[])
                    mems[mid].merge_state(remote_data, cert_index)

                store.save(mems[mid])
                index.add_memory(mems[mid])

            index_store.save(index)
            print(f"[PULL] Success. Merged {len(updates)} updates and {len(certs)} certificates.")
        else:
            print(f"[PULL] Failed: {response.text}")
    except Exception as e:
        print(f"[PULL] Error: {e}")

def add_peer_node(url):
    from runtime.core import add_peer
    peers = add_peer(url)
    print(f"[PEER] Added peer: {url}. Total peers: {len(peers)}")

def discover(user_id):
    insights = runtime.discover_insights(user_id)
    if not insights:
        print("No new insights discovered yet. Try adding more connections.")
        return
    print(f"\n[NEW INSIGHTS DISCOVERED]")
    for i, insight in enumerate(insights):
        print(f"{i+1}. {insight}")

if __name__ == "__main__":
    restore_all()
    if len(sys.argv) < 2:
        print("Usage: python cli.py <cmd> [args...]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "remember": remember(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv)>4 else "project", sys.argv[5] if len(sys.argv)>5 else "mim")
    elif cmd == "recall": recall(sys.argv[2], sys.argv[3] if len(sys.argv)>3 else None)
    elif cmd == "search": search(sys.argv[2], sys.argv[3])
    elif cmd == "forget": forget(sys.argv[2])
    elif cmd == "sync": sync(sys.argv[2])
    elif cmd == "pull": remote_pull(sys.argv[2], sys.argv[3])
    elif cmd == "peer": add_peer_node(sys.argv[2])
    elif cmd == "ingest": ingest(sys.argv[2], sys.argv[3])
    elif cmd == "link": link(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv)>5 else 1.0)
    elif cmd == "graph_query": graph_query(sys.argv[2], sys.argv[3])
    elif cmd == "ingest_folder": ingest_folder(sys.argv[2], sys.argv[3])
    elif cmd == "discover": discover(sys.argv[2])
    elif cmd == "maintain": maintain()
    elif cmd == "visualize": visualize(sys.argv[2], sys.argv[3] if len(sys.argv)>3 else "mermaid")
    else: print("Commands: remember, recall, search, forget, sync, pull, ingest, maintain, link, graph_query, ingest_folder, visualize")
