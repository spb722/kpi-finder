"""Generate a PNG visualization of the KPI Finder LangGraph."""

from dotenv import load_dotenv
load_dotenv()

from kpi_finder.graph import condition_graph

png_bytes = condition_graph.get_graph(xray=True).draw_mermaid_png()

output_path = "kpi_finder_graph.png"
with open(output_path, "wb") as f:
    f.write(png_bytes)

print(f"Graph saved to {output_path}")