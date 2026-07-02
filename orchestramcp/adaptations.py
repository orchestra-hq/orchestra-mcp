from dataclasses import dataclass

from mcp.types import ToolAnnotations


@dataclass(frozen=True)
class Adaptation:
    """Optional MCP-side overrides for a generated tool, keyed by operationId.

    Endpoints with no entry are exposed as-is from the spec. Add an entry only to
    tune how a tool reads to a model (LLM-facing description, safety annotations).
    """

    description: str | None = None
    annotations: ToolAnnotations | None = None


ADAPTATIONS: dict[str, Adaptation] = {
    "list_pipeline_runs": Adaptation(
        description=(
            "List pipeline runs with optional filters. status accepts comma-separated values: "
            "CREATED, RUNNING, SUCCEEDED, WARNING, FAILED, CANCELLING, CANCELLED."
        ),
        annotations=ToolAnnotations(title="List Pipeline Runs", readOnlyHint=True),
    ),
    "cancel_pipeline_run": Adaptation(
        description="Cancel a running pipeline run by its ID.",
        annotations=ToolAnnotations(title="Cancel Pipeline Run", destructiveHint=True),
    ),
}


def adapt_component(route, component) -> None:
    adaptation = ADAPTATIONS.get(route.operation_id)
    if adaptation is None:
        return
    if adaptation.description is not None:
        component.description = adaptation.description
    if adaptation.annotations is not None:
        component.annotations = adaptation.annotations
