# Generated contract examples

Illustrative contract fixtures; these are not claimed live solver executions.

## Discover all methods

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-describe",
  "method": "describe",
  "params": {}
}
```

## Inspect a typed task

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-inspect-a-typed-task",
  "method": "describe",
  "params": {
    "subject": "task",
    "name": "simulate.spice"
  }
}
```

## Query PDK building blocks

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-query",
  "method": "query",
  "params": {
    "from": {
      "kind": "pdk",
      "id": "sky130A",
      "revision": "r1"
    },
    "relation": "components",
    "limit": 50
  }
}
```

## Query installed GDSFactory factories without executing them

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-query-installed-gdsfactory-factories-without-executing-them",
  "method": "query",
  "params": {
    "from": {
      "kind": "package",
      "id": "gdsfactory",
      "revision": "9.51.0",
      "profile": {
        "scope": "engine",
        "id": "design-profile",
        "revision": "r1"
      }
    },
    "relation": "components",
    "search": "bend",
    "limit": 20
  }
}
```

## Query reusable engine IP

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-query-reusable-engine-ip",
  "method": "query",
  "params": {
    "from": {
      "kind": "library",
      "id": "engine-ip",
      "revision": "r1"
    },
    "relation": "components"
  }
}
```

## Query hierarchy occurrence

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-query-hierarchy-occurrence",
  "method": "query",
  "params": {
    "from": {
      "kind": "entity",
      "id": "receiver",
      "project_id": "chip",
      "revision": "r7",
      "occurrence": [
        "soc",
        "receiver"
      ]
    },
    "relation": "hierarchy",
    "depth": 4
  }
}
```

## Read original request-to-run association

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-read-original-request-to-run-association",
  "method": "query",
  "params": {
    "from": {
      "kind": "request",
      "id": "req-tran",
      "project_id": "chip"
    },
    "relation": "self"
  }
}
```

## Create a new project

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-edit",
  "method": "edit",
  "params": {
    "preconditions": [],
    "changes": [
      {
        "op": "create",
        "key": "@project",
        "entity": {
          "kind": "project",
          "name": "chip",
          "config_path": "canvas.toml"
        }
      }
    ]
  }
}
```

## Create a SPICE component preset

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-create-a-spice-component-preset",
  "method": "edit",
  "params": {
    "project_id": "chip",
    "preconditions": [],
    "changes": [
      {
        "op": "create",
        "key": "@amp",
        "entity": {
          "kind": "component",
          "name": "amp",
          "component_type": "spice_block",
          "domains": [
            "analog"
          ],
          "ports": [],
          "models": {
            "spice": {
              "state": "unavailable",
              "reason": "Draft interface; subcircuit source pending."
            }
          },
          "views": []
        }
      }
    ]
  }
}
```

## Create linked GDSFactory source and component atomically

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-create-linked-gdsfactory-source-and-component-atomically",
  "method": "edit",
  "params": {
    "project_id": "chip",
    "preconditions": [],
    "changes": [
      {
        "op": "create",
        "key": "@source",
        "entity": {
          "kind": "source",
          "name": "filter.py",
          "path": "sources/filter.py",
          "format": "python",
          "role": "generator"
        }
      },
      {
        "op": "create",
        "key": "@filter",
        "entity": {
          "kind": "component",
          "name": "filter",
          "component_type": "gdsf_component",
          "domains": [
            "photonic"
          ],
          "ports": [],
          "models": {
            "spice": {
              "state": "not_applicable",
              "reason": "Pure optical layout; optical compact model is separate."
            }
          },
          "views": [
            {
              "id": "layout-source",
              "role": "layout_generator",
              "format": "python",
              "authority": "generator",
              "sources": [
                {
                  "local": "@source"
                }
              ],
              "entry": "make_filter",
              "profile": {
                "scope": "engine",
                "id": "design-profile",
                "revision": "r1"
              }
            }
          ]
        }
      }
    ]
  }
}
```

