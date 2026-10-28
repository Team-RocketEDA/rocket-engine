# adapters/cli — headless debug client (parked)

## Responsibility (project decision)

Every engine operation invokable, every event printable: the terminal
client for debugging the headless engine without RocketIDE.

## Boundaries

Same as every transport: protocol ↔ ports only. No logic.

## Routing

- Parent rules → `../README.md`.

## Status

Parked stretch goal — intentionally last. Until then, headless
verification runs through pytest directly, not through this client.
