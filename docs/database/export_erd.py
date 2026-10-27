"""Export the supplied classic ER drawing to a standalone SVG, using only stdlib.

Run from any directory: python -B docs/database/export_erd.py
Supports the rectangles, plain text and explicitly routed ER edges in erd.drawio.
The original drawing remains the editable source of truth.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)


def add(parent, tag, **attrs):
    return ET.SubElement(parent, f"{{{SVG}}}{tag}", {k.replace("_", "-"): str(v) for k, v in attrs.items()})


def main():
    drawing = ET.parse(ROOT / "erd.drawio")
    graph = drawing.find(".//mxGraphModel")
    cells = drawing.findall(".//mxCell")
    lookup = {cell.get("id"): cell for cell in cells}
    styles = {
        cell.get("id"): dict(part.split("=", 1) for part in cell.get("style", "").split(";") if "=" in part)
        for cell in cells
    }

    @lru_cache(maxsize=None)
    def bounds(cell_id):
        cell = lookup[cell_id]
        geometry = cell.find("mxGeometry")
        if geometry is None:
            return 0, 0, 0, 0
        assert geometry.get("relative") != "1", f"Unsupported relative vertex: {cell_id}"
        x, y, width, height = (float(geometry.get(key, "0")) for key in ("x", "y", "width", "height"))
        parent = cell.get("parent")
        if parent in lookup:
            px, py, _, _ = bounds(parent)
            x, y = x + px, y + py
        return x, y, width, height

    vertices = [cell for cell in cells if cell.get("vertex") == "1"]
    edges = [cell for cell in cells if cell.get("edge") == "1"]
    width = max(bounds(cell.get("id"))[0] + bounds(cell.get("id"))[2] for cell in vertices) + 24
    height = max(bounds(cell.get("id"))[1] + bounds(cell.get("id"))[3] for cell in vertices) + 48
    waypoints = drawing.findall(".//mxPoint")
    if waypoints:
        width = max(width, max(float(point.get("x", "0")) for point in waypoints) + 24)
        height = max(height, max(float(point.get("y", "0")) for point in waypoints) + 24)
    svg = ET.Element(f"{{{SVG}}}svg", {
        "width": f"{width:g}", "height": f"{height:g}", "viewBox": f"0 0 {width:g} {height:g}",
        "role": "img", "aria-labelledby": "title desc",
    })
    add(svg, "title", id="title").text = "FixRate AI — ER-модель ТО/ППР"
    add(svg, "desc", id="desc").text = "Экспорт исходного erd.drawio: 35 таблиц, 310 полей, 72 связи. Логический проект PostgreSQL 16."
    add(svg, "rect", width=width, height=height, fill=graph.get("background", "#111111"))
    defs = add(svg, "defs")
    for name in ("ERmandOne", "ERmany", "ERoneToMany"):
        marker = add(defs, "marker", id=name, markerWidth=18, markerHeight=16, refX=0, refY=8,
                     orient="auto-start-reverse", markerUnits="userSpaceOnUse", overflow="visible")
        if name == "ERmandOne":
            add(marker, "path", d="M-5 3 V13 M-9 3 V13", fill="none", stroke="#a3adb7", stroke_width=1)
        else:
            add(marker, "path", d="M0 3 L-10 8 L0 13 M0 8 H-10", fill="none", stroke="#a3adb7", stroke_width=1)
            if name == "ERoneToMany":
                add(marker, "circle", cx=-14, cy=8, r=3, fill="#111111", stroke="#a3adb7", stroke_width=1)

    for cell in edges:
        style = styles[cell.get("id")]
        source, target = cell.get("source"), cell.get("target")
        sx, sy, sw, sh = bounds(source)
        tx, ty, tw, th = bounds(target)
        points = [(sx + sw * float(style["exitX"]), sy + sh * float(style["exitY"]))]
        points += [(float(p.get("x")), float(p.get("y"))) for p in cell.findall("mxGeometry/Array/mxPoint")]
        points += [(tx + tw * float(style["entryX"]), ty + th * float(style["entryY"]))]
        edge = add(svg, "g", id=cell.get("id"), data_source=source, data_target=target)
        attrs = {
            "points": " ".join(f"{x:g},{y:g}" for x, y in points), "fill": "none",
            "stroke": style["strokeColor"], "stroke_width": style["strokeWidth"],
        }
        for end in ("start", "end"):
            arrow = style.get(end + "Arrow")
            assert arrow in (None, "none", "ERmandOne", "ERmany", "ERoneToMany"), arrow
            if arrow and arrow != "none":
                attrs["marker_" + end] = f"url(#{arrow})"
        add(edge, "polyline", **attrs)

    for cell in vertices:
        cell_id = cell.get("id")
        style = styles[cell_id]
        x, y, w, h = bounds(cell_id)
        group = add(svg, "g", id=cell_id)
        fill, stroke = style.get("fillColor", "none"), style.get("strokeColor", "none")
        if fill != "none" or stroke != "none":
            add(group, "rect", x=x, y=y, width=w, height=h, fill=fill, stroke=stroke,
                stroke_width=style.get("strokeWidth", "1"))
        value = cell.get("value", "")
        if not value:
            continue
        assert "<" not in value, f"HTML labels need a draw.io export: {cell_id}"
        align = style.get("align", "center")
        anchor = {"left": "start", "center": "middle", "right": "end"}[align]
        font_size = float(style.get("fontSize", "12"))
        if align == "left":
            text_x = x + float(style.get("spacingLeft", "2"))
        elif align == "right":
            text_x = x + w - float(style.get("spacingRight", "2"))
        else:
            text_x = x + w / 2
        text = add(group, "text", x=text_x, y=y + h / 2 + font_size * 0.35,
                   fill=style.get("fontColor", "#d7dee8"), font_family="Arial, sans-serif",
                   font_size=font_size, font_weight="700" if int(style.get("fontStyle", "0")) & 1 else "400",
                   text_anchor=anchor)
        text.text = value
    ET.indent(svg)
    output = ROOT / "erd.svg"
    ET.ElementTree(svg).write(output, encoding="utf-8", xml_declaration=True)
    print(f"Exported {output.name}: {width:g} x {height:g}, {len(vertices)} vertices, {len(edges)} ER edges.")


if __name__ == "__main__":
    main()