## Create an HDL component preset

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-create-an-hdl-component-preset",
  "method": "edit",
  "params": {
    "project_id": "chip",
    "preconditions": [],
    "changes": [
      {
        "op": "create",
        "key": "@counter",
        "entity": {
          "kind": "component",
          "name": "counter",
          "component_type": "hdl_component",
          "domains": [
            "digital"
          ],
          "ports": [],
          "models": {
            "spice": {
              "state": "derivable",
              "task": "synthesize.hdl",
              "inputs": [],
              "reason": "Map RTL to qualified standard cells and resolve cell SPICE models first."
            }
          },
          "views": [],
          "hdl_language": "inherit"
        }
      }
    ]
  }
}
```

## Place a cocotb bench and generate saved template

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-place-a-cocotb-bench-and-generate-saved-template",
  "method": "edit",
  "params": {
    "project_id": "chip",
    "preconditions": [
      {
        "id": "top-sheet",
        "revision": "r3"
      },
      {
        "id": "counter-instance",
        "revision": "r2"
      }
    ],
    "changes": [
      {
        "op": "create",
        "key": "@tb",
        "entity": {
          "kind": "testbench",
          "name": "counter_test",
          "parent": "top-sheet",
          "bench_type": "cocotb",
          "target": {
            "sibling": "counter-instance",
            "descendants": []
          }
        }
      }
    ]
  }
}
```

## Place a transient bench for a child of a sibling

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-place-a-transient-bench-for-a-child-of-a-sibling",
  "method": "edit",
  "params": {
    "project_id": "chip",
    "preconditions": [
      {
        "id": "top-sheet",
        "revision": "r3"
      },
      {
        "id": "receiver-instance",
        "revision": "r4"
      }
    ],
    "changes": [
      {
        "op": "create",
        "key": "@tb",
        "entity": {
          "kind": "testbench",
          "name": "afe_tran",
          "parent": "top-sheet",
          "bench_type": "spice",
          "target": {
            "sibling": "receiver-instance",
            "descendants": [
              "afe-instance"
            ]
          },
          "analysis": "tran"
        }
      }
    ]
  }
}
```

## Save editable generated testbench code

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-save-editable-generated-testbench-code",
  "method": "edit",
  "params": {
    "project_id": "chip",
    "preconditions": [
      {
        "id": "tb-source",
        "revision": "r1"
      }
    ],
    "changes": [
      {
        "op": "write_source",
        "id": "tb-source",
        "encoding": "utf-8",
        "text": "import cocotb\n\n@cocotb.test()\nasync def smoke(dut):\n    assert int(dut.ready.value) == 1\n"
      }
    ]
  }
}
```

## Paint layout geometry through the shared editor API

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-paint-layout-geometry-through-the-shared-editor-api",
  "method": "edit",
  "params": {
    "project_id": "chip",
    "preconditions": [
      {
        "id": "amp-cell",
        "revision": "r2"
      }
    ],
    "changes": [
      {
        "op": "geometry",
        "change": {
          "action": "paint",
          "cell": "amp-cell",
          "layer": {
            "scope": "pdk",
            "id": "metal1",
            "revision": "r1"
          },
          "region": {
            "type": "rectangle",
            "origin": {
              "x": 0,
              "y": 0
            },
            "size": {
              "x": 5,
              "y": 1
            }
          }
        }
      }
    ]
  }
}
```

## Create on-schematic plot annotation

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-create-on-schematic-plot-annotation",
  "method": "edit",
  "params": {
    "project_id": "chip",
    "preconditions": [
      {
        "id": "top-sheet",
        "revision": "r3"
      }
    ],
    "changes": [
      {
        "op": "create",
        "key": "@plot",
        "entity": {
          "kind": "annotation",
          "parent": "top-sheet",
          "annotation_type": "plot",
          "plot": {
            "run": "sim-1",
            "signals": [
              "v(out)"
            ],
            "x_axis": "time",
            "y_axis": "voltage"
          }
        }
      }
    ]
  }
}
```

## Run workflow.asic

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-workflow-asic",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "workflow.asic",
    "options": {}
  }
}
```

## Run workflow.analog

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-workflow-analog",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "workflow.analog",
    "options": {
      "plan": {
        "scope": "project",
        "id": "id",
        "revision": "r1"
      }
    }
  }
}
```

