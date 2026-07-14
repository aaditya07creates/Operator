"""Memory persistence, locking, dedup, and retrieval."""

import json
import os
import threading

import pytest


def test_atomic_save_and_backup(temp_data):
    from learning_system import LearningSystem
    path = str(temp_data / "learn.json")

    ls = LearningSystem(path)
    ls.mark_dirty()
    ls.flush()
    assert os.path.exists(path)

    ls.mark_dirty()
    ls.flush()
    assert os.path.exists(path + ".bak"), "backup should rotate on the second save"


def test_corrupt_file_recovers_from_backup(temp_data):
    from learning_system import LearningSystem
    path = str(temp_data / "learn.json")

    ls = LearningSystem(path)
    ls.mark_dirty(); ls.flush()
    ls.mark_dirty(); ls.flush()  # now a good .bak exists

    with open(path, "w", encoding="utf-8") as f:
        f.write("{ this is not valid json ")

    recovered = LearningSystem(path)
    assert recovered.learnings["metadata"]["version"] == "4.0"
    assert os.path.exists(path + ".corrupt"), "corrupt file should be quarantined"


def test_dedup_and_id_allocation(temp_data):
    from memory import MemoryManager
    mm = MemoryManager()

    fid1 = mm.remember_fact("technical", "User codes in Python daily")
    fid2 = mm.remember_fact("technical", "user codes in  python daily")  # normalized dup
    assert fid1 == fid2

    fid3 = mm.remember_fact("personal", "Lives in Mumbai")
    assert fid3 != fid1
    assert mm.forget_fact(fid3)
    assert not mm.forget_fact("fact_999")


def test_get_statistics_reads_command_memory(temp_data):
    from memory import MemoryManager
    mm = MemoryManager()
    mm.learning_system.learn_app("chrome", strategy="alias")
    stats = mm.get_statistics()
    assert stats["apps_known"] == 1  # regression: previously always 0


def test_retrieval_bumps_access(temp_data):
    from memory import MemoryManager
    from context_retrieval import ContextRetriever

    mm = MemoryManager()
    fid = mm.remember_fact("technical", "The deploy script lives in scripts/deploy.sh")
    cr = ContextRetriever(mm.learning_system)

    results = cr.get_relevant_facts("where is the deploy script")
    assert results and results[0]["id"] == fid

    raw = next(f for f in mm.learning_system.learnings["knowledge_base"]["facts"] if f["id"] == fid)
    assert raw["access_count"] >= 1


def test_concurrent_writes_no_id_collision(temp_data):
    from memory import MemoryManager
    from context_retrieval import ContextRetriever

    mm = MemoryManager()
    cr = ContextRetriever(mm.learning_system)

    def writer(base):
        for i in range(150):
            mm.remember_fact("general", f"{base} fact {i}")

    def reader():
        for _ in range(150):
            cr.get_relevant_facts("fact")

    threads = [
        threading.Thread(target=writer, args=("alpha",)),
        threading.Thread(target=writer, args=("beta",)),
        threading.Thread(target=reader),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    mm.learning_system.flush()
    data = json.load(open(temp_data / "learn.json", encoding="utf-8"))
    ids = [f["id"] for f in data["knowledge_base"]["facts"]]
    assert len(ids) == len(set(ids)), "no duplicate fact ids under concurrency"
