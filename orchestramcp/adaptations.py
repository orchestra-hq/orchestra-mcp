from dataclasses import dataclass

from mcp.types import ToolAnnotations


@dataclass(frozen=True)
class Adaptation:
    """Optional MCP-side overrides for a generated tool, keyed by operationId.

    Endpoints with no entry are exposed as-is: their description comes from the
    spec and their safety hints are derived from the HTTP method. Add an entry
    only to tune wording or to correct a hint the method can't infer.
    """

    description: str | None = None
    annotations: ToolAnnotations | None = None


ADAPTATIONS: dict[str, Adaptation] = {
    "list_pipeline_runs": Adaptation(
        description=(
            "List pipeline runs with optional filters. status accepts comma-separated values: "
            "CREATED, RUNNING, SUCCEEDED, WARNING, FAILED, CANCELLING, CANCELLED."
        ),
        annotations=ToolAnnotations(title="List Pipeline Runs"),
    ),
    "cancel_pipeline_run": Adaptation(
        description="Cancel a running pipeline run by its ID.",
        annotations=ToolAnnotations(title="Cancel Pipeline Run", destructiveHint=True),
    ),
    "get_pipeline": Adaptation(
        description=(
            "Fetch a single pipeline. Provide exactly one selector: pipeline_id, alias, "
            "or repository together with yaml_path."
        ),
    ),
    "delete_pipeline": Adaptation(
        description=(
            "Delete a pipeline. Provide exactly one selector: pipeline_id, alias, "
            "or repository together with yaml_path."
        ),
    ),
    "validate_pipeline": Adaptation(
        description=(
            "Validate a pipeline model JSON without creating or updating a pipeline. "
            "Use it to check a definition before create_pipeline or update_pipeline."
        ),
        annotations=ToolAnnotations(title="Validate Pipeline", readOnlyHint=True),
    ),
    "migrate_pipeline": Adaptation(
        description=(
            "Migrate an Orchestra-backed pipeline to git-backed storage. Identify it with "
            "pipeline_id or alias, and omit working_branch when it equals default_branch."
        ),
    ),
}


def _method_annotations(method: str) -> ToolAnnotations:
    method = method.lower()
    if method == "get":
        return ToolAnnotations(readOnlyHint=True)
    if method == "delete":
        return ToolAnnotations(destructiveHint=True)
    return ToolAnnotations(destructiveHint=False)


def adapt_component(route, component) -> None:
    annotations = _method_annotations(route.method)
    adaptation = ADAPTATIONS.get(route.operation_id)
    if adaptation is not None:
        if adaptation.annotations is not None:
            overrides = adaptation.annotations.model_dump(exclude_none=True)
            annotations = annotations.model_copy(update=overrides)
        if adaptation.description is not None:
            component.description = adaptation.description
    component.annotations = annotations