## Run workflow.photonic

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-workflow-photonic",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "workflow.photonic",
    "options": {
      "plan": {
        "scope": "project",
        "id": "id",
        "revision": "r1"
      }
    }
  }
}
```

## Run check.syntax

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-check-syntax",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "check.syntax",
    "options": {}
  }
}
```

## Run check.connectivity

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-check-connectivity",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "check.connectivity",
    "options": {}
  }
}
```

## Run check.erc

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-check-erc",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "check.erc",
    "options": {}
  }
}
```

## Run check.drc

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-check-drc",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "check.drc",
    "options": {}
  }
}
```

## Run check.lvs

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-check-lvs",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "check.lvs",
    "options": {}
  }
}
```

## Run check.antenna

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-check-antenna",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "check.antenna",
    "options": {}
  }
}
```

## Run check.view_sync

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-check-view_sync",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "check.view_sync",
    "options": {}
  }
}
```

## Run check.layout_xor

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-check-layout_xor",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "check.layout_xor",
    "options": {}
  }
}
```

## Run check.formal

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-check-formal",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "check.formal",
    "options": {
      "mode": "prove"
    }
  }
}
```

## Run check.equivalence

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-check-equivalence",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "check.equivalence",
    "options": {
      "golden": {},
      "candidate": {}
    }
  }
}
```

## Run check.mutation

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-check-mutation",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "check.mutation",
    "options": {
      "tests": [
        {
          "scope": "project",
          "id": "id",
          "revision": "r1"
        }
      ],
      "max_mutations": 1
    }
  }
}
```

## Run simulate.spice

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-simulate-spice",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "simulate.spice",
    "options": {
      "analysis": "op"
    }
  }
}
```

## Run simulate.hdl

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-simulate-hdl",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "counter",
      "snapshot": "r7"
    },
    "task": "simulate.hdl",
    "options": {
      "testbench": {
        "scope": "project",
        "id": "tb-counter",
        "revision": "r1"
      },
      "test_kind": "cocotb"
    }
  }
}
```

## Run simulate.cosim

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-simulate-cosim",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "simulate.cosim",
    "options": {
      "analog": {
        "model": "spice"
      },
      "digital": {
        "implementation": "rtl"
      },
      "coupling": {
        "scope": "project",
        "id": "coupling",
        "revision": "r1"
      },
      "testbench": {
        "scope": "project",
        "id": "tb-system",
        "revision": "r1"
      }
    }
  }
}
```

## Run simulate.optical

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-simulate-optical",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "simulate.optical",
    "options": {
      "analysis": "sparameters"
    }
  }
}
```

## Run synthesize.hdl

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-synthesize-hdl",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "counter",
      "snapshot": "r7"
    },
    "task": "synthesize.hdl",
    "options": {
      "top": "top"
    }
  }
}
```

## Run implement.asic

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-implement-asic",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "implement.asic",
    "options": {
      "stage": "full"
    }
  }
}
```

## Run implement.fpga

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-implement-fpga",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "implement.fpga",
    "options": {
      "architecture": "architecture",
      "device": "device",
      "constraints": {
        "scope": "project",
        "id": "id",
        "revision": "r1"
      },
      "top": "top"
    }
  }
}
```

## Run analyze.timing

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-analyze-timing",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "analyze.timing",
    "options": {
      "constraints": {
        "scope": "project",
        "id": "id",
        "revision": "r1"
      }
    }
  }
}
```

## Run analyze.power

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-analyze-power",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "analyze.power",
    "options": {
      "analysis": "power"
    }
  }
}
```

## Run analyze.measurements

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-analyze-measurements",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "analyze.measurements",
    "options": {
      "analysis": "measure",
      "inputs": [],
      "definitions": [
        {
          "scope": "project",
          "id": "id",
          "revision": "r1"
        }
      ]
    }
  }
}
```

