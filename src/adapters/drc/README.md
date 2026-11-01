# Magic DRC adapter

MagicDrcAdapter serves run_drc with deck.tool set to magic, the current default. It loads a cell, runs headless DRC, and parses rule messages and bounding boxes into normalized violations.

The adapter is registered in Engine. Its documented qualification uses Magic 8.3.685 with the scmos technology. Process-specific support depends on a loadable technology and deck; query get_capabilities and heed preflight results before promising PDK coverage.

Magic may exit successfully despite DRC errors or a bad cell. The verdict comes from parsed output, not the process exit code. The alternate KLayout adapter handles synthetic rules and foundry .lydrc decks.
