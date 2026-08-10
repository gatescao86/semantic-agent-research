"""Pydantic schema for semantic model YAML files.

The same schema validates both domain-scoped models (semantic_models/domains/*.yaml)
and the generated unified model (semantic_models/unified/unified_model.yaml) — see
scripts/generate_unified_model.py. Using one schema for both is deliberate: it keeps
the unified model structurally identical to a concatenation of the domain models,
rather than a separately-authored artifact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class Entity(BaseModel):
    name: str
    table: str
    primary_key: str | list[str]
    description: str | None = None


class Relationship(BaseModel):
    from_: str = Field(alias="from")
    to: str
    type: Literal["many_to_one", "one_to_many", "one_to_one", "many_to_many"]

    model_config = {"populate_by_name": True}


class Dimension(BaseModel):
    name: str
    entity: str
    column: str
    type: Literal["categorical", "date", "numeric"] = "categorical"


class Metric(BaseModel):
    name: str
    entity: str
    expression: str
    description: str | None = None


class CrossDomainKey(BaseModel):
    """Declares that `entity.join_key` is a foreign key into another domain.

    Declared on the referencing (foreign-key) side only, e.g. an
    indicator_timeseries.geo_id column declares `references:
    geography.geography.geo_id` — the geography domain itself declares
    nothing, since nothing "reaches out" from it. This keeps each
    cross-domain join declared exactly once instead of on both sides.
    """

    entity: str
    join_key: str
    references: str  # "<domain>.<entity>.<column>"


class SemanticModel(BaseModel):
    domain: str
    description: str
    entities: list[Entity]
    relationships: list[Relationship] = Field(default_factory=list)
    dimensions: list[Dimension] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    cross_domain_keys: list[CrossDomainKey] = Field(default_factory=list)

    def entity_names(self) -> set[str]:
        return {e.name for e in self.entities}


def load_semantic_model(path: str | Path) -> SemanticModel:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return SemanticModel.model_validate(raw)


def validate_references(model: SemanticModel) -> list[str]:
    """Return a list of human-readable errors for dangling entity references.

    Structural validity (required fields, types) is enforced by pydantic at
    load time; this catches semantic issues pydantic can't: relationships,
    dimensions, and metrics that reference an entity name not defined in
    `entities`.
    """
    errors: list[str] = []
    known = model.entity_names()

    for rel in model.relationships:
        for side, ref in (("from", rel.from_), ("to", rel.to)):
            entity = ref.split(".")[0]
            if entity not in known:
                errors.append(
                    f"[{model.domain}] relationship.{side}={ref!r} references "
                    f"unknown entity {entity!r}"
                )

    for dim in model.dimensions:
        if dim.entity not in known:
            errors.append(
                f"[{model.domain}] dimension {dim.name!r} references unknown "
                f"entity {dim.entity!r}"
            )

    for metric in model.metrics:
        if metric.entity not in known:
            errors.append(
                f"[{model.domain}] metric {metric.name!r} references unknown "
                f"entity {metric.entity!r}"
            )

    for cdk in model.cross_domain_keys:
        if cdk.entity not in known:
            errors.append(
                f"[{model.domain}] cross_domain_key references unknown "
                f"entity {cdk.entity!r}"
            )

    return errors


DOMAINS_DIR = Path(__file__).resolve().parent / "domains"


def merge_domain_models(domain_names: list[str]) -> tuple[dict, list[str]]:
    """Build a merged semantic model dict for a routed set of domains.

    Used by agents/routed_agent.py (Experiment B) when the router selects
    2+ domains for one question. Cross-domain foreign keys are promoted to
    first-class relationships only when the *referenced* domain is also in
    `domain_names` — otherwise the routed agent has no way to actually join
    to it (that table isn't in its view at all), and silently promoting the
    relationship would hide exactly the failure mode this study wants to
    measure (H3: inability to synthesize across domains when routing omits
    a required domain). Returns (merged_model_dict, unavailable_refs) where
    unavailable_refs are cross-domain keys that were dropped because their
    target domain wasn't routed — surfaced as a comment in the rendered
    YAML so the agent (and a human reading the log) can see what's missing.
    """
    models = [load_semantic_model(DOMAINS_DIR / f"{name}.yaml") for name in domain_names]

    entities: list[dict] = []
    relationships: list[dict] = []
    dimensions: list[dict] = []
    metrics: list[dict] = []
    unavailable_refs: list[str] = []

    for m in models:
        entities.extend(e.model_dump(by_alias=True, exclude_none=True) for e in m.entities)
        relationships.extend(r.model_dump(by_alias=True, exclude_none=True) for r in m.relationships)
        dimensions.extend(d.model_dump(by_alias=True, exclude_none=True) for d in m.dimensions)
        metrics.extend(met.model_dump(by_alias=True, exclude_none=True) for met in m.metrics)

        for cdk in m.cross_domain_keys:
            ref_domain = cdk.references.split(".", 1)[0]
            if ref_domain in domain_names:
                relationships.append(
                    {
                        "from": f"{cdk.entity}.{cdk.join_key}",
                        "to": cdk.references.split(".", 1)[1],
                        "type": "many_to_one",
                    }
                )
            else:
                unavailable_refs.append(
                    f"{m.domain}.{cdk.entity}.{cdk.join_key} references "
                    f"{cdk.references} — domain {ref_domain!r} is not in this routed view"
                )

    merged = {
        "domain": "+".join(domain_names),
        "description": (
            "Routed view combining: " + ", ".join(m.domain for m in models) + "."
        ),
        "entities": entities,
        "relationships": relationships,
        "dimensions": dimensions,
        "metrics": metrics,
        "cross_domain_keys": [],
    }
    return merged, unavailable_refs