## Run extract.layout

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-extract-layout",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "extract.layout",
    "options": {
      "kind": "devices"
    }
  }
}
```

## Run characterize.circuit

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-characterize-circuit",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "characterize.circuit",
    "options": {
      "plan": {
        "scope": "project",
        "id": "id",
        "revision": "r1"
      },
      "mode": "sweep"
    }
  }
}
```

## Run simulate.em

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-simulate-em",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "simulate.em",
    "options": {
      "study": {
        "scope": "project",
        "id": "id",
        "revision": "r1"
      },
      "method": "fdtd"
    }
  }
}
```

## Run simulate.thermal

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-simulate-thermal",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "simulate.thermal",
    "options": {
      "study": {
        "scope": "project",
        "id": "id",
        "revision": "r1"
      },
      "analysis": "steady"
    }
  }
}
```

## Run simulate.device

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-simulate-device",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "simulate.device",
    "options": {
      "study": {
        "scope": "project",
        "id": "id",
        "revision": "r1"
      },
      "analysis": "equilibrium"
    }
  }
}
```

## Run generate.views

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-generate-views",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "generate.views",
    "options": {
      "kinds": [
        "symbol"
      ]
    }
  }
}
```

## Run generate.netlist

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-generate-netlist",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "generate.netlist",
    "options": {
      "format": "spice"
    }
  }
}
```

## Run export.design

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-export-design",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "export.design",
    "options": {
      "format": "gds"
    }
  }
}
```

## Run compile.model

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-compile-model",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "task": "compile.model",
    "options": {
      "source": {
        "scope": "project",
        "id": "id",
        "revision": "r1"
      },
      "format": "osdi"
    }
  }
}
```

## SPICE tran call point

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-tran",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "testbench",
      "id": "tb-amp"
    },
    "task": "simulate.spice",
    "tool": "ngspice",
    "options": {
      "analysis": "tran",
      "time": {
        "stop": {
          "value": 10,
          "unit": "us"
        },
        "step": {
          "value": 1,
          "unit": "ns"
        }
      }
    }
  }
}
```

## SPICE ac call point

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-ac",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "testbench",
      "id": "tb-amp"
    },
    "task": "simulate.spice",
    "tool": "ngspice",
    "options": {
      "analysis": "ac",
      "frequency": {
        "spacing": "log",
        "start": {
          "value": 1,
          "unit": "Hz"
        },
        "stop": {
          "value": 10,
          "unit": "MHz"
        },
        "points": 100
      }
    }
  }
}
```

## SPICE dc call point

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-dc",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "testbench",
      "id": "tb-amp"
    },
    "task": "simulate.spice",
    "tool": "ngspice",
    "options": {
      "analysis": "dc",
      "sweeps": [
        {
          "parameter": "Vinput",
          "start": {
            "value": 0,
            "unit": "V"
          },
          "stop": {
            "value": 1.8,
            "unit": "V"
          },
          "step": {
            "value": 0.01,
            "unit": "V"
          }
        }
      ]
    }
  }
}
```

## Run control cancel

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-run",
  "method": "run",
  "params": {
    "action": "cancel",
    "project_id": "chip",
    "run_id": "run-1"
  }
}
```

## Run control resume

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-run-control-resume",
  "method": "run",
  "params": {
    "action": "resume",
    "project_id": "chip",
    "run_id": "run-1"
  }
}
```

## Run control discard

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-run-control-discard",
  "method": "run",
  "params": {
    "action": "discard",
    "project_id": "chip",
    "run_id": "run-1"
  }
}
```

## Open prepared scripting workspace

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-script",
  "method": "script",
  "params": {
    "action": "open",
    "project_id": "chip",
    "profile": {
      "scope": "engine",
      "id": "design-profile",
      "revision": "r1"
    }
  }
}
```

## Full GDSFactory scripting with managed publication

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-script-execute",
  "method": "script",
  "params": {
    "action": "execute",
    "project_id": "chip",
    "workspace_id": "workspace-1",
    "generation": "g1",
    "snapshot": "r7",
    "history_cursor": "history-0",
    "code": "# Proposed managed project API fixture; provider integration is pending.\nimport gdsfactory as gf\nwith project.layout.edit(\"amp-cell\") as cell:\n    cell.add_polygon([(0, 0), (5, 0), (5, 1), (0, 1)], layer=pdk.layer(\"metal1\"))\n# Context exit publishes geometry through engine CAS and events.\n"
  }
}
```

## Watch initial snapshot and capacity transitions

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-watch",
  "method": "watch",
  "params": {
    "after": null,
    "project_id": "chip"
  }
}
```

