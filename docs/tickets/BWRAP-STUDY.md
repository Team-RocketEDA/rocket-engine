Problem (RULING-04): console sandbox undecided. The console is a plain python console in a trusted-local, never-cloud deployment with user-side permissions — so the only question is hygiene vs friction.
Study (comparative, evidence-based): (1) bwrap-keep: system hygiene gains vs adoption friction + observed/predicted future-bug surface (breakage reports, failure modes); (2) raw python exec: friction wins vs hygiene loss; (3) prepackaged scripting contexts (project-aware preludes, safe stdlib surface) as middle path.
Standing requirement (RULING-07): live env provides every library a client may need for scripting, with appropriate project contexts — evaluate each option against it.
Deliverable: decision + rationale recorded; feeds CONSOLE-LIFECYCLE (T-08). No code until the study lands.
