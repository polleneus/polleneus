import pathlib
import re

PKG = pathlib.Path(__file__).resolve().parents[1] / "soup_sim"
# Layers that must stay addressing-blind (read only id/created_at/ttl/size).
ENGINE_LAYERS = {"geometry.py", "cell_list.py", "mobility.py", "blob.py",
                 "buffer.py", "budget.py", "policies.py", "engine.py", "percolation.py"}


def test_no_module_global_rng():
    bad = re.compile(r"np\.random\.(seed|rand|randint|choice|normal|uniform)\b|random\.seed\(")
    hits = [p.name for p in PKG.glob("*.py") if bad.search(p.read_text())]
    assert not hits, f"module-global RNG in {hits}; inject a Generator instead"


def test_engine_layers_are_addressing_blind():
    bad = re.compile(r"\b(sender|recipient)\b")
    hits = [p.name for p in PKG.glob("*.py")
            if p.name in ENGINE_LAYERS and bad.search(p.read_text())]
    assert not hits, f"sender/recipient referenced in addressing-blind layer: {hits}"