## Watch after reconnect

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-watch-after-reconnect",
  "method": "watch",
  "params": {
    "after": "event-42",
    "project_id": "chip",
    "types": [
      "capacity.changed",
      "project.changed",
      "run.state"
    ],
    "wait_ms": 30000
  }
}
```

## Parsed canvas.toml

Schema: `#/$defs/CanvasConfig`

```json
{
  "schema": "rocketeda/canvas/v1",
  "hdl": {
    "language": "systemverilog",
    "top": "soc"
  },
  "technology": {
    "scope": "pdk",
    "id": "sky130A",
    "revision": "r1"
  },
  "pdks": [
    {
      "scope": "pdk",
      "id": "sky130A",
      "revision": "r1"
    }
  ],
  "targets": [
    {
      "metric": "clock.frequency",
      "operator": "ge",
      "limit": {
        "value": 100,
        "unit": "MHz"
      },
      "required": true
    }
  ],
  "tools": {
    "librelane": {
      "profile": {
        "scope": "engine",
        "id": "librelane-profile",
        "revision": "r1"
      },
      "density": 0.45,
      "effort": "standard",
      "corners": [
        "tt"
      ]
    },
    "ngspice": {
      "profile": {
        "scope": "engine",
        "id": "analog-profile",
        "revision": "r1"
      },
      "temperature": {
        "value": 27,
        "unit": "degC"
      },
      "reltol": 0.001
    }
  }
}
```

## Empty component query result

Schema: `#/$defs/QueryResult`

```json
{
  "items": [],
  "page": {
    "cursor": null,
    "has_more": false,
    "snapshot": {
      "scope": "project",
      "id": "chip",
      "revision": "r1"
    }
  }
}
```

## Queue saturation response

Schema: `#/$defs/ErrorResponse`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-tran",
  "error": {
    "code": "queue_full",
    "message": "Pause until capacity resumes. Request was not admitted.",
    "details": [],
    "retryable": true,
    "admitted": false,
    "capacity": {
      "lane": "jobs",
      "accepting": false,
      "available": 0,
      "pending": 32,
      "generation": "capacity-4",
      "retry_after_ms": 100
    },
    "retry_after_ms": 100
  }
}
```

## Durable run receipt

Schema: `#/$defs/RunReceipt`

```json
{
  "admitted": true,
  "run_id": "run-1",
  "project_id": "chip",
  "snapshot": "r7",
  "state": "queued",
  "coalesced": false,
  "event_cursor": "event-42",
  "capacity": {
    "lane": "jobs",
    "accepting": true,
    "available": 1,
    "pending": 32,
    "generation": "capacity-4",
    "retry_after_ms": 100
  }
}
```

## Engine-owned run record with I28 lock

Schema: `#/$defs/RunRecord`

```json
{
  "id": "run-1",
  "project_id": "chip",
  "request_ids": [
    "req-tran"
  ],
  "task": "simulate.spice",
  "state": "completed",
  "verdict": "PASS",
  "target": {
    "project_id": "chip",
    "kind": "component",
    "id": "amp",
    "snapshot": "r7"
  },
  "input_lock": {
    "snapshot": {
      "scope": "project",
      "id": "chip",
      "revision": "r7"
    },
    "target": {
      "project_id": "chip",
      "kind": "component",
      "id": "amp",
      "snapshot": "r7"
    },
    "canvas": {
      "path": "canvas.toml",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "schema": "rocketeda/canvas/v1"
    },
    "ingredients": [
      {
        "ref": {
          "scope": "project",
          "id": "amp-source",
          "revision": "r1"
        },
        "role": "implementation",
        "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      }
    ],
    "tools": [
      {
        "id": "ngspice",
        "version": "qualified-version",
        "digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "profile": {
          "scope": "engine",
          "id": "analog-profile",
          "revision": "r1"
        }
      }
    ],
    "pdks": [
      {
        "ref": {
          "scope": "pdk",
          "id": "sky130A",
          "revision": "r1"
        },
        "manifest_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      }
    ],
    "resolved_configuration": {
      "analysis": "op"
    },
    "seeds": {},
    "closure_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "effects": [],
  "cancel_requested": false,
  "freshness": "current",
  "convergence": "converged"
}
```

