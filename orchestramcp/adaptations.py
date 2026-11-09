from dataclasses import dataclass

from mcp.types import ToolAnnotations

DELETE_NEEDS_OAUTH = (
    "Only runs for a user signed in with OAuth; with an Orchestra API key it is refused."
)


@dataclass(frozen=True)
class Adaptation:
    """Optional MCP-side overrides for a generated tool, keyed by operationId.

    Endpoints with no entry are exposed as-is: their description and title come from
    the spec and their safety hints are derived from the HTTP method. Add an entry
    only to tune wording or to correct a hint the method can't infer.
    """

    description: str | None = None
    annotations: ToolAnnotations | None = None
    # Appended to the description: the composite tool that answers the usual question
    # this endpoint is called for, so an agent that loaded this tool by name finds it.
    prefer: str | None = None


_WHY_FAILED = (
    "To find why a task run failed, call diagnose(task_run_id) first: one call returns its "
    "messages, parameters, upstream statuses, log tail and artifact names. Use this tool only "
    "for detail diagnose does not return."
)


_PIPELINE_CONTEXT = (
    "Before editing or reasoning about a pipeline, call pipeline_context instead: one call "
    "returns its metadata, definition, integrations and recent runs."
)

ADAPTATIONS: dict[str, Adaptation] = {
    "list_pipeline_runs": Adaptation(
        description=(
            "List pipeline runs with optional filters. status accepts comma-separated values: "
            "CREATED, QUEUED, RUNNING, SUCCEEDED, WARNING, FAILED, SKIPPED, CANCELLING, "
            "CANCELLED."
        ),
        annotations=ToolAnnotations(title="List Pipeline Runs"),
        prefer="To find what is failing, call whats_broken instead; it joins failed runs to "
        "their failed tasks in one call.",
    ),
    "list_task_runs_for_pipeline_run": Adaptation(prefer=_WHY_FAILED),
    "list_operations": Adaptation(prefer=_WHY_FAILED),
    "list_task_run_logs": Adaptation(prefer=_WHY_FAILED),
    "cancel_pipeline_run": Adaptation(
        description="Cancel a running or queued pipeline run by its ID.",
        annotations=ToolAnnotations(title="Cancel Pipeline Run", destructiveHint=True),
    ),
    "get_pipeline": Adaptation(
        description=(
            "Fetch a single pipeline. Provide exactly one selector: pipeline_id, alias, "
            "or repository together with yaml_path."
        ),
        prefer=_PIPELINE_CONTEXT,
    ),
    "get_pipeline_data": Adaptation(prefer=_PIPELINE_CONTEXT),
    "delete_pipeline": Adaptation(
        description=(
            "Delete a pipeline. Provide exactly one selector: pipeline_id, alias, "
            "or repository together with yaml_path."
        ),
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
        return ToolAnnotations(readOnlyHint=False, destructiveHint=True)
    return ToolAnnotations(readOnlyHint=False, destructiveHint=False)


def adapt_component(route, component) -> None:
    annotations = _method_annotations(route.method).model_copy(update={"title": route.summary})
    adaptation = ADAPTATIONS.get(route.operation_id)
    if adaptation is not None:
        if adaptation.annotations is not None:
            overrides = adaptation.annotations.model_dump(exclude_none=True)
            annotations = annotations.model_copy(update=overrides)
        if adaptation.description is not None:
            component.description = adaptation.description
        if adaptation.prefer is not None:
            component.description = f"{component.description or ''} {adaptation.prefer}".strip()
    if route.method.upper() == "DELETE":
        component.description = f"{component.description or ''} {DELETE_NEEDS_OAUTH}".strip()
    component.annotations = annotations
