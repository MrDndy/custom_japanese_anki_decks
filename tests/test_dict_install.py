from __future__ import annotations

from jp_anki_builder.dict_install import _build_offline_payload_from_jmdict_xml_bytes


def test_build_offline_payload_from_jmdict_xml_bytes_extracts_forms():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<JMdict>
  <entry>
    <k_ele><keb>無駄飯食い</keb></k_ele>
    <r_ele><reb>むだめしくい</reb></r_ele>
    <sense>
      <gloss>good-for-nothing</gloss>
      <gloss>idler</gloss>
    </sense>
  </entry>
  <entry>
    <r_ele><reb>すごい</reb></r_ele>
    <sense><gloss>amazing</gloss></sense>
  </entry>
</JMdict>
"""
    payload = _build_offline_payload_from_jmdict_xml_bytes(xml.encode("utf-8"), max_meanings=3)
    assert payload["無駄飯食い"]["reading"] == "むだめしくい"
    assert payload["無駄飯食い"]["meanings"] == ["good-for-nothing", "idler"]
    assert payload["すごい"]["reading"] == "すごい"
    assert payload["すごい"]["meanings"] == ["amazing"]
