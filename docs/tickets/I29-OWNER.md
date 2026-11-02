Problem: verbatim PDK serving (bytes+sha256, parse client-side) is demanded by invariants:210-215, suggested-api.md:318 ("planned"), frontend-tooling-spec.md:293 ("Planned (I29)"), but NO MVP-track ticket owns it. Code partially ships it RENAMED (list_assets/serve_asset; PRD names list_pdk_assets/get_pdk_asset unaliased). PDK-STORE.md is Backlog register/verify/list only.
Expected-per: I29 invariant + suggested-api §10. Audit X-12, T-18, D-35.
Fix: own it end-to-end — alias or rename to PRD names, close serving gaps (size caps/paging per MC-43), flip "planned" prose to shipped.
