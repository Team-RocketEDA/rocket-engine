# RocketEDA engine skill library

This engine-owned source collection packages guidance for AI clients that use
RocketEDA. It is suitable for later extraction/publishing as a skill repository;
there is no nested Git repository, remote publication or automatic installation.

[`rocket-engine/SKILL.md`](rocket-engine/SKILL.md) is the entry point. It routes to
project-authoring, task/results and API-version references only as needed.
[`manifest.yaml`](manifest.yaml) identifies the collection and canonical contract.

The attached runtime's exposed schemas and readiness decide what an agent can
actually call. The skill distinguishes live v0 operations from the v1 design,
preserves I28 and project revisions, follows the owner's client-edge execution
permissions, and leaves plotting to typed data views in the local frontend.

The release/harness integration should register this skill through its existing
skill loader and package the canonical contract/help assets. Updating these
instructions does not install tools or grant execution permission. Keep payload
shapes in the canonical contract, not copied into the skill.

Validation: use the installed Skill Creator `scripts/quick_validate.py` on the
`skills/rocket-engine` directory. That checks frontmatter/scaffold structure;
it does not prove provider support or qualify the engine's workflows.
