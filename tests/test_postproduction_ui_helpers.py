import json
import os

from tvc_postproduction import list_text_layers, reorder_text_layers


def test_reorder_text_layers_roundtrip(tmp_path):
    project = tmp_path / "post_project.json"
    payload = {
        "text_layers": [
            {"id": "layer-a", "track": "subtitle", "style": "Fade Caption", "start": 0.0, "end": 1.0, "text": "A"},
            {"id": "layer-b", "track": "subtitle", "style": "Fade Caption", "start": 1.0, "end": 2.0, "text": "B"},
            {"id": "layer-c", "track": "callout", "style": "News Strap", "start": 2.0, "end": 3.0, "text": "C"},
        ]
    }
    project.write_text(json.dumps(payload), encoding="utf-8")

    out = reorder_text_layers(str(project), ["layer-c", "layer-a"])
    assert out["status"] == "ok"
    rows = list_text_layers(str(project))
    assert [r["id"] for r in rows] == ["layer-c", "layer-a", "layer-b"]


def test_list_text_layers_shape(tmp_path):
    project = tmp_path / "post_project.json"
    payload = {"text_layers": [{"id": "x1", "track": "subtitle", "style": "Fade Caption", "start": 0.0, "end": 2.0, "text": "hello"}]}
    project.write_text(json.dumps(payload), encoding="utf-8")
    rows = list_text_layers(str(project))
    assert len(rows) == 1
    assert rows[0]["id"] == "x1"
    assert rows[0]["track"] == "subtitle"
    assert rows[0]["style"] == "Fade Caption"

