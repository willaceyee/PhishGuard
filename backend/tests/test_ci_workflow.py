from pathlib import Path


def test_frontend_ci_uses_supported_node_and_quality_order():
    workflow = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    assert 'node-version: "24"' in workflow
    assert workflow.index("npm ci") < workflow.index("npm test")
    assert workflow.index("npm test") < workflow.index("npm run lint")
    assert workflow.index("npm run lint") < workflow.index("npm run build")
