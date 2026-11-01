# Circulax time-domain adapter

The Circulax package has two roles:

- Its RC step smoke qualifies the installed library with a small, known-good and known-bad circuit. It returns solver version, time samples, capacitor voltage, and final voltage.
- CirculaxAdapter is registered for the run_optical operation as the circulax deck tool. Engine jobs provide the simulation inputs and receive normalized results.

The smoke uses a voltage step, resistor, and capacitor compiled through kfnetlist. With Circulax 0.2.5, the 1 kΩ / 1 nF case reaches 0.9933 V at 5 μs; the 100 kΩ / 1 nF case reaches 0.0488 V and misses the threshold. A missing Circulax dependency reports missing_dependency rather than a fabricated verdict.

See [adapter.py](adapter.py) and the [solver map](../README.md).
