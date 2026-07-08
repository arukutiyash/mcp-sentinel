import sys, os, asyncio, json
sys.path.insert(0, os.path.join(os.getcwd(), "..", "backend"))
sys.path.insert(0, os.getcwd())
import server

print("=== Registered tools ===")
tools = asyncio.run(server.mcp.list_tools())
for t in tools:
    print("-", t.name)

print("\n=== list_purchase_orders() ===")
print(json.dumps(server.list_purchase_orders(), indent=2))

print("\n=== list_flagged_anomalies() ===")
print(json.dumps(server.list_flagged_anomalies(), indent=2))

print("\n=== get_vendor_risk_score('Harbor') ===")
print(json.dumps(server.get_vendor_risk_score("Harbor"), indent=2))