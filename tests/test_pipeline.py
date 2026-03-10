import os
from src.pipeline import Pipeline

def test_pipeline_runs():
    pipeline = Pipeline()
    pipeline.run()
    assert os.path.exists('outputs/poe_output.txt')
    with open('outputs/poe_output.txt', 'r', encoding='utf-8') as f:
        content = f.read()
    assert len(content) > 0
