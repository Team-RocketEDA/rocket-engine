# stores — durable project state behind ports

Project state lives here, never in [`interfaces/`](../interfaces/README.md)
(contracts only: no I/O, no logic). One word per module.

- `settings.py`: project settings, manifests, and defaults I/O.
- `ecs.py`: entity/component store (create, resolve, address).
- `wireplace.py`: schematic connectivity — wires, junctions, nets, ERC.
- `layers.py`: layer serving and stackup data operations.

These are the hexagonal direction made concrete: `interfaces/`
holds the data contracts, `stores/` holds the state they describe.
