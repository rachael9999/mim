# validate_p3_spreading.py
from actor_runtime import ActorRegistry

reg = ActorRegistry()

# Spawn actors
food     = reg.spawn("category:food")
carbon   = reg.spawn("category:high-carbon")
beef     = reg.spawn("action:eat-beef")
commute  = reg.spawn("action:commute-car")
transit  = reg.spawn("action:commute-subway")

print("\n--- Linking Distributed Edges ---")
# Each actor only declares its own outbound edges
food.send({"type": "link", "to_id": "action:eat-beef", "edge_type": "Contains", "label": "food includes eating beef", "strength": 0.9})
food.send({"type": "link", "to_id": "action:commute-subway", "edge_type": "Unrelated", "label": "food unrelated to subway", "strength": 0.1})

beef.send({"type": "link", "to_id": "category:high-carbon", "edge_type": "Causes", "label": "eating beef produces high carbon emissions", "strength": 0.95})

commute.send({"type": "link", "to_id": "category:high-carbon", "edge_type": "Causes", "label": "driving a car produces carbon emissions", "strength": 0.88})

transit.send({"type": "link", "to_id": "category:high-carbon", "edge_type": "Reduces", "label": "subway reduces carbon compared to driving", "strength": 0.75})

print("\n--- Spreading Activation Query ---")
# Bypass bootstrap to test deep spreading with mock vectors
results = reg.query(
    entry_actor_id="category:food",
    query_text="carbon footprint from food choices",
    max_hops=3,
    threshold=-1.0,
    max_activations_per_hop=3
)

print(f"\nTop results ({len(results)} found):")
for r in results[:5]:
    print(f"  [{r['score']:+.4f}] (hop {r['hop']}) {r['from_id']} --[{r['edge_type']}]--> {r['to_id']}")
    print(f"           \"{r['label']}\"")
