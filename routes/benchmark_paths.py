"""Where the benchmark area keeps its files, shared by its routers."""

from config import BASE_DIR

ROOT = BASE_DIR
BENCH_DIR = ROOT / "benchmark"
DATA_DIR = BENCH_DIR / "data"
RESULTS_DIR = BENCH_DIR / "results"
