"""DRC lyrdb bbox grammar pin (ESCAPE-HARDEN MC-44, SHAPE-HARDEN).

Deck-mode bbox floats must come from the lyrdb value geometry
grammar — parenthesized `x,y` vertex pairs after `polygon:` or
`edge-pair:` — never from generic float scraping of the whole
value text. A value carrying stray numbers outside geometry
(parasitic reports, area notes) must yield no bbox rather than
a bogus box; the violation message still carries the full text.
"""

POLYGON_LYRDB = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
 <description>SKY130 DRC runset</description>
 <top-cell>TOP</top-cell>
 <categories>
  <category>
   <name>li.5</name>
   <description>li.5 : min li enclosure of licon</description>
  </category>
 </categories>
 <cells>
  <cell><name>TOP</name></cell>
 </cells>
 <items>
  <item>
   <tags/>
   <category>'li.5'</category>
   <cell>TOP</cell>
   <visited>false</visited>
   <multiplicity>1</multiplicity>
   <image/>
   <values>
    <value>polygon: (168.805,173.255;168.805,173.425;168.975,173.425;168.975,173.255)</value>
   </values>
  </item>
 </items>
</report-database>
"""

POLLUTED_LYRDB = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
 <description>SKY130 DRC runset</description>
 <top-cell>TOP</top-cell>
 <categories>
  <category>
   <name>m1.9</name>
   <description>m1.9 : spacing note</description>
  </category>
 </categories>
 <cells>
  <cell><name>TOP</name></cell>
 </cells>
 <items>
  <item>
   <tags/>
   <category>'m1.9'</category>
   <cell>TOP</cell>
   <visited>false</visited>
   <multiplicity>1</multiplicity>
   <image/>
   <values>
    <value>spacing 0.5um, width 0.14um, length 1.2um, margin 0.3um</value>
   </values>
  </item>
 </items>
</report-database>
"""

PIPE_EDGE_LYRDB = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
 <description>SKY130 DRC runset</description>
 <top-cell>TOP</top-cell>
 <categories>
  <category>
   <name>m1.1</name>
   <description>m1.1 : min. m1 width : 0.14um</description>
  </category>
 </categories>
 <cells>
  <cell><name>TOP</name></cell>
 </cells>
 <items>
  <item>
   <tags/>
   <category>'m1.1'</category>
   <cell>TOP</cell>
   <visited>false</visited>
   <multiplicity>1</multiplicity>
   <image/>
   <values>
    <value>edge-pair: (0,0;0,2)|(0.05,2;0.05,0)</value>
   </values>
  </item>
 </items>
</report-database>
"""


def test_polygon_value_yields_vertex_bbox():
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    result = KlayoutDrcAdapter().parse(
        {"report_xml": POLYGON_LYRDB, "report_file": "canned.lyrdb"}
    )
    assert result["total"] == 1
    assert result["violations"][0]["bbox_um"] == [
        168.805, 173.255, 168.975, 173.425,
    ]


def test_pipe_edge_pair_yields_vertex_bbox():
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    result = KlayoutDrcAdapter().parse(
        {"report_xml": PIPE_EDGE_LYRDB, "report_file": "canned.lyrdb"}
    )
    assert result["total"] == 1
    assert result["violations"][0]["bbox_um"] == [0.0, 0.0, 0.05, 2.0]


def test_bare_shape_pairs_yield_bbox_without_parens():
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    xml = PIPE_EDGE_LYRDB.replace(
        "edge-pair: (0,0;0,2)|(0.05,2;0.05,0)", "shape 188.6,197.205;190.0,197.205"
    ).replace("m1.1 : min. m1 width : 0.14um", "m4.5ab : min spacing")
    result = KlayoutDrcAdapter().parse(
        {"report_xml": xml, "report_file": "canned.lyrdb"}
    )
    assert result["total"] == 1
    assert result["violations"][0]["bbox_um"] == [188.6, 197.205, 190.0, 197.205]


def test_stray_numbers_without_geometry_yield_no_bbox():
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    result = KlayoutDrcAdapter().parse(
        {"report_xml": POLLUTED_LYRDB, "report_file": "canned.lyrdb"}
    )
    assert result["total"] == 1
    assert "bbox_um" not in result["violations"][0]
    assert "spacing 0.5um" in result["violations"][0]["message"]
