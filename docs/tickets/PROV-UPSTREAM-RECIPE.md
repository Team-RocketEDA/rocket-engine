Problem (RULING-03): provision script does not follow the tools' documented GitHub README recipes — e.g. opensta needs cudd cloned+made per the opensta README recipe first (nonlinear order), which the script missed. openEMS/xyce/opensta are PARKED until provisioning is solved (user is building manually meanwhile).
Fix: rewrite install_opensta/install_xyce/install_openems (+ deps) to copy the upstream README recipes verbatim — git clone steps, bootstrap/configure/make order, dep builds (cudd, trilinos, CSXCAD/CGAL) — preserving nonlinear ordering. Cross-check each recipe against the live README at provision time; record doc URLs + revisions in docs/provision-sources.md.
Acceptance: scripts/provision_toolchain.sh --install reproduces README builds for the trio; user manual builds confirm parity; trio unparks (TIMING-STA restaffs, STA grammar graduates from residue).

*Verify 2026-11-03: validated live on host. CUDD ships 1.14-era
build files — git clones MUST autoreconf -fi first (README's
plain ./configure only covers release tarballs); fail-fast
autoconf/automake/libtool prereqs added, apt remedy names
libtool AND libtool-bin (the libtool .deb alone lacks
/usr/bin/libtool — tonight's exact trap), CUDD gated on the
installed lib + stale-cmake clearing for retry-safety. OpenSTA
857316f built, version-asserted, TIMING-STA proved live (32/32).
Xyce recipe already matches the building guide (bootstrap after
clone, serial Trilinos, gtest OFF); remaining step is one host
apt line. READMEs curled at provision time: OpenSTA prereqs
(cmake/gcc/tcl8.6/swig/bison/flex + eigen/cudd required,
tclreadline/zlib optional, libfmt if no std::format), CUDD
BUILD section, Xyce building-guide autotools-primary flow.*
