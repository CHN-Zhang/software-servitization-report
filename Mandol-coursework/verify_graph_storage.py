"""Real Mandol graph/FAISS/BM25/RocksDB checkpoints, deterministic embeddings.

Only the embedding model loader is substituted. No AST extraction or mock graph.
Fresh-process verification reopens each checkpoint after the writer has closed.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
UPSTREAM = HERE.parent / "Mandol"
sys.path.insert(0, str(UPSTREAM / "src"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np
from mandol.core.memory_unit import MemoryUnit
from mandol.core.semantic_graph import SemanticGraph
from mandol.core.semantic_map import SemanticMap
from mandol.retrieval.bm25_retriever import BM25Retriever
from mandol.retrieval.retrieval_interface import RetrievalMethod
from mandol.utils.model_manager import global_model_manager
from mandol.auto_builder.hierarchical_builder import HierarchicalAutoBuilder, HierarchicalBuilderConfig, L1ExtractionResult
from experiment import ConservativeMerger


class FeatureEmbedding:
    words = ("shanghai", "return", "budget", "friday", "sunday", "control")

    def encode(self, texts, **kwargs):
        single = isinstance(texts, str)
        items = [texts] if single else list(texts)
        vectors = []
        for text in items:
            text = text.lower()
            vector = np.array([float(w in text) for w in self.words], dtype=np.float32)
            if not vector.any():
                vector[-1] = 1
            vectors.append(vector)
        return vectors[0] if single else np.stack(vectors)


def model_loader(**kwargs):
    if kwargs.get("model_type") != "text_embedding":
        raise RuntimeError("Unexpected model load: " + str(kwargs.get("model_type")))
    return FeatureEmbedding()


def new_graph():
    return SemanticGraph(semantic_map_instance=SemanticMap(
        embedding_model_name="coursework/feature-fixture-v1", embedding_dim=6,
        use_flash_attention=False))


def add(graph, uid, text, space, metadata=None):
    graph.add_unit(MemoryUnit(uid, {"text_content": text}, metadata or {"kind": "fixture"}),
                   space_names=[space], generate_sparse_embedding=False)


def populate(graph):
    add(graph, "raw_a", "Shanghai Friday", "L0")
    add(graph, "raw_b", "Shanghai Friday; return Sunday", "L0")
    first = L1ExtractionResult("s1", "knowledge", "Shanghai Friday", "a", ["raw_a"], {"user_id": "u1"})
    second = L1ExtractionResult("s2", "knowledge", "Shanghai Friday; return Sunday", "b", ["raw_b"], {"user_id": "u1"})
    merged, plans = ConservativeMerger().merge([first, second],
        {"merged_items": [{"merged_from": ["a", "b"]}]})
    assert len(merged) == 1 and merged[0].unit_uid == "b"
    builder = HierarchicalAutoBuilder(semantic_system=graph,
        config=HierarchicalBuilderConfig(l1_space_name="L1"))
    assert builder.add_to_semantic_system(merged, rebuild_index=False)["l1_added"] == 1
    add(graph, "budget", "budget 300", "L1")
    add(graph, "control", "control unrelated record", "L1")
    graph.add_relationship("b", "raw_a", "DERIVED_FROM")
    graph.add_relationship("b", "raw_b", "DERIVED_FROM")
    graph.add_relationship("budget", "control", "CONTROL_EDGE")
    graph.build_semantic_map_index()
    assert graph.rx_graph.num_nodes() == 5 and graph.rx_graph.num_edges() == 3
    assert graph.get_unit("b").metadata["source_unit_uids"] == ["raw_a", "raw_b"]
    return [asdict(p) for p in plans]


def retrieval(graph):
    dense = graph.semantic_map.search_similarity_by_text("return", k=3, ms_names=["L1"])
    assert dense and dense[0][0].uid == "b"
    assert "a" not in [u.uid for u, _ in dense]
    bm25 = BM25Retriever(graph, use_jieba=False)
    bm25.build_index()
    lexical = bm25.search("return", top_k=3, ms_names=["L1"])
    assert lexical and lexical[0].unit.uid == "b"
    assert graph.semantic_map.faiss_index.ntotal >= 1
    return {"dense": [[u.uid, round(float(s), 6)] for u, s in dense],
            "bm25": [[r.unit.uid, round(float(r.score), 6)] for r in lexical]}


def state(graph):
    units = sorted(graph.get_all_units(), key=lambda u: u.uid)
    # get_all_units materializes cold records; use it only after eviction assertions.
    rows = [{"uid": u.uid, "raw_data": u.raw_data, "metadata": u.metadata,
             "embedding": u.embedding.tolist() if u.embedding is not None else None} for u in units]
    edges = sorted([graph._index_to_uid[a], graph._index_to_uid[b], data["type"]]
                   for a, b, data in graph.rx_graph.weighted_edge_list())
    spaces = {name: sorted(space._unit_uids) for name, space in graph.semantic_map.memory_spaces.items()}
    mapping = dict(graph.semantic_map._get_uid_to_int_id_map())
    return {"units": rows, "edges": edges, "spaces": spaces, "uid_mapping": mapping,
            "retrieval": retrieval(graph)}


def write_checkpoint(graph, folder):
    graph.save_graph(str(folder), build_sparse_vectors=False,
                     retriever_methods_to_build=[RetrievalMethod.BM25])
    required = [folder / "rx_graph.pkl", folder / "semantic_map_data/faiss_index.bin",
                folder / "semantic_map_data/semantic_map_meta.json"]
    assert all(p.is_file() for p in required), "Missing checkpoint artifacts"


def verify_child(snapshot, expected):
    graph = SemanticGraph.load_graph(str(snapshot))
    try:
        actual = state(graph)
        (expected.parent / "restored.json").write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")
        assert actual == json.loads(expected.read_text(encoding="utf-8"))
        assert graph.get_unit("b").metadata["source_unit_uids"] == ["raw_a", "raw_b"]
        # Validate the persisted BM25 index itself, rather than only rebuilding.
        bm25 = BM25Retriever(graph, use_jieba=False)
        index_path = snapshot / "retrieval_indices/bm25"
        assert bm25.load_index(str(index_path)), "BM25 checkpoint did not load"
        assert bm25.search("return", top_k=1, ms_names=["L1"])[0].unit.uid == "b"
        return {"fresh_process_roundtrip": True, "persisted_bm25_load": True}
    finally:
        graph.close()


def run_mode(root, mode):
    folder = root / mode
    folder.mkdir()
    graph = new_graph()
    plans = populate(graph)
    before = state(graph)
    eviction = None
    if mode == "rocksdb":
        assert graph.connect_to_l2(str(folder / "live-db"), max_capacity=100)
        manager = graph.tiered_storage_manager
        result = manager._evict_once(len(graph.semantic_map.memory_units), count=3)
        assert result.error is None and result.removed_count == 3
        cold = set(graph.semantic_map._storage_uids) - set(graph.semantic_map.memory_units)
        assert len(cold) >= 3
        assert graph.rx_graph.num_nodes() == len(before["units"])
        index_count = graph.semantic_map.faiss_index.ntotal
        for uid in cold:
            assert graph.get_unit(uid) is not None
        assert graph.semantic_map.faiss_index.ntotal == index_count
        assert state(graph) == before
        eviction = {"cold_uids": sorted(cold), "removed_count": result.removed_count,
                    "retrieval_state_unchanged": True}
        # Force the deletion target onto disk so deletion is not a trivial miss.
        result = manager._evict_once(len(graph.semantic_map.memory_units),
                                     count=len(graph.semantic_map.memory_units))
        assert result.error is None
        assert "control" not in graph.semantic_map.memory_units
        assert graph._payload_store.get_unit("control") is not None
    # Delete one control node to test stale graph and index membership removal.
    graph.delete_unit("control", rebuild_semantic_map_index_immediately=True)
    assert graph.get_unit("control") is None
    assert not graph.has_node("control")
    assert "control" not in graph.semantic_map.memory_spaces["L1"]._unit_uids
    assert not graph.has_edge("budget", "control")
    assert graph.rx_graph.num_nodes() == 4 and graph.rx_graph.num_edges() == 2
    assert graph.semantic_map.faiss_index.ntotal == 4
    after = state(graph)
    assert all(u["uid"] != "control" for u in after["units"])
    assert all(u["uid"] != "a" for u in after["units"])
    if mode == "rocksdb":
        assert graph._payload_store.get_unit("control") is None
        # Leave payloads cold at the time of snapshot, not just before retrieval.
        result = graph.tiered_storage_manager._evict_once(len(graph.semantic_map.memory_units), count=2)
        assert result.error is None and result.removed_count == 2
    expected = folder / "expected.json"
    expected.write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
    snapshot = folder / "snapshot"
    write_checkpoint(graph, snapshot)
    graph.close()
    child = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--verify",
                            str(snapshot), "--expected", str(expected)],
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
    (folder / "fresh-process.log").write_text(child.stdout + child.stderr, encoding="utf-8")
    assert child.returncode == 0, "Fresh-process verification failed; see " + str(folder / "fresh-process.log")
    return {"mode": mode, "graph_insert_edges_spaces": True, "dense_faiss": True,
            "bm25": True, "delete_no_stale_control": True, "fresh_process_roundtrip": True,
            "eviction": eviction, "merge_plans": plans, "artifact_dir": str(folder)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--expected", type=Path)
    args = parser.parse_args()
    with patch.object(global_model_manager, "get_or_load_model", side_effect=model_loader):
        if args.verify:
            print(json.dumps(verify_child(args.verify, args.expected)))
            return
        root = Path(tempfile.mkdtemp(prefix="mandol-graph-", dir=str(HERE.parents[1] / "tmp")))
        result = {"scope": "real graph, FAISS, BM25, RocksDB and disk checkpoints; controlled embeddings; no LLM or semantic-quality evaluation",
                  "upstream_files_sha256": {str(p.relative_to(UPSTREAM)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in [UPSTREAM / "src/mandol/core/semantic_graph.py", UPSTREAM / "src/mandol/core/semantic_map.py",
                                UPSTREAM / "src/mandol/auto_builder/hierarchical_builder.py"]},
                  "test_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "runs": [], "versions": {n: importlib.metadata.version(n) for n in
                       ["numpy", "torch", "faiss-cpu", "rustworkx", "rocksdict", "sentence-transformers"]}}
        try:
            for mode in ["resident", "rocksdb"]:
                result["runs"].append(run_mode(root, mode))
            result["passed"] = True
        except Exception as exc:
            result.update(passed=False, error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            target = HERE / "results/graph_storage"
            target.mkdir(parents=True, exist_ok=True)
            (target / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS: resident and RocksDB modes, fresh-process roundtrips. Artifacts: " + str(root))


if __name__ == "__main__":
    main()
