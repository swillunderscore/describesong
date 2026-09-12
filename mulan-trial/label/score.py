"""Score each system's CLAIMS against his labels: for every event, of the clips a
system put forward (captions said it / CLAP top-14 / referee top-10), how many
did he confirm? Random clips give the base rate."""
import json, os
R=os.path.dirname(os.path.abspath(__file__)); items=json.load(open(R+"/set.json")); labels=json.load(open(R+"/labels.json")) if os.path.exists(R+"/labels.json") else {}
print(f"{len(labels)} of {len(items)} labelled\n")
for event in ["hand claps","whistling","female lead vocals"]:
    print(f"== {event}")
    for src in ["captions","clap","referee","random"]:
        rows=[it for it in items if it["event"]==event and src in it["sources"] and str(it["id"]) in labels]
        if not rows: print(f"   {src:9s} (nothing labelled yet)"); continue
        yes=sum(1 for it in rows if labels[str(it["id"])]=="yes"); no=sum(1 for it in rows if labels[str(it["id"])]=="no"); un=len(rows)-yes-no
        print(f"   {src:9s} claimed {len(rows):2d}: {yes:2d} yes, {no:2d} no, {un} unsure  → precision {yes/max(1,yes+no):.0%}")
