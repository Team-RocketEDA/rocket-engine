# Slang syntax adapter

SyntaxAdapter serves run_syntax with Slang. It runs lint-only mode over project sources and normalizes file, line, and column diagnostics. Errors fail the check; warnings are findings and do not fail it by themselves. A failed build with no parsed diagnostic is reported as an error rather than clean output.

The adapter is registered in Engine as the slang solver. Tool resolution uses PATH or an explicit job tool_dir, with a version-checked remedy when the binary is unavailable.