## Partial scripting failure retains committed edits

Schema: `#/$defs/RunRecord`

```json
{
  "id": "run-1",
  "project_id": "chip",
  "request_ids": [
    "req-script-partial"
  ],
  "task": "script.python",
  "state": "failed",
  "verdict": "UNKNOWN",
  "target": {
    "project_id": "chip",
    "kind": "project",
    "snapshot": "r7"
  },
  "input_lock": {
    "snapshot": {
      "scope": "project",
      "id": "chip",
      "revision": "r7"
    },
    "target": {
      "project_id": "chip",
      "kind": "project",
      "snapshot": "r7"
    },
    "canvas": {
      "path": "canvas.toml",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "schema": "rocketeda/canvas/v1"
    },
    "ingredients": [
      {
        "ref": {
          "scope": "project",
          "id": "script-source",
          "revision": "r1"
        },
        "role": "script_source",
        "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      }
    ],
    "tools": [
      {
        "id": "gdsfactory",
        "version": "qualified-version",
        "digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "profile": {
          "scope": "engine",
          "id": "design-profile",
          "revision": "r1"
        }
      }
    ],
    "pdks": [
      {
        "ref": {
          "scope": "pdk",
          "id": "sky130A",
          "revision": "r1"
        },
        "manifest_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      }
    ],
    "resolved_configuration": {
      "workspace_generation": "g1",
      "history_cursor": "history-0"
    },
    "seeds": {},
    "closure_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "effects": [
    {
      "request_id": "script-edit-1",
      "project_id": "chip",
      "revision": "r8",
      "entities": [
        "amp-cell"
      ],
      "event_cursor": "event-43"
    }
  ],
  "cancel_requested": false,
  "freshness": "stale",
  "convergence": "not_applicable",
  "failure": {
    "code": "python_exception",
    "message": "Generator raised after first publication.",
    "details": [],
    "retryable": false
  },
  "script_context": {
    "workspace_id": "workspace-1",
    "generation": "g1",
    "history_cursor": "history-0",
    "source": {
      "scope": "project",
      "id": "script-source",
      "revision": "r1"
    }
  }
}
```

## Capacity event

Schema: `#/$defs/Event`

```json
{
  "protocol": "rocketeda/v1",
  "id": "event-43",
  "cursor": "cursor-43",
  "type": "capacity.changed",
  "actor": "engine",
  "time": "2026-11-01T15:00:00Z",
  "data": {
    "lane": "jobs",
    "accepting": false,
    "available": 0,
    "pending": 32,
    "generation": "capacity-4",
    "retry_after_ms": 100
  }
}
```

## Saved editable testbench record

Schema: `#/$defs/EntityRecord`

```json
{
  "id": "tb-counter",
  "revision": "r4",
  "project_id": "chip",
  "data": {
    "kind": "testbench",
    "name": "counter_test",
    "parent": "top-sheet",
    "bench_type": "cocotb",
    "target": {
      "sibling": "counter-instance",
      "descendants": []
    },
    "source": {
      "scope": "project",
      "id": "tb-source"
    },
    "binding_state": "resolved",
    "bindings": [
      {
        "target": 0,
        "port_id": "clk",
        "signal": "dut.clk"
      }
    ],
    "interface_digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
}
```

## Response envelope describe

