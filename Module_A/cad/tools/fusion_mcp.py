#!/usr/bin/env python3
"""Minimal MCP client for the local Fusion MCP server (http://127.0.0.1:27182/mcp).
   fusion.py list                      -> tool names + schemas
   fusion.py call TOOL '{"arg":...}'   -> result text
   fusion.py call TOOL @file.json      -> args from file
"""
import json, os, sys, urllib.request
URL = "http://127.0.0.1:27182/mcp"
SID_FILE = os.path.join(os.path.expanduser("~"), ".brics_fusion_sid")
HDR = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

def post(payload, sid=None, timeout=600):
    h = dict(HDR)
    if sid:
        h["MCP-Session-Id"] = sid
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
        sid2 = r.headers.get("MCP-Session-Id")
    if body.startswith("event:") or "\ndata:" in body or body.startswith("data:"):
        datas = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")]
        body = datas[-1] if datas else "{}"
    return (json.loads(body) if body.strip() else {}), sid2

def session():
    if os.path.exists(SID_FILE):
        sid = open(SID_FILE).read().strip()
        try:
            r, _ = post({"jsonrpc": "2.0", "id": 0, "method": "tools/list", "params": {}}, sid, 30)
            if "result" in r:
                return sid
        except Exception:
            pass
    r, sid = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18",
                   "capabilities": {}, "clientInfo": {"name": "brics-cad-script", "version": "1"}}})
    try:
        post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid, 30)
    except Exception:
        pass
    open(SID_FILE, "w").write(sid)
    return sid

def main():
    sid = session()
    if sys.argv[1] == "list":
        r, _ = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, sid)
        for t in r["result"]["tools"]:
            print("==", t["name"]); print(t.get("description", "")); print("schema:", json.dumps(t.get("inputSchema", {}))); print()
        return
    if sys.argv[1] == "resources":
        r, _ = post({"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}}, sid)
        print(json.dumps(r, indent=1)[:4000]); return
    if sys.argv[1] == "read":
        r, _ = post({"jsonrpc": "2.0", "id": 4, "method": "resources/read", "params": {"uri": sys.argv[2]}}, sid)
        for c in r.get("result", {}).get("contents", []):
            print(c.get("text", "")[:20000])
        if "error" in r: print(r["error"])
        return
    name = sys.argv[2]
    a = sys.argv[3] if len(sys.argv) > 3 else "{}"
    args = json.load(open(a[1:])) if a.startswith("@") else json.loads(a)
    r, _ = post({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": name, "arguments": args}}, sid)
    if "error" in r:
        print("ERROR:", json.dumps(r["error"])); sys.exit(1)
    res = r["result"]
    import base64
    for c in res.get("content", []):
        if c.get("type") == "text":
            t = c["text"]
            if os.environ.get("FUSION_IMG") and '"base64Data"' in t:
                d = json.loads(t)
                open(os.environ["FUSION_IMG"], "wb").write(base64.b64decode(d["base64Data"]))
                print("saved image", os.environ["FUSION_IMG"])
            else:
                print(t)
        elif c.get("type") == "image" and os.environ.get("FUSION_IMG"):
            open(os.environ["FUSION_IMG"], "wb").write(base64.b64decode(c["data"]))
            print("saved image", os.environ["FUSION_IMG"])
        else:
            print("[%s content]" % c.get("type"))
    if res.get("isError"):
        sys.exit(2)

if __name__ == "__main__":
    main()