Schema: `#/$defs/Response`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-describe",
  "method": "describe",
  "data": {
    "contract_version": "1.0.0",
    "contract_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "methods": [],
    "items": [],
    "page": {
      "cursor": null,
      "has_more": false,
      "snapshot": {
        "scope": "project",
        "id": "chip",
        "revision": "r1"
      }
    }
  }
}
```

## Response envelope query

Schema: `#/$defs/Response`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-query",
  "method": "query",
  "data": {
    "items": [],
    "page": {
      "cursor": null,
      "has_more": false,
      "snapshot": {
        "scope": "project",
        "id": "chip",
        "revision": "r1"
      }
    }
  }
}
```

## Response envelope edit

Schema: `#/$defs/Response`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-edit",
  "method": "edit",
  "data": {
    "project_id": "chip",
    "revision": "r8",
    "changed": [],
    "deleted": [],
    "ids": {},
    "event_cursor": "event-43",
    "diagnostics": []
  }
}
```

## Response envelope run

Schema: `#/$defs/Response`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-run",
  "method": "run",
  "data": {
    "admitted": true,
    "run_id": "run-1",
    "project_id": "chip",
    "snapshot": "r7",
    "state": "queued",
    "coalesced": false,
    "event_cursor": "event-42",
    "capacity": {
      "lane": "jobs",
      "accepting": true,
      "available": 1,
      "pending": 32,
      "generation": "capacity-4",
      "retry_after_ms": 100
    }
  }
}
```

## Response envelope script

Schema: `#/$defs/Response`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-script",
  "method": "script",
  "data": {
    "id": "workspace-1",
    "project_id": "chip",
    "generation": "g1",
    "profile": {
      "scope": "engine",
      "id": "design-profile",
      "revision": "r1"
    },
    "history_cursor": "h0",
    "prebound": [
      "gf",
      "project",
      "pdk",
      "api"
    ]
  }
}
```

## Response envelope watch

Schema: `#/$defs/Response`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-watch",
  "method": "watch",
  "data": {
    "events": [
      {
        "protocol": "rocketeda/v1",
        "id": "event-43",
        "cursor": "cursor-43",
        "type": "capacity.changed",
        "actor": "engine",
        "time": "2026-11-01T15:00:00Z",
        "data": {
          "lane": "jobs",
          "accepting": false,
          "available": 0,
          "pending": 32,
          "generation": "capacity-4",
          "retry_after_ms": 100
        }
      }
    ],
    "cursor": "cursor-43",
    "has_more": false
  }
}
```

## Qualified Amaranth native testbench call point

Schema: `#/$defs/Request`

```json
{
  "protocol": "rocketeda/v1",
  "request_id": "req-amaranth-native",
  "method": "run",
  "params": {
    "action": "start",
    "target": {
      "project_id": "chip",
      "kind": "testbench",
      "id": "tb-amaranth"
    },
    "task": "simulate.hdl",
    "tool": "amaranth",
    "options": {
      "testbench": {
        "scope": "project",
        "id": "tb-amaranth",
        "revision": "r1"
      },
      "test_kind": "hdl",
      "waves": true
    }
  }
}
```

## Harmonic-balance SPICE bench selection

Schema: `#/$defs/TestbenchData`

```json
{
  "kind": "testbench",
  "name": "rf_hb",
  "parent": "rf-sheet",
  "bench_type": "spice",
  "analysis": "harmonic_balance",
  "target": {
    "sibling": "rf-instance",
    "descendants": []
  }
}
```

## Photonic-only canvas.toml (no authored HDL)

Schema: `#/$defs/CanvasConfig`

```json
{
  "schema": "rocketeda/canvas/v1",
  "technology": {
    "scope": "pdk",
    "id": "cornerstone_si340",
    "revision": "r1"
  },
  "pdks": [
    {
      "scope": "pdk",
      "id": "cornerstone_si340",
      "revision": "r1"
    }
  ],
  "targets": [
    {
      "metric": "optical.wavelength",
      "operator": "eq",
      "limit": {
        "value": 1550,
        "unit": "nm"
      },
      "required": true
    }
  ],
  "tools": {
    "ngspice": {
      "profile": {
        "scope": "engine",
        "id": "analog-profile",
        "revision": "r1"
      },
      "temperature": {
        "value": 27,
        "unit": "degC"
      },
      "reltol": 0.001
    }
  }
}
```
